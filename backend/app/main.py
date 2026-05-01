from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth_routes import router as auth_router
from app.services.asset_store import asset_store
from app.services.database import initialize_database
from app.services.geo_monitor import append_geo_access_log
from app.services.geo_monitor import build_geo_access_record
from app.services.geo_monitor import should_log_geo_access
from app.services.runtime_cleanup import cleanup_failed_download
from app.services.runtime_cleanup import prune_download_directories
from app.services.task_store import task_store
from app.services.ytdlp_service import DEFAULT_FORMAT, DEFAULT_HTTP_HEADERS, YtDlpService, friendly_error_message
from app.summary_routes import router as summary_router


PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_DIR / "runtime"
DOWNLOAD_DIR = RUNTIME_DIR / "downloads"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
GEO_ACCESS_LOG = RUNTIME_DIR / "geo-access.jsonl"
MAX_COMPLETED_DOWNLOADS = 5
FRONTEND_HTML_CACHE_CONTROL = "no-cache"
FRONTEND_STATIC_CACHE_CONTROL = "public, max-age=31536000, immutable"
FRONTEND_DISCOVERY_CACHE_CONTROL = "public, max-age=300"
CANONICAL_REDIRECT_ENV_VALUES = {"1", "true", "yes", "on"}
FRONTEND_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".svg": "image/svg+xml",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
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

app.include_router(summary_router)
app.include_router(auth_router)

service = YtDlpService()


@app.middleware("http")
async def geo_access_monitor(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    user_agent = request.headers.get("user-agent")
    if should_log_geo_access(request.method, path, response.status_code, user_agent):
        record = build_geo_access_record(request.method, path, response.status_code, user_agent)
        try:
            append_geo_access_log(GEO_ACCESS_LOG, record)
        except OSError:
            pass
    return response


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


def _frontend_media_type(path: Path) -> str | None:
    return FRONTEND_MEDIA_TYPES.get(path.suffix.lower())


def _frontend_cache_control(path: Path) -> str:
    suffix = path.suffix.lower()
    if "assets" in path.parts:
        return FRONTEND_STATIC_CACHE_CONTROL
    if suffix == ".html":
        return FRONTEND_HTML_CACHE_CONTROL
    if suffix in {".md", ".txt", ".xml"}:
        return FRONTEND_DISCOVERY_CACHE_CONTROL
    return "public, max-age=86400"


def _canonical_site_origin() -> str | None:
    site_url = (os.getenv("PUBLIC_SITE_URL") or os.getenv("VITE_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if not site_url:
        return None
    parsed = urlsplit(site_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _frontend_canonical_redirect_url(request: Request) -> str | None:
    if os.getenv("SEO_CANONICAL_REDIRECTS", "").strip().lower() not in CANONICAL_REDIRECT_ENV_VALUES:
        return None
    if request.method not in {"GET", "HEAD"}:
        return None
    if request.url.path == "/api" or request.url.path.startswith(("/api/", "/files/")):
        return None

    canonical_origin = _canonical_site_origin()
    if not canonical_origin:
        return None

    canonical = urlsplit(canonical_origin)
    current_scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    current_host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    if current_scheme == canonical.scheme and current_host == canonical.netloc:
        return None
    return urlunsplit((canonical.scheme, canonical.netloc, request.url.path, request.url.query, ""))


@app.middleware("http")
async def add_frontend_cache_headers(request: Request, call_next):
    canonical_redirect_url = _frontend_canonical_redirect_url(request)
    if canonical_redirect_url:
        return RedirectResponse(canonical_redirect_url, status_code=308)

    response = await call_next(request)
    if response.status_code == 200 and request.url.path.startswith("/assets/"):
        response.headers.setdefault("Cache-Control", FRONTEND_STATIC_CACHE_CONTROL)
        response.headers.setdefault("Vary", "Accept-Encoding")
    return response


def _resolve_frontend_file(asset_path: str) -> Path | None:
    if not FRONTEND_DIST.exists():
        return None

    root = FRONTEND_DIST.resolve()
    normalized = asset_path.strip("/")
    if not normalized:
        index_file = root / "index.html"
        return index_file if index_file.is_file() else None

    requested = (root / normalized).resolve()
    try:
        requested.relative_to(root)
    except ValueError:
        return None

    if requested.is_file():
        return requested

    if requested.is_dir():
        index_file = requested / "index.html"
        if index_file.is_file():
            return index_file

    directory_index = requested / "index.html"
    if directory_index.is_file():
        return directory_index

    return None


def _frontend_directory_needs_slash(asset_path: str) -> bool:
    if not FRONTEND_DIST.exists() or not asset_path or asset_path.endswith("/"):
        return False
    normalized = asset_path.strip("/")
    if Path(normalized).suffix:
        return False
    root = FRONTEND_DIST.resolve()
    requested = (root / normalized).resolve()
    try:
        requested.relative_to(root)
    except ValueError:
        return False
    return requested.is_dir() and (requested / "index.html").is_file()


def _frontend_file_response(path: Path, status_code: int = 200) -> FileResponse:
    return FileResponse(
        path,
        status_code=status_code,
        media_type=_frontend_media_type(path),
        filename=None,
        headers={"Cache-Control": _frontend_cache_control(path)},
    )


def _frontend_not_found_response() -> FileResponse | None:
    not_found = FRONTEND_DIST / "404.html"
    if not_found.is_file():
        return _frontend_file_response(not_found, status_code=404)
    return None


def demo_analyze_result(url: str) -> dict | None:
    demo_enabled = os.getenv("SAVEANY_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    if demo_enabled and url.startswith("https://demo.saveany.local/"):
        return {
            "kind": "video",
            "id": "demo-ai-summary",
            "title": "AI 视频总结演示课",
            "webpage_url": url,
            "thumbnail": None,
            "duration": 618,
            "extractor": "demo",
            "formats": [],
            "subtitles": [{"lang": "zh-CN", "ext": "vtt", "name": "中文演示字幕", "automatic": False}],
            "entries": [],
        }
    return None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "free-video-downloader"}


@app.post("/api/analyze")
async def analyze(
    url: str = Form(...),
) -> dict:
    try:
        demo_result = demo_analyze_result(url)
        if demo_result is not None:
            return demo_result
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = await asyncio.to_thread(service.analyze, url)
                break
            except Exception as exc:
                last_error = exc
                if not _is_transient_youtube_bot_check(exc) or attempt == 2:
                    raise
                await asyncio.sleep(1)
        else:
            raise last_error or RuntimeError("Analyze failed")
        result = proxy_media_assets(result)
        return result
    except Exception as exc:  # yt-dlp raises many extractor-specific errors.
        raise HTTPException(status_code=400, detail=friendly_error_message(exc)) from exc


def _run_download(task_id: str, payload: DownloadRequest) -> None:
    task_dir = DOWNLOAD_DIR / task_id

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


@app.get("/{frontend_path:path}", include_in_schema=False)
def serve_frontend(frontend_path: str, request: Request) -> Response:
    if _frontend_directory_needs_slash(frontend_path):
        return RedirectResponse(str(request.url.replace(path=f"{request.url.path}/")), status_code=308)

    path = _resolve_frontend_file(frontend_path)
    if path is None:
        not_found = _frontend_not_found_response()
        if not_found is not None:
            return not_found
        raise HTTPException(status_code=404, detail="Frontend asset not found")
    return _frontend_file_response(path)
