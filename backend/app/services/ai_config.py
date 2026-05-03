from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.env_file import load_project_env_values

AI_ENV_MAPPING = {
    "AI_PROVIDER": "provider",
    "AI_BASE_URL": "base_url",
    "AI_API_KEY": "api_key",
    "AI_TEXT_MODEL": "text_model",
    "AI_TRANSCRIBE_PROVIDER": "transcribe_provider",
    "AI_TRANSCRIBE_BASE_URL": "transcribe_base_url",
    "AI_TRANSCRIBE_API_KEY": "transcribe_api_key",
    "AI_TRANSCRIBE_MODEL": "transcribe_model",
    "AI_TRANSCRIBE_DEVICE": "transcribe_device",
    "AI_TRANSCRIBE_COMPUTE_TYPE": "transcribe_compute_type",
    "AI_TRANSCRIBE_BEAM_SIZE": "transcribe_beam_size",
    "AI_TRANSCRIBE_VAD_FILTER": "transcribe_vad_filter",
    "AI_TIMEOUT_SECONDS": "timeout_seconds",
}


@dataclass(frozen=True)
class AIProviderConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    text_model: str = "gpt-4o-mini"
    transcribe_provider: str = "openai-compatible"
    transcribe_base_url: str = ""
    transcribe_api_key: str = ""
    transcribe_model: str = "gpt-4o-mini-transcribe"
    transcribe_device: str = "cpu"
    transcribe_compute_type: str = "int8"
    transcribe_beam_size: int = 5
    transcribe_vad_filter: bool = True
    timeout_seconds: float = 120.0
    provider: str = "openai-compatible"


def load_ai_provider_config(config_path: Path | None = None) -> AIProviderConfig:
    values = {
        "provider": AIProviderConfig.provider,
        "base_url": AIProviderConfig.base_url,
        "api_key": AIProviderConfig.api_key,
        "text_model": AIProviderConfig.text_model,
        "transcribe_provider": AIProviderConfig.transcribe_provider,
        "transcribe_base_url": AIProviderConfig.transcribe_base_url,
        "transcribe_api_key": AIProviderConfig.transcribe_api_key,
        "transcribe_model": AIProviderConfig.transcribe_model,
        "transcribe_device": AIProviderConfig.transcribe_device,
        "transcribe_compute_type": AIProviderConfig.transcribe_compute_type,
        "transcribe_beam_size": AIProviderConfig.transcribe_beam_size,
        "transcribe_vad_filter": AIProviderConfig.transcribe_vad_filter,
        "timeout_seconds": AIProviderConfig.timeout_seconds,
    }

    legacy_config_file = config_path or _explicit_legacy_config_path()
    if legacy_config_file is not None:
        _apply_config_values(values, _load_config_file(legacy_config_file))

    env_file_values = load_project_env_values()
    _apply_env_values(values, env_file_values)
    _apply_env_values(values, os.environ)

    return AIProviderConfig(**values)


def _explicit_legacy_config_path() -> Path | None:
    raw = os.getenv("AI_CONFIG_FILE")
    if not raw:
        return None
    return Path(raw)


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 配置文件格式错误：{path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"AI 配置文件必须是 JSON 对象：{path}")
    return payload


def _apply_config_values(values: dict[str, Any], raw_values: dict[str, Any]) -> None:
    for key in AIProviderConfig.__dataclass_fields__:
        if key in raw_values:
            _assign_config_value(values, key, raw_values[key])


def _apply_env_values(values: dict[str, Any], raw_values) -> None:
    for env_key, key in AI_ENV_MAPPING.items():
        if env_key in raw_values:
            _assign_config_value(values, key, raw_values[env_key])


def _assign_config_value(values: dict[str, Any], key: str, raw_value: Any) -> None:
    if key == "transcribe_beam_size":
        values[key] = _coerce_int(raw_value, values[key])
        return
    if key == "transcribe_vad_filter":
        values[key] = _coerce_bool(raw_value, values[key])
        return
    if key == "timeout_seconds":
        values[key] = _coerce_timeout(raw_value, values[key])
        return
    value = str(raw_value or "").strip()
    if not value:
        return
    if key in {"base_url", "transcribe_base_url"}:
        value = value.rstrip("/")
    values[key] = value


def _coerce_timeout(value: Any, default: float) -> float:
    if value in {None, ""}:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("AI_TIMEOUT_SECONDS 必须是数字。") from exc


def _coerce_int(value: Any, default: int) -> int:
    if value in {None, ""}:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("AI_TRANSCRIBE_BEAM_SIZE 必须是整数。") from exc


def _coerce_bool(value: Any, default: bool) -> bool:
    if value in {None, ""}:
        return bool(default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError("AI_TRANSCRIBE_VAD_FILTER 必须是布尔值。")
