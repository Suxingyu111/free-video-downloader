from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx


BILIBILI_BVID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10,}")
BILIBILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_PLAYER_API = "https://api.bilibili.com/x/player/v2"
BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


class HttpClient(Protocol):
    def get(self, url: str, **kwargs) -> httpx.Response:
        ...


def is_bilibili_url(url: str) -> bool:
    hostname = urlsplit(url).netloc.lower()
    return hostname == "bilibili.com" or hostname.endswith(".bilibili.com")


def extract_bilibili_bvid(url: str) -> str | None:
    if not is_bilibili_url(url):
        return None
    match = BILIBILI_BVID_PATTERN.search(url)
    return match.group(0) if match else None


def fetch_bilibili_public_metadata(
    url: str,
    *,
    client: HttpClient | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    bvid = extract_bilibili_bvid(url)
    if not bvid:
        raise RuntimeError("Bilibili URL does not contain a BV id.")

    referer = f"https://www.bilibili.com/video/{bvid}/"
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.bilibili.com",
        "Referer": referer,
    }
    view_payload = _get_json(
        BILIBILI_VIEW_API,
        params={"bvid": bvid},
        headers=headers,
        timeout=timeout,
        client=client,
    )
    view_data = _require_success_payload(view_payload, context="Bilibili view API")
    cid = view_data.get("cid")
    player_data: dict[str, Any] = {}
    if cid:
        player_payload = _get_json(
            BILIBILI_PLAYER_API,
            params={"bvid": bvid, "cid": cid},
            headers=headers,
            timeout=timeout,
            client=client,
        )
        try:
            player_data = _require_success_payload(player_payload, context="Bilibili player API")
        except RuntimeError:
            player_data = {}

    subtitles = _normalize_player_subtitles(player_data)
    return {
        "kind": "video",
        "id": view_data.get("bvid") or bvid,
        "title": view_data.get("title") or "Untitled",
        "webpage_url": referer,
        "thumbnail": view_data.get("pic"),
        "duration": view_data.get("duration"),
        "extractor": "bilibili-public",
        "formats": [],
        "subtitles": subtitles,
        "entries": [],
        "subtitle_login_required": bool(player_data.get("need_login_subtitle")),
        "bilibili": {
            "aid": view_data.get("aid"),
            "cid": cid,
        },
    }


def describe_bilibili_transcript_unavailable(url: str) -> str | None:
    if not is_bilibili_url(url):
        return None
    try:
        metadata = fetch_bilibili_public_metadata(url)
    except Exception:
        return None
    if metadata.get("subtitle_login_required"):
        return (
            "该 Bilibili 视频的字幕接口要求登录态。当前未使用 Cookie 时，yt-dlp 只能获取弹幕 XML，"
            "不能获取可用于视频内容总结的人工字幕或自动字幕。"
        )
    if not metadata.get("subtitles"):
        return "该 Bilibili 视频公开接口没有返回可用字幕，当前版本仅支持已有字幕的视频总结。"
    return None


def _get_json(
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    client: HttpClient | None,
) -> dict[str, Any]:
    if client is None:
        response = httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    else:
        response = client.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned an unsupported response.")
    return payload


def _require_success_payload(payload: dict[str, Any], *, context: str) -> dict[str, Any]:
    if payload.get("code") != 0:
        message = payload.get("message") or "unknown error"
        raise RuntimeError(f"{context} failed: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{context} returned no data.")
    return data


def _normalize_player_subtitles(player_data: dict[str, Any]) -> list[dict[str, Any]]:
    subtitle_info = player_data.get("subtitle") if isinstance(player_data, dict) else None
    subtitle_items = subtitle_info.get("subtitles") if isinstance(subtitle_info, dict) else None
    normalized: list[dict[str, Any]] = []
    for item in subtitle_items or []:
        if not isinstance(item, dict):
            continue
        lang = item.get("lan") or item.get("language")
        if not lang:
            continue
        normalized.append(
            {
                "lang": lang,
                "ext": "json",
                "name": item.get("lan_doc") or lang,
                "automatic": bool(item.get("ai_type") or item.get("type") == 1),
            }
        )
    return normalized
