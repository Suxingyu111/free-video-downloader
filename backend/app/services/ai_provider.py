from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx

from app.services.ai_config import AIProviderConfig, load_ai_provider_config


class AIProvider(Protocol):
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        ...

    def summarize_transcript(self, *, title: str, transcript: str, language: str) -> dict:
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

    def summarize_transcript(self, *, title: str, transcript: str, language: str) -> dict:
        response = self.client.post(
            f"{self.config.base_url}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "model": self.config.text_model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是专业的视频学习笔记助手。请只输出 JSON，不要输出 Markdown。"
                            "字段必须包含 overview, outline, key_points, highlights, terms, questions, mind_map, qa_pairs。"
                            "mind_map 要层级清晰、分支角色不同，避免空泛重复。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_summary_prompt(title=title, transcript=transcript, language=language),
                    },
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return normalize_summary_payload(parse_json_content(content))

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        response = self.client.post(
            f"{self.config.base_url}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "model": self.config.text_model,
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
                            transcript=transcript,
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

    def summarize_transcript(self, *, title: str, transcript: str, language: str) -> dict:
        response = self.client.post(
            f"{self.config.base_url}/v1/messages",
            headers=self._headers(),
            json={
                "model": self.config.text_model,
                "max_tokens": 4096,
                "temperature": 0.2,
                "system": (
                    "你是专业的视频学习笔记助手。请只输出 JSON，不要输出 Markdown。"
                    "字段必须包含 overview, outline, key_points, highlights, terms, questions, mind_map, qa_pairs。"
                    "mind_map 要层级清晰、分支角色不同，避免空泛重复。"
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
            raise RuntimeError("AI 总结服务未返回文本。")
        return normalize_summary_payload(parse_json_content(text))

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        response = self.client.post(
            f"{self.config.base_url}/v1/messages",
            headers=self._headers(),
            json={
                "model": self.config.text_model,
                "max_tokens": 2048,
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
                                    transcript=transcript,
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
    return f"""请用 {language} 总结下面的视频转写稿。

视频标题：{title or "未命名视频"}

输出 JSON 格式：
{{
  "overview": "一句话概览",
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

思维导图要求：
1. mind_map 必须包含 4-6 个一级分支，每个一级分支至少 2 个子节点。
2. 一级分支要按角色区分，可使用：知识框架、内容脉络、方法步骤、案例证据、风险边界、行动建议。
3. 子节点要使用字幕里的具体名词、动作、结论、例子或限制条件；有依据时继续补充三级节点。
4. 避免使用“核心内容”“要点总结”这类泛化标题，也不要把章节标题机械重复成多个分支。

转写稿：
{transcript}
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


def parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def normalize_summary_payload(payload: dict) -> dict:
    outline = _list_of_dicts(payload.get("outline"))
    key_points = _list_of_strings(payload.get("key_points"))
    highlights = _list_of_dicts(payload.get("highlights"))
    terms = _list_of_dicts(payload.get("terms"))
    questions = _list_of_strings(payload.get("questions"))
    return {
        "overview": str(payload.get("overview") or "暂无概览"),
        "outline": outline,
        "key_points": key_points,
        "highlights": highlights,
        "terms": terms,
        "questions": questions,
        "mind_map": _normalize_mind_map(
            payload.get("mind_map"),
            fallback_title=str(payload.get("overview") or "视频主题"),
            outline=outline,
            key_points=key_points,
            highlights=highlights,
            terms=terms,
            questions=questions,
        ),
        "qa_pairs": _normalize_qa_pairs(payload.get("qa_pairs"), questions=questions),
    }


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


def _normalize_qa_pairs(value, *, questions: list[str]) -> list[dict]:
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
    if pairs:
        return pairs
    return [{"question": question, "answer": "可以在 AI 问答中继续追问这个问题。"} for question in questions]


class MockAIProvider:
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        return "[00:00] 这是演示转写内容，用于本地浏览器验收。 [01:10] 视频介绍了核心概念、章节结构和实践建议。"

    def summarize_transcript(self, *, title: str, transcript: str, language: str) -> dict:
        title = title or "演示视频"
        return {
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

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        return f"基于《{title or '演示视频'}》的字幕，可以这样理解：{question} 与视频的主题、章节和核心知识点直接相关。"
