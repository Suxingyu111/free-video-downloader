from pathlib import Path

from app.services.transcript_service import (
    TranscriptSegment,
    TranscriptService,
    build_transcript_ytdlp_options,
    parse_cookies_from_browser,
    parse_srt,
    parse_vtt,
    transcript_to_text,
)


def test_parse_srt_returns_timestamped_segments():
    content = """1
00:00:01,000 --> 00:00:04,500
欢迎来到机器学习课程。

2
00:00:05,000 --> 00:00:08,000
今天讲模型训练。
"""

    segments = parse_srt(content)

    assert segments == [
        TranscriptSegment(start=1.0, end=4.5, text="欢迎来到机器学习课程。"),
        TranscriptSegment(start=5.0, end=8.0, text="今天讲模型训练。"),
    ]


def test_parse_vtt_skips_header_and_cue_settings():
    content = """WEBVTT

00:00:02.000 --> 00:00:03.500 align:start position:0%
第一段字幕

00:00:04.000 --> 00:00:06.000
第二段字幕
继续这一段
"""

    segments = parse_vtt(content)

    assert segments == [
        TranscriptSegment(start=2.0, end=3.5, text="第一段字幕"),
        TranscriptSegment(start=4.0, end=6.0, text="第二段字幕 继续这一段"),
    ]


def test_transcript_to_text_keeps_readable_timestamps():
    text = transcript_to_text(
        [
            TranscriptSegment(start=2.0, end=3.5, text="第一段字幕"),
            TranscriptSegment(start=64.0, end=70.0, text="第二段字幕"),
        ]
    )

    assert text == "[00:02] 第一段字幕\n[01:04] 第二段字幕"


def test_parse_subtitle_file_selects_parser_by_suffix(tmp_path: Path):
    from app.services.transcript_service import parse_subtitle_file

    subtitle = tmp_path / "lesson.zh.vtt"
    subtitle.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n你好\n", encoding="utf-8")

    assert parse_subtitle_file(subtitle) == [TranscriptSegment(start=1.0, end=2.0, text="你好")]


def test_parse_cookies_from_browser_matches_ytdlp_tuple_shape():
    assert parse_cookies_from_browser("chrome") == ("chrome", None, None, None)
    assert parse_cookies_from_browser("Chrome:Default") == ("chrome", "Default", None, None)
    assert parse_cookies_from_browser("firefox:release::Personal") == ("firefox", "release", None, "Personal")
    assert parse_cookies_from_browser("chromium+basictext:Profile 1") == ("chromium", "Profile 1", "BASICTEXT", None)


def test_build_transcript_ytdlp_options_adds_optional_cookie_auth(tmp_path: Path):
    options = build_transcript_ytdlp_options(
        prepared_url="https://www.bilibili.com/video/BV1yMn3zuE7L/",
        output_dir=tmp_path,
        subtitle_languages=["zh-CN"],
        cookie_file=tmp_path / "cookies.txt",
        cookies_from_browser=("chrome", None, None, None),
    )

    assert options["cookiefile"] == str(tmp_path / "cookies.txt")
    assert options["cookiesfrombrowser"] == ("chrome", None, None, None)
    assert options["subtitleslangs"] == ["zh-CN"]


def test_build_transcript_ytdlp_options_uses_public_youtube_clients(tmp_path: Path):
    options = build_transcript_ytdlp_options(
        prepared_url="https://www.youtube.com/watch?v=DXVHmGoCTco",
        output_dir=tmp_path,
        subtitle_languages=["zh-Hans"],
    )

    assert options["extractor_args"] == {"youtube": {"player_client": ["android", "web"]}}


def test_transcript_service_reads_cookie_auth_from_environment(monkeypatch):
    monkeypatch.setenv("BILIBILI_COOKIE_FILE", "/tmp/bilibili-cookies.txt")
    monkeypatch.setenv("BILIBILI_COOKIES_FROM_BROWSER", "safari")

    service = TranscriptService()

    assert service.cookie_file == Path("/tmp/bilibili-cookies.txt")
    assert service.cookies_from_browser == ("safari", None, None, None)


def test_transcript_service_skips_public_douyin_ytdlp_cookie_probe(monkeypatch, tmp_path):
    def fail_if_called(_options):
        raise AssertionError("Douyin public-only summaries should not ask yt-dlp for subtitles")

    monkeypatch.setattr("app.services.transcript_service.YoutubeDL", fail_if_called)

    transcript = TranscriptService().fetch_transcript(
        "https://v.douyin.com/0B3khUkIwRw/",
        tmp_path,
    )

    assert transcript is None
