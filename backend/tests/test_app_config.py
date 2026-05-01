from __future__ import annotations

from app.services.app_config import load_config


APP_CONFIG_ENV_KEYS = [
    "BILLING_MODE",
    "PUBLIC_APP_URL",
    "STRIPE_CONFIG_FILE",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRO_MONTHLY_PRICE_ID",
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
