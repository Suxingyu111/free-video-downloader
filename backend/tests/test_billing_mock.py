from fastapi.testclient import TestClient

from app.main import app
from app.services import database
from app.services.database import transaction


def csrf_headers(client):
    response = client.get("/api/csrf")
    return {"x-csrf-token": response.json()["csrf_token"], "origin": "http://localhost:5173"}


def register_and_get_csrf(client, email="member@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "member-password"},
        headers=csrf_headers(client),
    )
    return {"x-csrf-token": response.json()["csrf_token"], "origin": "http://localhost:5173"}


def _login(client):
    return register_and_get_csrf(client)


def test_mock_billing_requires_session_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    missing = client.post("/api/billing/mock/activate", headers={"Origin": "http://localhost:5173"})
    assert missing.status_code == 403

    activated = client.post("/api/billing/mock/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["membership"]["active"] is True


def test_mock_checkout_activates_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    checkout = client.post("/api/billing/checkout", headers=headers)
    assert checkout.status_code == 200
    assert checkout.json()["mode"] == "mock"
    assert checkout.json()["url"].endswith("#pricing")

    activated = client.post("/api/billing/mock/activate", headers=headers)
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
    headers = _login(client)
    client.post("/api/billing/mock/activate", headers=headers)

    canceled = client.post("/api/billing/mock/cancel", headers=headers)
    assert canceled.status_code == 200
    assert canceled.json()["membership"]["cancel_at_period_end"] is True
    assert canceled.json()["membership"]["active"] is True

    expired = client.post("/api/billing/mock/expire", headers=headers)
    assert expired.status_code == 200
    assert expired.json()["membership"]["active"] is False
    assert expired.json()["membership"]["status"] == "canceled"


def test_membership_inactive_after_period_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)
    client.post("/api/billing/mock/activate", headers=headers)

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
    headers = _login(client)
    client.post("/api/billing/mock/activate", headers=headers)
    client.post("/api/billing/mock/expire", headers=headers)

    failed = client.post("/api/billing/mock/payment-failed", headers=headers)
    assert failed.status_code == 200
    assert failed.json()["membership"]["status"] == "canceled"
    assert failed.json()["membership"]["active"] is False


def test_mock_expire_clears_cancel_at_period_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)
    client.post("/api/billing/mock/activate", headers=headers)
    client.post("/api/billing/mock/cancel", headers=headers)

    expired = client.post("/api/billing/mock/expire", headers=headers)
    assert expired.status_code == 200
    assert expired.json()["membership"]["status"] == "canceled"
    assert expired.json()["membership"]["cancel_at_period_end"] is False


def test_stripe_portal_missing_secret_returns_503(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)
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

    response = client.post("/api/billing/portal", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "Stripe 支付尚未配置"


def test_mock_credit_pack_purchase_grants_balance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    response = client.post("/api/billing/mock/credit-pack/summary_small")
    status = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["credit_pack"]["pack_id"] == "summary_small"
    assert status.json()["credit_packs"]["summary"]["remaining"] == 20


def test_mock_credit_pack_repeat_purchase_stacks_balance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    first = client.post("/api/billing/mock/credit-pack/summary_small")
    second = client.post("/api/billing/mock/credit-pack/summary_small")
    status = client.get("/api/entitlements/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["credit_pack"]["id"] != second.json()["credit_pack"]["id"]
    assert status.json()["credit_packs"]["summary"]["remaining"] == 40


def test_mock_credit_pack_unknown_pack_returns_400(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app, raise_server_exceptions=False)
    headers = _login(client)

    mock_response = client.post("/api/billing/mock/credit-pack/missing_pack")
    checkout_response = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "missing_pack"},
        headers=headers,
    )

    assert mock_response.status_code == 400
    assert checkout_response.status_code == 400
