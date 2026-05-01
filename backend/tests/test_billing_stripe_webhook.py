import hashlib
import json
import pytest
from time import time

from fastapi.testclient import TestClient

from app import billing_routes
from app.main import app
from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import begin_stripe_event_processing, get_membership
from app.services.database import transaction


class FakeStripeWebhook:
    calls = 0

    @staticmethod
    def construct_event(payload, sig_header, secret):
        FakeStripeWebhook.calls += 1
        if sig_header != "valid":
            raise ValueError("bad signature")
        return json.loads(payload)


class FakeStripeCustomer:
    created = []

    @classmethod
    def create(cls, **kwargs):
        cls.created.append(kwargs)
        return type("StripeCustomer", (), {"id": "cus_reused"})()


class FakeStripeCheckoutSession:
    created = []

    @classmethod
    def create(cls, **kwargs):
        cls.created.append(kwargs)
        return type(
            "StripeCheckoutSession",
            (),
            {"id": f"cs_{len(cls.created)}", "url": f"https://checkout.test/{len(cls.created)}"},
        )()


class FakeStripeCheckout:
    Session = FakeStripeCheckoutSession


def _stripe_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_monthly")


def _post_event(client, event):
    return client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )


def test_stripe_checkout_creates_and_reuses_customer(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "checkout@example.com", "password": "checkout-password"},
    )

    first = client.post("/api/billing/checkout")
    second = client.post("/api/billing/checkout")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]
    assert first.json()["url"] == second.json()["url"]
    assert len(FakeStripeCustomer.created) == 1
    assert len(FakeStripeCheckoutSession.created) == 1
    assert FakeStripeCustomer.created[0]["email"] == "checkout@example.com"
    assert FakeStripeCustomer.created[0]["metadata"]["saveany_user_id"]
    assert [call["customer"] for call in FakeStripeCheckoutSession.created] == [
        "cus_reused",
    ]
    assert FakeStripeCheckoutSession.created[0]["client_reference_id"]
    conn = database.connect(tmp_path / "saveany.db")
    try:
        rows = conn.execute(
            """
            select stripe_customer_id, count(*) as count
            from subscriptions
            group by stripe_customer_id
            """
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["stripe_customer_id"] == "cus_reused"
    assert rows[0]["count"] == 1


def test_stripe_checkout_creates_new_session_after_open_attempt_expires(
    monkeypatch, tmp_path
):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "expired-checkout@example.com", "password": "checkout-password"},
    )

    first = client.post("/api/billing/checkout")
    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            update billing_attempts
            set updated_at = updated_at - 3600
            where stripe_checkout_session_id = ?
            """,
            (first.json()["session_id"],),
        )
    second = client.post("/api/billing/checkout")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] != second.json()["session_id"]
    assert first.json()["url"] != second.json()["url"]
    assert len(FakeStripeCustomer.created) == 1
    assert len(FakeStripeCheckoutSession.created) == 2
    conn = database.connect(tmp_path / "saveany.db")
    try:
        attempts = conn.execute(
            """
            select stripe_checkout_session_id, status
            from billing_attempts
            order by created_at
            """
        ).fetchall()
    finally:
        conn.close()
    assert [attempt["stripe_checkout_session_id"] for attempt in attempts] == [
        first.json()["session_id"],
        second.json()["session_id"],
    ]
    assert [attempt["status"] for attempt in attempts] == ["expired", "open"]


def test_stripe_event_processing_claim_blocks_pending_duplicate(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")

    first = begin_stripe_event_processing(
        "evt_lock",
        "customer.subscription.updated",
        b'{"id":"evt_lock"}',
    )

    assert first is True
    with pytest.raises(billing_routes.StripeEventInProgress):
        begin_stripe_event_processing(
            "evt_lock",
            "customer.subscription.updated",
            b'{"id":"evt_lock"}',
        )
    conn = database.connect(tmp_path / "saveany.db")
    try:
        row = conn.execute(
            "select status, processed_at from stripe_events where event_id = 'evt_lock'"
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "processing"
    assert row["processed_at"] == 0


def test_webhook_duplicate_during_processing_is_retryable_without_processing(
    monkeypatch, tmp_path
):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("inflight@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_inflight",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_inflight",
                "customer": "cus_inflight",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": False,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_inflight"}}]},
            }
        },
    }
    payload = json.dumps(event).encode()
    assert begin_stripe_event_processing(event["id"], event["type"], payload) is True

    duplicate = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": "valid"},
    )

    assert duplicate.status_code == 409
    assert get_membership(user.id).active is False
    conn = database.connect(tmp_path / "saveany.db")
    try:
        subscription = conn.execute(
            """
            select id from subscriptions
            where stripe_subscription_id = 'sub_inflight'
            """
        ).fetchone()
        event_row = conn.execute(
            """
            select status, processed_at from stripe_events
            where event_id = 'evt_inflight'
            """
        ).fetchone()
    finally:
        conn.close()
    assert subscription is None
    assert event_row["status"] == "processing"
    assert event_row["processed_at"] == 0


def test_webhook_reclaims_stale_processing_event(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("stale@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_stale",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_stale",
                "customer": "cus_stale",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": False,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_stale"}}]},
            }
        },
    }
    payload = json.dumps(event).encode()
    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into stripe_events
            (event_id, event_type, status, processed_at, payload_hash, processing_started_at)
            values (?, ?, 'processing', 0, ?, ?)
            """,
            (
                event["id"],
                event["type"],
                hashlib.sha256(payload).hexdigest(),
                time() - 1000,
            ),
        )

    response = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": "valid"},
    )

    assert response.status_code == 200
    assert get_membership(user.id).active is True
    conn = database.connect(tmp_path / "saveany.db")
    try:
        event_row = conn.execute(
            """
            select status, processed_at from stripe_events
            where event_id = 'evt_stale'
            """
        ).fetchone()
    finally:
        conn.close()
    assert event_row["status"] == "processed"
    assert event_row["processed_at"] > 0


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


