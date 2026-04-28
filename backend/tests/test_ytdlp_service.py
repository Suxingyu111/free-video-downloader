from app.services.ytdlp_service import (
    DEFAULT_FORMAT,
    BILIBILI_DEFAULT_FORMAT,
    download_with_resumable_retries,
    build_download_options,
    friendly_error_message,
    normalize_info,
    prepare_url,
    resolve_format_selector,
    select_output_artifact,
    validate_media_streams,
)


def test_normalize_info_returns_video_formats_and_subtitles():
    info = {
        "_type": "video",
        "id": "abc",
        "title": "Demo Video",
        "webpage_url": "https://example.com/watch/abc",
        "thumbnail": "https://example.com/thumb.jpg",
        "duration": 125,
        "extractor": "generic",
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "resolution": "640x360",
                "height": 360,
                "filesize": 1024,
                "vcodec": "h264",
                "acodec": "aac",
            },
            {
                "format_id": "251",
                "ext": "webm",
                "resolution": "audio only",
                "filesize_approx": 2048,
                "vcodec": "none",
                "acodec": "opus",
            },
        ],
        "subtitles": {
            "en": [{"ext": "vtt", "name": "English"}],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "vtt", "name": "Chinese"}],
        },
    }

    result = normalize_info(info)

    assert result["kind"] == "video"
    assert result["id"] == "abc"
    assert result["title"] == "Demo Video"
    assert result["formats"][0]["format_id"] == "18"
    assert result["formats"][0]["label"] == "360p mp4"
    assert result["subtitles"] == [
        {"lang": "en", "ext": "vtt", "name": "English", "automatic": False},
        {"lang": "zh-Hans", "ext": "vtt", "name": "Chinese", "automatic": True},
    ]


def test_normalize_info_expands_playlist_entries():
    info = {
        "_type": "playlist",
        "id": "pl",
        "title": "Course Playlist",
        "webpage_url": "https://example.com/playlist",
        "entries": [
            {
                "id": "v1",
                "title": "Lesson 1",
                "webpage_url": "https://example.com/v1",
                "duration": 60,
                "thumbnail": "https://example.com/v1.jpg",
            },
            None,
        ],
    }

    result = normalize_info(info)

    assert result["kind"] == "playlist"
    assert result["title"] == "Course Playlist"
    assert result["entries"] == [
        {
            "id": "v1",
            "title": "Lesson 1",
            "url": "https://example.com/v1",
            "duration": 60,
            "thumbnail": "https://example.com/v1.jpg",
        }
    ]


def test_prepare_url_removes_tracking_query_but_keeps_playlist_part():
    url = (
        "https://www.bilibili.com/video/BV1aFoyBnE4D/"
        "?spm_id_from=333.337.search-card.all.click&vd_source=abc&p=2"
    )

    assert prepare_url(url) == "https://www.bilibili.com/video/BV1aFoyBnE4D/?p=2"


def test_friendly_error_message_explains_bilibili_412_public_boundary_without_cookie_prompt():
    message = friendly_error_message(
        "ERROR: [BiliBili] 1aFoyBnE4D: Unable to download JSON metadata: "
        "HTTP Error 412: Precondition Failed"
    )

    assert "Bilibili 返回 412" in message
    assert "公开视频" in message
    assert "cookies.txt" not in message


def test_build_download_options_uses_resilient_network_defaults(tmp_path):
    options = build_download_options(
        url="https://www.bilibili.com/video/BV1ZB9EBmEAU/",
        output_dir=tmp_path,
        format_id=DEFAULT_FORMAT,
        subtitle_langs=[],
        write_auto_subs=False,
        prefer_srt=True,
        progress_hook=None,
    )

    assert options["format"] == BILIBILI_DEFAULT_FORMAT
    assert options["source_address"] == "0.0.0.0"
    assert options["http_chunk_size"] == 1024 * 1024
    assert options["retries"] >= 10
    assert options["fragment_retries"] >= 10
    assert options["continuedl"] is True
    assert options["js_runtimes"] == {"node": {}}


def test_build_download_options_avoids_chunked_youtube_media_requests(tmp_path):
    options = build_download_options(
        url="https://www.youtube.com/watch?v=zRtGL0-5rg4",
        output_dir=tmp_path,
        format_id=DEFAULT_FORMAT,
        subtitle_langs=[],
        write_auto_subs=False,
        prefer_srt=True,
        progress_hook=None,
    )

    assert "http_chunk_size" not in options


def test_download_with_resumable_retries_reextracts_youtube_url_after_403(monkeypatch):
    calls = []

    class FakeYdl:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            calls.append(urls)
            if len(calls) == 1:
                raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr("app.services.ytdlp_service.YoutubeDL", FakeYdl)

    download_with_resumable_retries(
        options={},
        prepared_url="https://www.youtube.com/watch?v=abc",
        max_attempts=2,
    )

    assert calls == [
        ["https://www.youtube.com/watch?v=abc"],
        ["https://www.youtube.com/watch?v=abc"],
    ]


