from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

import httpx

from app.services.ai_config import AIProviderConfig, load_ai_provider_config
from app.services.transcript_service import format_timestamp


class TranscriptionProvider(Protocol):
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        ...


def build_transcription_provider_from_env() -> TranscriptionProvider:
    return build_transcription_provider(load_ai_provider_config())


def build_transcription_provider(config: AIProviderConfig) -> TranscriptionProvider:
    names = [
        name.strip().lower()
        for name in re.split(r"[,>]+", config.transcribe_provider or "")
        if name.strip()
    ]
    if not names:
        names = ["openai-compatible"]

    providers = [_build_single_transcription_provider(name, config) for name in names]
    if len(providers) == 1:
        return providers[0]
    return FallbackTranscriptionProvider(providers)


def _build_single_transcription_provider(name: str, config: AIProviderConfig) -> TranscriptionProvider:
    if name == "mock":
        return MockTranscriptionProvider()
    if name in {"local", "local-faster-whisper", "faster-whisper"}:
        return LocalFasterWhisperTranscriptionProvider(config)
    if name in {"openai", "openai-compatible", "groq"}:
        return OpenAICompatibleTranscriptionProvider(config)
    raise RuntimeError(f"未知语音转写服务：{name}")


class FallbackTranscriptionProvider:
    def __init__(self, providers: list[TranscriptionProvider]) -> None:
        self.providers = providers

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.transcribe_audio(audio_path, language)
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError("所有语音转写服务都失败：" + "；".join(errors))


class OpenAICompatibleTranscriptionProvider:
    def __init__(self, config: AIProviderConfig, *, client=None) -> None:
        self.base_url = (config.transcribe_base_url or config.base_url).rstrip("/")
        self.api_key = config.transcribe_api_key or config.api_key
        self.model = config.transcribe_model
        self.client = client or httpx.Client(timeout=config.timeout_seconds, follow_redirects=True)
        if not self.api_key:
            raise RuntimeError("AI_TRANSCRIBE_API_KEY 或 AI_API_KEY 未配置，无法使用云端语音转写服务。")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        with audio_path.open("rb") as file:
            response = self.client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=self._headers(),
                data={"model": self.model, "language": _normalize_openai_language(language)},
                files={"file": (audio_path.name, file, "application/octet-stream")},
            )
        response.raise_for_status()
        data = response.json()
        text = data.get("text") if isinstance(data, dict) else None
        if not text:
            raise RuntimeError("AI 语音转写服务未返回文本。")
        return str(text).strip()


class LocalFasterWhisperTranscriptionProvider:
    def __init__(self, config: AIProviderConfig, *, model_factory=None) -> None:
        self.model_name = config.transcribe_model or "small"
        self.device = config.transcribe_device or "cpu"
        self.compute_type = config.transcribe_compute_type or "int8"
        self.beam_size = config.transcribe_beam_size
        self.vad_filter = config.transcribe_vad_filter
        self.model_factory = model_factory
        self._model = None

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        model = self._load_model()
        options = {
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
        }
        normalized_language = _normalize_whisper_language(language)
        if normalized_language:
            options["language"] = normalized_language

        segments, _info = model.transcribe(str(audio_path), **options)
        lines: list[str] = []
        for segment in segments:
            text = str(getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            start = float(getattr(segment, "start", 0.0) or 0.0)
            lines.append(f"[{format_timestamp(start)}] {text}")
        if not lines:
            raise RuntimeError("本地 faster-whisper 未返回可用转写文本。")
        return "\n".join(lines)

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self.model_factory is not None:
            self._model = self.model_factory(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "本地语音转写需要安装 faster-whisper：pip install faster-whisper"
            ) from exc
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model


class MockTranscriptionProvider:
    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        return "[00:00] 这是演示转写内容，用于本地浏览器验收。 [01:10] 视频介绍了核心概念、章节结构和实践建议。"


def _normalize_openai_language(language: str) -> str:
    normalized = (language or "").strip()
    if normalized.lower().startswith("zh"):
        return "zh"
    return normalized or "zh"


def _normalize_whisper_language(language: str) -> str | None:
    normalized = (language or "").strip().lower()
    if not normalized or normalized == "auto":
        return None
    language_map = {
        "zh-cn": "zh",
        "zh-hans": "zh",
        "zh-hant": "zh",
        "zh-tw": "zh",
        "zh": "zh",
        "zho": "zh",
        "cmn": "zh",
        "en-us": "en",
        "en-gb": "en",
        "eng": "en",
        "ja-jp": "ja",
        "jpn": "ja",
        "ko-kr": "ko",
        "kor": "ko",
    }
    return language_map.get(normalized, normalized.split("-", 1)[0])
