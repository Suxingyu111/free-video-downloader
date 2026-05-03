from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from yt_dlp.utils import sanitize_filename

from app.services.env_file import env_value


DOUYIN_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

DOUYIN_AWEME_DETAIL_PATH = "aweme/v1/web/aweme/detail"
DOUYIN_VIDEO_ID_PATTERN = re.compile(r"/video/(?P<id>\d+)")


def is_douyin_url(url: str) -> bool:
    hostname = urlsplit(url).netloc.lower()
    return hostname == "v.douyin.com" or hostname.endswith(".douyin.com") or hostname == "douyin.com"


def extract_douyin_aweme_id(url: str) -> str | None:
    match = DOUYIN_VIDEO_ID_PATTERN.search(urlsplit(url).path)
    return match.group("id") if match else None


def _first_url(value: dict[str, Any] | None) -> str | None:
    urls = (value or {}).get("url_list") or []
    return next((item for item in urls if item), None)


def _parse_height(url_key: str | None) -> int | None:
    if not url_key:
        return None
    match = re.search(r"_(?P<height>\d+)p(?:_|$)", url_key)
    return int(match.group("height")) if match else None


def _deduplicate_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls = set()
    deduped = []
    for item in formats:
        url = item.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(item)
    return deduped


def collect_douyin_formats(detail: dict[str, Any]) -> list[dict[str, Any]]:
    video = detail.get("video") or {}
    formats: list[dict[str, Any]] = []

    def add_format(format_id: str, address: dict[str, Any] | None, *, vcodec: str = "h264", preference: int = 0) -> None:
        url = _first_url(address)
        if not url:
            return
        url_key = (address or {}).get("url_key")
        formats.append(
            {
                "format_id": format_id,
                "url": url,
                "ext": "mp4",
                "resolution": None,
                "width": video.get("width"),
                "height": _parse_height(url_key) or video.get("height"),
                "filesize": (address or {}).get("data_size"),
                "vcodec": vcodec,
                "acodec": "aac",
                "tbr": None,
                "preference": preference,
                "label": format_id,
            }
        )

    add_format("play_addr_h264", video.get("play_addr_h264"), vcodec="h264", preference=30)
    add_format("play_addr", video.get("play_addr"), vcodec="h265" if video.get("is_h265") else "h264", preference=20)
    add_format("download_addr", video.get("download_addr"), vcodec="h264", preference=5)

    for item in video.get("bit_rate") or []:
        address = item.get("play_addr") or {}
        url = _first_url(address)
        if not url:
            continue
        url_key = address.get("url_key")
        format_id = item.get("gear_name") or url_key or f"bitrate_{len(formats)}"
        height = _parse_height(url_key) or address.get("height") or video.get("height")
        formats.append(
            {
                "format_id": str(format_id),
                "url": url,
                "ext": "mp4",
                "resolution": None,
                "width": address.get("width") or video.get("width"),
                "height": height,
                "filesize": address.get("data_size"),
                "vcodec": "h265" if item.get("is_h265") else "h264",
                "acodec": "aac",
                "tbr": item.get("bit_rate"),
                "fps": item.get("FPS"),
                "preference": 10,
                "label": f"{height}p mp4" if height else "mp4",
            }
        )

    return _deduplicate_formats(formats)


def select_douyin_format(formats: list[dict[str, Any]], format_id: str | None) -> dict[str, Any]:
    if not formats:
        raise RuntimeError("Douyin returned no downloadable video formats.")
    if format_id and "/" not in format_id:
        for item in formats:
            if item.get("format_id") == format_id:
                return item

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
        is_h264 = 1 if item.get("vcodec") == "h264" else 0
        height = item.get("height") or 0
        preference = item.get("preference") or 0
        return is_h264, preference, height

    return max(formats, key=sort_key)


def normalize_douyin_detail(detail: dict[str, Any], webpage_url: str) -> dict[str, Any]:
    video = detail.get("video") or {}
    cover = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    duration = video.get("duration")
    return {
        "kind": "video",
        "id": detail.get("aweme_id"),
        "title": detail.get("desc") or "Untitled Douyin video",
        "webpage_url": webpage_url,
        "thumbnail": cover,
        "duration": duration / 1000 if isinstance(duration, int | float) else None,
        "extractor": "douyin:browser",
        "formats": [
            {key: value for key, value in item.items() if key != "url"}
            for item in collect_douyin_formats(detail)
        ],
        "subtitles": [],
        "entries": [],
    }


class DouyinBrowserService:
    def __init__(self, *, timeout_ms: int | None = None, browser_channel: str | None = None) -> None:
        self.timeout_ms = timeout_ms or int(env_value("DOUYIN_BROWSER_TIMEOUT_MS", "30000"))
        self.browser_channel = browser_channel or env_value("DOUYIN_BROWSER_CHANNEL", "chrome")

    def analyze(self, url: str) -> dict[str, Any]:
        detail, webpage_url = self.fetch_detail(url)
        return normalize_douyin_detail(detail, webpage_url)

    def download(
        self,
        *,
        url: str,
        output_dir: Path,
        format_id: str,
        progress_hook=None,
    ) -> Path:
        detail, webpage_url = self.fetch_detail(url)
        selected = select_douyin_format(collect_douyin_formats(detail), format_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{sanitize_filename(detail.get('desc') or 'douyin-video')[:120]}-{detail.get('aweme_id')}.mp4"
        self._stream_download(selected["url"], output_file, referer=webpage_url, progress_hook=progress_hook)
        return output_file

    def fetch_detail(self, url: str) -> tuple[dict[str, Any], str]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Douyin browser extraction requires the Python playwright package.") from exc

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel=self.browser_channel, headless=True)
            except Exception:
                try:
                    browser = playwright.chromium.launch(headless=True)
                except Exception as exc:
                    raise RuntimeError(
                        "Douyin browser extraction requires Chrome or a Playwright Chromium browser. "
                        "Install Chrome or run `python -m playwright install chromium` on the server."
                    ) from exc

            try:
                context = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 720})
                page = context.new_page()
                details: list[tuple[dict[str, Any], str]] = []

                def collect_detail_response(response) -> None:
                    if DOUYIN_AWEME_DETAIL_PATH not in response.url or response.status != 200:
                        return
                    try:
                        data = response.json()
                    except Exception:
                        return
                    detail = data.get("aweme_detail")
                    if detail:
                        details.append((detail, response.url))

                page.on("response", collect_detail_response)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    deadline = self.timeout_ms
                    while not details and deadline > 0:
                        page.wait_for_timeout(500)
                        deadline -= 500
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError(
                        "Douyin did not return public video metadata in the browser session. "
                        "The short link may be expired, the video may be private, or the server IP may be rate limited."
                    ) from exc

                if not details:
                    raise RuntimeError(
                        "Douyin did not return public video metadata in the browser session. "
                        "The short link may be expired, the video may be private, or the server IP may be rate limited."
                    )
                detail, _ = details[0]
                return detail, page.url
            finally:
                browser.close()

    def _stream_download(self, media_url: str, output_file: Path, *, referer: str, progress_hook=None) -> None:
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
