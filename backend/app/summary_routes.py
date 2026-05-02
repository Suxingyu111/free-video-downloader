from __future__ import annotations

import asyncio
import json
import secrets
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import auth_routes
from app.auth_routes import current_user
from app.services.auth_service import User
from app.services.entitlements import (
    QuotaExceeded,
    get_usage_summary,
    refund_summary_quota_reservation,
    reserve_summary_quota,
)
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


def _assert_summary_session_csrf(request: Request) -> None:
    assert_session_csrf = getattr(auth_routes, "assert_session_csrf", auth_routes._assert_session_csrf)
    assert_session_csrf(request)


def _get_owned_summary_task(summary_id: str, user: User):
    task = summary_store.get_task(summary_id)
    if task is None or task.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Summary task not found")
    return task


def _run_summary(
    summary_id: str,
    payload: SummaryRequest,
    seed_result: dict | None = None,
    refund_on_failure: bool = False,
) -> None:
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
        if refund_on_failure:
            try:
                refund_summary_quota_reservation(summary_id)
                summary_store.mark_quota_refunded(summary_id)
            except Exception:
                pass
        summary_store.fail_task(summary_id, _friendly_summary_error(exc))


def get_summary_service() -> SummaryService:
    global summary_service
    if summary_service is None:
        summary_service = SummaryService()
    return summary_service


@router.post("")
def create_summary(payload: SummaryRequest, user: User = Depends(current_user)) -> dict[str, object]:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    cached_task = summary_store.get_cached_task(payload.url, language=payload.language, owner_user_id=user.id)
    seed_result = None
    if cached_task is not None:
        if cached_task.owner_user_id != user.id:
            cloned_task = summary_store.clone_completed_task_for_owner(cached_task.id, user.id)
            if cloned_task is None:
                raise HTTPException(status_code=404, detail="Summary task not found")
            cached_task = cloned_task
            usage = get_usage_summary(user)
            return {
                "summary_id": cached_task.id,
                "cache_hit": True,
                "status": cached_task.status,
                "usage": usage.as_dict(),
            }
        if not payload.force:
            usage = get_usage_summary(user)
            return {
                "summary_id": cached_task.id,
                "cache_hit": True,
                "status": cached_task.status,
                "usage": usage.as_dict(),
            }
        if cached_task.status == "completed" and cached_task.result:
            seed_result = cached_task.result

    summary_id = f"summary_{secrets.token_urlsafe(10)}"
    try:
        usage = reserve_summary_quota(user, summary_id)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    quota_user_id = None if usage.membership_active else user.id
    task = None
    try:
        task = summary_store.create_task(
            payload.url,
            title=payload.title,
            language=payload.language,
            owner_user_id=user.id,
            quota_user_id=quota_user_id,
            task_id=summary_id,
        )
        worker = threading.Thread(
            target=_run_summary,
            args=(task.id, payload, seed_result, quota_user_id is not None),
            daemon=True,
        )
        worker.start()
    except Exception as exc:
        if quota_user_id is not None:
            try:
                refund_summary_quota_reservation(summary_id)
                summary_store.mark_quota_refunded(summary_id)
            except Exception:
                pass
        if task is not None:
            summary_store.fail_task(task.id, "AI 总结任务创建失败，请稍后重试。")
        raise HTTPException(status_code=500, detail="AI 总结任务创建失败，请稍后重试。") from exc
    return {"summary_id": task.id, "cache_hit": False, "status": task.status, "usage": usage.as_dict()}


def refund_interrupted_summary_quotas() -> None:
    for task in summary_store.pending_quota_refunds():
        if not task.quota_user_id:
            continue
        try:
            refund_summary_quota_reservation(task.id)
            summary_store.mark_quota_refunded(task.id)
        except Exception:
            continue


@router.get("/{summary_id}")
def get_summary(summary_id: str, user: User = Depends(current_user)) -> dict:
    task = _get_owned_summary_task(summary_id, user)
    return task.as_dict()


@router.post("/{summary_id}/questions")
def ask_summary_question(
    summary_id: str,
    payload: SummaryQuestionRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, str]:
    _assert_summary_session_csrf(request)
    task = _get_owned_summary_task(summary_id, user)
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
async def summary_events(summary_id: str, user: User = Depends(current_user)) -> StreamingResponse:
    _get_owned_summary_task(summary_id, user)

    async def event_stream():
        last_payload = None
        while True:
            task = summary_store.get_task(summary_id)
            if task is None or task.owner_user_id != user.id:
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
def download_summary_markdown(summary_id: str, user: User = Depends(current_user)) -> FileResponse:
    _get_owned_summary_task(summary_id, user)
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
