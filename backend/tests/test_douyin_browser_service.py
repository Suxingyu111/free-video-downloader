from pathlib import Path

from app.services.douyin_browser_service import (
    DouyinBrowserService,
    collect_douyin_formats,
    extract_douyin_aweme_id,
    is_douyin_url,
    normalize_douyin_detail,
    select_douyin_format,
)
from app.services.ytdlp_service import YtDlpService


def sample_detail() -> dict:
    return {
        "aweme_id": "7601048622565821747",
        "desc": "Demo Douyin video",
        "author": {"nickname": "Demo Creator"},
        "video": {
            "duration": 12345,
            "width": 720,
            "height": 1280,
            "is_h265": True,
            "cover": {"url_list": ["https://example.com/cover.jpg"]},
            "play_addr": {
                "url_list": ["https://example.com/h265.mp4"],
                "data_size": 2000,
                "url_key": "v0200_h265_1080p_2000",
            },
            "play_addr_h264": {
                "url_list": ["https://example.com/h264.mp4"],
                "data_size": 1800,
                "url_key": "v0200_h264_1080p_1800",
            },
            "download_addr": {
                "url_list": ["https://example.com/watermarked.mp4"],
                "data_size": 1700,
            },
            "bit_rate": [
                {
                    "gear_name": "normal_720_0",
                    "bit_rate": 1000,
                    "FPS": 30,
                    "play_addr": {
                        "url_list": ["https://example.com/720.mp4"],
                        "data_size": 1000,
                        "url_key": "v0200_h264_720p_1000",
                    },
                }
            ],
        },
    }


def test_detects_and_extracts_douyin_video_ids():
    url = "https://www.douyin.com/video/7601048622565821747?previous_page=app_code_link"

    assert is_douyin_url(url)
    assert extract_douyin_aweme_id(url) == "7601048622565821747"


def test_normalize_douyin_detail_returns_video_metadata_and_formats():
    result = normalize_douyin_detail(sample_detail(), "https://www.douyin.com/video/7601048622565821747")

    assert result["id"] == "7601048622565821747"
    assert result["title"] == "Demo Douyin video"
    assert result["duration"] == 12.345
    assert result["thumbnail"] == "https://example.com/cover.jpg"
    assert result["extractor"] == "douyin:browser"
    assert {item["format_id"] for item in result["formats"]} >= {"play_addr_h264", "normal_720_0"}


def test_select_douyin_format_prefers_h264_direct_playback():
    selected = select_douyin_format(collect_douyin_formats(sample_detail()), "best")

    assert selected["format_id"] == "play_addr_h264"
    assert selected["url"] == "https://example.com/h264.mp4"


def test_ytdlp_service_routes_douyin_to_browser_service_without_user_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.ytdlp_service.validate_media_file", lambda _: None)

    class FakeDouyinService:
        def __init__(self):
            self.analyzed = []
            self.downloaded = []

        def analyze(self, url):
            self.analyzed.append(url)
            return {"id": "7601048622565821747", "title": "Demo", "formats": []}

        def download(self, **kwargs):
            self.downloaded.append(kwargs)
            output = Path(kwargs["output_dir"]) / "demo.mp4"
            output.write_bytes(b"fake")
            return output

    fake = FakeDouyinService()
    service = YtDlpService(douyin_service=fake)

    assert service.analyze("https://www.douyin.com/video/7601048622565821747")["title"] == "Demo"
    output = service.download(
        url="https://www.douyin.com/video/7601048622565821747",
        output_dir=tmp_path,
        format_id="best",
    )

    assert output.name == "demo.mp4"
    assert fake.analyzed == ["https://www.douyin.com/video/7601048622565821747"]
    assert fake.downloaded[0]["url"] == "https://www.douyin.com/video/7601048622565821747"
