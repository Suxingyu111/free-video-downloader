from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Protocol

import httpx
from yt_dlp.utils import sanitize_filename

from app.services.douyin_browser_service import DOUYIN_DEFAULT_USER_AGENT
from app.services.douyin_browser_service import DouyinBrowserService
from app.services.douyin_browser_service import extract_douyin_aweme_id
from app.services.douyin_browser_service import select_douyin_format


DOUYIN_PUBLIC_FAILURE_MESSAGE = (
    "抖音公开视频解析失败。该视频可能是私密、登录限定、验证码拦截、地区限制、短链失效，"
    "或当前服务器网络触发了平台风控。请换一个公开视频链接后重试。"
)
DOUYINVD_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) "
    "AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 "
    "Chrome/87.0.4280.141 Mobile Safari/537.36"
)
DOUYINVD_VIDEO_PATTERN = re.compile(r'"video":\{"play_addr":\{"uri":"(?P<id>[a-z0-9]+)"')
DOUYINVD_DESC_PATTERN = re.compile(r'"desc":\s*"(?P<desc>[^"]+)"')
DOUYINVD_AWEME_PATTERN = re.compile(r'"aweme_id"\s*:\s*"(?P<id>[^"]+)"')
DOUYINVD_COVER_PATTERN = re.compile(r'"cover":\{"uri":"[^"]+","url_list":\["(?P<url>https:[^"]+)"')
DOUYINVD_PLAY_URL = "https://www.iesdouyin.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0"


class DouyinResolver(Protocol):
    def analyze(self, url: str) -> dict[str, Any]:
        ...

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str,
        progress_hook=None,
    ) -> Path:
        ...


def import_f2_douyin_handler():
    try:
        from f2.apps.douyin.handler import DouyinHandler
    except ImportError as exc:
        raise RuntimeError("F2 Douyin resolver is not installed. Install the `f2` Python package.") from exc
    return DouyinHandler


def _run_async(coro):
    return asyncio.run(coro)


def _first_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, str) and item), None)
    if isinstance(value, dict):
        urls = value.get("url_list") or value.get("urls") or []
        return _first_url(urls)
    return None


