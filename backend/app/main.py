from __future__ import annotations

import asyncio
import ipaddress
import json
import secrets
import shutil
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth_routes import optional_user
from app.auth_routes import router as auth_router
from app.billing_routes import router as billing_router
from app.entitlement_routes import router as entitlement_router
from app.services.analysis_store import AnalysisSnapshot, analysis_store
from app.services.asset_store import asset_store
from app.services.auth_service import User
from app.services.client_ip import client_ip_from_request
from app.services.database import initialize_database
from app.services.env_file import bool_env_enabled, env_value
from app.services.geo_monitor import append_geo_access_log
from app.services.geo_monitor import build_geo_access_record
from app.services.geo_monitor import should_log_geo_access
from app.services.plan_catalog import MeterType
from app.services.runtime_cleanup import cleanup_failed_download
from app.services.runtime_cleanup import prune_download_directories
from app.services.task_store import task_store
from app.services.usage_meter import (
    MeterExceeded,
    assert_duration_allowed,
    consume_anonymous_meter,
    refund_anonymous_meter,
    refund_reservation,
    reserve_user_meter,
)
from app.services.ytdlp_service import DEFAULT_FORMAT, DEFAULT_HTTP_HEADERS, YtDlpService, friendly_error_message
from app.summary_routes import refund_interrupted_summary_quotas
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
PROXY_ASSET_MAX_BYTES = 5 * 1024 * 1024
PROXY_ASSET_MAX_REDIRECTS = 3
TRUSTED_PUBLIC_ASSET_HOST_SUFFIXES = (
    "hdslb.com",
    "ytimg.com",
    "img.youtube.com",
    "ggpht.com",
    "googleusercontent.com",
    "douyinpic.com",
    "douyinstatic.com",
    "byteimg.com",
    "pstatp.com",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "byteoversea.com",
    "ibytedtos.com",
    "muscdn.com",
    "ttwstatic.com",
    "cdninstagram.com",
    "fbcdn.net",
)
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
    refund_interrupted_summary_quotas()
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
app.include_router(billing_router)
app.include_router(entitlement_router)

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


def _client_ip(request: Request) -> str:
    return client_ip_from_request(request)


def _analysis_snapshot_matches(snapshot: AnalysisSnapshot, url: str) -> bool:
    return snapshot.url == url or snapshot.result.get("webpage_url") == url


def _download_duration_values(result: dict, payload: "DownloadRequest") -> list[object]:
    entries = result.get("entries")
    if isinstance(entries, list) and entries:
        if payload.entry_ids:
            selected_ids = {str(entry_id) for entry_id in payload.entry_ids}
            selected_entries = [
                entry
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("id") or "") in selected_ids
            ]
            if selected_entries:
                return [entry.get("duration") for entry in selected_entries]
        else:
            entry_durations = [
                entry.get("duration") for entry in entries if isinstance(entry, dict)
            ]
            if entry_durations:
                return entry_durations
    return [result.get("duration")]


class DownloadRequest(BaseModel):
    url: str
    analysis_token: str | None = None
    entry_ids: list[str] = Field(default_factory=list)
    format_id: str = DEFAULT_FORMAT
    subtitle_langs: list[str] = Field(default_factory=list)
    write_auto_subs: bool = False
    prefer_srt: bool = True


