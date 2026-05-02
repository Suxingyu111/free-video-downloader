from __future__ import annotations

import pytest

from app.services.app_config import load_config


APP_CONFIG_ENV_KEYS = [
    "AUTH_RATE_LIMIT_ATTEMPTS",
    "AUTH_RATE_LIMIT_WINDOW_SECONDS",
    "BILLING_MODE",
    "FREE_SUMMARY_DAILY_LIMIT",
    "PUBLIC_APP_URL",
    "SAVEANY_ALLOWED_ORIGINS",
    "SAVEANY_DB_PATH",
    "SAVEANY_DEV_MODE",
    "SAVEANY_ENV",
    "SAVEANY_IP_HASH_SALT",
    "SAVEANY_SECURE_COOKIES",
    "SAVEANY_SESSION_COOKIE",
    "SAVEANY_SESSION_DAYS",
    "SAVEANY_SESSION_IDLE_DAYS",
    "STRIPE_CONFIG_FILE",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRO_MONTHLY_PRICE_ID",
    "PASSWORD_RESET_TOKEN_MINUTES",
]


def clear_app_config_env(monkeypatch):
    for key in APP_CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_load_config_reads_stripe_env_file(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    config_path = tmp_path / "stripe.env"
    config_path.write_text(
        """
        # Local Stripe test settings
        BILLING_MODE=stripe
        PUBLIC_APP_URL=http://127.0.0.1:5173/
        STRIPE_SECRET_KEY=sk_test_file
        STRIPE_WEBHOOK_SECRET=whsec_file
        STRIPE_PRO_MONTHLY_PRICE_ID=price_file
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(config_path))

    config = load_config()

    assert config.billing_mode == "stripe"
    assert config.public_app_url == "http://127.0.0.1:5173"
    assert config.stripe_secret_key == "sk_test_file"
    assert config.stripe_webhook_secret == "whsec_file"
    assert config.stripe_pro_monthly_price_id == "price_file"


def test_load_config_env_overrides_stripe_env_file(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    config_path = tmp_path / "stripe.env"
    config_path.write_text(
        """
        BILLING_MODE=mock
        PUBLIC_APP_URL=http://file.example.test
        STRIPE_SECRET_KEY=sk_test_file
        STRIPE_WEBHOOK_SECRET=whsec_file
        STRIPE_PRO_MONTHLY_PRICE_ID=price_file
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("PUBLIC_APP_URL", "http://env.example.test/")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_env")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_env")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_env")

    config = load_config()

    assert config.billing_mode == "stripe"
    assert config.public_app_url == "http://env.example.test"
    assert config.stripe_secret_key == "sk_test_env"
    assert config.stripe_webhook_secret == "whsec_env"
    assert config.stripe_pro_monthly_price_id == "price_env"


def test_load_config_reads_complete_production_config_from_file(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    config_path = tmp_path / "stripe.env"
    config_path.write_text(
        """
        SAVEANY_ENV=production
        SAVEANY_SECURE_COOKIES=true
        SAVEANY_DEV_MODE=false
        SAVEANY_ALLOWED_ORIGINS=https://app.example.com/
        SAVEANY_SESSION_COOKIE=custom_session
        PASSWORD_RESET_TOKEN_MINUTES=45
        SAVEANY_SESSION_IDLE_DAYS=5
        SAVEANY_SESSION_DAYS=14
        SAVEANY_DB_PATH=/tmp/saveany-prod.db
        SAVEANY_IP_HASH_SALT=file-salt
        AUTH_RATE_LIMIT_ATTEMPTS=9
        AUTH_RATE_LIMIT_WINDOW_SECONDS=120
        FREE_SUMMARY_DAILY_LIMIT=2
        BILLING_MODE=stripe
        PUBLIC_APP_URL=https://app.example.com/
        STRIPE_SECRET_KEY=sk_live_file
        STRIPE_WEBHOOK_SECRET=whsec_live_file
        STRIPE_PRO_MONTHLY_PRICE_ID=price_live_file
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(config_path))

    config = load_config()

    assert config.environment == "production"
    assert config.secure_cookies is True
    assert config.dev_mode is False
    assert config.allowed_origins == ("https://app.example.com",)
    assert config.session_cookie_name == "custom_session"
    assert config.password_reset_token_minutes == 45
    assert config.session_idle_days == 5
    assert config.session_days == 14
    assert str(config.db_path) == "/tmp/saveany-prod.db"
    assert config.ip_hash_salt == "file-salt"
    assert config.auth_rate_limit_attempts == 9
    assert config.auth_rate_limit_window_seconds == 120
    assert config.free_summary_daily_limit == 2
    assert config.billing_mode == "stripe"
    assert config.public_app_url == "https://app.example.com"
    assert config.stripe_secret_key == "sk_live_file"
    assert config.stripe_webhook_secret == "whsec_live_file"
    assert config.stripe_pro_monthly_price_id == "price_live_file"


def test_app_config_loads_credit_pack_price_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    monkeypatch.setenv("STRIPE_SUMMARY_LARGE_PACK_PRICE_ID", "price_summary_large")
    monkeypatch.setenv("STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID", "price_transcription_small")
    monkeypatch.setenv("STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID", "price_transcription_large")
    monkeypatch.setenv("SAVEANY_IP_HASH_SALT", "test-salt")

    config = load_config()

    assert config.stripe_summary_small_pack_price_id == "price_summary_small"
    assert config.stripe_summary_large_pack_price_id == "price_summary_large"
    assert config.stripe_transcription_small_pack_price_id == "price_transcription_small"
    assert config.stripe_transcription_large_pack_price_id == "price_transcription_large"
    assert config.ip_hash_salt == "test-salt"


def test_production_requires_secure_cookies(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "false")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.com")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live_test")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_live_test")

    with pytest.raises(ValueError, match="SAVEANY_SECURE_COOKIES"):
        load_config()


def test_rejects_invalid_saveany_env(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "staging")

    with pytest.raises(ValueError, match="SAVEANY_ENV"):
        load_config()


def test_production_rejects_dev_mode_and_mock_billing(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    monkeypatch.setenv("BILLING_MODE", "mock")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.com")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live_test")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_live_test")

    with pytest.raises(ValueError, match="SAVEANY_DEV_MODE"):
        load_config()

    monkeypatch.setenv("SAVEANY_DEV_MODE", "false")
    with pytest.raises(ValueError, match="BILLING_MODE"):
        load_config()


def test_production_requires_https_public_app_url(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("PUBLIC_APP_URL", "http://app.example.com")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live_test")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_live_test")

    with pytest.raises(ValueError, match="PUBLIC_APP_URL"):
        load_config()


def test_production_requires_explicit_allowed_origins_without_wildcard(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.com")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live_test")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_live_test")

    with pytest.raises(ValueError, match="SAVEANY_ALLOWED_ORIGINS"):
        load_config()

    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://app.example.com,*")
    with pytest.raises(ValueError, match="SAVEANY_ALLOWED_ORIGINS"):
        load_config()


def test_allowed_origins_trim_whitespace_and_trailing_slashes(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", " https://app.example.com/ , http://localhost:5173/ ")

    config = load_config()

    assert config.allowed_origins == ("https://app.example.com", "http://localhost:5173")


def test_production_requires_stripe_config_and_defaults_to_host_session_cookie(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.com")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://app.example.com")

    with pytest.raises(ValueError, match="STRIPE_SECRET_KEY"):
        load_config()

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
        load_config()

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live_test")
    with pytest.raises(ValueError, match="STRIPE_PRO_MONTHLY_PRICE_ID"):
        load_config()

    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_live_test")
    config = load_config()

    assert config.session_cookie_name == "__Host-saveany_session"


def test_development_defaults_include_allowed_origins_and_session_idle_days(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))

    config = load_config()

    assert config.environment == "development"
    assert config.billing_mode == "mock"
    assert config.public_app_url == "http://localhost:5173"
    assert config.allowed_origins == ("http://localhost:5173", "http://127.0.0.1:5173")
    assert config.secure_cookies is False
    assert config.password_reset_token_minutes == 30
    assert config.session_cookie_name == "saveany_session"
    assert config.session_idle_days == 7
