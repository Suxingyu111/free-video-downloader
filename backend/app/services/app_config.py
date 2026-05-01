from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_DIR / "runtime"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    billing_mode: str
    free_summary_daily_limit: int
    session_cookie_name: str
    session_days: int
    secure_cookies: bool
    public_app_url: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_pro_monthly_price_id: str


def load_config() -> AppConfig:
    billing_mode = os.getenv("BILLING_MODE", "mock").strip().lower()
    if billing_mode not in {"mock", "stripe"}:
        raise ValueError("BILLING_MODE must be one of: mock, stripe")
    return AppConfig(
        db_path=Path(os.getenv("SAVEANY_DB_PATH", RUNTIME_DIR / "saveany.db")),
        billing_mode=billing_mode,
        free_summary_daily_limit=int(os.getenv("FREE_SUMMARY_DAILY_LIMIT", "3")),
        session_cookie_name=os.getenv("SAVEANY_SESSION_COOKIE", "saveany_session"),
        session_days=int(os.getenv("SAVEANY_SESSION_DAYS", "30")),
        secure_cookies=_bool_env("SAVEANY_SECURE_COOKIES", False),
        public_app_url=os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/"),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        stripe_pro_monthly_price_id=os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
    )
