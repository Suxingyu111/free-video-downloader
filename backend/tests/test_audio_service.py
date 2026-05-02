from __future__ import annotations

from pathlib import Path

from app.services import audio_service
from app.services.audio_service import AudioExtractionService


class FakeYoutubeDL:
    captured_options = None

    def __init__(self, options):
        FakeYoutubeDL.captured_options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def download(self, urls):
        output_template = FakeYoutubeDL.captured_options["outtmpl"]
        output_dir = Path(output_template).parent
        (output_dir / "audio.m4a").write_bytes(b"audio")


def test_audio_extraction_uses_resilient_youtube_audio_options(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_service, "YoutubeDL", FakeYoutubeDL)

    path = AudioExtractionService().extract_audio(
        "https://www.youtube.com/watch?v=_SA8TYC7Ctc",
        tmp_path,
    )

    assert path.name == "audio.m4a"
    options = FakeYoutubeDL.captured_options
    assert options["format"].startswith("worstaudio[ext=m4a]")
    assert "bestaudio[ext=m4a]" in options["format"]
    assert options["http_chunk_size"] == 1024 * 1024
    assert options["retries"] == 10
    assert options["extractor_retries"] == 5
    assert options["js_runtimes"] == {"node": {}}
    assert options["extractor_args"] == {"youtube": {"player_client": ["android", "web"]}}


class FakeDouyinResolver:
    def __init__(self):
        self.downloads = []

    def download(self, **kwargs):
        self.downloads.append(kwargs)
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        media_path = output_dir / "douyin-video.mp4"
        media_path.write_bytes(b"video")
        return media_path


def test_audio_extraction_uses_public_douyin_resolver_before_ffmpeg(monkeypatch, tmp_path):
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"audio")

    monkeypatch.setattr(audio_service.subprocess, "run", fake_run)
    douyin = FakeDouyinResolver()

    path = AudioExtractionService(douyin_service=douyin).extract_audio(
        "https://v.douyin.com/0B3khUkIwRw/",
        tmp_path,
    )

    assert path == tmp_path / "douyin-video.m4a"
    assert path.read_bytes() == b"audio"
    assert douyin.downloads[0]["url"] == "https://v.douyin.com/0B3khUkIwRw/"
    assert douyin.downloads[0]["format_id"] == "best"
    assert douyin.downloads[0]["output_dir"] == tmp_path / "source"
    assert commands[0][0] == "ffmpeg"
    assert "-vn" in commands[0]
    assert str(tmp_path / "source" / "douyin-video.mp4") in commands[0]
