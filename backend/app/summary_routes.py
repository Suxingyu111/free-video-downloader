from __future__ import annotations

import asyncio
import json
import math
import secrets
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import auth_routes
from app.auth_routes import current_user
from app.services.auth_service import User
from app.services.analysis_store import analysis_store
from app.services.entitlements import (
    QuotaExceeded,
    get_usage_summary,
    refund_summary_quota_reservation,
    reserve_summary_quota,
)
from app.services.summary_service import SummaryService
from app.services.summary_store import SummaryStore, summary_store
from app.services.transcript_service import DEFAULT_SUBTITLE_LANGUAGES
from app.services.usage_meter import (
    MeterExceeded,
    MeterType,
    assert_duration_allowed,
    refund_reservation,
    reserve_user_meter,
    reserve_user_meter_by_id,
)
from app.services.ytdlp_service import friendly_error_message


SUMMARY_DIR = summary_store.base_dir
SUMMARY_SUBTITLE_LANGUAGE_SET = {language.lower() for language in DEFAULT_SUBTITLE_LANGUAGES}
SUMMARY_SUBTITLE_FORMATS = {"srt", "vtt"}

router = APIRouter(prefix="/api/summaries", tags=["summaries"])
summary_service: SummaryService | None = None
QUESTION_QUOTA_EXCEEDED_MESSAGE = "本月 AI 问答次数已用完，请下月继续使用或升级套餐。"


class SummaryRequest(BaseModel):
    url: str
    title: str | None = None
    language: str = "zh-CN"
    force: bool = False
    duration: float | None = None
    analysis_token: str | None = None


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


def _summary_task_payload(task, user: User) -> dict:
    payload = task.as_dict()
    payload["usage"] = get_usage_summary(user).as_dict()
    return payload


def _run_summary(
    summary_id: str,
    payload: SummaryRequest,
    seed_result: dict | None = None,
    quota_user_id: str | None = None,
    initial_transcription_reservation_id: str | None = None,
    initial_transcription_minutes: int = 0,
    store: SummaryStore | None = None,
    summary_dir=None,
    service: SummaryService | None = None,
) -> None:
    store = store or summary_store
    summary_dir = summary_dir or SUMMARY_DIR
    service = service or get_summary_service()
    output_dir = summary_dir / summary_id
    transcription_reservation_ids = [initial_transcription_reservation_id] if initial_transcription_reservation_id else []
    transcription_reserved_minutes = {"value": initial_transcription_minutes if initial_transcription_reservation_id else 0}

    def refund_transcription_reservations() -> None:
        while transcription_reservation_ids:
            reservation_id = transcription_reservation_ids.pop()
            if not reservation_id:
                continue
            try:
                refund_reservation(reservation_id)
            except Exception:
                pass

    def progress_hook(stage: str, progress: float, message: str, **changes: object) -> None:
        status = "transcribing" if stage in {"subtitle", "speech_to_text"} else "summarizing"
        transcription_seconds = changes.pop("transcription_seconds", None)
        if transcription_seconds is not None and quota_user_id:
            minutes = _transcription_minutes_from_seconds(transcription_seconds)
            if minutes is not None:
                extra_minutes = minutes - transcription_reserved_minutes["value"]
                if extra_minutes > 0:
                    reservation_id = (
                        f"{summary_id}_transcription"
                        if not transcription_reservation_ids
                        else f"{summary_id}_transcription_extra"
                    )
                    reserve_user_meter_by_id(
                        quota_user_id,
                        MeterType.TRANSCRIPTION_MINUTES,
                        extra_minutes,
                        reservation_id=reservation_id,
                    )
                    transcription_reservation_ids.append(reservation_id)
                    transcription_reserved_minutes["value"] += extra_minutes
        store.update_task(
            summary_id,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            **changes,
        )

    try:
        store.update_task(summary_id, status="transcribing", stage="subtitle", progress=5, message="Preparing subtitles")
        result, markdown_path = service.generate_summary(
            url=payload.url,
            title=payload.title,
            language=payload.language,
            output_dir=output_dir,
            progress_hook=progress_hook,
            seed_result=seed_result,
        )
        if (
            initial_transcription_reservation_id
            and result.get("transcript_source") != "speech_to_text"
        ):
            refund_transcription_reservations()
        store.complete_task(summary_id, result=result, markdown_path=markdown_path)
    except Exception as exc:
        refund_transcription_reservations()
        if quota_user_id:
            try:
                refund_summary_quota_reservation(summary_id)
                store.mark_quota_refunded(summary_id)
            except Exception:
                pass
        store.fail_task(summary_id, _friendly_summary_error(exc))


def _transcription_minutes_from_seconds(transcription_seconds: object) -> int | None:
    try:
        seconds = float(transcription_seconds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds):
        return None
    return max(1, math.ceil(seconds / 60))


def get_summary_service() -> SummaryService:
    global summary_service
    if summary_service is None:
        summary_service = SummaryService()
    return summary_service


def _numeric_duration(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value)


def _analysis_snapshot_matches(snapshot, url: str) -> bool:
    return snapshot.url == url or snapshot.result.get("webpage_url") == url


def _summary_analysis_snapshot(payload: SummaryRequest):
    token_snapshot = analysis_store.get(payload.analysis_token)
    if token_snapshot is not None and _analysis_snapshot_matches(token_snapshot, payload.url):
        return token_snapshot
    return analysis_store.find_by_url(payload.url)


