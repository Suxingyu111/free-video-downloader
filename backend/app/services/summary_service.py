from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from time import monotonic
from typing import Callable
from urllib.parse import urlsplit

import httpx
from app.services.ai_provider import (
    AIProvider,
    build_ai_provider_from_env,
    normalize_summary_payload,
)
from app.services.audio_service import AudioExtractionService
from app.services.bilibili_public_metadata import describe_bilibili_transcript_unavailable
from app.services.env_file import bool_env_enabled, env_value
from app.services.transcript_service import (
    DEFAULT_SUBTITLE_LANGUAGES,
    Transcript,
    TranscriptSegment,
    TranscriptService,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    parse_vtt,
    transcript_to_text,
)
from app.services.transcription_provider import TranscriptionProvider, build_transcription_provider_from_env
from app.services.ytdlp_service import build_http_headers


SummaryProgressHook = Callable[..., None]
TRANSCRIBED_LINE_PATTERN = re.compile(r"^\[(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\]\s*(?P<text>.+)$")
DIRECT_SUBTITLE_TIMEOUT_SECONDS = 12.0


class SummaryService:
    def __init__(
        self,
        *,
        transcript_service: TranscriptService | None = None,
        audio_service=None,
        ai_provider: AIProvider | None = None,
        transcription_provider: TranscriptionProvider | None = None,
    ) -> None:
        self.transcript_service = transcript_service or TranscriptService()
        self.audio_service = audio_service or AudioExtractionService()
        self.ai_provider = ai_provider or build_ai_provider_from_env()
        if transcription_provider is not None:
            self.transcription_provider = transcription_provider
        elif ai_provider is not None and hasattr(ai_provider, "transcribe_audio"):
            self.transcription_provider = ai_provider
        else:
            self.transcription_provider = build_transcription_provider_from_env()

    def generate_summary(
        self,
        *,
        url: str,
        title: str | None,
        language: str,
        output_dir: Path,
        progress_hook: SummaryProgressHook | None = None,
        seed_result: dict | None = None,
    ) -> tuple[dict, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title or "未命名视频"
        transcript = transcript_from_summary_result(seed_result, language=language)

        if transcript:
            if progress_hook:
                emit_summary_progress(progress_hook, "subtitle", 24, "Reusing previous transcript")
        else:
            transcript = transcript_from_analysis_subtitles(seed_result, language=language, video_url=url)
            if transcript and progress_hook:
                emit_summary_progress(progress_hook, "subtitle", 28, "Using analyzed subtitle track")

        if not transcript:
            if _demo_mode_enabled() and url.startswith("https://demo.saveany.local/"):
                transcript = Transcript(
                    source="subtitle",
                    language=language,
                    segments=[
                        TranscriptSegment(start=0, end=35, text="演示视频介绍了 AI 总结的工作流。"),
                        TranscriptSegment(start=70, end=130, text="系统会使用已有字幕生成摘要、大纲、思维导图和问答。"),
                    ],
                )
            elif has_analyzed_subtitles(seed_result):
                if progress_hook:
                    emit_summary_progress(progress_hook, "subtitle", 24, "Skipping slow subtitle extraction")
            else:
                if progress_hook:
                    emit_summary_progress(progress_hook, "subtitle", 12, "Extracting subtitles")
                try:
                    transcript = self.transcript_service.fetch_transcript(url, output_dir / "subtitles")
                except Exception:
                    transcript = None

        if transcript:
            source = transcript.source
            transcript_text = transcript_to_text(transcript.segments)
        else:
            reason = describe_bilibili_transcript_unavailable(url)
            if reason and progress_hook:
                emit_summary_progress(progress_hook, "speech_to_text", 26, reason)
            if progress_hook:
                emit_summary_progress(progress_hook, "speech_to_text", 30, "Extracting audio for speech-to-text")
            audio_path = self.audio_service.extract_audio(url, output_dir / "audio")
            transcription_seconds = estimate_audio_duration_seconds(audio_path)
            if progress_hook:
                emit_summary_progress(
                    progress_hook,
                    "speech_to_text",
                    32,
                    "Speech-to-text minutes required",
                    transcription_seconds=transcription_seconds,
                )
                emit_summary_progress(progress_hook, "speech_to_text", 48, "Transcribing audio")
            transcribed_text = self.transcription_provider.transcribe_audio(audio_path, language)
            segments = segments_from_transcribed_text(transcribed_text)
            if not segments:
                raise RuntimeError("AI 语音转写服务未返回可用文本。")
            transcript = Transcript(source="speech_to_text", language=language, segments=segments)
            source = transcript.source
            transcript_text = transcript_to_text(transcript.segments)

        stream_hook = None
        if progress_hook:
            emit_summary_progress(progress_hook, "summary", 72, "Generating readable summary")

            last_stream = {"text": "", "at": 0.0}

            def stream_hook(preview_text: str) -> None:
                preview = str(preview_text or "").strip()
                if not preview or preview == last_stream["text"]:
                    return
                now = monotonic()
                line_count = max(1, len([line for line in preview.splitlines() if line.strip()]))
                progress = min(96.0, 72.0 + line_count * 1.5)
                if now - float(last_stream["at"]) < 0.12 and len(preview) - len(str(last_stream["text"])) < 24:
                    return
                last_stream["text"] = preview
                last_stream["at"] = now
                emit_summary_progress(
                    progress_hook,
                    "summary",
                    progress,
                    "Streaming readable summary",
                    streamed_text=preview,
                )

        summary = self.ai_provider.summarize_transcript(
            title=safe_title,
            transcript=transcript_text,
            language=language,
            stream_hook=stream_hook,
        )
        result = normalize_summary_payload(summary, title=safe_title, transcript=transcript_text)
        result["transcript_source"] = source
        result["language"] = language
        result["transcript_language"] = transcript.language
        result["transcript_text"] = transcript_text
        result["transcript_segments"] = serialize_transcript_segments(transcript.segments)

        markdown = render_markdown(result, title=safe_title)
        markdown_path = output_dir / "summary.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        return result, markdown_path

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        return self.ai_provider.answer_question(
            title=title,
            transcript=transcript,
            summary=summary,
            question=question,
            language=language,
        )

def emit_summary_progress(
    progress_hook: SummaryProgressHook | None,
    stage: str,
    progress: float,
    message: str,
    **changes: object,
) -> None:
    if not progress_hook:
        return
    try:
        progress_hook(stage, progress, message, **changes)
    except TypeError:
        progress_hook(stage, progress, message)


def segments_from_transcribed_text(text: str) -> list[TranscriptSegment]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        value = str(text or "").strip()
        return [TranscriptSegment(start=0.0, end=30.0, text=value)] if value else []

    segments: list[TranscriptSegment] = []
    for index, line in enumerate(lines):
        match = TRANSCRIBED_LINE_PATTERN.match(line)
        if match:
            start = parse_timestamp(match.group("time"))
            body = match.group("text").strip()
        else:
            start = float(index * 30)
            body = line
        if not body:
            continue
        segments.append(TranscriptSegment(start=start, end=start + 30.0, text=body))

    for index in range(len(segments) - 1):
        current = segments[index]
        next_segment = segments[index + 1]
        if next_segment.start > current.start:
            segments[index] = TranscriptSegment(
                start=current.start,
                end=max(current.start + 1.0, next_segment.start),
                text=current.text,
            )
    return segments


def _demo_mode_enabled() -> bool:
    return bool_env_enabled("SAVEANY_DEMO_MODE")


def serialize_transcript_segments(segments: list[TranscriptSegment]) -> list[dict]:
    return [
        {
            "start": segment.start,
            "end": segment.end,
            "time": format_timestamp(segment.start),
            "text": segment.text,
        }
        for segment in segments
    ]


def transcript_from_analysis_subtitles(result: dict | None, *, language: str, video_url: str) -> Transcript | None:
    if not isinstance(result, dict):
        return None
    for item in _rank_analysis_subtitle_tracks(result.get("subtitles"), language=language):
        content = _subtitle_track_content(item, video_url=video_url)
        if not content:
            continue
        segments = _parse_subtitle_content(content, ext=str(item.get("ext") or ""))
        if segments:
            source = "auto_subtitle" if item.get("automatic") else "subtitle"
            return Transcript(
                source=source,
                language=str(item.get("lang") or language or "unknown"),
                segments=segments,
            )
    return None


def has_analyzed_subtitles(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    subtitles = result.get("subtitles")
    return isinstance(subtitles, list) and any(isinstance(item, dict) for item in subtitles)


def _rank_analysis_subtitle_tracks(value: object, *, language: str) -> list[dict]:
    if not isinstance(value, list):
        return []
    candidates = [item for item in value if isinstance(item, dict) and _is_direct_summary_subtitle(item)]
    return sorted(candidates, key=lambda item: _analysis_subtitle_priority(item, language=language))


def _is_direct_summary_subtitle(item: dict) -> bool:
    ext = str(item.get("ext") or "").strip().lower()
    if ext not in {"srt", "vtt"}:
        return False
    if str(item.get("data") or item.get("content") or "").strip():
        return True
    url = str(item.get("url") or "").strip()
    if not url:
        return False
    scheme = urlsplit(url).scheme.lower()
    return scheme in {"http", "https"}


def _analysis_subtitle_priority(item: dict, *, language: str) -> tuple[int, int, int, str]:
    requested = str(language or "").strip().lower()
    requested_base = requested.split("-", 1)[0]
    track_lang = str(item.get("lang") or "").strip().lower()
    track_base = track_lang.split("-", 1)[0]
    default_languages = [value.lower() for value in DEFAULT_SUBTITLE_LANGUAGES]
    if requested and track_lang == requested:
        language_score = 0
    elif requested_base and track_base == requested_base:
        language_score = 1
    elif track_lang in default_languages:
        language_score = 2 + default_languages.index(track_lang)
    elif track_base in default_languages:
        language_score = 2 + default_languages.index(track_base)
    else:
        language_score = 100
    automatic_score = 1 if item.get("automatic") else 0
    ext_score = 0 if str(item.get("ext") or "").strip().lower() == "vtt" else 1
    return language_score, automatic_score, ext_score, str(item.get("lang") or "")


def _subtitle_track_content(item: dict, *, video_url: str) -> str:
    inline_content = str(item.get("data") or item.get("content") or "").strip()
    if inline_content:
        return inline_content
    url = str(item.get("url") or "").strip()
    if not url:
        return ""
    try:
        response = httpx.get(
            url,
            headers=build_http_headers(video_url),
            timeout=DIRECT_SUBTITLE_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return ""
    return str(response.text or "").strip()


def _parse_subtitle_content(content: str, *, ext: str) -> list[TranscriptSegment]:
    value = str(content or "").strip()
    if not value:
        return []
    suffix = ext.strip().lower()
    if suffix == "srt":
        return parse_srt(value)
    if suffix == "vtt" or value.lstrip().startswith("WEBVTT"):
        return parse_vtt(value)
    return parse_vtt(value) or parse_srt(value)


def create_audio_preview_clip(audio_path: Path, output_dir: Path, *, seconds: int | None = None) -> Path | None:
    preview_seconds = seconds or int(env_value("SUMMARY_DRAFT_AUDIO_SECONDS", "45") or "45")
    if preview_seconds <= 0:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / "preview.wav"
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-t",
        str(preview_seconds),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(preview_path),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return preview_path if preview_path.exists() and preview_path.stat().st_size > 0 else None


def estimate_audio_duration_seconds(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        duration = float(result.stdout.strip() or "0")
        if not math.isfinite(duration) or duration <= 0:
            return 1.0
        return max(duration, 1.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1.0


def transcript_from_summary_result(result: dict | None, *, language: str) -> Transcript | None:
    if not isinstance(result, dict):
        return None

    source = result.get("transcript_source")
    if source not in {"subtitle", "auto_subtitle", "speech_to_text"}:
        source = "subtitle"
    transcript_language = str(result.get("transcript_language") or language or "zh-CN")
    segments = _segments_from_summary_result(result)
    if not segments:
        segments = segments_from_transcribed_text(str(result.get("transcript_text") or ""))
    if not segments:
        return None
    return Transcript(source=source, language=transcript_language, segments=segments)


def _segments_from_summary_result(result: dict) -> list[TranscriptSegment]:
    raw_segments = result.get("transcript_segments")
    if not isinstance(raw_segments, list):
        return []

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = _coerce_segment_time(item.get("start"))
        if start is None:
            start = _coerce_segment_time(item.get("time"))
        if start is None:
            start = float(len(segments) * 30)
        end = _coerce_segment_time(item.get("end"))
        if end is None or end <= start:
            end = start + 30.0
        segments.append(TranscriptSegment(start=start, end=end, text=text))
    return segments


def _coerce_segment_time(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return parse_timestamp(value.strip())
        except (ValueError, TypeError):
            try:
                return float(value)
            except ValueError:
                return None
    return None


def render_markdown(result: dict, *, title: str) -> str:
    note_title = str(title or result.get("title") or "视频学习笔记").strip()
    readable_summary = str(result.get("readable_summary") or "").strip()
    lines = [
        f"# {note_title}",
        "",
        "> 这份学习笔记由 SaveAny 基于公开视频字幕或语音转写生成，适合复盘、检索和继续整理。",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 视频标题 | {_table_cell(note_title)} |",
        f"| 转写来源 | {_table_cell(_source_label(result.get('transcript_source')))} |",
        f"| 总结语言 | {_table_cell(result.get('language') or result.get('transcript_language') or 'zh-CN')} |",
        "",
        "## 快速导读",
        "",
    ]
    if readable_summary:
        lines.extend(["### 流式可读总结", "", readable_summary, ""])
    lines.extend([
        "### 一句话概览",
        "",
        str(result.get("overview") or "暂无概览"),
        "",
        "### 核心结论",
        "",
    ])
    lines.extend(_render_string_list(result.get("key_points") or [], limit=3, fallback="暂无核心结论"))
    understanding_lines = _render_understanding(result)
    if understanding_lines:
        lines.extend(["", *understanding_lines])
    lines.extend(["", "## 章节大纲", ""])
    lines.extend(_render_outline(result.get("outline") or []))
    lines.extend(["", "## 核心知识点", ""])
    lines.extend(_render_string_list(result.get("key_points") or [], fallback="暂无核心知识点"))
    lines.extend(["", "## 时间轴要点", ""])
    lines.extend(_render_highlights(result.get("highlights") or []))
    lines.extend(["", "## 术语解释", ""])
    lines.extend(_render_terms(result.get("terms") or []))
    lines.extend(["", "## 思维导图", ""])
    lines.extend(_render_mind_map(result.get("mind_map") or {}))
    lines.extend(["", "## AI 问答", ""])
    lines.extend(_render_qa_pairs(result.get("qa_pairs") or [], result.get("questions") or []))
    lines.extend(["", "## 后续追问", ""])
    lines.extend(_render_question_list(result.get("questions") or []))
    lines.extend(["", "<details>", "<summary>字幕原文</summary>", "", "```text"])
    lines.extend(_render_transcript(result.get("transcript_segments") or [], result.get("transcript_text") or ""))
    lines.extend(["```", "", "</details>", ""])
    return "\n".join(lines)


def _render_understanding(result: dict) -> list[str]:
    topic = str(result.get("topic") or "").strip()
    audience = str(result.get("audience") or "").strip()
    main_thread = result.get("main_thread") or []
    examples = result.get("examples") or []
    action_items = result.get("action_items") or []
    limitations = result.get("limitations") or []
    if not any([topic, audience, main_thread, examples, action_items, limitations]):
        return []

    lines = ["## 完整理解", ""]
    if topic or audience:
        lines.extend([
            f"| 主题 | {_table_cell(topic or '暂无')} |",
            "| --- | --- |",
            f"| 适合人群 | {_table_cell(audience or '暂无')} |",
        ])

    if main_thread:
        lines.extend(["", "### 主线脉络", ""])
        lines.extend(_render_string_list(main_thread, fallback="暂无主线脉络"))

    if examples:
        lines.extend(["", "### 例子和证据", ""])
        lines.extend(_render_examples(examples))

    if action_items:
        lines.extend(["", "### 行动清单", ""])
        lines.extend(_render_string_list(action_items, fallback="暂无行动建议"))

    if limitations:
        lines.extend(["", "### 边界和限制", ""])
        lines.extend(_render_string_list(limitations, fallback="暂无边界说明"))

    return lines


def _render_outline(items: list[dict]) -> list[str]:
    if not items:
        return ["暂无章节大纲"]
    lines = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            text = str(item or "").strip()
            if text:
                lines.append(f"{index}. {text}")
            continue
        time = str(item.get("time") or item.get("timestamp") or "").strip()
        title = str(item.get("title") or item.get("text") or "未命名章节").strip()
        summary = str(item.get("summary") or item.get("description") or "").strip()
        prefix = f"[{time}] " if time else ""
        body = f"{prefix}**{title}**"
        if summary and summary != title:
            body = f"{body}：{summary}"
        lines.append(f"{index}. {body}")
    return lines


def _render_highlights(items: list[dict]) -> list[str]:
    if not items:
        return ["暂无时间轴要点"]
    lines = ["| 时间 | 内容 |", "| --- | --- |"]
    for item in items:
        if isinstance(item, dict):
            time = item.get("time") or item.get("timestamp") or "时间未知"
            text = item.get("text") or item.get("summary") or item.get("title") or ""
        else:
            time = "时间未知"
            text = item
        lines.append(f"| {_table_cell(time)} | {_table_cell(text)} |")
    return lines


def _render_examples(items: list[dict]) -> list[str]:
    if not items:
        return ["暂无例子和证据"]
    lines = ["| 时间 | 内容 |", "| --- | --- |"]
    for item in items:
        if isinstance(item, dict):
            time = item.get("time") or item.get("timestamp") or item.get("start") or "时间未知"
            text = item.get("text") or item.get("summary") or item.get("title") or ""
        else:
            time = "时间未知"
            text = item
        lines.append(f"| {_table_cell(time)} | {_table_cell(text)} |")
    return lines


def _render_terms(items: list[dict]) -> list[str]:
    if not items:
        return ["暂无术语解释"]
    lines = ["| 术语 | 解释 |", "| --- | --- |"]
    for item in items:
        if isinstance(item, dict):
            term = item.get("term") or item.get("name") or item.get("title") or "术语"
            explanation = item.get("explanation") or item.get("definition") or item.get("summary") or item.get("text") or ""
        else:
            term = item
            explanation = ""
        lines.append(f"| {_table_cell(term)} | {_table_cell(explanation)} |")
    return lines


def _render_transcript(segments: list[dict], transcript_text: str) -> list[str]:
    if segments:
        lines = []
        for item in segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"[{item.get('time') or '时间未知'}] {text}")
        return lines or ["暂无字幕文本"]
    if transcript_text.strip():
        return [line for line in transcript_text.splitlines() if line.strip()]
    return ["暂无字幕文本"]


def _render_mind_map(node: dict, *, level: int = 0) -> list[str]:
    if not isinstance(node, dict):
        return ["- 视频主题"]
    title = str(node.get("title") or "视频主题").strip()
    lines = [f"{'  ' * level}- {title}"]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            lines.extend(_render_mind_map(child, level=level + 1))
    return lines


def _render_qa_pairs(items: list[dict], questions: list[str]) -> list[str]:
    if items:
        lines = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                question = str(item or f"问题 {index}").strip()
                answer = "字幕中没有足够依据。"
            else:
                question = str(item.get("question") or item.get("prompt") or f"问题 {index}").strip()
                answer = str(item.get("answer") or item.get("response") or "字幕中没有足够依据。").strip()
            lines.extend([f"### Q{index}. {question}", "", answer, ""])
        if lines and not lines[-1]:
            lines.pop()
        return lines
    question_items = _question_items(questions)
    if question_items:
        lines = []
        for index, question in enumerate(question_items, start=1):
            lines.extend([f"### Q{index}. {question}", "", "可以在 AI 问答中继续追问这个问题。", ""])
        if lines and not lines[-1]:
            lines.pop()
        return lines
    return ["暂无问答"]


def _render_string_list(items: list[str], *, limit: int | None = None, fallback: str = "暂无内容") -> list[str]:
    values = [str(item or "").strip() for item in items if str(item or "").strip()]
    if limit is not None:
        values = values[:limit]
    if not values:
        return [fallback]
    return [f"- {item}" for item in values]


def _render_question_list(items: list[str]) -> list[str]:
    values = _question_items(items)
    if not values:
        return ["暂无后续追问"]
    return [f"- {item}" for item in values]


def _question_items(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    values = []
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("question") or item.get("prompt") or item.get("title") or item.get("text") or "").strip()
        else:
            value = str(item or "").strip()
        if value:
            values.append(value)
    return values


def _table_cell(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return "暂无"
    return text.replace("|", "\\|")


def _source_label(source: str | None) -> str:
    return {
        "subtitle": "字幕",
        "auto_subtitle": "自动字幕",
        "speech_to_text": "语音转写",
    }.get(source or "", "未知")
