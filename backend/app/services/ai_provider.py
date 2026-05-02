from __future__ import annotations

import json
import re
from pathlib import Path
from time import monotonic
from typing import Callable, Protocol

import httpx

from app.services.ai_config import AIProviderConfig, load_ai_provider_config

SUMMARY_TRANSCRIPT_CHAR_BUDGET = 12_000
SUMMARY_RESPONSE_MAX_TOKENS = 8_192
SUMMARY_REQUEST_TIMEOUT_SECONDS = 45.0
QUESTION_TRANSCRIPT_CHAR_BUDGET = 8_000
QUESTION_RESPONSE_MAX_TOKENS = 1_000
SUMMARY_STREAM_PREVIEW_MAX_LINES = 18

TRANSCRIPT_LINE_PATTERN = re.compile(r"^\[(?P<time>[^\]]+)\]\s*(?P<text>.+)$")
LATIN_TERM_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9.+#/-]*(?:\s+[A-Za-z][A-Za-z0-9.+#/-]*){0,2}\b")
GENERIC_SUMMARY_PHRASES = (
    "核心内容",
    "要点总结",
    "主要内容",
    "重要内容",
    "内容概览",
    "总结内容",
    "本视频介绍核心内容",
    "这个视频讲了核心内容",
    "讲了什么",
    "概览",
    "暂无概览",
)


class AIProvider(Protocol):
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        ...

    def summarize_transcript(
        self,
        *,
        title: str,
        transcript: str,
        language: str,
        stream_hook: Callable[[str], None] | None = None,
    ) -> dict:
        ...

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        ...


def provider_config_from_env() -> AIProviderConfig:
    return load_ai_provider_config()


def build_ai_provider_from_env() -> AIProvider:
    config = provider_config_from_env()
    return build_ai_provider(config)


def build_ai_provider(config: AIProviderConfig) -> AIProvider:
    provider_name = config.provider.strip().lower()
    if provider_name == "mock":
        return MockAIProvider()
    if provider_name == "anthropic" or config.base_url.rstrip("/").endswith("/anthropic"):
        return AnthropicCompatibleProvider(config)
    return OpenAICompatibleProvider(config)


