from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_AI_CONFIG_FILE = BACKEND_DIR / "config" / "ai.config.json"


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
    path = config_path or Path(os.getenv("AI_CONFIG_FILE", DEFAULT_AI_CONFIG_FILE))
    file_values = _load_config_file(path)
    values = {
        "provider": str(file_values.get("provider") or AIProviderConfig.provider).strip() or AIProviderConfig.provider,
        "base_url": str(file_values.get("base_url") or AIProviderConfig.base_url).strip().rstrip("/"),
        "api_key": str(file_values.get("api_key") or AIProviderConfig.api_key).strip(),
        "text_model": str(file_values.get("text_model") or AIProviderConfig.text_model).strip() or AIProviderConfig.text_model,
        "transcribe_provider": str(file_values.get("transcribe_provider") or AIProviderConfig.transcribe_provider).strip()
        or AIProviderConfig.transcribe_provider,
        "transcribe_base_url": str(file_values.get("transcribe_base_url") or AIProviderConfig.transcribe_base_url).strip().rstrip("/"),
        "transcribe_api_key": str(file_values.get("transcribe_api_key") or AIProviderConfig.transcribe_api_key).strip(),
        "transcribe_model": str(file_values.get("transcribe_model") or AIProviderConfig.transcribe_model).strip()
        or AIProviderConfig.transcribe_model,
        "transcribe_device": str(file_values.get("transcribe_device") or AIProviderConfig.transcribe_device).strip()
        or AIProviderConfig.transcribe_device,
        "transcribe_compute_type": str(file_values.get("transcribe_compute_type") or AIProviderConfig.transcribe_compute_type).strip()
        or AIProviderConfig.transcribe_compute_type,
        "transcribe_beam_size": _coerce_int(file_values.get("transcribe_beam_size"), AIProviderConfig.transcribe_beam_size),
        "transcribe_vad_filter": _coerce_bool(file_values.get("transcribe_vad_filter"), AIProviderConfig.transcribe_vad_filter),
        "timeout_seconds": _coerce_timeout(file_values.get("timeout_seconds"), AIProviderConfig.timeout_seconds),
    }

    _override_from_env(values, "provider", "AI_PROVIDER")
    _override_from_env(values, "base_url", "AI_BASE_URL", strip_trailing_slash=True)
    _override_from_env(values, "api_key", "AI_API_KEY")
    _override_from_env(values, "text_model", "AI_TEXT_MODEL")
    _override_from_env(values, "transcribe_provider", "AI_TRANSCRIBE_PROVIDER")
    _override_from_env(values, "transcribe_base_url", "AI_TRANSCRIBE_BASE_URL", strip_trailing_slash=True)
    _override_from_env(values, "transcribe_api_key", "AI_TRANSCRIBE_API_KEY")
    _override_from_env(values, "transcribe_model", "AI_TRANSCRIBE_MODEL")
    _override_from_env(values, "transcribe_device", "AI_TRANSCRIBE_DEVICE")
    _override_from_env(values, "transcribe_compute_type", "AI_TRANSCRIBE_COMPUTE_TYPE")
    if os.getenv("AI_TRANSCRIBE_BEAM_SIZE"):
        values["transcribe_beam_size"] = _coerce_int(os.getenv("AI_TRANSCRIBE_BEAM_SIZE"), values["transcribe_beam_size"])
    if os.getenv("AI_TRANSCRIBE_VAD_FILTER"):
        values["transcribe_vad_filter"] = _coerce_bool(
            os.getenv("AI_TRANSCRIBE_VAD_FILTER"),
            values["transcribe_vad_filter"],
        )
    if os.getenv("AI_TIMEOUT_SECONDS"):
        values["timeout_seconds"] = _coerce_timeout(os.getenv("AI_TIMEOUT_SECONDS"), values["timeout_seconds"])

    return AIProviderConfig(**values)


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


def _override_from_env(
    values: dict[str, Any],
    key: str,
    env_key: str,
    *,
    strip_trailing_slash: bool = False,
) -> None:
    raw = os.getenv(env_key)
    if raw is None:
        return
    value = raw.strip()
    if strip_trailing_slash:
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
