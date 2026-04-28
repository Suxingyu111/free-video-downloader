from __future__ import annotations

import asyncio
import json
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.asset_store import asset_store
from app.services.cookie_store import CookieStore
from app.services.runtime_cleanup import cleanup_failed_download
from app.services.runtime_cleanup import prune_download_directories
from app.services.task_store import task_store
from app.services.ytdlp_service import DEFAULT_FORMAT, DEFAULT_HTTP_HEADERS, YtDlpService, friendly_error_message


PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_DIR / "runtime"
DOWNLOAD_DIR = RUNTIME_DIR / "downloads"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
MAX_COMPLETED_DOWNLOADS = 5


@asynccontextmanager
async def lifespan(_: FastAPI):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    prune_download_directories(DOWNLOAD_DIR, keep_completed=MAX_COMPLETED_DOWNLOADS)
    yield
    tmp_dir = RUNTIME_DIR / "tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)


app = FastAPI(title="Free Video Downloader", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

service = YtDlpService()
cookie_store = CookieStore(RUNTIME_DIR / "tmp" / "cookies")


def _is_transient_youtube_bot_check(exc: Exception) -> bool:
    text = str(exc)
    return "[youtube]" in text and "Sign in to confirm" in text


class DownloadRequest(BaseModel):
    url: str
    entry_ids: list[str] = Field(default_factory=list)
    format_id: str = DEFAULT_FORMAT
    subtitle_langs: list[str] = Field(default_factory=list)
    write_auto_subs: bool = False
    prefer_srt: bool = True
    cookie_ref: str | None = None


def _asset_proxy_url(url: str | None, referer: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return url
    token = asset_store.register(url, referer=referer)
    return f"/api/proxy/assets/{token}"


def proxy_media_assets(result: dict) -> dict:
    webpage_url = result.get("webpage_url")
    result["thumbnail"] = _asset_proxy_url(result.get("thumbnail"), webpage_url)
    for entry in result.get("entries") or []:
        entry["thumbnail"] = _asset_proxy_url(
            entry.get("thumbnail"),
            entry.get("url") or webpage_url,
        )
    return result


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "free-video-downloader"}


@app.post("/api/analyze")
async def analyze(
    url: str = Form(...),
    cookies_file: UploadFile | None = File(default=None),
) -> dict:
    cookie_path: Path | None = None
    try:
        if cookies_file is not None:
            cookie_ref = cookie_store.save(await cookies_file.read())
            cookie_path = cookie_store.pop(cookie_ref)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = service.analyze(url, cookie_path)
                break
            except Exception as exc:
                last_error = exc
                if not _is_transient_youtube_bot_check(exc) or attempt == 2:
                    raise
                await asyncio.sleep(1)
        else:
            raise last_error or RuntimeError("Analyze failed")
        result = proxy_media_assets(result)
        if cookies_file is not None and cookie_path is not None:
            result["cookie_ref"] = cookie_store.save(cookie_path.read_bytes())
        return result
    except Exception as exc:  # yt-dlp raises many extractor-specific errors.
        raise HTTPException(status_code=400, detail=friendly_error_message(exc)) from exc
    finally:
        if cookie_path:
            cookie_path.unlink(missing_ok=True)


def _run_download(task_id: str, payload: DownloadRequest) -> None:
    task_dir = DOWNLOAD_DIR / task_id
    cookie_path = cookie_store.pop(payload.cookie_ref)

    def progress_hook(status: dict) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            downloaded = status.get("downloaded_bytes") or 0
            progress = round(downloaded / total * 100, 2) if total else 0.0
            task_store.update_task(
                task_id,
                status="downloading",
                progress=progress,
                message=status.get("_default_template") or "Downloading media",
                speed=status.get("speed"),
                eta=status.get("eta"),
            )
        elif status.get("status") == "finished":
            task_store.update_task(
                task_id,
                status="processing",
                progress=95.0,
                message="Processing downloaded file",
            )

    try:
        task_store.update_task(task_id, status="downloading", progress=1.0, message="Starting download")
        output_file = service.download(
            url=payload.url,
            output_dir=task_dir,
            format_id=payload.format_id,
            subtitle_langs=payload.subtitle_langs,
            write_auto_subs=payload.write_auto_subs,
            prefer_srt=payload.prefer_srt,
            cookie_file=cookie_path,
            progress_hook=progress_hook,
            entry_ids=payload.entry_ids,
        )
        token = task_store.register_file(output_file)
        task_store.update_task(
            task_id,
            status="completed",
            progress=100.0,
            message="Download complete",
            download_url=f"/files/{token}",
        )
        prune_download_directories(
            DOWNLOAD_DIR,
            keep_completed=MAX_COMPLETED_DOWNLOADS,
            exclude_task_ids=task_store.active_task_ids(),
        )
    except Exception as exc:
        task_store.update_task(
            task_id,
            status="failed",
            progress=0.0,
            message="Download failed",
            error=friendly_error_message(exc),
        )
        cleanup_failed_download(task_dir)
    finally:
        if cookie_path:
            cookie_path.unlink(missing_ok=True)


@app.post("/api/download")
def create_download(payload: DownloadRequest) -> dict[str, str]:
    task = task_store.create_task(payload.url)
    worker = threading.Thread(target=_run_download, args=(task.id, payload), daemon=True)
    worker.start()
    return {"task_id": task.id}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.as_dict()


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str) -> StreamingResponse:
    async def event_stream():
        last_payload = None
        while True:
            task = task_store.get_task(task_id)
            if task is None:
                yield "event: error\ndata: {\"error\":\"Task not found\"}\n\n"
                break
            payload = json.dumps(task.as_dict(), ensure_ascii=False)
            if payload != last_payload:
                yield f"event: task\ndata: {payload}\n\n"
                last_payload = payload
            if task.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/proxy/assets/{token}")
async def proxy_asset(token: str) -> Response:
    asset = asset_store.resolve(token)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    headers = {
        **DEFAULT_HTTP_HEADERS,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    if asset.referer:
        headers["Referer"] = asset.referer

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            upstream = await client.get(asset.url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to proxy remote asset: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Remote asset request failed with status {upstream.status_code}",
        )

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/files/{token}")
def download_file(token: str) -> FileResponse:
    path = task_store.resolve_file(token)
    if path is None or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=path.name)
