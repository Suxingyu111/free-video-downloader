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


def test_mock_billing_routes_are_not_registered(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    schema = client.get("/openapi.json").json()
    assert not any(path.startswith("/api/billing/mock") for path in schema["paths"])

    for path in [
        "/api/billing/mock/activate",
        "/api/billing/mock/cancel",
        "/api/billing/mock/expire",
        "/api/billing/mock/payment-failed",
        "/api/billing/mock/credit-pack/summary_small",
    ]:
        response = client.post(path, headers=headers)
        assert response.status_code in {404, 405}


def test_subscription_checkout_requires_stripe_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.delenv("BILLING_MODE", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRO_MONTHLY_PRICE_ID", raising=False)
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    checkout = client.post("/api/billing/checkout", headers=headers)

    assert checkout.status_code == 503
    assert checkout.json()["detail"] == "Stripe 支付尚未配置"


def test_credit_pack_checkout_requires_stripe_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.delenv("BILLING_MODE", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", raising=False)
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    checkout = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
        headers=headers,
    )

    assert checkout.status_code == 503
    assert checkout.json()["detail"] == "Stripe 按量包支付尚未配置"


def test_membership_inactive_after_period_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    with transaction(tmp_path / "saveany.db") as conn:
        user = conn.execute("select id from users where email = 'member@example.com'").fetchone()
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, current_period_start, current_period_end,
             cancel_at_period_end, created_at, updated_at)
            values ('expired_sub', ?, 'pro', 'active',
                    strftime('%s', 'now') - 2592000,
                    strftime('%s', 'now') - 1,
                    0, strftime('%s', 'now'), strftime('%s', 'now'))
            """,
            (user["id"],),
        )

    status = client.get("/api/billing/status")
    assert status.status_code == 200
    assert status.json()["membership"]["plan"] == "pro"
    assert status.json()["membership"]["status"] == "active"
    assert status.json()["membership"]["active"] is False


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


def test_unknown_credit_pack_returns_400(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = _login(client)

    checkout_response = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "missing_pack"},
        headers=headers,
    )

    assert checkout_response.status_code == 400
