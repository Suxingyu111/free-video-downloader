from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx

from app.services.ai_config import AIProviderConfig
from app.services.transcription_provider import (
    FallbackTranscriptionProvider,
    LocalFasterWhisperTranscriptionProvider,
    OpenAICompatibleTranscriptionProvider,
    build_transcription_provider,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse({"text": "[00:00] 云端转写文本"})


class FakeWhisperModel:
    def __init__(self, segments):
        self.segments = segments
        self.calls = []

    def transcribe(self, audio_path: str, **options):
        self.calls.append((audio_path, options))
        return self.segments, SimpleNamespace(language="zh", duration=12.0)


def test_openai_transcription_provider_uses_separate_speech_config(tmp_path: Path):
    client = FakeClient()
    provider = OpenAICompatibleTranscriptionProvider(
        AIProviderConfig(
            base_url="https://text.example.com/v1",
            api_key="text-key",
            transcribe_base_url="https://speech.example.com/v1",
            transcribe_api_key="speech-key",
            transcribe_model="speech-model",
        ),
        client=client,
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    text = provider.transcribe_audio(audio, "zh-CN")

    url, kwargs = client.calls[0]
    assert url == "https://speech.example.com/v1/audio/transcriptions"
    assert kwargs["headers"]["Authorization"] == "Bearer speech-key"
    assert kwargs["data"] == {"model": "speech-model", "language": "zh"}
    assert text == "[00:00] 云端转写文本"


def test_local_faster_whisper_transcription_provider_formats_timestamped_segments(tmp_path: Path):
    fake_model = FakeWhisperModel(
        [
            SimpleNamespace(start=0.0, end=1.5, text="第一段"),
            SimpleNamespace(start=65.2, end=70.0, text="第二段"),
        ]
    )
    created = []

    def model_factory(model_name, *, device, compute_type):
        created.append((model_name, device, compute_type))
        return fake_model

    provider = LocalFasterWhisperTranscriptionProvider(
        AIProviderConfig(
            transcribe_model="small",
            transcribe_device="cpu",
            transcribe_compute_type="int8",
            transcribe_beam_size=3,
            transcribe_vad_filter=True,
        ),
        model_factory=model_factory,
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    text = provider.transcribe_audio(audio, "zh-CN")

    assert created == [("small", "cpu", "int8")]
    assert fake_model.calls == [(str(audio), {"beam_size": 3, "vad_filter": True, "language": "zh"})]
    assert text == "[00:00] 第一段\n[01:05] 第二段"


def test_build_transcription_provider_supports_local_first_chain():
    provider = build_transcription_provider(
        AIProviderConfig(
            api_key="secret",
            transcribe_provider="local-faster-whisper,openai-compatible",
        )
    )

    assert isinstance(provider, FallbackTranscriptionProvider)
    assert len(provider.providers) == 2


def test_fallback_transcription_provider_uses_second_provider_after_failure(tmp_path: Path):
    class FailingProvider:
        def transcribe_audio(self, audio_path: Path, language: str) -> str:
            raise RuntimeError("local failed")

    class WorkingProvider:
        def transcribe_audio(self, audio_path: Path, language: str) -> str:
            return "[00:00] fallback"

    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    assert FallbackTranscriptionProvider([FailingProvider(), WorkingProvider()]).transcribe_audio(audio, "zh-CN") == "[00:00] fallback"


def test_openai_transcription_provider_surfaces_http_errors(tmp_path: Path):
    class ErrorClient:
        def post(self, url, **kwargs):
            return httpx.Response(
                429,
                json={"error": {"type": "insufficient_quota"}},
                request=httpx.Request("POST", url),
            )

    provider = OpenAICompatibleTranscriptionProvider(
        AIProviderConfig(api_key="secret", transcribe_model="speech-model"),
        client=ErrorClient(),
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    try:
        provider.transcribe_audio(audio, "zh-CN")
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 429
    else:
        raise AssertionError("HTTP 429 should be surfaced to summary error handling")
