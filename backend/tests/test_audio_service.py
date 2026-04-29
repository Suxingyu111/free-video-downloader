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
