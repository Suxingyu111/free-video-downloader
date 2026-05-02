from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_DIR / "runtime"
DEFAULT_STRIPE_CONFIG_FILE = BACKEND_DIR / "config" / "stripe.env"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise RuntimeError(f"Stripe 配置文件第 {line_number} 行缺少 '='：{path}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError(f"Stripe 配置文件第 {line_number} 行缺少配置名：{path}")
        values[key] = _strip_optional_quotes(value.strip())
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class AppConfig:
    environment: str
    db_path: Path
    billing_mode: str
    dev_mode: bool
    auth_rate_limit_attempts: int
    auth_rate_limit_window_seconds: int
    free_summary_daily_limit: int
    allowed_origins: tuple[str, ...]
    password_reset_token_minutes: int
    session_cookie_name: str
    session_days: int
    session_idle_days: int
    secure_cookies: bool
    public_app_url: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_pro_monthly_price_id: str
    stripe_summary_small_pack_price_id: str
    stripe_summary_large_pack_price_id: str
    stripe_transcription_small_pack_price_id: str
    stripe_transcription_large_pack_price_id: str
    ip_hash_salt: str


def _validate_production_config(config: AppConfig) -> None:
    if config.environment != "production":
        return
    if not config.secure_cookies:
        raise ValueError("SAVEANY_SECURE_COOKIES must be true when SAVEANY_ENV=production")
    if config.dev_mode:
        raise ValueError("SAVEANY_DEV_MODE must be false when SAVEANY_ENV=production")
    if config.billing_mode == "mock":
        raise ValueError("BILLING_MODE=mock is not allowed when SAVEANY_ENV=production")
    if not config.public_app_url.startswith("https://"):
        raise ValueError("PUBLIC_APP_URL must start with https:// when SAVEANY_ENV=production")
    if not config.allowed_origins or "*" in config.allowed_origins:
        raise ValueError("SAVEANY_ALLOWED_ORIGINS must be explicitly configured without '*' in production")
    if not config.stripe_secret_key:
        raise ValueError("STRIPE_SECRET_KEY is required when SAVEANY_ENV=production")
    if not config.stripe_webhook_secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is required when SAVEANY_ENV=production")
    if not config.stripe_pro_monthly_price_id:
        raise ValueError("STRIPE_PRO_MONTHLY_PRICE_ID is required when SAVEANY_ENV=production")


def load_config() -> AppConfig:
    stripe_config_file = Path(os.getenv("STRIPE_CONFIG_FILE", DEFAULT_STRIPE_CONFIG_FILE))
    file_values = _load_env_file(stripe_config_file)

    def config_value(name: str, default: str = "") -> str:
        return os.getenv(name, file_values.get(name, default))

    environment = config_value("SAVEANY_ENV", "development").strip().lower()
    billing_mode = config_value("BILLING_MODE", "mock").strip().lower()
    if billing_mode not in {"mock", "stripe"}:
        raise ValueError("BILLING_MODE must be one of: mock, stripe")
    allowed_origins_value = config_value("SAVEANY_ALLOWED_ORIGINS")
    if not allowed_origins_value and environment != "production":
        allowed_origins_value = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_origins = _split_csv(allowed_origins_value)
    session_cookie_name = os.getenv(
        "SAVEANY_SESSION_COOKIE",
        "__Host-saveany_session" if environment == "production" else "saveany_session",
    )
    config = AppConfig(
        environment=environment,
        db_path=Path(os.getenv("SAVEANY_DB_PATH", RUNTIME_DIR / "saveany.db")),
        billing_mode=billing_mode,
        dev_mode=_bool_env("SAVEANY_DEV_MODE", False),
        auth_rate_limit_attempts=int(os.getenv("AUTH_RATE_LIMIT_ATTEMPTS", "5")),
        auth_rate_limit_window_seconds=int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")),
        free_summary_daily_limit=int(os.getenv("FREE_SUMMARY_DAILY_LIMIT", "3")),
        allowed_origins=allowed_origins,
        password_reset_token_minutes=int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30")),
        session_cookie_name=session_cookie_name,
        session_days=int(os.getenv("SAVEANY_SESSION_DAYS", "30")),
        session_idle_days=int(os.getenv("SAVEANY_SESSION_IDLE_DAYS", "30")),
        secure_cookies=_bool_env("SAVEANY_SECURE_COOKIES", False),
        public_app_url=config_value("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/"),
        stripe_secret_key=config_value("STRIPE_SECRET_KEY").strip(),
        stripe_webhook_secret=config_value("STRIPE_WEBHOOK_SECRET").strip(),
        stripe_pro_monthly_price_id=config_value("STRIPE_PRO_MONTHLY_PRICE_ID").strip(),
        stripe_summary_small_pack_price_id=config_value("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID").strip(),
        stripe_summary_large_pack_price_id=config_value("STRIPE_SUMMARY_LARGE_PACK_PRICE_ID").strip(),
        stripe_transcription_small_pack_price_id=config_value("STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID").strip(),
        stripe_transcription_large_pack_price_id=config_value("STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID").strip(),
        ip_hash_salt=config_value("SAVEANY_IP_HASH_SALT", "saveany-local-ip-meter").strip(),
    )
    _validate_production_config(config)
    return config
