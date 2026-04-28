from pathlib import Path

import pytest

from app.services.douyin_public_resolver import (
    DOUYIN_PUBLIC_FAILURE_MESSAGE,
    DouyinPublicResolver,
    F2DouyinService,
    normalize_f2_detail,
)


class FakeResolver:
    def __init__(self, name: str, *, result: dict | None = None, output: Path | None = None, error: Exception | None = None):
        self.name = name
        self.result = result
        self.output = output
        self.error = error
        self.analyzed = []
        self.downloaded = []

    def analyze(self, url: str) -> dict:
        self.analyzed.append(url)
        if self.error:
            raise self.error
        return self.result or {"title": self.name, "formats": []}

    def download(self, **kwargs) -> Path:
        self.downloaded.append(kwargs)
        if self.error:
            raise self.error
        return self.output or Path(kwargs["output_dir"]) / f"{self.name}.mp4"


class FakeF2Filter:
    def __init__(self, data: dict):
        self.data = data

    def _to_dict(self):
        return self.data


def test_normalize_f2_detail_returns_video_metadata_and_direct_format():
    result = normalize_f2_detail(
        {
            "aweme_id": "7601048622565821747",
            "desc": "公开视频",
            "duration": 12000,
            "cover": "https://example.com/cover.jpg",
            "video_play_addr": "https://example.com/video.mp4",
            "video_bit_rate": [
                {
                    "gear_name": "normal_720_0",
                    "bit_rate": 1000,
                    "play_addr": {"url_list": ["https://example.com/720.mp4"], "data_size": 1234, "url_key": "v_h264_720p"},
                }
            ],
        },
        "https://www.douyin.com/video/7601048622565821747",
    )

    assert result["id"] == "7601048622565821747"
    assert result["title"] == "公开视频"
    assert result["thumbnail"] == "https://example.com/cover.jpg"
    assert result["duration"] == 12
    assert result["extractor"] == "douyin:f2"
    assert {item["format_id"] for item in result["formats"]} >= {"f2_play_addr", "normal_720_0"}


def test_f2_service_uses_fetch_one_video_with_aweme_id(monkeypatch):
    calls = []

    class FakeHandler:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        async def fetch_one_video(self, aweme_id: str):
            calls.append((self.kwargs, aweme_id))
            return FakeF2Filter({"aweme_id": aweme_id, "desc": "F2 video", "video_play_addr": "https://example.com/f2.mp4"})

    monkeypatch.setattr("app.services.douyin_public_resolver.import_f2_douyin_handler", lambda: FakeHandler)

    result = F2DouyinService().analyze("https://www.douyin.com/video/7601048622565821747")

    assert result["title"] == "F2 video"
    assert calls[0][1] == "7601048622565821747"
    assert calls[0][0]["cookie"] == ""


def test_public_resolver_falls_back_through_configured_chain(tmp_path):
    f2 = FakeResolver("f2", error=RuntimeError("f2 failed"))
    douyinvd = FakeResolver("douyinvd", error=RuntimeError("douyinvd failed"))
    browser = FakeResolver("browser", result={"title": "browser result", "formats": []}, output=tmp_path / "browser.mp4")

    resolver = DouyinPublicResolver(resolvers=[f2, douyinvd, browser])

    assert resolver.analyze("https://www.douyin.com/video/7601048622565821747")["title"] == "browser result"
    output = resolver.download(url="https://www.douyin.com/video/7601048622565821747", output_dir=tmp_path, format_id="best")

    assert output == tmp_path / "browser.mp4"
    assert f2.analyzed
    assert douyinvd.analyzed
    assert browser.analyzed


def test_public_resolver_raises_public_boundary_message_after_all_failures(tmp_path):
    resolver = DouyinPublicResolver(
        resolvers=[
            FakeResolver("f2", error=RuntimeError("f2 failed")),
            FakeResolver("douyinvd", error=RuntimeError("douyinvd failed")),
            FakeResolver("browser", error=RuntimeError("browser failed")),
        ]
    )

    with pytest.raises(RuntimeError) as exc:
        resolver.download(url="https://www.douyin.com/video/7601048622565821747", output_dir=tmp_path, format_id="best")

    assert DOUYIN_PUBLIC_FAILURE_MESSAGE in str(exc.value)
    assert "cookies.txt" not in str(exc.value)
