from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zipfile import ZIP_DEFLATED, ZipFile

from yt_dlp import YoutubeDL

from app.services.bilibili_public_metadata import fetch_bilibili_public_metadata
from app.services.bilibili_public_metadata import is_bilibili_url
from app.services.douyin_browser_service import is_douyin_url
from app.services.douyin_public_resolver import DOUYIN_PUBLIC_FAILURE_MESSAGE
from app.services.douyin_public_resolver import DouyinPublicResolver
from app.services.douyin_public_resolver import is_douyin_public_only_enabled


ProgressHook = Callable[[dict[str, Any]], None]

DEFAULT_FORMAT = (
    "18/"
    "bestvideo[ext=mp4][vcodec^=avc][height<=360]+bestaudio[ext=m4a]/"
    "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/"
    "best[ext=mp4][vcodec^=avc][height<=360]/best[height<=360]/best"
)
BILIBILI_DEFAULT_FORMAT = (
    "bestvideo[ext=mp4][vcodec^=avc][height<=720]+bestaudio[ext=m4a]/"
    "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/"
    "best[ext=mp4][vcodec^=avc][height<=720]/best[ext=mp4][vcodec^=avc]/best"
)
TIKTOK_DEFAULT_FORMAT = (
    "best[ext=mp4][vcodec=h264][acodec!=none]/"
    "best[ext=mp4][vcodec^=avc][acodec!=none]/"
    "bestvideo[ext=mp4][vcodec=h264]+bestaudio[ext=m4a]/"
    "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/"
    f"{DEFAULT_FORMAT}"
)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

TRACKING_QUERY_KEYS = {
    "spm_id_from",
    "vd_source",
    "from",
    "seid",
    "share_source",
}
INFO_METADATA_FIELDS = (
    "description",
    "uploader",
    "uploader_id",
    "channel",
    "channel_id",
    "timestamp",
    "upload_date",
    "view_count",
    "like_count",
    "favorite_count",
    "comment_count",
    "danmaku_count",
    "share_count",
    "tags",
    "categories",
)
BILIBILI_PUBLIC_ENRICH_FIELDS = (
    *INFO_METADATA_FIELDS,
    "subtitle_login_required",
    "bilibili",
)


def prepare_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def resolve_format_selector(url: str, format_id: str) -> str:
    hostname = urlsplit(url).netloc.lower()
    if format_id == DEFAULT_FORMAT and "bilibili.com" in hostname:
        return BILIBILI_DEFAULT_FORMAT
    if format_id == DEFAULT_FORMAT and "tiktok.com" in hostname:
        return TIKTOK_DEFAULT_FORMAT
    return format_id or DEFAULT_FORMAT


def build_http_headers(url: str) -> dict[str, str]:
    hostname = urlsplit(url).netloc.lower()
    headers = {
        **DEFAULT_HTTP_HEADERS,
        "Referer": url,
    }
    if "bilibili.com" in hostname:
        headers["Origin"] = "https://www.bilibili.com"
    return headers


def is_youtube_url(url: str) -> bool:
    hostname = urlsplit(url).netloc.lower()
    return "youtube.com" in hostname or "youtu.be" in hostname


def build_extractor_args(url: str) -> dict[str, dict[str, list[str]]]:
    if is_youtube_url(url):
        return {"youtube": {"player_client": ["android", "web"]}}
    return {}


def friendly_error_message(error: Exception | str) -> str:
    text = str(error)
    if "[BiliBili]" in text and "HTTP Error 412" in text:
        return (
            "Bilibili 返回 412 Precondition Failed，通常表示当前无登录态或请求被 B 站风控拦截。"
            "当前仅支持可直接访问的公开视频；如果仍失败，可能是 IP/地区/账号风控限制，"
            "请稍后重试或改用公开视频链接。"
        )
    if "[youtube]" in text and "Sign in to confirm" in text:
        return (
            "YouTube 要求登录验证，当前访客会话被判定需要确认不是机器人。"
            "当前仅支持可直接访问的公开视频；请稍后更换网络环境后重试，或改用公开视频链接。"
        )
    if "[Douyin]" in text and "Fresh cookies" in text:
        return DOUYIN_PUBLIC_FAILURE_MESSAGE
    if "Unsupported URL: https://www.douyin.com/" in text:
        return (
            "抖音短链已失效或被重定向到首页，无法从首页还原视频。"
            "请重新复制分享链接，或使用形如 https://www.douyin.com/video/视频ID 的永久地址后再试。"
        )
    return text


def _format_label(format_info: dict[str, Any]) -> str:
    ext = format_info.get("ext") or "media"
    if format_info.get("vcodec") == "none":
        return f"audio {ext}"
    height = format_info.get("height")
    if height:
        return f"{height}p {ext}"
    resolution = format_info.get("resolution")
    if resolution and resolution != "unknown":
        return f"{resolution} {ext}"
    return f"{format_info.get('format_id', 'best')} {ext}"


