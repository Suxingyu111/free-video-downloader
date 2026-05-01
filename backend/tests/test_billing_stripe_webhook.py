import json
from time import time

from fastapi.testclient import TestClient

from app import billing_routes
from app.main import app
from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import get_membership
from app.services.database import transaction


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
    conn = database.connect(tmp_path / "saveany.db")
    try:
        events = conn.execute("select count(*) as count from stripe_events").fetchone()
        event_row = conn.execute(
            "select status from stripe_events where event_id = 'evt_1'"
        ).fetchone()
        subscription = conn.execute(
            """
            select stripe_customer_id, stripe_subscription_id, stripe_price_id, status
            from subscriptions where user_id = ?
            """,
            (user.id,),
        ).fetchone()
    finally:
        conn.close()
    assert events["count"] == 1
    assert event_row["status"] == "processed"
    assert subscription["stripe_customer_id"] == "cus_123"
    assert subscription["stripe_subscription_id"] == "sub_123"
    assert subscription["stripe_price_id"] == "price_123"
    assert subscription["status"] == "active"


def test_webhook_processing_failure_keeps_event_retryable(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("retry@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    original_upsert = billing_routes.upsert_stripe_subscription
    calls = {"count": 0}

    def flaky_upsert(subscription):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary database failure")
        return original_upsert(subscription)

    monkeypatch.setattr(billing_routes, "upsert_stripe_subscription", flaky_upsert)
    client = TestClient(app, raise_server_exceptions=False)
    event = {
        "id": "evt_retry",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_retry",
                "customer": "cus_retry",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": False,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_retry"}}]},
            }
        },
    }

    first = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )
    retry = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )

    assert first.status_code == 500
    assert retry.status_code == 200
    assert calls["count"] == 2
    membership = get_membership(user.id)
    assert membership.active is True
    conn = database.connect(tmp_path / "saveany.db")
    try:
        event_row = conn.execute(
            "select status, processed_at from stripe_events where event_id = 'evt_retry'"
        ).fetchone()
    finally:
        conn.close()
    assert event_row["status"] == "processed"
    assert event_row["processed_at"] > 0


def test_existing_subscription_cannot_be_reassigned_by_webhook_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    database.initialize_database(tmp_path / "saveany.db")
    original_user = create_user("owner-a@example.com", "stripe-password")
    metadata_user = create_user("owner-b@example.com", "stripe-password")
    now = time()
    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
             stripe_price_id, current_period_start, current_period_end,
             cancel_at_period_end, created_at, updated_at)
            values (?, ?, 'pro', 'active', 'cus_original', 'sub_existing',
                    'price_old', ?, ?, 0, ?, ?)
            """,
            ("local_sub", original_user.id, now - 100, now + 100, now, now),
        )
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_owner",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_existing",
                "customer": "cus_changed",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": True,
                "metadata": {"saveany_user_id": metadata_user.id},
                "items": {"data": [{"price": {"id": "price_new"}}]},
            }
        },
    }

    response = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )

    assert response.status_code == 200
    assert get_membership(original_user.id).active is True
    assert get_membership(metadata_user.id).active is False
    conn = database.connect(tmp_path / "saveany.db")
    try:
        subscription = conn.execute(
            """
            select user_id, stripe_customer_id, stripe_price_id, cancel_at_period_end
            from subscriptions where stripe_subscription_id = 'sub_existing'
            """
        ).fetchone()
    finally:
        conn.close()
    assert subscription["user_id"] == original_user.id
    assert subscription["stripe_customer_id"] == "cus_changed"
    assert subscription["stripe_price_id"] == "price_new"
    assert subscription["cancel_at_period_end"] == 1