def test_download_with_resumable_retries_handles_bot_check_during_reextract(monkeypatch):
    calls = []

    class FakeYdl:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            calls.append(urls)
            if len(calls) == 1:
                raise RuntimeError("ERROR: [youtube] abc: Sign in to confirm you’re not a bot.")

    monkeypatch.setattr("app.services.ytdlp_service.YoutubeDL", FakeYdl)

    download_with_resumable_retries(
        options={},
        prepared_url="https://www.youtube.com/watch?v=abc",
        max_attempts=2,
    )

    assert len(calls) == 2


def test_default_format_prefers_progressive_mp4_before_youtube_dash_formats():
    assert DEFAULT_FORMAT.startswith("18/")
    assert "[vcodec^=avc]" in DEFAULT_FORMAT
    assert "bestaudio[ext=m4a]" in DEFAULT_FORMAT


def test_resolve_format_selector_maps_default_to_bilibili_mergeable_formats():
    selector = resolve_format_selector(
        "http://www.bilibili.com/video/BV1mAAmzqEfP",
        DEFAULT_FORMAT,
    )

    assert selector == BILIBILI_DEFAULT_FORMAT


def test_resolve_format_selector_maps_default_to_tiktok_h264_formats():
    selector = resolve_format_selector(
        "https://www.tiktok.com/@undchi/video/7625640899388771617",
        DEFAULT_FORMAT,
    )

    assert selector != DEFAULT_FORMAT
    assert "[vcodec=h264]" in selector
    assert selector.endswith(DEFAULT_FORMAT)


def test_bilibili_default_format_prefers_browser_compatible_h264_video_with_m4a_audio():
    assert "[vcodec^=avc]" in BILIBILI_DEFAULT_FORMAT
    assert "bestaudio[ext=m4a]" in BILIBILI_DEFAULT_FORMAT
    assert BILIBILI_DEFAULT_FORMAT.startswith("bestvideo[ext=mp4][vcodec^=avc]")


def test_build_download_options_adds_bilibili_origin_header(tmp_path):
    options = build_download_options(
        url="https://www.bilibili.com/video/BV1ZB9EBmEAU/",
        output_dir=tmp_path,
        format_id=DEFAULT_FORMAT,
        subtitle_langs=[],
        write_auto_subs=False,
        prefer_srt=True,
        progress_hook=None,
    )

    assert options["http_headers"]["Referer"] == "https://www.bilibili.com/video/BV1ZB9EBmEAU/"
    assert options["http_headers"]["Origin"] == "https://www.bilibili.com"


def test_friendly_error_message_explains_youtube_bot_boundary_without_cookie_prompt():
    message = friendly_error_message(
        "ERROR: [youtube] zRtGL0-5rg4: Sign in to confirm you’re not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )

    assert "YouTube 要求登录验证" in message
    assert "公开视频" in message
    assert "cookies.txt" not in message


def test_friendly_error_message_explains_douyin_public_video_boundary_without_cookie_prompt():
    message = friendly_error_message(
        "ERROR: [Douyin] 7601048622565821747: Fresh cookies "
        "(not necessarily logged in) are needed"
    )

    assert "抖音公开视频" in message
    assert "私密" in message
    assert "风控" in message
    assert "cookies.txt" not in message


def test_friendly_error_message_explains_expired_douyin_short_link():
    message = friendly_error_message("ERROR: Unsupported URL: https://www.douyin.com/")

    assert "抖音短链" in message
    assert "永久地址" in message


def test_build_download_options_filters_playlist_entries_by_selected_ids(tmp_path):
    options = build_download_options(
        url="https://www.youtube.com/playlist?list=PL123",
        output_dir=tmp_path,
        format_id=DEFAULT_FORMAT,
        subtitle_langs=[],
        write_auto_subs=False,
        prefer_srt=True,
        progress_hook=None,
        entry_ids=["video-1", "video-3"],
    )

    assert options["match_filter"]({"id": "video-1"}) is None
    assert options["match_filter"]({"id": "video-2"}) == "Entry was not selected"


def test_select_output_artifact_returns_zip_for_multiple_created_files(tmp_path):
    before = set(tmp_path.glob("*"))
    first = tmp_path / "lesson-1.mp4"
    second = tmp_path / "lesson-1.en.srt"
    first.write_bytes(b"video")
    second.write_text("subtitle", encoding="utf-8")

    artifact = select_output_artifact(tmp_path, before)

    assert artifact.suffix == ".zip"
    assert artifact.exists()


def test_validate_media_streams_rejects_mp4_with_av1_video():
    error = validate_media_streams(
        [
            {"codec_type": "video", "codec_name": "av1"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        suffix=".mp4",
    )

    assert "H.264" in error


def test_validate_media_streams_accepts_mp4_with_h264_video_and_audio():
    error = validate_media_streams(
        [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        suffix=".mp4",
    )

    assert error is None