class OpenAICompatibleProvider:
    def __init__(self, config: AIProviderConfig, *, client=None) -> None:
        if not config.api_key:
            raise RuntimeError("AI_API_KEY 未配置，无法使用内置 AI 总结服务。")
        self.config = config
        self.client = client or httpx.Client(timeout=config.timeout_seconds, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        with audio_path.open("rb") as file:
            response = self.client.post(
                f"{self.config.base_url}/audio/transcriptions",
                headers=self._headers(),
                data={"model": self.config.transcribe_model, "language": language},
                files={"file": (audio_path.name, file, "application/octet-stream")},
            )
        response.raise_for_status()
        data = response.json()
        text = data.get("text") if isinstance(data, dict) else None
        if not text:
            raise RuntimeError("AI 语音转写服务未返回文本。")
        return str(text).strip()

    def summarize_transcript(
        self,
        *,
        title: str,
        transcript: str,
        language: str,
        stream_hook: Callable[[str], None] | None = None,
    ) -> dict:
        timeout_seconds = _summary_timeout_seconds(self.config)
        request_payload = {
            "model": self.config.text_model,
            "temperature": 0.1,
            "max_tokens": SUMMARY_RESPONSE_MAX_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是专业的视频学习笔记助手。只输出紧凑 JSON，不要输出 Markdown。"
                        "字段必须包含 overview, outline, key_points, highlights, terms, questions, mind_map, qa_pairs。"
                        "所有字符串必须是合法 JSON 字符串，换行必须转义为 \\n。"
                    ),
                },
                {
                    "role": "user",
                    "content": build_summary_prompt(title=title, transcript=transcript, language=language),
                },
            ],
        }
        try:
            if stream_hook and hasattr(self.client, "stream"):
                content = self._stream_summary_completion(
                    request_payload,
                    title=title,
                    transcript=transcript,
                    stream_hook=stream_hook,
                )
            else:
                response = self.client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    timeout=timeout_seconds,
                    json=request_payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            return normalize_summary_payload(
                build_fallback_summary_payload(
                    title=title,
                    transcript=transcript,
                    reason=f"AI 总结请求超过 {int(timeout_seconds)} 秒，已先用字幕生成快速摘要。",
                ),
                title=title,
                transcript=transcript,
            )
        return normalize_summary_payload(
            parse_summary_content(content, title=title, transcript=transcript),
            title=title,
            transcript=transcript,
        )

    def _stream_summary_completion(
        self,
        request_payload: dict,
        *,
        title: str,
        transcript: str,
        stream_hook: Callable[[str], None],
    ) -> str:
        content_parts: list[str] = []
        last_preview = ""
        started_at = monotonic()
        total_timeout = _summary_timeout_seconds(self.config)
        with self.client.stream(
            "POST",
            f"{self.config.base_url}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            timeout=_summary_timeout_seconds(self.config),
            json={**request_payload, "stream": True},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                _raise_if_stream_timed_out(started_at, total_timeout)
                delta = _openai_stream_delta(line)
                if not delta:
                    continue
                content_parts.append(delta)
                preview = build_stream_preview_from_summary_text(
                    "".join(content_parts),
                    title=title,
                    transcript=transcript,
                )
                if preview and preview != last_preview:
                    stream_hook(preview)
                    last_preview = preview
        content = "".join(content_parts).strip()
        if not content:
            raise RuntimeError("AI 总结服务未返回文本。")
        return content

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        response = self.client.post(
            f"{self.config.base_url}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            timeout=_question_timeout_seconds(self.config),
            json={
                "model": self.config.text_model,
                "max_tokens": QUESTION_RESPONSE_MAX_TOKENS,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是专业的视频学习助教。只能基于给定字幕和总结回答，不确定时明确说明。",
                    },
                    {
                        "role": "user",
                        "content": build_question_prompt(
                            title=title,
                            transcript=compact_transcript_for_prompt(
                                transcript,
                                max_chars=QUESTION_TRANSCRIPT_CHAR_BUDGET,
                            ),
                            summary=summary,
                            question=question,
                            language=language,
                        ),
                    },
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content).strip()


class AnthropicCompatibleProvider:
    def __init__(self, config: AIProviderConfig, *, client=None) -> None:
        if not config.api_key:
            raise RuntimeError("AI_API_KEY 未配置，无法使用内置 AI 总结服务。")
        self.config = config
        self.client = client or httpx.Client(timeout=config.timeout_seconds, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        raise RuntimeError("当前 Anthropic-compatible AI 服务不支持语音转写，请配置支持 /audio/transcriptions 的 AI 服务。")

    def summarize_transcript(
        self,
        *,
        title: str,
        transcript: str,
        language: str,
        stream_hook: Callable[[str], None] | None = None,
    ) -> dict:
        timeout_seconds = _summary_timeout_seconds(self.config)
        request_payload = {
            "model": self.config.text_model,
            "max_tokens": SUMMARY_RESPONSE_MAX_TOKENS,
            "temperature": 0.1,
            "system": (
                "你是专业的视频学习笔记助手。只输出紧凑 JSON，不要输出 Markdown。"
                "字段必须包含 overview, outline, key_points, highlights, terms, questions, mind_map, qa_pairs。"
                "所有字符串必须是合法 JSON 字符串，换行必须转义为 \\n。"
            ),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": build_summary_prompt(title=title, transcript=transcript, language=language),
                        }
                    ],
                }
            ],
        }
        try:
            response = self.client.post(
                f"{self.config.base_url}/v1/messages",
                headers=self._headers(),
                timeout=timeout_seconds,
                json=request_payload,
            )
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content") if isinstance(data, dict) else []
            text = "\n".join(
                str(block.get("text") or "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
        except httpx.TimeoutException:
            return normalize_summary_payload(
                build_fallback_summary_payload(
                    title=title,
                    transcript=transcript,
                    reason=f"AI 总结请求超过 {int(timeout_seconds)} 秒，已先用字幕生成快速摘要。",
                ),
                title=title,
                transcript=transcript,
            )
        if not text:
            raise RuntimeError("AI 总结服务未返回文本。")
        return normalize_summary_payload(
            parse_summary_content(text, title=title, transcript=transcript),
            title=title,
            transcript=transcript,
        )

    def _stream_summary_completion(
        self,
        request_payload: dict,
        *,
        title: str,
        transcript: str,
        stream_hook: Callable[[str], None],
    ) -> str:
        content_parts: list[str] = []
        last_preview = ""
        started_at = monotonic()
        total_timeout = _summary_timeout_seconds(self.config)
        with self.client.stream(
            "POST",
            f"{self.config.base_url}/v1/messages",
            headers=self._headers(),
            timeout=_summary_timeout_seconds(self.config),
            json={**request_payload, "stream": True},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                _raise_if_stream_timed_out(started_at, total_timeout)
                delta = _anthropic_stream_delta(line)
                if not delta:
                    continue
                content_parts.append(delta)
                preview = build_stream_preview_from_summary_text(
                    "".join(content_parts),
                    title=title,
                    transcript=transcript,
                )
                if preview and preview != last_preview:
                    stream_hook(preview)
                    last_preview = preview
        return "".join(content_parts).strip()

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        response = self.client.post(
            f"{self.config.base_url}/v1/messages",
            headers=self._headers(),
            timeout=_question_timeout_seconds(self.config),
            json={
                "model": self.config.text_model,
                "max_tokens": QUESTION_RESPONSE_MAX_TOKENS,
                "temperature": 0.2,
                "system": "你是专业的视频学习助教。只能基于给定字幕和总结回答，不确定时明确说明。",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": build_question_prompt(
                                    title=title,
                                    transcript=compact_transcript_for_prompt(
                                        transcript,
                                        max_chars=QUESTION_TRANSCRIPT_CHAR_BUDGET,
                                    ),
                                    summary=summary,
                                    question=question,
                                    language=language,
                                ),
                            }
                        ],
                    }
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        content_blocks = data.get("content") if isinstance(data, dict) else []
        text = "\n".join(
            str(block.get("text") or "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not text:
            raise RuntimeError("AI 问答服务未返回文本。")
        return text


def build_summary_prompt(*, title: str, transcript: str, language: str) -> str:
    prepared_transcript = compact_transcript_for_prompt(transcript)
    return f"""请用 {language} 总结下面的视频转写稿。

视频标题：{title or "未命名视频"}

保真要求：
1. 只能基于视频标题和转写稿总结，所有结论、步骤、风险、术语和问答都必须能从字幕中找到依据。
2. 不得编造字幕未出现的人名、工具、数据、结论、案例或时间点；字幕没有依据时必须明确写“字幕没有依据”。
3. 不要输出“核心内容”“要点总结”“主要讲了很多内容”等泛化占位句，必须写出字幕里的具体对象、动作、原因、证据和限制。
4. 必须覆盖开头、中段和结尾，不能只总结前几行字幕。
5. 先逐段提取字幕事实，再做归纳；不要只根据标题猜测视频内容。

输出必须是紧凑 JSON，禁止 Markdown、解释文字和代码块。字段必须完整，不得省略；字段和类型如下：
{{
  "overview": "120-220 字，完整说明视频主题、核心过程、关键结论和限制",
  "outline": [{{"time":"00:00","title":"章节标题","summary":"章节摘要"}}],
  "key_points": ["核心知识点"],
  "highlights": [{{"time":"00:00","text":"重要片段"}}],
  "terms": [{{"term":"术语","explanation":"解释"}}],
  "questions": ["适合继续追问的问题"],
  "mind_map": {{
    "title": "中心主题",
    "children": [
      {{"title":"知识框架","children":[{{"title":"核心概念","children":[{{"title":"具体解释或结论"}}]}}]}},
      {{"title":"内容脉络","children":[{{"title":"章节推进","children":[{{"title":"对应时间段和摘要"}}]}}]}},
      {{"title":"方法步骤","children":[{{"title":"可执行动作","children":[{{"title":"操作条件或注意事项"}}]}}]}},
      {{"title":"案例证据","children":[{{"title":"字幕中的例子或论据","children":[{{"title":"支持的结论"}}]}}]}},
      {{"title":"风险边界","children":[{{"title":"限制条件","children":[{{"title":"适用或不适用场景"}}]}}]}}
    ]
  }},
  "qa_pairs": [{{"question":"学习者可能会问的问题","answer":"基于字幕的简洁回答"}}]
}}

长度要求：
1. overview 120-220 字，必须紧扣标题和字幕，不要写空泛套话。
2. outline 4-8 项，按字幕时间顺序覆盖主要章节，每项 summary 40-90 字。
3. key_points 6-10 项，每项必须包含字幕里的具体对象、动作、结论或条件。
4. highlights 4-8 项，必须带原字幕时间点，并解释该片段为什么重要。
5. terms 3-6 项，优先解释字幕中出现的专有名词、工具、指标、方法或缩写；不足时不要编造。
6. questions 4-6 项，必须是基于字幕内容可以继续追问的问题。
7. qa_pairs 3-5 项，answer 必须基于字幕回答，不确定时写“字幕没有依据”。
8. outline、key_points、highlights、terms、questions、qa_pairs 都应尽量信息互补，避免重复同一句话。
9. 所有字符串必须是合法 JSON 字符串；如需换行，必须写成 \\n。

思维导图要求：
1. mind_map 必须包含 4-6 个一级分支，每个一级分支至少 2 个子节点。
2. 一级分支要按角色区分，可使用：知识框架、内容脉络、方法步骤、案例证据、风险边界、行动建议。
3. 子节点要使用字幕里的具体名词、动作、结论、例子或限制条件；有依据时继续补充三级节点。
4. 避免使用“核心内容”“要点总结”这类泛化标题，也不要把章节标题机械重复成多个分支。

转写稿：
{prepared_transcript}
"""


def build_question_prompt(*, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
    summary_text = json.dumps(summary, ensure_ascii=False)
    return f"""请用 {language} 回答学习者关于视频的问题。

视频标题：{title or "未命名视频"}

已生成总结：
{summary_text}

字幕文本：
{transcript}

问题：{question}

回答要求：
1. 只基于字幕文本和总结回答。
2. 优先给出直接答案，再列出必要依据。
3. 如果字幕里没有依据，请明确说明“字幕中没有足够依据”。
"""


def build_stream_preview_from_summary_text(
    content: str,
    *,
    title: str | None = None,
    transcript: str | None = None,
) -> str:
    text = _strip_json_wrapping(content)
    try:
        payload = parse_json_content(text)
    except json.JSONDecodeError:
        return _build_stream_preview_from_partial_json(text)
    return build_stream_preview_from_payload(payload, title=title, transcript=transcript)


def build_stream_preview_from_payload(
    payload: dict,
    *,
    title: str | None = None,
    transcript: str | None = None,
) -> str:
    if not isinstance(payload, dict):
        return ""
    lines: list[str] = []
    overview = str(payload.get("overview") or "").strip()
    if overview:
        lines.append(f"一句话概览：{overview}")

    outline = _list_of_dicts(payload.get("outline"))
    if outline:
        lines.append("章节大纲：")
        lines.extend(f"- {_format_stream_outline_item(item)}" for item in outline[:5])

    key_points = _list_of_strings(payload.get("key_points"))
    if key_points:
        lines.append("核心知识点：")
        lines.extend(f"- {point}" for point in key_points[:6])

    highlights = _list_of_dicts(payload.get("highlights"))
    if highlights:
        lines.append("时间轴要点：")
        lines.extend(f"- {_format_stream_timed_item(item)}" for item in highlights[:4])

    terms = _list_of_dicts(payload.get("terms"))
    if terms:
        lines.append("术语解释：")
        lines.extend(f"- {_format_stream_term_item(item)}" for item in terms[:4])

    questions = _list_of_strings(payload.get("questions"))
    if questions:
        lines.append("可以继续追问：")
        lines.extend(f"- {question}" for question in questions[:4])

    if not lines and transcript:
        fallback = build_fallback_summary_payload(title=title or "", transcript=transcript)
        return build_stream_preview_from_payload(fallback, title=title, transcript=None)
    return _join_stream_preview_lines(lines)


def _build_stream_preview_from_partial_json(text: str) -> str:
    lines: list[str] = []
    overview = _first_stream_value(_extract_json_key_values(text, "overview"))
    if overview:
        lines.append(f"一句话概览：{overview}")

    outline_fragment = _json_section_fragment(text, "outline")
    outline_times = _extract_json_key_values(outline_fragment, "time")
    outline_titles = _extract_json_key_values(outline_fragment, "title")
    outline_summaries = _extract_json_key_values(outline_fragment, "summary")
    outline_items = _combine_stream_items(
        outline_times,
        outline_titles,
        outline_summaries,
        formatter=_format_stream_outline_parts,
    )
    if outline_items:
        lines.append("章节大纲：")
        lines.extend(f"- {item}" for item in outline_items[:5])

    key_point_items = _extract_json_array_strings(_json_section_fragment(text, "key_points"))
    if key_point_items:
        lines.append("核心知识点：")
        lines.extend(f"- {item}" for item in key_point_items[:6])

    highlight_fragment = _json_section_fragment(text, "highlights")
    highlight_items = _combine_stream_items(
        _extract_json_key_values(highlight_fragment, "time"),
        _extract_json_key_values(highlight_fragment, "text"),
        [],
        formatter=lambda time, text, _: _format_stream_timed_parts(time, text),
    )
    if highlight_items:
        lines.append("时间轴要点：")
        lines.extend(f"- {item}" for item in highlight_items[:4])

    term_fragment = _json_section_fragment(text, "terms")
    term_items = _combine_stream_items(
        [],
        _extract_json_key_values(term_fragment, "term"),
        _extract_json_key_values(term_fragment, "explanation"),
        formatter=lambda _, term, explanation: _format_stream_term_parts(term, explanation),
    )
    if term_items:
        lines.append("术语解释：")
        lines.extend(f"- {item}" for item in term_items[:4])

    question_items = _extract_json_array_strings(_json_section_fragment(text, "questions"))
    if question_items:
        lines.append("可以继续追问：")
        lines.extend(f"- {item}" for item in question_items[:4])

    return _join_stream_preview_lines(lines)


def _json_section_fragment(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:', text)
    if not match:
        return ""
    start = match.end()
    next_positions = [
        next_match.start()
        for next_match in re.finditer(r'"(?:overview|outline|key_points|highlights|terms|questions|mind_map|qa_pairs)"\s*:', text)
        if next_match.start() > match.start()
    ]
    end = min(next_positions) if next_positions else len(text)
    return text[start:end]


def _extract_json_key_values(fragment: str, key: str) -> list[str]:
    values = []
    for match in re.finditer(rf'"{re.escape(key)}"\s*:\s*"', fragment):
        value = _read_json_string_fragment(fragment, match.end())
        if value:
            values.append(value)
    return values


def _extract_json_array_strings(fragment: str) -> list[str]:
    start = fragment.find("[")
    if start == -1:
        return []
    values = []
    index = start + 1
    while index < len(fragment):
        if fragment[index] != '"':
            index += 1
            continue
        value, end_index = _read_json_string_with_end(fragment, index + 1)
        if value:
            values.append(value)
        index = max(end_index + 1, index + 1)
    return values


def _read_json_string_fragment(text: str, start: int) -> str:
    value, _ = _read_json_string_with_end(text, start)
    return value


def _read_json_string_with_end(text: str, start: int) -> tuple[str, int]:
    output: list[str] = []
    escaped = False
    index = start
    while index < len(text):
        char = text[index]
        if escaped:
            output.append(_decode_json_escape(char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return "".join(output).strip(), index
        elif char in "\r\n":
            break
        else:
            output.append(char)
        index += 1
    return "".join(output).strip(), index


def _decode_json_escape(char: str) -> str:
    return {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
        '"': '"',
        "\\": "\\",
        "/": "/",
    }.get(char, char)


def _first_stream_value(values: list[str]) -> str:
    return next((value for value in values if len(value.strip()) >= 4), "")


def _combine_stream_items(times: list[str], titles: list[str], summaries: list[str], *, formatter) -> list[str]:
    count = max(len(times), len(titles), len(summaries))
    items = []
    for index in range(count):
        item = formatter(
            times[index] if index < len(times) else "",
            titles[index] if index < len(titles) else "",
            summaries[index] if index < len(summaries) else "",
        )
        if item:
            items.append(item)
    return items


def _format_stream_outline_item(item: dict) -> str:
    return _format_stream_outline_parts(
        str(item.get("time") or item.get("timestamp") or ""),
        str(item.get("title") or item.get("text") or ""),
        str(item.get("summary") or ""),
    )


def _format_stream_outline_parts(time: str, title: str, summary: str) -> str:
    title = title.strip()
    summary = summary.strip()
    if not title and not summary:
        return ""
    prefix = f"[{time.strip()}] " if time.strip() else ""
    if title and summary and summary != title:
        return f"{prefix}{title}：{summary}"
    return f"{prefix}{title or summary}"


def _format_stream_timed_item(item: dict) -> str:
    return _format_stream_timed_parts(
        str(item.get("time") or item.get("timestamp") or ""),
        str(item.get("text") or item.get("summary") or item.get("title") or ""),
    )


def _format_stream_timed_parts(time: str, text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return f"[{time.strip()}] {text}" if time.strip() else text


def _format_stream_term_item(item: dict) -> str:
    return _format_stream_term_parts(
        str(item.get("term") or item.get("name") or ""),
        str(item.get("explanation") or item.get("definition") or item.get("summary") or ""),
    )


def _format_stream_term_parts(term: str, explanation: str) -> str:
    term = term.strip()
    explanation = explanation.strip()
    if not term and not explanation:
        return ""
    if term and explanation:
        return f"{term}：{explanation}"
    return term or explanation


def _join_stream_preview_lines(lines: list[str]) -> str:
    clean_lines = []
    for line in lines:
        value = re.sub(r"\s+", " ", str(line or "")).strip().strip(",，")
        if not value or value in {"-", "："}:
            continue
        clean_lines.append(value)
    return "\n".join(_dedupe_strings(clean_lines)[:SUMMARY_STREAM_PREVIEW_MAX_LINES])


def _openai_stream_delta(line) -> str:
    data = _stream_data_payload(line)
    if not data:
        return ""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        return ""
    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if isinstance(content, str) and content:
        return content
    return ""


def _anthropic_stream_delta(line) -> str:
    data = _stream_data_payload(line)
    if not data:
        return ""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    delta = payload.get("delta")
    if isinstance(delta, dict):
        return str(delta.get("text") or "")
    return ""


def _stream_data_payload(line) -> str:
    if isinstance(line, bytes):
        text = line.decode("utf-8", errors="ignore")
    else:
        text = str(line or "")
    text = text.strip()
    if not text.startswith("data:"):
        return ""
    data = text.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return ""
    return data


def compact_transcript_for_prompt(transcript: str, *, max_chars: int = SUMMARY_TRANSCRIPT_CHAR_BUDGET) -> str:
    text = "\n".join(line.strip() for line in str(transcript or "").splitlines() if line.strip())
    if len(text) <= max_chars:
        return text

    lines = text.splitlines()
    marker = f"[字幕已压缩：原始字幕约 {len(text)} 字，以下按时间均匀抽样，保留开头、中段和结尾。]"
    line_budget = max(1_000, max_chars - len(marker) - 2)
    sampled = _sample_lines_for_budget(lines, line_budget)
    return f"{marker}\n{sampled}"


def _sample_lines_for_budget(lines: list[str], char_budget: int) -> str:
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0][:char_budget]

    average_line_length = max(1, sum(len(line) + 1 for line in lines) // len(lines))
    target_count = max(2, min(len(lines), char_budget // average_line_length))
    indices = _evenly_spaced_indices(len(lines), target_count)
    selected = [lines[index] for index in indices]
    sampled = "\n".join(selected)
    while len(sampled) > char_budget and len(selected) > 2:
        selected.pop(len(selected) // 2)
        sampled = "\n".join(selected)
    if len(sampled) > char_budget:
        half = max(1, (char_budget - 20) // 2)
        sampled = f"{selected[0][:half]}\n...\n{selected[-1][-half:]}"
    return sampled


def _evenly_spaced_indices(length: int, count: int) -> list[int]:
    if count >= length:
        return list(range(length))
    if count <= 1:
        return [0]
    return sorted({round(index * (length - 1) / (count - 1)) for index in range(count)})


def parse_summary_content(content: str, *, title: str, transcript: str) -> dict:
    try:
        return parse_json_content(content)
    except json.JSONDecodeError:
        return build_fallback_summary_payload(
            title=title,
            transcript=transcript,
            reason="AI 返回内容不是合法 JSON，已先用字幕生成快速摘要。",
        )


def parse_json_content(content: str) -> dict:
    text = _strip_json_wrapping(content)
    candidates = [text]
    object_slice = _extract_json_object(text)
    if object_slice and object_slice != text:
        candidates.append(object_slice)

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        for repaired in (candidate, _escape_control_chars_in_json_strings(candidate)):
            try:
                payload = json.loads(repaired)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("JSON content must be an object", repaired, 0)
            return payload

    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("Empty JSON content", text, 0)


def _strip_json_wrapping(content: str) -> str:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _escape_control_chars_in_json_strings(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
            continue

        if escaped:
            output.append(char)
            escaped = False
        elif char == "\\":
            output.append(char)
            escaped = True
        elif char == '"':
            output.append(char)
            in_string = False
        elif char == "\n":
            output.append("\\n")
        elif char == "\r":
            output.append("\\r")
        elif char == "\t":
            output.append("\\t")
        else:
            output.append(char)
    return "".join(output)


def build_fallback_summary_payload(*, title: str, transcript: str, reason: str | None = None) -> dict:
    segments = _extract_transcript_points(transcript)
    if not segments:
        overview = reason or "暂时无法生成结构化总结，但可以继续下载视频。"
        return {
            "overview": overview,
            "outline": [],
            "key_points": [],
            "highlights": [],
            "terms": [],
            "questions": ["这段视频最重要的结论是什么？"],
            "mind_map": {"title": title or "视频主题", "children": []},
            "qa_pairs": [],
        }

    outline_segments = _sample_transcript_points(segments, 8)
    key_points = [_clip_text(item["text"], 110) for item in _sample_transcript_points(segments, 8)]
    highlights = [
        {"time": item["time"], "text": _clip_text(item["text"], 110)}
        for item in _sample_transcript_points(segments, 8)
    ]
    terms = _extract_terms_from_segments(segments)
    questions = _build_grounded_questions(title=title, segments=segments)
    overview = _build_grounded_overview(title=title, segments=segments, reason=reason)
    return {
        "overview": overview,
        "outline": [
            {
                "time": item["time"],
                "title": _derive_outline_title(item["text"], index),
                "summary": _clip_text(item["text"], 90),
            }
            for index, item in enumerate(outline_segments)
        ],
        "key_points": key_points,
        "highlights": highlights,
        "terms": terms,
        "questions": questions,
        "mind_map": {"title": title or "视频主题", "children": []},
        "qa_pairs": _build_grounded_qa_pairs(questions=questions, segments=segments, key_points=key_points),
    }


def _build_grounded_overview(*, title: str, segments: list[dict[str, str]], reason: str | None = None) -> str:
    topic = f"《{title}》" if title else "该视频"
    sampled = _sample_transcript_points(segments, min(4, len(segments)))
    content = "；".join(_clip_text(item["text"], 48) for item in sampled if item.get("text"))
    lead = reason or "已基于转写文本生成快速摘要。"
    if content:
        return f"{lead}{topic}围绕这些字幕内容展开：{content}。"
    return f"{lead}{topic}有字幕内容，但暂时只能提取有限信息。"


def _derive_outline_title(text: str, index: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return f"章节 {index + 1}"
    first_clause = re.split(r"[。！？；;,.，：:]", clean, maxsplit=1)[0].strip()
    first_clause = re.sub(r"^(主讲人)?(说明|介绍|指出|强调|首先|接着|然后|最后|后续动作是|关键风险是)", "", first_clause).strip()
    return _clip_text(first_clause or clean, 28)


def _extract_terms_from_segments(segments: list[dict[str, str]]) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []
    seen: set[str] = set()
    stop_words = {"and", "or", "the", "a", "an"}
    for item in segments:
        text = item["text"]
        for match in LATIN_TERM_PATTERN.finditer(text):
            term = " ".join(match.group(0).split())
            key = term.lower()
            if len(term) <= 1 or key in stop_words or key in seen:
                continue
            seen.add(key)
            terms.append(
                {
                    "term": term,
                    "explanation": f"字幕在 {item['time']} 提到：{_clip_text(text, 80)}",
                }
            )
            if len(terms) >= 6:
                return terms
    for item in segments:
        for term in _extract_chinese_term_candidates(item["text"]):
            key = _mind_key(term)
            if key in seen:
                continue
            seen.add(key)
            terms.append(
                {
                    "term": term,
                    "explanation": f"字幕在 {item['time']} 提到：{_clip_text(item['text'], 80)}",
                }
            )
            if len(terms) >= 6:
                return terms
    return terms


def _extract_chinese_term_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for clause in re.split(r"[。！？；;，,：:\n]", str(text or "")):
        value = re.sub(r"\s+", "", clause).strip()
        if len(value) < 4:
            continue
        for _ in range(2):
            value = re.sub(
                r"^(主讲人|作者|团队|系统|视频)?(介绍|说明|复盘|指出|强调|首先|先|再|接着|然后|最后|关键风险是|风险是|后续动作是|使用|通过|利用|借助|配置|创建|生成|同步|检查)",
                "",
                value,
            )
        for pattern in (
            r"([\u4e00-\u9fffA-Za-z0-9]{2,16})(?:是指|指的是|叫做|称为|简称)",
            r"([\u4e00-\u9fffA-Za-z0-9]{2,12}(?:流程|方法|模型|策略|指标|风险|步骤|机制|工具|平台|功能|体系))",
        ):
            match = re.search(pattern, value)
            if match:
                candidates.append(_clip_text(match.group(1), 18))
                break
    return _dedupe_strings(candidates)


def _build_grounded_questions(*, title: str, segments: list[dict[str, str]]) -> list[str]:
    subject = title or _derive_outline_title(segments[0]["text"], 0)
    risk_text = next((item["text"] for item in segments if _contains_risk_marker(item["text"])), "")
    action_text = segments[-1]["text"] if segments else ""
    questions = [
        f"{subject}的核心流程和结论是什么？",
        f"字幕中哪些步骤最影响{subject}的结果？",
        "视频提到的关键证据或数据应该如何理解？",
    ]
    if risk_text:
        questions.append(f"字幕提到的风险或限制是什么：{_clip_text(risk_text, 30)}？")
    if action_text:
        questions.append(f"看完后应优先执行哪些动作：{_clip_text(action_text, 30)}？")
    return _dedupe_strings(questions)[:6]


def _build_grounded_qa_pairs(
    *,
    questions: list[str],
    segments: list[dict[str, str]],
    key_points: list[str],
) -> list[dict[str, str]]:
    if not questions:
        return []
    risk_segment = next((item for item in segments if _contains_risk_marker(item["text"])), None)
    qa_pairs: list[dict[str, str]] = []
    answer_sources = [
        "；".join(key_points[:2]),
        "；".join(key_points[2:4] or key_points[:2]),
        _clip_text(risk_segment["text"], 120) if risk_segment else "；".join(key_points[-2:] or key_points[:2]),
        _clip_text(segments[-1]["text"], 120) if segments else "",
    ]
    for index, question in enumerate(questions[:5]):
        source = answer_sources[min(index, len(answer_sources) - 1)].strip()
        answer = f"字幕显示：{source}" if source else "字幕没有依据。"
        qa_pairs.append({"question": question, "answer": answer})
    return qa_pairs


def _contains_risk_marker(text: str) -> bool:
    return any(marker in text for marker in ("风险", "限制", "不能", "不要", "避免", "注意", "问题", "失败"))


def _extract_transcript_points(transcript: str) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    for index, line in enumerate(str(transcript or "").splitlines()):
        text = line.strip()
        if not text:
            continue
        match = TRANSCRIPT_LINE_PATTERN.match(text)
        if match:
            points.append({"time": match.group("time"), "text": match.group("text").strip()})
        else:
            points.append({"time": format_fallback_time(index), "text": text})
    return [point for point in points if point["text"]]


def _sample_transcript_points(points: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    if len(points) <= count:
        return points
    return [points[index] for index in _evenly_spaced_indices(len(points), count)]


def _clip_text(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def format_fallback_time(index: int) -> str:
    minutes = index // 2
    seconds = (index % 2) * 30
    return f"{minutes:02d}:{seconds:02d}"


def _summary_timeout_seconds(config: AIProviderConfig) -> float:
    configured_timeout = float(config.timeout_seconds or SUMMARY_REQUEST_TIMEOUT_SECONDS)
    return max(1.0, configured_timeout)


def _question_timeout_seconds(config: AIProviderConfig) -> float:
    return min(float(config.timeout_seconds), 20.0)


def _raise_if_stream_timed_out(started_at: float, timeout_seconds: float) -> None:
    if monotonic() - started_at > timeout_seconds:
        raise httpx.TimeoutException("AI summary stream exceeded total timeout")


def normalize_summary_payload(payload: dict, *, title: str | None = None, transcript: str | None = None) -> dict:
    fallback = _build_transcript_enrichment_payload(title=title or "", transcript=transcript or "")
    outline = _list_of_dicts(payload.get("outline"))
    if fallback:
        outline = _merge_dict_section(
            outline,
            _list_of_dicts(fallback.get("outline")),
            min_count=4,
            limit=8,
        )

    key_points = _list_of_strings(payload.get("key_points"))
    if fallback:
        key_points = _merge_string_section(
            key_points,
            _list_of_strings(fallback.get("key_points")),
            min_count=4,
            limit=10,
        )

    highlights = _list_of_dicts(payload.get("highlights"))
    if fallback:
        highlights = _merge_dict_section(
            highlights,
            _list_of_dicts(fallback.get("highlights")),
            min_count=4,
            limit=8,
        )

    terms = _list_of_dicts(payload.get("terms"))
    if fallback:
        terms = _merge_dict_section(
            terms,
            _list_of_dicts(fallback.get("terms")),
            min_count=2,
            limit=6,
        )

    questions = _list_of_strings(payload.get("questions"))
    if fallback:
        questions = _merge_string_section(
            questions,
            _list_of_strings(fallback.get("questions")),
            min_count=3,
            limit=6,
        )

    overview = str(payload.get("overview") or "暂无概览").strip()
    if fallback and _overview_needs_enrichment(overview):
        overview = str(fallback.get("overview") or overview).strip()

    fallback_qa_pairs = _list_of_dicts(fallback.get("qa_pairs")) if fallback else []
    return {
        "overview": overview,
        "outline": outline,
        "key_points": key_points,
        "highlights": highlights,
        "terms": terms,
        "questions": questions,
        "mind_map": _normalize_mind_map(
            payload.get("mind_map"),
            fallback_title=str(title or overview or "视频主题"),
            outline=outline,
            key_points=key_points,
            highlights=highlights,
            terms=terms,
            questions=questions,
        ),
        "qa_pairs": _normalize_qa_pairs(payload.get("qa_pairs"), questions=questions, fallback_pairs=fallback_qa_pairs),
    }


def _build_transcript_enrichment_payload(*, title: str, transcript: str) -> dict | None:
    segments = _extract_transcript_points(transcript)
    total_chars = sum(len(item["text"]) for item in segments)
    if not segments or total_chars < 40 or (len(segments) == 1 and total_chars < 80):
        return None
    return build_fallback_summary_payload(title=title, transcript=transcript)


def _merge_string_section(existing: list[str], fallback: list[str], *, min_count: int, limit: int) -> list[str]:
    if not fallback:
        return existing
    clean_existing = [item for item in existing if not _looks_generic_text(item)]
    desired = min(min_count, len(fallback))
    if len(clean_existing) >= desired and len(clean_existing) == len(existing):
        return existing[:limit]
    return _dedupe_strings([*clean_existing, *fallback])[:limit]


def _merge_dict_section(existing: list[dict], fallback: list[dict], *, min_count: int, limit: int) -> list[dict]:
    if not fallback:
        return existing
    clean_existing = [item for item in existing if not _looks_generic_text(_dict_text(item))]
    desired = min(min_count, len(fallback))
    if len(clean_existing) >= desired and len(clean_existing) == len(existing):
        return existing[:limit]
    return _dedupe_dicts([*clean_existing, *fallback])[:limit]


def _overview_needs_enrichment(overview: str) -> bool:
    text = overview.strip()
    return not text or len(text) < 30 or _looks_generic_text(text)


def _looks_generic_text(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or "")).strip("。！？!?，,；;：:")
    if not value:
        return True
    lowered = value.lower()
    if lowered in {"a", "q", "n/a", "na"}:
        return True
    return any(phrase in value for phrase in GENERIC_SUMMARY_PHRASES)


def _dict_text(item: dict) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("time", "title", "summary", "text", "term", "explanation", "question", "answer")
    ).strip()


def _dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = _mind_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _dedupe_dicts(items: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = _mind_key(_dict_text(item))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _list_of_strings(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _list_of_dicts(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_mind_map(
    value,
    *,
    fallback_title: str,
    outline: list[dict],
    key_points: list[str],
    highlights: list[dict] | None = None,
    terms: list[dict] | None = None,
    questions: list[str] | None = None,
) -> dict:
    fallback_children = _build_mind_map_branches(
        outline=outline,
        key_points=key_points,
        highlights=highlights or [],
        terms=terms or [],
        questions=questions or [],
    )
    if isinstance(value, dict):
        node = _normalize_mind_node(value)
        if node["title"]:
            if _looks_generic_text(node["title"]):
                node["title"] = fallback_title or "视频主题"
            if _mind_map_needs_enrichment(node):
                node["children"] = _merge_mind_branches(node["children"], fallback_children)
            return node
    return {"title": fallback_title or "视频主题", "children": fallback_children}


def _build_mind_map_branches(
    *,
    outline: list[dict],
    key_points: list[str],
    highlights: list[dict],
    terms: list[dict],
    questions: list[str],
) -> list[dict]:
    children = [
        {
            "title": _format_outline_title(item),
            "children": _child_nodes(str(item.get("summary") or item.get("text") or "")),
        }
        for item in outline[:8]
        if _format_outline_title(item)
    ]
    branches: list[dict] = []
    if children:
        branches.append({"title": "内容脉络", "children": children[:6]})
    if key_points:
        branches.append({"title": "核心知识点", "children": [{"title": point, "children": []} for point in key_points[:8]]})
    if highlights:
        branches.append(
            {
                "title": "关键证据",
                "children": [
                    {"title": _format_timed_text(item), "children": []}
                    for item in highlights[:6]
                    if _format_timed_text(item)
                ],
            }
        )
    if terms:
        branches.append(
            {
                "title": "术语概念",
                "children": [
                    {
                        "title": str(item.get("term") or item.get("title") or "术语").strip(),
                        "children": _child_nodes(str(item.get("explanation") or item.get("summary") or "")),
                    }
                    for item in terms[:6]
                    if str(item.get("term") or item.get("title") or "").strip()
                ],
            }
        )
    if questions:
        branches.append({"title": "延伸追问", "children": [{"title": question, "children": []} for question in questions[:6]]})
    return [branch for branch in branches if branch["children"]][:6]


def _format_outline_title(item: dict) -> str:
    title = str(item.get("title") or item.get("text") or item.get("time") or "章节").strip()
    time = str(item.get("time") or "").strip()
    if time and title and not title.startswith("["):
        return f"[{time}] {title}"
    return title


def _format_timed_text(item: dict) -> str:
    text = str(item.get("text") or item.get("summary") or item.get("title") or "").strip()
    time = str(item.get("time") or "").strip()
    if time and text:
        return f"[{time}] {text}"
    return text


def _child_nodes(text: str) -> list[dict]:
    text = text.strip()
    return [{"title": text, "children": []}] if text else []


def _mind_map_needs_enrichment(node: dict) -> bool:
    branches = node.get("children") or []
    if len(branches) < 4:
        return True
    detailed_branch_count = sum(1 for branch in branches if len(branch.get("children") or []) >= 2)
    return detailed_branch_count < 4


def _merge_mind_branches(existing: list[dict], fallback: list[dict]) -> list[dict]:
    merged = [branch for branch in existing if branch.get("title")]
    by_title = {_mind_key(branch["title"]): branch for branch in merged}
    for branch in fallback:
        key = _mind_key(branch["title"])
        if key in by_title:
            target = by_title[key]
            target["children"] = _merge_mind_nodes(target.get("children") or [], branch.get("children") or [])
            continue
        merged.append(branch)
        by_title[key] = branch
    return merged[:6]


def _merge_mind_nodes(existing: list[dict], fallback: list[dict]) -> list[dict]:
    merged = [node for node in existing if node.get("title")]
    seen = {_mind_key(node["title"]) for node in merged}
    for node in fallback:
        key = _mind_key(node["title"])
        if key in seen:
            continue
        merged.append(node)
        seen.add(key)
    return merged[:6]


def _mind_key(title: str) -> str:
    return "".join(str(title).lower().split())


def _normalize_mind_node(value) -> dict:
    if not isinstance(value, dict):
        return {"title": str(value or ""), "children": []}
    title = str(value.get("title") or value.get("text") or value.get("name") or "").strip()
    children = [_normalize_mind_node(item) for item in value.get("children") or []]
    children = [child for child in children if child["title"]]
    return {"title": title, "children": children}


def _normalize_qa_pairs(value, *, questions: list[str], fallback_pairs: list[dict] | None = None) -> list[dict]:
    pairs: list[dict] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                question = str(item.get("question") or item.get("q") or "").strip()
                answer = str(item.get("answer") or item.get("a") or "").strip()
                if question or answer:
                    pairs.append({"question": question or "问题", "answer": answer or "字幕中没有足够依据。"})
            elif isinstance(item, str) and item.strip():
                pairs.append({"question": item.strip(), "answer": "可以在 AI 问答中继续追问这个问题。"})
    fallback_pairs = fallback_pairs or []
    clean_pairs = [item for item in pairs if not _looks_generic_text(_dict_text(item)) and "继续追问" not in item["answer"]]
    if clean_pairs and len(clean_pairs) == len(pairs):
        return clean_pairs
    if fallback_pairs:
        return _dedupe_dicts([*clean_pairs, *fallback_pairs])[:5]
    if pairs:
        return pairs
    return [{"question": question, "answer": "可以在 AI 问答中继续追问这个问题。"} for question in questions]


class MockAIProvider:
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        return "[00:00] 这是演示转写内容，用于本地浏览器验收。 [01:10] 视频介绍了核心概念、章节结构和实践建议。"

    def summarize_transcript(
        self,
        *,
        title: str,
        transcript: str,
        language: str,
        stream_hook: Callable[[str], None] | None = None,
    ) -> dict:
        title = title or "演示视频"
        payload = {
            "overview": f"《{title}》主要帮助用户快速理解长视频的知识结构和关键结论。",
            "outline": [
                {"time": "00:00", "title": "内容背景", "summary": "说明视频主题和学习目标。"},
                {"time": "01:10", "title": "核心知识", "summary": "提炼关键概念、方法和应用场景。"},
            ],
            "key_points": [
                "优先利用字幕可以降低成本并提升处理速度。",
                "当前版本聚焦已有字幕视频，无法获取字幕时会明确提示。",
                "结构化输出比单段摘要更适合学习复盘。",
            ],
            "highlights": [
                {"time": "00:00", "text": "先建立视频主题认知，再深入章节细节。"},
                {"time": "01:10", "text": "把长视频转成大纲、要点和问题清单。"},
            ],
            "terms": [
                {"term": "字幕总结", "explanation": "将视频已有字幕转换为大纲、要点和问答材料。"},
                {"term": "结构化总结", "explanation": "把内容拆成章节、要点、术语和追问问题。"},
            ],
            "questions": ["这段视频最适合解决什么学习问题？", "哪些章节值得回看？"],
            "mind_map": {
                "title": title,
                "children": [
                    {
                        "title": "知识框架",
                        "children": [
                            {"title": "已有字幕优先", "children": [{"title": "直接利用平台字幕降低处理成本", "children": []}]},
                            {"title": "结构化学习笔记", "children": [{"title": "把字幕拆成大纲、要点、术语和问答", "children": []}]},
                        ],
                    },
                    {
                        "title": "内容脉络",
                        "children": [
                            {"title": "[00:00] 内容背景", "children": [{"title": "先说明视频主题和学习目标", "children": []}]},
                            {"title": "[01:10] 核心知识", "children": [{"title": "再提炼关键概念、方法和应用场景", "children": []}]},
                        ],
                    },
                    {
                        "title": "方法步骤",
                        "children": [
                            {"title": "提取字幕", "children": [{"title": "优先人工字幕，其次自动字幕", "children": []}]},
                            {"title": "生成学习结构", "children": [{"title": "产出摘要、思维导图和可追问问题", "children": []}]},
                        ],
                    },
                    {
                        "title": "风险边界",
                        "children": [
                            {"title": "无字幕视频", "children": [{"title": "当前版本会明确提示不可总结", "children": []}]},
                            {"title": "平台限制", "children": [{"title": "登录态字幕不会静默使用 Cookie", "children": []}]},
                        ],
                    },
                ],
            },
            "qa_pairs": [
                {"question": "这段视频最适合解决什么学习问题？", "answer": "适合快速建立长视频的主题认知和复盘路径。"},
                {"question": "哪些章节值得回看？", "answer": "建议优先回看核心知识和实践建议相关章节。"},
            ],
        }
        if stream_hook:
            stream_hook(build_stream_preview_from_payload(payload, title=title, transcript=transcript))
        return payload

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        return f"基于《{title or '演示视频'}》的字幕，可以这样理解：{question} 与视频的主题、章节和核心知识点直接相关。"
