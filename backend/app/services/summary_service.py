from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from app.services.ai_provider import AIProvider, build_ai_provider_from_env, normalize_summary_payload
from app.services.bilibili_public_metadata import describe_bilibili_transcript_unavailable
from app.services.transcript_service import Transcript, TranscriptSegment, TranscriptService, format_timestamp, transcript_to_text


SummaryProgressHook = Callable[[str, float, str], None]


class SummaryService:
    def __init__(
        self,
        *,
        transcript_service: TranscriptService | None = None,
        audio_service=None,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self.transcript_service = transcript_service or TranscriptService()
        self.audio_service = audio_service
        self.ai_provider = ai_provider or build_ai_provider_from_env()

    def generate_summary(
        self,
        *,
        url: str,
        title: str | None,
        language: str,
        output_dir: Path,
        progress_hook: SummaryProgressHook | None = None,
    ) -> tuple[dict, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title or "未命名视频"

        if _demo_mode_enabled() and url.startswith("https://demo.saveany.local/"):
            transcript = Transcript(
                source="subtitle",
                language=language,
                segments=[
                    TranscriptSegment(start=0, end=35, text="演示视频介绍了 AI 总结的工作流。"),
                    TranscriptSegment(start=70, end=130, text="系统会使用已有字幕生成摘要、大纲、思维导图和问答。"),
                ],
            )
        else:
            if progress_hook:
                progress_hook("subtitle", 12, "Extracting subtitles")
            try:
                transcript = self.transcript_service.fetch_transcript(url, output_dir / "subtitles")
            except Exception:
                transcript = None

        if transcript:
            source = transcript.source
            transcript_text = transcript_to_text(transcript.segments)
        else:
            reason = describe_bilibili_transcript_unavailable(url)
            raise RuntimeError(reason or "该视频没有可用字幕，当前版本仅支持已有字幕的视频总结。")

        if progress_hook:
            progress_hook("summary", 72, "Generating structured summary")
        summary = self.ai_provider.summarize_transcript(title=safe_title, transcript=transcript_text, language=language)
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


def _demo_mode_enabled() -> bool:
    return os.getenv("SAVEANY_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


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


def render_markdown(result: dict, *, title: str) -> str:
    lines = [
        f"# {title or '视频学习笔记'}",
        "",
        f"> 转写来源：{_source_label(result.get('transcript_source'))}",
        "",
        "## 一句话概览",
        "",
        str(result.get("overview") or "暂无概览"),
        "",
        "## 章节大纲",
        "",
    ]
    outline = result.get("outline") or []
    lines.extend(_render_outline(outline))
    lines.extend(["", "## 核心知识点", ""])
    lines.extend(_render_string_list(result.get("key_points") or []))
    lines.extend(["", "## 时间轴要点", ""])
    lines.extend(_render_highlights(result.get("highlights") or []))
    lines.extend(["", "## 术语解释", ""])
    lines.extend(_render_terms(result.get("terms") or []))
    lines.extend(["", "## 字幕文本", ""])
    lines.extend(_render_transcript(result.get("transcript_segments") or [], result.get("transcript_text") or ""))
    lines.extend(["", "## 思维导图", ""])
    lines.extend(_render_mind_map(result.get("mind_map") or {}))
    lines.extend(["", "## AI 问答", ""])
    lines.extend(_render_qa_pairs(result.get("qa_pairs") or [], result.get("questions") or []))
    lines.extend(["", "## 可以继续追问", ""])
    lines.extend(_render_string_list(result.get("questions") or []))
    lines.append("")
    return "\n".join(lines)


def _render_outline(items: list[dict]) -> list[str]:
    if not items:
        return ["- 暂无章节大纲"]
    lines = []
    for item in items:
        time = item.get("time") or "时间未知"
        title = item.get("title") or "未命名章节"
        summary = item.get("summary") or item.get("text") or ""
        lines.append(f"- [{time}] **{title}**：{summary}")
    return lines


def _render_highlights(items: list[dict]) -> list[str]:
    if not items:
        return ["- 暂无时间轴要点"]
    return [f"- [{item.get('time') or '时间未知'}] {item.get('text') or item.get('summary') or ''}" for item in items]


def _render_terms(items: list[dict]) -> list[str]:
    if not items:
        return ["- 暂无术语解释"]
    return [f"- **{item.get('term') or '术语'}**：{item.get('explanation') or item.get('summary') or ''}" for item in items]


def _render_transcript(segments: list[dict], transcript_text: str) -> list[str]:
    if segments:
        return [f"- [{item.get('time') or '时间未知'}] {item.get('text') or ''}" for item in segments]
    if transcript_text.strip():
        return [f"- {line}" for line in transcript_text.splitlines() if line.strip()]
    return ["- 暂无字幕文本"]


def _render_mind_map(node: dict, *, level: int = 0) -> list[str]:
    title = str(node.get("title") or "视频主题").strip()
    lines = [f"{'  ' * level}- {title}"]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            lines.extend(_render_mind_map(child, level=level + 1))
    return lines


def _render_qa_pairs(items: list[dict], questions: list[str]) -> list[str]:
    if items:
        lines = []
        for item in items:
            question = item.get("question") or "问题"
            answer = item.get("answer") or "字幕中没有足够依据。"
            lines.append(f"- **问：{question}**")
            lines.append(f"  答：{answer}")
        return lines
    return [f"- **问：{question}**\n  答：可以在 AI 问答中继续追问这个问题。" for question in questions] or ["- 暂无问答"]


def _render_string_list(items: list[str]) -> list[str]:
    if not items:
        return ["- 暂无内容"]
    return [f"- {item}" for item in items]


def _source_label(source: str | None) -> str:
    return {
        "subtitle": "字幕",
        "auto_subtitle": "自动字幕",
    }.get(source or "", "未知")