def test_checkout_session_completed_webhook_links_subscription(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("checkout-complete@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_checkout_complete",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_complete",
                "customer": "cus_complete",
                "subscription": "sub_complete",
                "payment_status": "paid",
                "client_reference_id": user.id,
                "metadata": {"saveany_user_id": user.id},
            }
        },
    }

    response = _post_event(client, event)

    assert response.status_code == 200
    membership = get_membership(user.id)
    assert membership.active is False
    assert membership.current_period_end is None
    conn = database.connect(tmp_path / "saveany.db")
    try:
        subscription = conn.execute(
            """
            select stripe_customer_id, stripe_subscription_id, status
            from subscriptions where user_id = ?
            """,
            (user.id,),
        ).fetchone()
    finally:
        conn.close()
    assert subscription["stripe_customer_id"] == "cus_complete"
    assert subscription["stripe_subscription_id"] == "sub_complete"
    assert subscription["status"] == "incomplete"


def test_checkout_session_completed_preserves_active_subscription_when_it_arrives_late(
    monkeypatch, tmp_path
):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("late-checkout@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    subscription_event = {
        "id": "evt_subscription_first",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_late",
                "customer": "cus_late",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": True,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_late"}}]},
            }
        },
    }
    checkout_event = {
        "id": "evt_checkout_late",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_late",
                "customer": "cus_late",
                "subscription": "sub_late",
                "payment_status": "paid",
                "client_reference_id": user.id,
                "metadata": {"saveany_user_id": user.id},
            }
        },
    }

    subscription_response = _post_event(client, subscription_event)
    checkout_response = _post_event(client, checkout_event)

    assert subscription_response.status_code == 200
    assert checkout_response.status_code == 200
    membership = get_membership(user.id)
    assert membership.status == "active"
    assert membership.active is True
    assert membership.current_period_end == 1780278400
    assert membership.cancel_at_period_end is True
    conn = database.connect(tmp_path / "saveany.db")
    try:
        subscription = conn.execute(
            """
            select status, stripe_customer_id, stripe_subscription_id, stripe_price_id,
                   current_period_start, current_period_end, cancel_at_period_end
            from subscriptions where user_id = ?
            """,
            (user.id,),
        ).fetchone()
    finally:
        conn.close()
    assert subscription["status"] == "active"
    assert subscription["stripe_customer_id"] == "cus_late"
    assert subscription["stripe_subscription_id"] == "sub_late"
    assert subscription["stripe_price_id"] == "price_late"
    assert subscription["current_period_start"] == 1777600000
    assert subscription["current_period_end"] == 1780278400
    assert subscription["cancel_at_period_end"] == 1


def test_invoice_paid_webhook_marks_subscription_active_and_updates_period(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("invoice-paid@example.com", "stripe-password")
    now = time()
    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, stripe_customer_id, current_period_start,
             current_period_end, cancel_at_period_end, created_at, updated_at)
            values ('local_invoice', ?, 'pro', 'incomplete', 'cus_invoice',
                    ?, ?, 0, ?, ?)
            """,
            (user.id, now - 100, now + 100, now, now),
        )
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_invoice_paid",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_paid",
                "customer": "cus_invoice",
                "subscription": "sub_invoice",
                "lines": {
                    "data": [
                        {
                            "period": {"start": 1777600000, "end": 1780278400},
                            "price": {"id": "price_monthly"},
                        }
                    ]
                },
            }
        },
    }

    response = _post_event(client, event)

    assert response.status_code == 200
    membership = get_membership(user.id)
    assert membership.active is True
    assert membership.current_period_end == 1780278400
    conn = database.connect(tmp_path / "saveany.db")
    try:
        subscription = conn.execute(
            """
            select status, stripe_subscription_id, stripe_price_id
            from subscriptions where id = 'local_invoice'
            """
        ).fetchone()
    finally:
        conn.close()
    assert subscription["status"] == "active"
    assert subscription["stripe_subscription_id"] == "sub_invoice"
    assert subscription["stripe_price_id"] == "price_monthly"


def test_invoice_payment_failed_webhook_marks_subscription_past_due(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("invoice-failed@example.com", "stripe-password")
    now = time()
    with transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
             current_period_start, current_period_end, cancel_at_period_end,
             created_at, updated_at)
            values ('local_failed', ?, 'pro', 'active', 'cus_failed', 'sub_failed',
                    ?, ?, 0, ?, ?)
            """,
            (user.id, now - 100, now + 2592000, now, now),
        )
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_invoice_failed",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_failed",
                "customer": "cus_failed",
                "subscription": "sub_failed",
            }
        },
    }

    response = _post_event(client, event)

    assert response.status_code == 200
    membership = get_membership(user.id)
    assert membership.status == "past_due"
    assert membership.active is False


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
