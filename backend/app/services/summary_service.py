from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from time import monotonic
from typing import Callable

from app.services.ai_provider import (
    AIProvider,
    build_ai_provider_from_env,
    build_fallback_summary_payload,
    build_stream_preview_from_payload,
    normalize_summary_payload,
)
from app.services.audio_service import AudioExtractionService
from app.services.bilibili_public_metadata import describe_bilibili_transcript_unavailable
from app.services.transcript_service import (
    Transcript,
    TranscriptSegment,
    TranscriptService,
    format_timestamp,
    parse_timestamp,
    transcript_to_text,
)
from app.services.transcription_provider import TranscriptionProvider, build_transcription_provider_from_env


SummaryProgressHook = Callable[..., None]
TRANSCRIBED_LINE_PATTERN = re.compile(r"^\[(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\]\s*(?P<text>.+)$")


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
        elif _demo_mode_enabled() and url.startswith("https://demo.saveany.local/"):
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
                preview_transcript = self._try_build_speech_preview_draft(
                    audio_path=audio_path,
                    output_dir=output_dir,
                    title=safe_title,
                    language=language,
                    progress_hook=progress_hook,
                )
                message = "Transcribing full audio" if preview_transcript else "Transcribing audio"
                emit_summary_progress(
                    progress_hook,
                    "speech_to_text",
                    46,
                    "Speech-to-text minutes required",
                    transcription_seconds=transcription_seconds,
                )
                emit_summary_progress(progress_hook, "speech_to_text", 48, message)
            transcribed_text = self.transcription_provider.transcribe_audio(audio_path, language)
            segments = segments_from_transcribed_text(transcribed_text)
            if not segments:
                raise RuntimeError("AI 语音转写服务未返回可用文本。")
            transcript = Transcript(source="speech_to_text", language=language, segments=segments)
            source = transcript.source
            transcript_text = transcript_to_text(transcript.segments)

        draft_result = build_draft_summary_result(
            title=safe_title,
            transcript=transcript,
            transcript_text=transcript_text,
            language=language,
        )
        stream_hook = None
        if progress_hook:
            draft_preview = build_stream_preview_from_payload(draft_result, title=safe_title, transcript=transcript_text)
            draft_source = "转写文本" if source == "speech_to_text" else "字幕"
            if draft_preview:
                emit_summary_progress(
                    progress_hook,
                    "summary",
                    58,
                    f"快速版已生成，完整总结正在完善中（基于{draft_source}）",
                    draft_result=draft_result,
                    streamed_text=draft_preview,
                )
            emit_summary_progress(progress_hook, "summary", 72, "Generating structured summary")

            last_stream = {"text": draft_preview, "at": 0.0}

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
                    "Streaming structured summary",
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

    def _try_build_speech_preview_draft(
        self,
        *,
        audio_path: Path,
        output_dir: Path,
        title: str,
        language: str,
        progress_hook: SummaryProgressHook,
    ) -> Transcript | None:
        emit_summary_progress(progress_hook, "speech_to_text", 36, "Preparing quick speech preview")
        preview_path = create_audio_preview_clip(audio_path, output_dir / "audio-preview")
        if preview_path is None:
            return None
        try:
            emit_summary_progress(progress_hook, "speech_to_text", 40, "Transcribing quick speech preview")
            preview_text = self.transcription_provider.transcribe_audio(preview_path, language)
            segments = segments_from_transcribed_text(preview_text)
        except Exception:
            return None
        if not segments:
            return None
        transcript = Transcript(source="speech_to_text", language=language, segments=segments)
        transcript_text = transcript_to_text(transcript.segments)
        draft_result = build_draft_summary_result(
            title=title,
            transcript=transcript,
            transcript_text=transcript_text,
            language=language,
        )
        preview = build_stream_preview_from_payload(draft_result, title=title, transcript=transcript_text)
        emit_summary_progress(
            progress_hook,
            "speech_to_text",
            44,
            "快速版已生成，完整转写正在继续",
            draft_result=draft_result,
            streamed_text=preview,
        )
        return transcript


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


def build_draft_summary_result(
    *,
    title: str,
    transcript: Transcript,
    transcript_text: str,
    language: str,
) -> dict:
    draft = normalize_summary_payload(
        build_fallback_summary_payload(title=title, transcript=transcript_text),
        title=title,
        transcript=transcript_text,
    )
    draft["transcript_source"] = transcript.source
    draft["language"] = language
    draft["transcript_language"] = transcript.language
    draft["transcript_text"] = transcript_text
    draft["transcript_segments"] = serialize_transcript_segments(transcript.segments)
    draft["summary_quality"] = "draft"
    return draft


def create_audio_preview_clip(audio_path: Path, output_dir: Path, *, seconds: int | None = None) -> Path | None:
    preview_seconds = seconds or int(os.getenv("SUMMARY_DRAFT_AUDIO_SECONDS", "45") or "45")
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
        return max(float(result.stdout.strip() or "0"), 1.0)
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
        "speech_to_text": "语音转写",
    }.get(source or "", "未知")
