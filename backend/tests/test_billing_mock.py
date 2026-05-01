from fastapi.testclient import TestClient

from app.main import app
from app.services import database
from app.services.database import transaction


def _login(client):
    client.post(
        "/api/auth/register",
        json={"email": "member@example.com", "password": "member-password"},
    )


def test_mock_checkout_activates_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    checkout = client.post("/api/billing/checkout")
    assert checkout.status_code == 200
    assert checkout.json()["mode"] == "mock"
    assert checkout.json()["url"].endswith("#pricing")

    activated = client.post("/api/billing/mock/activate")
    assert activated.status_code == 200
    assert activated.json()["membership"]["active"] is True
    assert activated.json()["membership"]["plan"] == "pro"

    me = client.get("/api/me").json()
    assert me["membership"]["active"] is True


def test_mock_cancel_and_expire_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    client.post("/api/billing/mock/activate")

    canceled = client.post("/api/billing/mock/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["membership"]["cancel_at_period_end"] is True
    assert canceled.json()["membership"]["active"] is True

    expired = client.post("/api/billing/mock/expire")
    assert expired.status_code == 200
    assert expired.json()["membership"]["active"] is False
    assert expired.json()["membership"]["status"] == "canceled"


def test_membership_inactive_after_period_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    client.post("/api/billing/mock/activate")

    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            update subscriptions
            set current_period_end = strftime('%s', 'now') - 1
            where user_id = (select id from users where email = 'member@example.com')
            """
        )

    status = client.get("/api/billing/status")
    assert status.status_code == 200
    assert status.json()["membership"]["plan"] == "pro"
    assert status.json()["membership"]["status"] == "active"
    assert status.json()["membership"]["active"] is False


def test_mock_payment_failed_does_not_update_canceled_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    client.post("/api/billing/mock/activate")
    client.post("/api/billing/mock/expire")

    failed = client.post("/api/billing/mock/payment-failed")
    assert failed.status_code == 200
    assert failed.json()["membership"]["status"] == "canceled"
    assert failed.json()["membership"]["active"] is False


def test_mock_expire_clears_cancel_at_period_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    client.post("/api/billing/mock/activate")
    client.post("/api/billing/mock/cancel")

    expired = client.post("/api/billing/mock/expire")
    assert expired.status_code == 200
    assert expired.json()["membership"]["status"] == "canceled"
    assert expired.json()["membership"]["cancel_at_period_end"] is False


def test_stripe_portal_missing_secret_returns_503(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    with transaction(tmp_path / "saveany.db") as conn:
        user = conn.execute("select id from users where email = 'member@example.com'").fetchone()
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
             current_period_start, current_period_end, cancel_at_period_end,
             created_at, updated_at)
            values ('portal_sub', ?, 'pro', 'active', 'cus_portal', 'sub_portal',
                    strftime('%s', 'now'), strftime('%s', 'now') + 2592000, 0,
                    strftime('%s', 'now'), strftime('%s', 'now'))
            """,
            (user["id"],),
        )

    response = client.post("/api/billing/portal")

    assert response.status_code == 503
    assert response.json()["detail"] == "Stripe 支付尚未配置"