def _summary_analysis_context(
    payload: SummaryRequest,
    seed_result: dict | None,
) -> tuple[bool, float | None, dict | None]:
    if seed_result is not None:
        duration = _numeric_duration(seed_result.get("duration"))
        return True, duration, seed_result
    snapshot = _summary_analysis_snapshot(payload)
    if snapshot is None:
        return False, None, None
    return True, _numeric_duration(snapshot.result.get("duration")), snapshot.result


def _has_reusable_transcript(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if str(result.get("transcript_text") or "").strip():
        return True
    segments = result.get("transcript_segments")
    return isinstance(segments, list) and any(
        isinstance(item, dict) and str(item.get("text") or "").strip()
        for item in segments
    )


def _summary_needs_transcription_preflight(analysis_result: dict | None) -> bool:
    if not isinstance(analysis_result, dict) or _has_reusable_transcript(analysis_result):
        return False
    subtitles = analysis_result.get("subtitles")
    if not isinstance(subtitles, list):
        return False
    return not any(_is_usable_summary_subtitle(item) for item in subtitles)


def _is_usable_summary_subtitle(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    ext = str(item.get("ext") or "").strip().lower()
    if ext not in SUMMARY_SUBTITLE_FORMATS:
        return False
    lang = str(item.get("lang") or "").strip().lower()
    if not lang:
        return False
    lang_base = lang.split("-", 1)[0]
    return lang in SUMMARY_SUBTITLE_LANGUAGE_SET or lang_base in SUMMARY_SUBTITLE_LANGUAGE_SET


def _reserve_transcription_quota_for_summary(
    user: User,
    summary_id: str,
    duration_seconds: float | None,
) -> tuple[str, int] | None:
    minutes = _transcription_minutes_from_seconds(duration_seconds)
    if minutes is None:
        return None
    reservation_id = f"{summary_id}_transcription"
    reserve_user_meter(
        user,
        MeterType.TRANSCRIPTION_MINUTES,
        minutes,
        reservation_id=reservation_id,
    )
    return reservation_id, minutes


@router.post("")
def create_summary(payload: SummaryRequest, request: Request, user: User = Depends(current_user)) -> dict[str, object]:
    _assert_summary_session_csrf(request)
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
    has_analysis_snapshot, duration, analysis_result = _summary_analysis_context(payload, seed_result)
    if not has_analysis_snapshot:
        raise HTTPException(status_code=400, detail="请先解析视频后再生成 AI 总结。")
    try:
        assert_duration_allowed(user, capability="summary", duration_seconds=duration)
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    transcription_reservation_id = None
    transcription_reserved_minutes = 0
    try:
        usage = reserve_summary_quota(user, summary_id)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    try:
        if _summary_needs_transcription_preflight(analysis_result):
            transcription_reservation = _reserve_transcription_quota_for_summary(
                user,
                summary_id,
                duration,
            )
            if transcription_reservation:
                transcription_reservation_id, transcription_reserved_minutes = transcription_reservation
                usage = get_usage_summary(user)
    except MeterExceeded as exc:
        try:
            refund_summary_quota_reservation(summary_id)
        except Exception:
            pass
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    quota_user_id = user.id
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
        summary_seed_result = seed_result or analysis_result
        worker = threading.Thread(
            target=_run_summary,
            args=(
                task.id,
                payload,
                summary_seed_result,
                user.id,
                transcription_reservation_id,
                transcription_reserved_minutes,
                summary_store,
                SUMMARY_DIR,
                get_summary_service(),
            ),
            daemon=True,
        )
        worker.start()
    except Exception as exc:
        if transcription_reservation_id:
            try:
                refund_reservation(transcription_reservation_id)
            except Exception:
                pass
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
        for reservation_id in (f"{task.id}_transcription", f"{task.id}_transcription_extra"):
            try:
                refund_reservation(reservation_id)
            except Exception:
                pass
        try:
            refund_summary_quota_reservation(task.id)
            summary_store.mark_quota_refunded(task.id)
        except Exception:
            continue


@router.get("/{summary_id}")
def get_summary(summary_id: str, user: User = Depends(current_user)) -> dict:
    task = _get_owned_summary_task(summary_id, user)
    return _summary_task_payload(task, user)


@router.post("/{summary_id}/questions")
def ask_summary_question(
    summary_id: str,
    payload: SummaryQuestionRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, object]:
    _assert_summary_session_csrf(request)
    task = _get_owned_summary_task(summary_id, user)
    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=409, detail="Summary task is not completed")
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    reservation_id = f"question_{summary_id}_{secrets.token_urlsafe(8)}"
    try:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=reservation_id,
        )
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=QUESTION_QUOTA_EXCEEDED_MESSAGE) from exc
    transcript = _transcript_from_result(task.result)
    try:
        answer = get_summary_service().answer_question(
            title=task.title or "未命名视频",
            transcript=transcript,
            summary=task.result,
            question=question,
            language=payload.language,
        )
    except Exception as exc:
        try:
            refund_reservation(reservation_id)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=_friendly_summary_error(exc)) from exc
    usage = get_usage_summary(user)
    return {"answer": answer, "usage": usage.as_dict()}


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
            payload = json.dumps(_summary_task_payload(task, user), ensure_ascii=False)
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
