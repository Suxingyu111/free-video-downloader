from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def project_env_path() -> Path:
    configured = os.getenv("SAVEANY_ENV_FILE", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_ENV_FILE


def load_project_env_values(path: Path | None = None) -> dict[str, str]:
    env_path = path or project_env_path()
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise RuntimeError(f".env 配置文件第 {line_number} 行缺少 '='：{env_path}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError(f".env 配置文件第 {line_number} 行缺少配置名：{env_path}")
        values[key] = strip_optional_quotes(value.strip())
    return values


def strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def env_value(name: str, default: str = "", *, file_values: dict[str, str] | None = None) -> str:
    values = file_values if file_values is not None else load_project_env_values()
    return os.getenv(name, values.get(name, default))


def bool_env_value(name: str, default: bool = False, *, file_values: dict[str, str] | None = None) -> bool:
    raw = env_value(name, "true" if default else "false", file_values=file_values)
    return raw.strip().lower() in TRUE_VALUES


def bool_env_enabled(name: str, default: bool = False, *, file_values: dict[str, str] | None = None) -> bool:
    raw = env_value(name, "true" if default else "false", file_values=file_values)
    return raw.strip().lower() not in FALSE_VALUES if default else raw.strip().lower() in TRUE_VALUES