def _normalize_formats(formats: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = []
    for item in formats or []:
        format_id = item.get("format_id")
        if not format_id:
            continue
        normalized.append(
            {
                "format_id": str(format_id),
                "ext": item.get("ext"),
                "resolution": item.get("resolution"),
                "height": item.get("height"),
                "filesize": item.get("filesize") or item.get("filesize_approx"),
                "vcodec": item.get("vcodec"),
                "acodec": item.get("acodec"),
                "label": _format_label(item),
            }
        )
    return normalized


def _normalize_subtitle_group(
    subtitles: dict[str, list[dict[str, Any]]] | None, *, automatic: bool
) -> list[dict[str, Any]]:
    normalized = []
    for lang, tracks in (subtitles or {}).items():
        for track in tracks:
            item = {
                "lang": lang,
                "ext": track.get("ext"),
                "name": track.get("name") or lang,
                "automatic": automatic,
            }
            if isinstance(track.get("url"), str) and track.get("url"):
                item["url"] = track["url"]
            if isinstance(track.get("data"), str) and track.get("data"):
                item["data"] = track["data"]
            normalized.append(item)
    return normalized


def _normalize_entries(entries: list[dict[str, Any] | None] | None) -> list[dict[str, Any]]:
    normalized = []
    for entry in entries or []:
        if not entry:
            continue
        normalized.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title") or "Untitled video",
                "url": entry.get("webpage_url") or entry.get("url"),
                "duration": entry.get("duration"),
                "thumbnail": entry.get("thumbnail"),
            }
        )
    return normalized


def _metadata_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_info(info: dict[str, Any]) -> dict[str, Any]:
    kind = "playlist" if info.get("_type") == "playlist" else "video"
    return {
        "kind": kind,
        "id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "webpage_url": info.get("webpage_url"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "description": info.get("description") or "",
        "uploader": info.get("uploader") or info.get("channel"),
        "uploader_id": info.get("uploader_id") or info.get("channel_id"),
        "channel": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "timestamp": info.get("timestamp"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "favorite_count": info.get("favorite_count"),
        "comment_count": info.get("comment_count"),
        "tags": _metadata_list(info.get("tags")),
        "categories": _metadata_list(info.get("categories")),
        "extractor": info.get("extractor"),
        "formats": _normalize_formats(info.get("formats")),
        "subtitles": [
            *_normalize_subtitle_group(info.get("subtitles"), automatic=False),
            *_normalize_subtitle_group(info.get("automatic_captions"), automatic=True),
        ],
        "entries": _normalize_entries(info.get("entries")),
    }


def _metadata_missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def _with_bilibili_public_metadata(info: dict[str, Any], url: str) -> dict[str, Any]:
    try:
        public_info = fetch_bilibili_public_metadata(url)
    except Exception:
        return info

    enriched = dict(info)
    for field in BILIBILI_PUBLIC_ENRICH_FIELDS:
        if field not in public_info or _metadata_missing(public_info.get(field)):
            continue
        if _metadata_missing(enriched.get(field)):
            enriched[field] = public_info[field]
    return enriched


def build_download_options(
    *,
    url: str,
    output_dir: Path,
    format_id: str,
    subtitle_langs: list[str] | None,
    write_auto_subs: bool,
    prefer_srt: bool,
    progress_hook: ProgressHook | None,
    entry_ids: list[str] | None = None,
) -> dict[str, Any]:
    prepared_url = prepare_url(url)
    output_template = str(output_dir / "%(title).120s-%(id)s.%(ext)s")
    selected_ids = {entry_id for entry_id in entry_ids or [] if entry_id}
    options: dict[str, Any] = {
        "format": resolve_format_selector(prepared_url, format_id),
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "progress_hooks": [progress_hook] if progress_hook else [],
        "http_headers": build_http_headers(prepared_url),
        "continuedl": True,
        "file_access_retries": 3,
        "fragment_retries": 10,
        "retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
        "source_address": "0.0.0.0",
        "merge_output_format": "mp4",
        "js_runtimes": {"node": {}},
    }
    extractor_args = build_extractor_args(prepared_url)
    if extractor_args:
        options["extractor_args"] = extractor_args
    if not is_youtube_url(prepared_url):
        options["http_chunk_size"] = 1024 * 1024
    if selected_ids:
        options["match_filter"] = _build_entry_match_filter(selected_ids)
    if subtitle_langs:
        options.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": write_auto_subs,
                "subtitleslangs": subtitle_langs,
                "subtitlesformat": "srt/best" if prefer_srt else "best",
            }
        )
    return options


