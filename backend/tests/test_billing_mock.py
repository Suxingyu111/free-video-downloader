from fastapi.testclient import TestClient

from app.main import app
from app.services import database


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