def _is_remote_asset_url(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _normalize_remote_asset_url(url: str | None) -> str | None:
    if not _is_remote_asset_url(url):
        return url
    parts = urlsplit(str(url))
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if parts.scheme == "http" and _is_trusted_public_asset_host(host):
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    return str(url)


def _asset_proxy_url(url: str | None, referer: str | None) -> str | None:
    normalized_url = _normalize_remote_asset_url(url)
    if not normalized_url:
        return None
    if not _is_remote_asset_url(normalized_url):
        return normalized_url
    token = asset_store.register(normalized_url, referer=referer)
    return f"/api/proxy/assets/{token}"


def proxy_media_assets(result: dict) -> dict:
    webpage_url = result.get("webpage_url")
    thumbnail = _normalize_remote_asset_url(result.get("thumbnail"))
    if _is_remote_asset_url(thumbnail):
        result["thumbnail_fallback_url"] = thumbnail
    result["thumbnail"] = _asset_proxy_url(thumbnail, webpage_url)
    for entry in result.get("entries") or []:
        entry_thumbnail = _normalize_remote_asset_url(entry.get("thumbnail"))
        if _is_remote_asset_url(entry_thumbnail):
            entry["thumbnail_fallback_url"] = entry_thumbnail
        entry["thumbnail"] = _asset_proxy_url(
            entry_thumbnail,
            entry.get("url") or webpage_url,
        )
    return result


def _asset_url_not_allowed() -> HTTPException:
    return HTTPException(status_code=400, detail="Remote asset URL is not allowed")


def _is_forbidden_proxy_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return not ip.is_global


def _is_trusted_public_asset_host(host: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in TRUSTED_PUBLIC_ASSET_HOST_SUFFIXES)


def _is_proxyable_resolved_address(host: str, address: str) -> bool:
    return _is_trusted_public_asset_host(host) or not _is_forbidden_proxy_ip(address)


def _assert_proxyable_asset_url(url: str) -> None:
    parts = urlsplit(str(url))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise _asset_url_not_allowed()

    host = parts.hostname.strip().lower().rstrip(".")
    if host == "localhost":
        raise _asset_url_not_allowed()

    try:
        ipaddress.ip_address(host)
    except ValueError:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise HTTPException(status_code=502, detail="Remote asset host could not be resolved") from exc
        if not infos:
            raise HTTPException(status_code=502, detail="Remote asset host could not be resolved")
        if any(not _is_proxyable_resolved_address(host, item[4][0]) for item in infos):
            raise _asset_url_not_allowed()
        return

    if not _is_proxyable_resolved_address(host, host):
        raise _asset_url_not_allowed()


def _asset_content_type_allowed(content_type: str | None) -> bool:
    if not content_type:
        return True
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type.startswith("image/")


def _asset_content_length(headers) -> int | None:
    try:
        value = headers.get("content-length")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    site_url = (env_value("PUBLIC_SITE_URL") or env_value("VITE_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if not site_url:
        return None
    parsed = urlsplit(site_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _frontend_canonical_redirect_url(request: Request) -> str | None:
    if env_value("SEO_CANONICAL_REDIRECTS").strip().lower() not in CANONICAL_REDIRECT_ENV_VALUES:
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
    if bool_env_enabled("SAVEANY_DEMO_MODE") and url.startswith("https://demo.saveany.local/"):
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


def demo_download_file(url: str, output_dir: Path) -> Path | None:
    if not bool_env_enabled("SAVEANY_DEMO_MODE") or not url.startswith("https://demo.saveany.local/"):
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "saveany-demo-video.mp4"
    output_file.write_bytes(
        b"SaveAny demo video placeholder for local QA. "
        b"This file is generated only when SAVEANY_DEMO_MODE is enabled.\n"
    )
    return output_file


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "free-video-downloader"}


@app.post("/api/analyze")
async def analyze(
    request: Request,
    url: str = Form(...),
    user: User | None = Depends(optional_user),
) -> dict:
    normalized_url = url.strip()
    if not normalized_url:
        raise HTTPException(status_code=400, detail="请输入视频链接")

    try:
        if user:
            reserve_user_meter(user, MeterType.ANALYZE, 1, reservation_id=f"analyze_{secrets.token_urlsafe(10)}")
        else:
            consume_anonymous_meter(_client_ip(request), MeterType.ANALYZE)
    except MeterExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        demo_result = demo_analyze_result(normalized_url)
        if demo_result is not None:
            result = proxy_media_assets(demo_result)
            result["analysis_token"] = analysis_store.create(normalized_url, result)
            return result
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = await asyncio.to_thread(service.analyze, normalized_url)
                break
            except Exception as exc:
                last_error = exc
                if not _is_transient_youtube_bot_check(exc) or attempt == 2:
                    raise
                await asyncio.sleep(1)
        else:
            raise last_error or RuntimeError("Analyze failed")
        result = proxy_media_assets(result)
        result["analysis_token"] = analysis_store.create(normalized_url, result)
        return result
    except Exception as exc:  # yt-dlp raises many extractor-specific errors.
        raise HTTPException(status_code=400, detail=friendly_error_message(exc)) from exc


def _refund_download_quota(
    *,
    reservation_id: str | None,
    anonymous_ip: str | None,
    amount: int,
) -> None:
    try:
        if reservation_id:
            refund_reservation(reservation_id)
        elif anonymous_ip and amount > 0:
            refund_anonymous_meter(anonymous_ip, MeterType.DOWNLOAD, amount=amount)
    except Exception:
        pass


def _run_download(
    task_id: str,
    payload: DownloadRequest,
    quota_reservation_id: str | None = None,
    anonymous_quota_ip: str | None = None,
    quota_amount: int = 0,
) -> None:
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
        output_file = demo_download_file(payload.url, task_dir)
        if output_file is None:
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
        _refund_download_quota(
            reservation_id=quota_reservation_id,
            anonymous_ip=anonymous_quota_ip,
            amount=quota_amount,
        )
        task_store.update_task(
            task_id,
            status="failed",
            progress=0.0,
            message="Download failed",
            error=friendly_error_message(exc),
        )
        cleanup_failed_download(task_dir)


@app.post("/api/download")
def create_download(
    payload: DownloadRequest,
    request: Request,
    user: User | None = Depends(optional_user),
) -> dict[str, str]:
    snapshot = analysis_store.get(payload.analysis_token)
    result = snapshot.result if snapshot and _analysis_snapshot_matches(snapshot, payload.url) else None
    if result is None:
        try:
            demo_result = demo_analyze_result(payload.url)
            result = demo_result if demo_result is not None else service.analyze(payload.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=friendly_error_message(exc)) from exc
    try:
        for duration in _download_duration_values(result, payload):
            assert_duration_allowed(user, capability="download", duration_seconds=duration)
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    entry_count = len(payload.entry_ids) if payload.entry_ids else max(len(result.get("entries") or []), 1)
    quota_reservation_id = None
    anonymous_quota_ip = None
    try:
        if user:
            quota_reservation_id = f"download_{secrets.token_urlsafe(10)}"
            reserve_user_meter(user, MeterType.DOWNLOAD, entry_count, reservation_id=quota_reservation_id)
        else:
            anonymous_quota_ip = _client_ip(request)
            consume_anonymous_meter(anonymous_quota_ip, MeterType.DOWNLOAD, amount=entry_count)
    except MeterExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        task = task_store.create_task(payload.url)
        worker = threading.Thread(
            target=_run_download,
            args=(task.id, payload, quota_reservation_id, anonymous_quota_ip, entry_count),
            daemon=True,
        )
        worker.start()
    except Exception as exc:
        _refund_download_quota(
            reservation_id=quota_reservation_id,
            anonymous_ip=anonymous_quota_ip,
            amount=entry_count,
        )
        raise HTTPException(status_code=500, detail="下载任务创建失败，请稍后重试。") from exc
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
        current_url = asset.url
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            for _ in range(PROXY_ASSET_MAX_REDIRECTS + 1):
                _assert_proxyable_asset_url(current_url)
                async with client.stream("GET", current_url, headers=headers) as upstream:
                    if upstream.status_code in {301, 302, 303, 307, 308}:
                        location = upstream.headers.get("location")
                        if not location:
                            raise HTTPException(status_code=502, detail="Remote asset redirect is missing location")
                        current_url = urljoin(current_url, location)
                        continue

                    if upstream.status_code >= 400:
                        raise HTTPException(
                            status_code=502,
                            detail=f"Remote asset request failed with status {upstream.status_code}",
                        )

                    content_type = upstream.headers.get("content-type", "application/octet-stream")
                    if not _asset_content_type_allowed(content_type):
                        raise HTTPException(status_code=502, detail="Remote asset content type is not allowed")

                    content_length = _asset_content_length(upstream.headers)
                    if content_length is not None and content_length > PROXY_ASSET_MAX_BYTES:
                        raise HTTPException(status_code=502, detail="Remote asset is too large")

                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in upstream.aiter_bytes():
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > PROXY_ASSET_MAX_BYTES:
                            raise HTTPException(status_code=502, detail="Remote asset is too large")
                        chunks.append(chunk)

                    return Response(
                        content=b"".join(chunks),
                        media_type=content_type,
                        headers={"Cache-Control": "private, max-age=3600"},
                    )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to proxy remote asset: {exc}") from exc

    raise HTTPException(status_code=502, detail="Remote asset redirected too many times")


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
