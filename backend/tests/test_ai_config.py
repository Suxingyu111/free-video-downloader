from __future__ import annotations

import json

from app.services.ai_config import load_ai_provider_config


AI_ENV_KEYS = [
    "AI_CONFIG_FILE",
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_TEXT_MODEL",
    "AI_TRANSCRIBE_PROVIDER",
    "AI_TRANSCRIBE_BASE_URL",
    "AI_TRANSCRIBE_API_KEY",
    "AI_TRANSCRIBE_MODEL",
    "AI_TRANSCRIBE_DEVICE",
    "AI_TRANSCRIBE_COMPUTE_TYPE",
    "AI_TRANSCRIBE_BEAM_SIZE",
    "AI_TRANSCRIBE_VAD_FILTER",
    "AI_TIMEOUT_SECONDS",
]


def clear_ai_env(monkeypatch):
    for key in AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_ai_config_uses_safe_defaults_without_file(monkeypatch, tmp_path):
    clear_ai_env(monkeypatch)
    monkeypatch.setenv("AI_CONFIG_FILE", str(tmp_path / "missing-ai-config.json"))

    config = load_ai_provider_config()

    assert config.provider == "openai-compatible"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.api_key == ""
    assert config.text_model == "gpt-4o-mini"
    assert config.transcribe_provider == "openai-compatible"
    assert config.transcribe_base_url == ""
    assert config.transcribe_api_key == ""
    assert config.transcribe_model == "gpt-4o-mini-transcribe"
    assert config.transcribe_device == "cpu"
    assert config.transcribe_compute_type == "int8"
    assert config.transcribe_beam_size == 5
    assert config.transcribe_vad_filter is True
    assert config.timeout_seconds == 120.0


def test_ai_config_reads_json_file(monkeypatch, tmp_path):
    clear_ai_env(monkeypatch)
    config_path = tmp_path / "ai.config.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai-compatible",
                "base_url": "https://ai.example.com/v1/",
                "api_key": "file-key",
                "text_model": "summary-model",
                "transcribe_provider": "local-faster-whisper",
                "transcribe_base_url": "https://speech.example.com/v1/",
                "transcribe_api_key": "speech-key",
                "transcribe_model": "speech-model",
                "transcribe_device": "cuda",
                "transcribe_compute_type": "float16",
                "transcribe_beam_size": 3,
                "transcribe_vad_filter": False,
                "timeout_seconds": 42,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_CONFIG_FILE", str(config_path))

    config = load_ai_provider_config()

    assert config.provider == "openai-compatible"
    assert config.base_url == "https://ai.example.com/v1"
    assert config.api_key == "file-key"
    assert config.text_model == "summary-model"
    assert config.transcribe_provider == "local-faster-whisper"
    assert config.transcribe_base_url == "https://speech.example.com/v1"
    assert config.transcribe_api_key == "speech-key"
    assert config.transcribe_model == "speech-model"
    assert config.transcribe_device == "cuda"
    assert config.transcribe_compute_type == "float16"
    assert config.transcribe_beam_size == 3
    assert config.transcribe_vad_filter is False
    assert config.timeout_seconds == 42.0


def test_ai_config_env_overrides_json_file(monkeypatch, tmp_path):
    clear_ai_env(monkeypatch)
    config_path = tmp_path / "ai.config.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai-compatible",
                "base_url": "https://file.example.com/v1",
                "api_key": "file-key",
                "text_model": "file-summary",
                "transcribe_provider": "local-faster-whisper",
                "transcribe_base_url": "https://file-speech.example.com/v1",
                "transcribe_api_key": "file-speech-key",
                "transcribe_model": "file-speech",
                "transcribe_device": "cpu",
                "transcribe_compute_type": "int8",
                "transcribe_beam_size": 2,
                "transcribe_vad_filter": True,
                "timeout_seconds": 42,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("AI_API_KEY", "env-key")
    monkeypatch.setenv("AI_TEXT_MODEL", "env-summary")
    monkeypatch.setenv("AI_TRANSCRIBE_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AI_TRANSCRIBE_BASE_URL", "https://env-speech.example.com/v1")
    monkeypatch.setenv("AI_TRANSCRIBE_API_KEY", "env-speech-key")
    monkeypatch.setenv("AI_TRANSCRIBE_MODEL", "env-speech")
    monkeypatch.setenv("AI_TRANSCRIBE_DEVICE", "cuda")
    monkeypatch.setenv("AI_TRANSCRIBE_COMPUTE_TYPE", "float16")
    monkeypatch.setenv("AI_TRANSCRIBE_BEAM_SIZE", "4")
    monkeypatch.setenv("AI_TRANSCRIBE_VAD_FILTER", "false")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "12.5")

    config = load_ai_provider_config()

    assert config.provider == "mock"
    assert config.base_url == "https://env.example.com/v1"
    assert config.api_key == "env-key"
    assert config.text_model == "env-summary"
    assert config.transcribe_provider == "openai-compatible"
    assert config.transcribe_base_url == "https://env-speech.example.com/v1"
    assert config.transcribe_api_key == "env-speech-key"
    assert config.transcribe_model == "env-speech"
    assert config.transcribe_device == "cuda"
    assert config.transcribe_compute_type == "float16"
    assert config.transcribe_beam_size == 4
    assert config.transcribe_vad_filter is False
    assert config.timeout_seconds == 12.5
