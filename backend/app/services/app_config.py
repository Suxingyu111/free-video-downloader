from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.env_file import bool_env_value, env_value, load_project_env_values


PROJECT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_DIR / "runtime"


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


def _project_relative_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


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
    trust_proxy_headers: bool
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
    file_values = load_project_env_values()

    def config_value(name: str, default: str = "") -> str:
        return env_value(name, default, file_values=file_values)

    environment = config_value("SAVEANY_ENV", "development").strip().lower()
    if environment not in {"development", "production"}:
        raise ValueError("SAVEANY_ENV must be one of: development, production")
    raw_billing_mode = config_value("BILLING_MODE", "stripe").strip().lower()
    if raw_billing_mode == "mock" and environment != "production":
        # Legacy local shells may still export BILLING_MODE=mock after mock billing was removed.
        billing_mode = "stripe"
    else:
        billing_mode = raw_billing_mode
    if billing_mode != "stripe":
        raise ValueError("BILLING_MODE must be stripe")
    allowed_origins_value = config_value("SAVEANY_ALLOWED_ORIGINS")
    if not allowed_origins_value and environment != "production":
        allowed_origins_value = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_origins = _split_csv(allowed_origins_value)
    session_cookie_name = config_value(
        "SAVEANY_SESSION_COOKIE",
        "__Host-saveany_session" if environment == "production" else "saveany_session",
    )
    config = AppConfig(
        environment=environment,
        db_path=_project_relative_path(config_value("SAVEANY_DB_PATH", str(RUNTIME_DIR / "saveany.db"))),
        billing_mode=billing_mode,
        dev_mode=bool_env_value("SAVEANY_DEV_MODE", False, file_values=file_values),
        auth_rate_limit_attempts=int(config_value("AUTH_RATE_LIMIT_ATTEMPTS", "5")),
        auth_rate_limit_window_seconds=int(config_value("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")),
        free_summary_daily_limit=int(config_value("FREE_SUMMARY_DAILY_LIMIT", "3")),
        allowed_origins=allowed_origins,
        password_reset_token_minutes=int(config_value("PASSWORD_RESET_TOKEN_MINUTES", "30")),
        session_cookie_name=session_cookie_name,
        session_days=int(config_value("SAVEANY_SESSION_DAYS", "30")),
        session_idle_days=int(config_value("SAVEANY_SESSION_IDLE_DAYS", "7")),
        secure_cookies=bool_env_value("SAVEANY_SECURE_COOKIES", False, file_values=file_values),
        trust_proxy_headers=bool_env_value("SAVEANY_TRUST_PROXY_HEADERS", False, file_values=file_values),
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
