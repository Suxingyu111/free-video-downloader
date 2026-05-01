from __future__ import annotations

import asyncio
import json
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.services.summary_service import SummaryService
from app.services.summary_store import summary_store
from app.services.ytdlp_service import friendly_error_message


SUMMARY_DIR = summary_store.base_dir

router = APIRouter(prefix="/api/summaries", tags=["summaries"])
summary_service: SummaryService | None = None


class SummaryRequest(BaseModel):
    url: str
    title: str | None = None
    language: str = "zh-CN"
    force: bool = False


class SummaryQuestionRequest(BaseModel):
    question: str
    language: str = "zh-CN"


def _friendly_summary_error(error: Exception | str) -> str:
    text = str(error)
    if "AI_API_KEY" in text:
        return "AI 总结服务尚未配置，请在后端配置 AI_API_KEY 后重试。"
    return friendly_error_message(text)


def _run_summary(summary_id: str, payload: SummaryRequest, seed_result: dict | None = None) -> None:
    output_dir = SUMMARY_DIR / summary_id

    def progress_hook(stage: str, progress: float, message: str, **changes: object) -> None:
        status = "transcribing" if stage in {"subtitle", "speech_to_text"} else "summarizing"
        summary_store.update_task(
            summary_id,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            **changes,
        )

    try:
        summary_store.update_task(summary_id, status="transcribing", stage="subtitle", progress=5, message="Preparing subtitles")
        result, markdown_path = get_summary_service().generate_summary(
            url=payload.url,
            title=payload.title,
            language=payload.language,
            output_dir=output_dir,
            progress_hook=progress_hook,
            seed_result=seed_result,
        )
        summary_store.complete_task(summary_id, result=result, markdown_path=markdown_path)
    except Exception as exc:
        summary_store.fail_task(summary_id, _friendly_summary_error(exc))


def get_summary_service() -> SummaryService:
    global summary_service
    if summary_service is None:
        summary_service = SummaryService()
    return summary_service


@router.post("")
def create_summary(payload: SummaryRequest) -> dict[str, object]:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    cached_task = summary_store.get_cached_task(payload.url, language=payload.language)
    seed_result = None
    if cached_task is not None:
        if not payload.force:
            return {
                "summary_id": cached_task.id,
                "cache_hit": True,
                "status": cached_task.status,
            }
        if cached_task.status == "completed" and cached_task.result:
            seed_result = cached_task.result

    task = summary_store.create_task(payload.url, title=payload.title, language=payload.language)
    worker = threading.Thread(target=_run_summary, args=(task.id, payload, seed_result), daemon=True)
    worker.start()
    return {"summary_id": task.id, "cache_hit": False, "status": task.status}


@router.get("/{summary_id}")
def get_summary(summary_id: str) -> dict:
    task = summary_store.get_task(summary_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Summary task not found")
    return task.as_dict()


@router.post("/{summary_id}/questions")
def ask_summary_question(summary_id: str, payload: SummaryQuestionRequest) -> dict[str, str]:
    task = summary_store.get_task(summary_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Summary task not found")
    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=409, detail="Summary task is not completed")
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    transcript = _transcript_from_result(task.result)
    answer = get_summary_service().answer_question(
        title=task.title or "未命名视频",
        transcript=transcript,
        summary=task.result,
        question=question,
        language=payload.language,
    )
    return {"answer": answer}


@router.get("/{summary_id}/events")
async def summary_events(summary_id: str) -> StreamingResponse:
    async def event_stream():
        last_payload = None
        while True:
            task = summary_store.get_task(summary_id)
            if task is None:
                yield "event: error\ndata: {\"error\":\"Summary task not found\"}\n\n"
                break
            payload = json.dumps(task.as_dict(), ensure_ascii=False)
            if payload != last_payload:
                yield f"event: summary\ndata: {payload}\n\n"
                last_payload = payload
            if task.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{summary_id}/markdown")
def download_summary_markdown(summary_id: str) -> FileResponse:
    path = summary_store.resolve_markdown(summary_id)
    if path is None or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Summary markdown not found")
    return FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")


def _transcript_from_result(result: dict) -> str:
    transcript = result.get("transcript_text")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()
    segments = result.get("transcript_segments")
    if isinstance(segments, list):
        lines = []
        for item in segments:
            if not isinstance(item, dict):
                continue
            time = item.get("time") or "时间未知"
            text = item.get("text") or ""
            if text:
                lines.append(f"[{time}] {text}")
        if lines:
            return "\n".join(lines)
    return ""