def _build_entry_match_filter(selected_ids: set[str]) -> Callable[[dict[str, Any]], str | None]:
    def match_filter(info: dict[str, Any]) -> str | None:
        entry_id = info.get("id")
        if entry_id is None or str(entry_id) in selected_ids:
            return None
        return "Entry was not selected"

    return match_filter


def is_retryable_youtube_download_error(error: Exception) -> bool:
    text = str(error)
    return ("HTTP Error 403" in text and "download video data" in text) or "Sign in to confirm" in text


def download_with_resumable_retries(
    *,
    options: dict[str, Any],
    prepared_url: str,
    max_attempts: int = 20,
) -> None:
    attempts = max(1, max_attempts if is_youtube_url(prepared_url) else 1)
    for attempt in range(attempts):
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([prepared_url])
            return
        except Exception as exc:
            if (
                attempt == attempts - 1
                or not is_youtube_url(prepared_url)
                or not is_retryable_youtube_download_error(exc)
            ):
                raise


def select_output_artifact(output_dir: Path, before: set[Path]) -> Path:
    created = [
        path
        for path in set(output_dir.glob("*")) - before
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if len(created) == 1:
        return created[0]
    if len(created) > 1:
        archive = output_dir / "download-artifacts.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
            for path in sorted(created, key=lambda item: item.name):
                if path != archive:
                    zip_file.write(path, arcname=path.name)
        return archive

    existing = [
        path
        for path in output_dir.glob("*")
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        archive = output_dir / "download-artifacts.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
            for path in sorted(existing, key=lambda item: item.name):
                if path != archive:
                    zip_file.write(path, arcname=path.name)
        return archive
    raise FileNotFoundError("Download finished but no output file was created.")


def validate_media_streams(streams: list[dict[str, Any]], *, suffix: str) -> str | None:
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        return "Downloaded file does not contain a video stream."
    if not audio_streams:
        return "Downloaded file does not contain an audio stream."
    if suffix.lower() == ".mp4":
        video_codecs = {stream.get("codec_name") for stream in video_streams}
        if "h264" not in video_codecs:
            return (
                "Downloaded MP4 does not contain H.264 video. "
                "Use the Reliable MP4 (H.264) format for playback-compatible output."
            )
    return None


def validate_media_file(path: Path) -> None:
    if path.suffix.lower() not in {".mp4", ".m4v", ".mov", ".webm", ".mkv"}:
        return
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required to verify downloaded media output.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Downloaded file could not be inspected: {exc.stderr.strip()}") from exc

    streams = json.loads(completed.stdout or "{}").get("streams") or []
    error = validate_media_streams(streams, suffix=path.suffix)
    if error:
        raise RuntimeError(error)


class YtDlpService:
    def __init__(self, douyin_service: DouyinPublicResolver | None = None) -> None:
        self.douyin_service = douyin_service or DouyinPublicResolver()

    def analyze(self, url: str) -> dict[str, Any]:
        prepared_url = prepare_url(url)
        if is_douyin_url(prepared_url) and is_douyin_public_only_enabled():
            return self.douyin_service.analyze(prepared_url)

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "http_headers": build_http_headers(prepared_url),
        }
        extractor_args = build_extractor_args(prepared_url)
        if extractor_args:
            options["extractor_args"] = extractor_args
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(prepared_url, download=False)
                normalized = normalize_info(ydl.sanitize_info(info))
                if is_bilibili_url(prepared_url):
                    return _with_bilibili_public_metadata(normalized, prepared_url)
                return normalized
        except Exception as exc:
            if not is_bilibili_url(prepared_url):
                raise
            try:
                return fetch_bilibili_public_metadata(prepared_url)
            except Exception:
                raise exc

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str = DEFAULT_FORMAT,
        subtitle_langs: list[str] | None = None,
        write_auto_subs: bool = False,
        prefer_srt: bool = True,
        progress_hook: ProgressHook | None = None,
        entry_ids: list[str] | None = None,
    ) -> Path:
        prepared_url = prepare_url(url)
        if is_douyin_url(prepared_url) and is_douyin_public_only_enabled():
            artifact = self.douyin_service.download(
                url=prepared_url,
                output_dir=output_dir,
                format_id=format_id,
                progress_hook=progress_hook,
            )
            validate_media_file(artifact)
            return artifact

        output_dir.mkdir(parents=True, exist_ok=True)
        options = build_download_options(
            url=prepared_url,
            output_dir=output_dir,
            format_id=format_id,
            subtitle_langs=subtitle_langs,
            write_auto_subs=write_auto_subs,
            prefer_srt=prefer_srt,
            progress_hook=progress_hook,
            entry_ids=entry_ids,
        )
        before = set(output_dir.glob("*"))
        download_with_resumable_retries(options=options, prepared_url=prepared_url)
        artifact = select_output_artifact(output_dir, before)
        validate_media_file(artifact)
        return artifact