def _first_existing(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return None


def _duration_seconds(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return value / 1000 if value > 1000 else float(value)


def _parse_height(url_key: str | None) -> int | None:
    if not url_key:
        return None
    match = re.search(r"_(?P<height>\d+)p(?:_|$)", url_key)
    return int(match.group("height")) if match else None


def _format_without_url(format_info: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in format_info.items() if key != "url"}


def _normalize_public_formats(data: dict[str, Any]) -> list[dict[str, Any]]:
    formats: list[dict[str, Any]] = []
    play_url = _first_url(_first_existing(data, ["video_play_addr", "play_addr", "download_addr"]))
    if play_url:
        formats.append(
            {
                "format_id": "f2_play_addr",
                "url": play_url,
                "ext": "mp4",
                "resolution": None,
                "height": _first_existing(data, ["height", "video_height"]),
                "filesize": _first_existing(data, ["size", "filesize"]),
                "vcodec": "h264",
                "acodec": "aac",
                "preference": 30,
                "label": "F2 mp4",
            }
        )

    for index, item in enumerate(_first_existing(data, ["video_bit_rate", "bit_rate"]) or []):
        if not isinstance(item, dict):
            continue
        address = item.get("play_addr") or item.get("addr") or {}
        url = _first_url(address)
        if not url:
            continue
        url_key = address.get("url_key")
        height = _parse_height(url_key) or address.get("height") or item.get("height")
        format_id = item.get("gear_name") or url_key or f"f2_bitrate_{index}"
        formats.append(
            {
                "format_id": str(format_id),
                "url": url,
                "ext": "mp4",
                "resolution": None,
                "height": height,
                "filesize": address.get("data_size") or item.get("data_size"),
                "vcodec": "h265" if item.get("is_h265") else "h264",
                "acodec": "aac",
                "tbr": item.get("bit_rate"),
                "fps": item.get("FPS") or item.get("fps"),
                "preference": 10,
                "label": f"{height}p mp4" if height else "F2 mp4",
            }
        )

    seen = set()
    deduped = []
    for item in formats:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


def normalize_f2_detail(data: dict[str, Any], webpage_url: str) -> dict[str, Any]:
    cover = _first_url(_first_existing(data, ["cover", "video_cover", "dynamic_cover"]))
    formats = _normalize_public_formats(data)
    return {
        "kind": "video",
        "id": _first_existing(data, ["aweme_id", "id"]),
        "title": _first_existing(data, ["desc", "title"]) or "Untitled Douyin video",
        "webpage_url": webpage_url,
        "thumbnail": cover,
        "duration": _duration_seconds(_first_existing(data, ["duration", "video_duration"])),
        "extractor": "douyin:f2",
        "formats": [_format_without_url(item) for item in formats],
        "subtitles": [],
        "entries": [],
    }


def normalize_douyinvd_detail(data: dict[str, Any], webpage_url: str) -> dict[str, Any]:
    video_url = data.get("video_url")
    formats = []
    if video_url:
        formats.append(
            {
                "format_id": "douyinvd_video",
                "url": video_url,
                "ext": "mp4",
                "resolution": None,
                "height": None,
                "filesize": None,
                "vcodec": "h264",
                "acodec": "aac",
                "preference": 20,
                "label": "DouyinVd mp4",
            }
        )
    return {
        "kind": "video" if video_url else "gallery",
        "id": data.get("aweme_id"),
        "title": data.get("desc") or "Untitled Douyin video",
        "webpage_url": webpage_url,
        "thumbnail": (data.get("image_url_list") or [None])[0],
        "duration": None,
        "extractor": "douyin:douyinvd",
        "formats": [_format_without_url(item) for item in formats],
        "subtitles": [],
        "entries": [],
    }


def _select_public_format(formats: list[dict[str, Any]], format_id: str | None) -> dict[str, Any]:
    if not formats:
        raise RuntimeError("Douyin resolver returned no public video formats.")
    return select_douyin_format(formats, format_id)


def _stream_download(media_url: str, output_file: Path, *, referer: str, progress_hook=None) -> None:
    headers = {
        "User-Agent": DOUYIN_DEFAULT_USER_AGENT,
        "Referer": referer,
    }
    downloaded = 0
    with httpx.stream("GET", media_url, headers=headers, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or 0)
        with output_file.open("wb") as file:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                file.write(chunk)
                downloaded += len(chunk)
                if progress_hook:
                    progress_hook(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total,
                            "_default_template": "Downloading Douyin media",
                        }
                    )
    if progress_hook:
        progress_hook({"status": "finished"})


class F2DouyinService:
    def __init__(self, *, timeout: int | None = None) -> None:
        self.timeout = timeout or int(os.getenv("DOUYIN_F2_TIMEOUT_SECONDS", "15"))

    def analyze(self, url: str) -> dict[str, Any]:
        data = self.fetch_detail(url)
        return normalize_f2_detail(data, url)

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str,
        progress_hook=None,
    ) -> Path:
        data = self.fetch_detail(url)
        formats = _normalize_public_formats(data)
        selected = _select_public_format(formats, format_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        title = _first_existing(data, ["desc", "title"]) or "douyin-video"
        aweme_id = _first_existing(data, ["aweme_id", "id"]) or "public"
        output_file = output_dir / f"{sanitize_filename(str(title))[:120]}-{aweme_id}.mp4"
        _stream_download(selected["url"], output_file, referer=url, progress_hook=progress_hook)
        return output_file

    def fetch_detail(self, url: str) -> dict[str, Any]:
        aweme_id = extract_douyin_aweme_id(url)
        if not aweme_id:
            raise RuntimeError("F2 Douyin resolver needs a /video/{aweme_id} URL.")
        handler_cls = import_f2_douyin_handler()
        kwargs = {
            "headers": {
                "User-Agent": DOUYIN_DEFAULT_USER_AGENT,
                "Referer": "https://www.douyin.com/",
            },
            "cookie": "",
            "proxies": {"http://": None, "https://": None},
            "timeout": self.timeout,
        }
        result = _run_async(handler_cls(kwargs).fetch_one_video(aweme_id=aweme_id))
        if hasattr(result, "_to_dict"):
            data = result._to_dict()
        elif hasattr(result, "_to_raw"):
            data = result._to_raw()
        elif isinstance(result, dict):
            data = result
        else:
            raise RuntimeError("F2 Douyin resolver returned an unsupported response.")
        if not isinstance(data, dict) or not data:
            raise RuntimeError("F2 Douyin resolver returned empty video data.")
        return data


class DouyinVdResolver:
    def __init__(self, *, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or os.getenv("DOUYINVD_BASE_URL") or "").rstrip("/")
        self.timeout = timeout or float(os.getenv("DOUYINVD_TIMEOUT_SECONDS", "20"))

    def analyze(self, url: str) -> dict[str, Any]:
        data = self.fetch_detail(url)
        return normalize_douyinvd_detail(data, url)

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str,
        progress_hook=None,
    ) -> Path:
        data = self.fetch_detail(url)
        formats = [{"format_id": "douyinvd_video", "url": data.get("video_url"), "vcodec": "h264", "preference": 20}]
        selected = _select_public_format(formats, format_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        title = data.get("desc") or "douyin-video"
        aweme_id = data.get("aweme_id") or "public"
        output_file = output_dir / f"{sanitize_filename(str(title))[:120]}-{aweme_id}.mp4"
        _stream_download(selected["url"], output_file, referer=url, progress_hook=progress_hook)
        return output_file

    def fetch_detail(self, url: str) -> dict[str, Any]:
        if self.base_url:
            response = httpx.get(self.base_url, params={"data": "", "url": url}, follow_redirects=True, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data
            raise RuntimeError("DouyinVd sidecar returned an unsupported response.")
        return self._fetch_from_public_page(url)

    def _fetch_from_public_page(self, url: str) -> dict[str, Any]:
        response = httpx.get(
            url,
            headers={"User-Agent": DOUYINVD_DEFAULT_USER_AGENT, "Referer": "https://www.douyin.com/"},
            follow_redirects=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.text.replace("\\u002F", "/")
        video_match = DOUYINVD_VIDEO_PATTERN.search(body)
        if not video_match:
            raise RuntimeError("DouyinVd public page resolver found no video id.")
        desc_match = DOUYINVD_DESC_PATTERN.search(body)
        aweme_match = DOUYINVD_AWEME_PATTERN.search(body)
        cover_match = DOUYINVD_COVER_PATTERN.search(body)
        image_url_list = [cover_match.group("url")] if cover_match else []
        return {
            "aweme_id": aweme_match.group("id") if aweme_match else extract_douyin_aweme_id(str(response.url)),
            "desc": desc_match.group("desc") if desc_match else "Untitled Douyin video",
            "video_url": DOUYINVD_PLAY_URL.format(video_id=video_match.group("id")),
            "type": "video",
            "image_url_list": image_url_list,
        }


class DouyinPublicResolver:
    def __init__(self, resolvers: list[DouyinResolver] | None = None) -> None:
        self.resolvers = resolvers or build_default_resolver_chain()

    def analyze(self, url: str) -> dict[str, Any]:
        return self._run_first_success("analyze", url=url)

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str,
        progress_hook=None,
    ) -> Path:
        return self._run_first_success(
            "download",
            url=url,
            output_dir=output_dir,
            format_id=format_id,
            progress_hook=progress_hook,
        )

    def _run_first_success(self, method_name: str, **kwargs):
        errors: list[str] = []
        for resolver in self.resolvers:
            try:
                method = getattr(resolver, method_name)
                return method(**kwargs) if method_name == "download" else method(kwargs["url"])
            except Exception as exc:
                errors.append(f"{resolver.__class__.__name__}: {exc}")
        raise RuntimeError(f"{DOUYIN_PUBLIC_FAILURE_MESSAGE} Resolver errors: {' | '.join(errors)}")


def build_default_resolver_chain() -> list[DouyinResolver]:
    chain = [item.strip().lower() for item in os.getenv("DOUYIN_RESOLVER_CHAIN", "f2,douyinvd,browser").split(",")]
    resolvers: list[DouyinResolver] = []
    for item in chain:
        if item == "f2":
            resolvers.append(F2DouyinService())
        elif item == "douyinvd":
            resolvers.append(DouyinVdResolver())
        elif item == "browser":
            resolvers.append(DouyinBrowserService())
    return resolvers


def is_douyin_public_only_enabled() -> bool:
    return os.getenv("DOUYIN_PUBLIC_ONLY", "true").strip().lower() not in {"0", "false", "no", "off"}
