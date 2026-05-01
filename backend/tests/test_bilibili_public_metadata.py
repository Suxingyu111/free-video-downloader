from __future__ import annotations

import httpx

from app.services.bilibili_public_metadata import extract_bilibili_bvid
from app.services.bilibili_public_metadata import describe_bilibili_transcript_unavailable
from app.services.bilibili_public_metadata import fetch_bilibili_public_metadata


class FakeBilibiliClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/x/web-interface/view"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "OK",
                    "data": {
                        "bvid": "BV1mAAmzqEfP",
                        "aid": 116140797991021,
                        "cid": 36319134306,
                        "title": "做了个新项目，我要出海了！",
                        "pic": "https://i0.hdslb.com/bfs/archive/demo.jpg",
                        "duration": 211,
                    },
                },
                request=httpx.Request("GET", url),
            )
        if url.endswith("/x/player/v2"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "OK",
                    "data": {
                        "need_login_subtitle": True,
                        "subtitle": {"subtitles": []},
                    },
                },
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"Unexpected URL: {url}")


def test_extract_bilibili_bvid_accepts_bilibili_hosts():
    assert extract_bilibili_bvid("https://bilibili.com/video/BV1mAAmzqEfP") == "BV1mAAmzqEfP"
    assert extract_bilibili_bvid("https://www.bilibili.com/video/BV1mAAmzqEfP/?spm_id_from=abc") == "BV1mAAmzqEfP"


def test_fetch_bilibili_public_metadata_normalizes_view_payload():
    client = FakeBilibiliClient()

    result = fetch_bilibili_public_metadata("https://bilibili.com/video/BV1mAAmzqEfP", client=client)

    assert result["kind"] == "video"
    assert result["id"] == "BV1mAAmzqEfP"
    assert result["title"] == "做了个新项目，我要出海了！"
    assert result["webpage_url"] == "https://www.bilibili.com/video/BV1mAAmzqEfP/"
    assert result["thumbnail"] == "https://i0.hdslb.com/bfs/archive/demo.jpg"
    assert result["duration"] == 211
    assert result["extractor"] == "bilibili-public"
    assert result["subtitles"] == []
    assert result["formats"] == []
    assert result["entries"] == []
    assert result["subtitle_login_required"] is True
    assert result["bilibili"]["cid"] == 36319134306
    assert client.calls[0][1]["params"] == {"bvid": "BV1mAAmzqEfP"}
    assert client.calls[1][1]["params"] == {"bvid": "BV1mAAmzqEfP", "cid": 36319134306}


def test_describe_bilibili_transcript_unavailable_returns_login_required_reason(monkeypatch):
    monkeypatch.setattr(
        "app.services.bilibili_public_metadata.fetch_bilibili_public_metadata",
        lambda url: {"subtitle_login_required": True, "subtitles": []},
    )

    message = describe_bilibili_transcript_unavailable("https://www.bilibili.com/video/BV1mAAmzqEfP/")

    assert "字幕接口要求登录态" in message
    assert "弹幕 XML" in message
    assert "语音转写" in message
