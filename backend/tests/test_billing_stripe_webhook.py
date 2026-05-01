import json

from fastapi.testclient import TestClient

from app import billing_routes
from app.main import app
from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import get_membership


class FakeStripeWebhook:
    calls = 0

    @staticmethod
    def construct_event(payload, sig_header, secret):
        FakeStripeWebhook.calls += 1
        if sig_header != "valid":
            raise ValueError("bad signature")
        return json.loads(payload)


def test_webhook_rejects_bad_signature(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    database.initialize_database(tmp_path / "saveany.db")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)

    response = client.post(
        "/api/billing/webhook",
        content=json.dumps({"id": "evt_bad", "type": "customer.subscription.updated"}),
        headers={"Stripe-Signature": "invalid"},
    )

    assert response.status_code == 400


def test_subscription_updated_webhook_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("stripe@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": False,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_123"}}]},
            }
        },
    }

    first = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )
    second = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    membership = get_membership(user.id)
    assert membership.active is True
    with database.connect(tmp_path / "saveany.db") as conn:
        events = conn.execute("select count(*) as count from stripe_events").fetchone()
    assert events["count"] == 1
