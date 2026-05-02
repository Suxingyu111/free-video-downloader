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


class FakeStripeSubscription:
    payloads = {}

    @classmethod
    def retrieve(cls, subscription_id):
        return cls.payloads[subscription_id]


class FakeStripeCheckoutSessionConfirm:
    calls = []
    payloads = {}

    @classmethod
    def retrieve(cls, session_id, expand=None):
        cls.calls.append({"session_id": session_id, "expand": expand})
        return cls.payloads[session_id]


class FakeStripeCheckoutConfirm:
    Session = FakeStripeCheckoutSessionConfirm


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


def _credit_pack_checkout_event(
    event_id,
    user_id,
    *,
    session_id=None,
    event_type="checkout.session.completed",
    pack_id="summary_small",
    payment_status="paid",
    payment_intent=None,
    price_id="price_summary_small",
    include_line_items=True,
):
    checkout_session = {
        "id": session_id or f"cs_{event_id}",
        "mode": "payment",
        "payment_status": payment_status,
        "payment_intent": payment_intent or f"pi_{event_id}",
        "client_reference_id": user_id,
        "metadata": {
            "saveany_user_id": user_id,
            "purchase_type": "credit_pack",
            "pack_id": pack_id,
        },
    }
    if include_line_items:
        checkout_session["line_items"] = {
            "data": [{"price": {"id": price_id} if price_id else {}}]
        }
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": checkout_session},
    }


def _assert_rejected_credit_pack_event(client, tmp_path, event, user_id):
    response = _post_event(client, event)

    assert response.status_code == 500
    with database.connect(tmp_path / "saveany.db") as conn:
        pack_count = conn.execute(
            "select count(*) as count from credit_packs where user_id = ?",
            (user_id,),
        ).fetchone()
        event_row = conn.execute(
            "select status, processed_at from stripe_events where event_id = ?",
            (event["id"],),
        ).fetchone()
    assert pack_count["count"] == 0
    assert event_row["status"] == "pending"
    assert event_row["processed_at"] == 0


def _assert_processed_credit_pack_event_without_grant(client, tmp_path, event, user_id):
    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack_count = conn.execute(
            "select count(*) as count from credit_packs where user_id = ?",
            (user_id,),
        ).fetchone()
        event_row = conn.execute(
            "select status, processed_at from stripe_events where event_id = ?",
            (event["id"],),
        ).fetchone()
    assert pack_count["count"] == 0
    assert event_row["status"] == "processed"
    assert event_row["processed_at"] > 0


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
    with database.connect(tmp_path / "saveany.db") as conn:
        rows = conn.execute(
            """
            select stripe_customer_id
            from stripe_customers
            """
        ).fetchall()
        subscription_count = conn.execute(
            """
            select count(*) as count
            from subscriptions
            """
        ).fetchone()
    assert len(rows) == 1
    assert rows[0]["stripe_customer_id"] == "cus_reused"
    assert subscription_count["count"] == 0


def test_stripe_credit_pack_checkout_does_not_change_membership(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "pack-checkout-free@example.com", "password": "checkout-password"},
    ).json()
    user_id = registered["user"]["id"]

    response = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
    )
    me = client.get("/api/me").json()
    membership = get_membership(user_id)

    assert response.status_code == 200
    assert me["membership"]["plan"] == "free"
    assert me["membership"]["status"] == "free"
    assert membership.plan == "free"
    assert membership.status == "free"
    with database.connect(tmp_path / "saveany.db") as conn:
        subscription_count = conn.execute(
            "select count(*) as count from subscriptions where user_id = ?",
            (user_id,),
        ).fetchone()
        customer = conn.execute(
            "select stripe_customer_id from stripe_customers where user_id = ?",
            (user_id,),
        ).fetchone()
    assert subscription_count["count"] == 0
    assert customer["stripe_customer_id"] == "cus_reused"


def test_stripe_credit_pack_checkout_marks_return_urls(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "pack-return@example.com", "password": "checkout-password"},
    )

    response = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
    )

    assert response.status_code == 200
    session_call = FakeStripeCheckoutSession.created[0]
    assert "checkout=success&purchase_type=credit_pack&session_id=" in session_call["success_url"]
    assert session_call["cancel_url"].endswith(
        "/#pricing?checkout=cancel&purchase_type=credit_pack"
    )


def test_stripe_checkout_uses_request_origin_for_return_urls(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "origin-checkout@example.com", "password": "checkout-password"},
    )

    response = client.post(
        "/api/billing/checkout",
        json={"return_url": "http://127.0.0.1:5175"},
        headers={"Origin": "http://127.0.0.1:5175"},
    )

    assert response.status_code == 200
    session_call = FakeStripeCheckoutSession.created[0]
    assert session_call["success_url"].startswith(
        "http://127.0.0.1:5175/#pricing?checkout=success"
    )
    assert session_call["cancel_url"] == "http://127.0.0.1:5175/#pricing?checkout=cancel"
    assert "purchase_type=credit_pack" not in session_call["success_url"]
    assert "purchase_type=credit_pack" not in session_call["cancel_url"]


def test_stripe_checkout_recreates_session_when_return_origin_changes(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "origin-change@example.com", "password": "checkout-password"},
    )

    first = client.post("/api/billing/checkout")
    second = client.post(
        "/api/billing/checkout",
        json={"return_url": "http://127.0.0.1:5175"},
        headers={"Origin": "http://127.0.0.1:5175"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] != second.json()["session_id"]
    assert len(FakeStripeCheckoutSession.created) == 2
    conn = database.connect(tmp_path / "saveany.db")
    try:
        attempts = conn.execute(
            """
            select status, stripe_return_url
            from billing_attempts
            order by created_at
            """
        ).fetchall()
    finally:
        conn.close()
    assert [attempt["status"] for attempt in attempts] == ["expired", "open"]
    assert [attempt["stripe_return_url"] for attempt in attempts] == [
        "http://localhost:5173",
        "http://127.0.0.1:5175",
    ]


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


def test_stripe_credit_pack_checkout_attempt_not_reused_for_subscription(
    monkeypatch, tmp_path
):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "pack-attempt@example.com", "password": "checkout-password"},
    )

    pack_checkout = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
    )
    subscription_checkout = client.post("/api/billing/checkout")

    assert pack_checkout.status_code == 200
    assert subscription_checkout.status_code == 200
    assert pack_checkout.json()["session_id"] != subscription_checkout.json()["session_id"]
    assert len(FakeStripeCheckoutSession.created) == 2
    assert FakeStripeCheckoutSession.created[0]["mode"] == "payment"
    assert FakeStripeCheckoutSession.created[1]["mode"] == "subscription"


def test_checkout_confirm_syncs_paid_subscription(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCheckoutSessionConfirm.payloads = {}
    FakeStripeSubscription.payloads = {}
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "confirm-paid@example.com", "password": "stripe-password"},
    ).json()
    user_id = registered["user"]["id"]
    FakeStripeCheckoutSessionConfirm.payloads["cs_paid"] = {
        "id": "cs_paid",
        "customer": "cus_confirm",
        "subscription": "sub_confirm",
        "payment_status": "paid",
        "client_reference_id": user_id,
        "metadata": {"saveany_user_id": user_id},
    }
    FakeStripeSubscription.payloads["sub_confirm"] = {
        "id": "sub_confirm",
        "customer": "cus_confirm",
        "status": "active",
        "current_period_start": 1777600000,
        "current_period_end": 1780278400,
        "cancel_at_period_end": False,
        "metadata": {"saveany_user_id": user_id},
        "items": {"data": [{"price": {"id": "price_monthly"}}]},
    }

    response = client.post(
        "/api/billing/checkout/confirm",
        json={"session_id": "cs_paid"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "stripe"
    assert response.json()["membership"]["active"] is True
    assert response.json()["membership"]["plan"] == "pro"
    assert get_membership(user_id).active is True


def test_checkout_confirm_rejects_session_for_another_user(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    other_user = create_user("other-confirm@example.com", "stripe-password")
    FakeStripeCheckoutSessionConfirm.payloads = {
        "cs_other": {
            "id": "cs_other",
            "customer": "cus_other",
            "subscription": "sub_other",
            "payment_status": "paid",
            "client_reference_id": other_user.id,
            "metadata": {"saveany_user_id": other_user.id},
        }
    }
    FakeStripeSubscription.payloads = {
        "sub_other": {
            "id": "sub_other",
            "customer": "cus_other",
            "status": "active",
            "current_period_start": 1777600000,
            "current_period_end": 1780278400,
            "cancel_at_period_end": False,
            "metadata": {"saveany_user_id": other_user.id},
            "items": {"data": [{"price": {"id": "price_monthly"}}]},
        }
    }
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    current = client.post(
        "/api/auth/register",
        json={"email": "current-confirm@example.com", "password": "stripe-password"},
    ).json()

    response = client.post("/api/billing/checkout/confirm", json={"session_id": "cs_other"})

    assert response.status_code == 403
    assert get_membership(current["user"]["id"]).active is False
    assert get_membership(other_user.id).active is False


def test_checkout_confirm_waits_for_unpaid_session(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCheckoutSessionConfirm.payloads = {}
    FakeStripeSubscription.payloads = {}
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "confirm-unpaid@example.com", "password": "stripe-password"},
    ).json()
    user_id = registered["user"]["id"]
    FakeStripeCheckoutSessionConfirm.payloads["cs_unpaid"] = {
        "id": "cs_unpaid",
        "customer": "cus_unpaid",
        "subscription": "sub_unpaid",
        "payment_status": "unpaid",
        "client_reference_id": user_id,
        "metadata": {"saveany_user_id": user_id},
    }
    FakeStripeSubscription.payloads["sub_unpaid"] = {
        "id": "sub_unpaid",
        "customer": "cus_unpaid",
        "status": "incomplete",
        "metadata": {"saveany_user_id": user_id},
        "items": {"data": [{"price": {"id": "price_monthly"}}]},
    }

    response = client.post("/api/billing/checkout/confirm", json={"session_id": "cs_unpaid"})

    assert response.status_code == 409
    assert get_membership(user_id).active is False


def test_checkout_confirm_uses_subscription_item_period_fields(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCheckoutSessionConfirm.payloads = {}
    FakeStripeSubscription.payloads = {}
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "confirm-item-period@example.com", "password": "stripe-password"},
    ).json()
    user_id = registered["user"]["id"]
    FakeStripeCheckoutSessionConfirm.payloads["cs_item_period"] = {
        "id": "cs_item_period",
        "customer": "cus_item_period",
        "subscription": "sub_item_period",
        "payment_status": "paid",
        "client_reference_id": user_id,
        "metadata": {"saveany_user_id": user_id},
    }
    FakeStripeSubscription.payloads["sub_item_period"] = {
        "id": "sub_item_period",
        "customer": "cus_item_period",
        "status": "active",
        "cancel_at_period_end": False,
        "metadata": {"saveany_user_id": user_id},
        "items": {
            "data": [
                {
                    "current_period_start": 1777600000,
                    "current_period_end": 1780278400,
                    "price": {"id": "price_monthly"},
                }
            ]
        },
    }

    response = client.post(
        "/api/billing/checkout/confirm",
        json={"session_id": "cs_item_period"},
    )

    assert response.status_code == 200
    assert response.json()["membership"]["active"] is True
    assert response.json()["membership"]["current_period_end"] == 1780278400


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


def test_stripe_checkout_payment_pack_grants_credit(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-webhook@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = _credit_pack_checkout_event("evt_pack_completed", user.id)

    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack = conn.execute("select * from credit_packs where user_id = ?", (user.id,)).fetchone()
    assert pack["pack_id"] == "summary_small"
    assert pack["remaining_amount"] == 20


def test_stripe_checkout_completed_unpaid_waits_for_async_success(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-unpaid@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    completed = _credit_pack_checkout_event(
        "evt_pack_unpaid_completed",
        user.id,
        session_id="cs_pack_delayed",
        payment_intent="pi_pack_delayed",
        payment_status="unpaid",
    )
    async_success = _credit_pack_checkout_event(
        "evt_pack_unpaid_async_success",
        user.id,
        session_id="cs_pack_delayed",
        event_type="checkout.session.async_payment_succeeded",
        payment_intent="pi_pack_delayed",
    )

    completed_response = _post_event(client, completed)
    assert completed_response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack_count = conn.execute(
            "select count(*) as count from credit_packs where user_id = ?",
            (user.id,),
        ).fetchone()
        completed_event = conn.execute(
            "select status, processed_at from stripe_events where event_id = ?",
            (completed["id"],),
        ).fetchone()
    assert pack_count["count"] == 0
    assert completed_event["status"] == "processed"
    assert completed_event["processed_at"] > 0

    async_response = _post_event(client, async_success)
    duplicate_async_response = _post_event(client, async_success)

    assert async_response.status_code == 200
    assert duplicate_async_response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        packs = conn.execute(
            "select * from credit_packs where user_id = ?",
            (user.id,),
        ).fetchall()
    assert len(packs) == 1
    assert packs[0]["pack_id"] == "summary_small"
    assert packs[0]["remaining_amount"] == 20


def test_stripe_async_payment_failed_pack_does_not_grant(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-async-failed@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = _credit_pack_checkout_event(
        "evt_pack_async_failed",
        user.id,
        event_type="checkout.session.async_payment_failed",
        payment_status="unpaid",
    )

    _assert_processed_credit_pack_event_without_grant(client, tmp_path, event, user.id)


def test_stripe_async_payment_failed_credit_pack_checkout_can_retry(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCustomer.created = []
    FakeStripeCheckoutSession.created = []
    monkeypatch.setattr(billing_routes.stripe, "Customer", FakeStripeCustomer)
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckout)
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "pack-failed-retry@example.com", "password": "checkout-password"},
    ).json()
    user_id = registered["user"]["id"]

    first = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
    )
    failed_event = _credit_pack_checkout_event(
        "evt_pack_retry_failed",
        user_id,
        session_id=first.json()["session_id"],
        event_type="checkout.session.async_payment_failed",
        payment_status="unpaid",
    )
    failed_response = _post_event(client, failed_event)
    second = client.post(
        "/api/billing/checkout",
        json={"purchase_type": "credit_pack", "pack_id": "summary_small"},
    )

    assert first.status_code == 200
    assert failed_response.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] != second.json()["session_id"]
    assert len(FakeStripeCheckoutSession.created) == 2
    with database.connect(tmp_path / "saveany.db") as conn:
        attempts = conn.execute(
            """
            select stripe_checkout_session_id, status
            from billing_attempts
            where user_id = ?
            order by created_at
            """,
            (user_id,),
        ).fetchall()
    assert [attempt["status"] for attempt in attempts] == ["failed", "open"]


def test_stripe_async_payment_succeeded_pack_grants_credit(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-async-success@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = _credit_pack_checkout_event(
        "evt_pack_async_success",
        user.id,
        event_type="checkout.session.async_payment_succeeded",
    )

    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack = conn.execute(
            "select * from credit_packs where user_id = ?",
            (user.id,),
        ).fetchone()
        subscription_count = conn.execute(
            "select count(*) as count from subscriptions where user_id = ?",
            (user.id,),
        ).fetchone()
    assert pack["pack_id"] == "summary_small"
    assert pack["remaining_amount"] == 20
    assert subscription_count["count"] == 0


def test_stripe_credit_pack_webhook_does_not_create_subscription(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-no-subscription@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = _credit_pack_checkout_event("evt_pack_no_subscription", user.id)

    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        subscription_count = conn.execute(
            "select count(*) as count from subscriptions where user_id = ?",
            (user.id,),
        ).fetchone()
    assert subscription_count["count"] == 0


def test_stripe_credit_pack_webhook_retrieves_missing_line_items(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-retrieve-line-items@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    FakeStripeCheckoutSessionConfirm.calls = []
    FakeStripeCheckoutSessionConfirm.payloads = {
        "cs_evt_pack_retrieve_line_items": {
            "id": "cs_evt_pack_retrieve_line_items",
            "line_items": {"data": [{"price": {"id": "price_summary_small"}}]},
        }
    }
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    client = TestClient(app)
    event = _credit_pack_checkout_event(
        "evt_pack_retrieve_line_items",
        user.id,
        include_line_items=False,
    )

    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack = conn.execute(
            "select * from credit_packs where user_id = ?",
            (user.id,),
        ).fetchone()
    assert pack["pack_id"] == "summary_small"
    assert FakeStripeCheckoutSessionConfirm.calls == [
        {
            "session_id": "cs_evt_pack_retrieve_line_items",
            "expand": ["line_items.data.price"],
        }
    ]


@pytest.mark.parametrize(
    ("event_id", "include_line_items", "price_id"),
    [
        ("evt_pack_missing_line_items", False, "price_summary_small"),
        ("evt_pack_missing_price_id", True, None),
    ],
)
def test_stripe_credit_pack_webhook_requires_line_item_price_id(
    monkeypatch,
    tmp_path,
    event_id,
    include_line_items,
    price_id,
):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user(f"{event_id}@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    if not include_line_items or price_id is None:
        FakeStripeCheckoutSessionConfirm.calls = []
        FakeStripeCheckoutSessionConfirm.payloads = {
            f"cs_{event_id}": {"id": f"cs_{event_id}", "line_items": {"data": []}}
        }
        monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    client = TestClient(app, raise_server_exceptions=False)
    event = _credit_pack_checkout_event(
        event_id,
        user.id,
        include_line_items=include_line_items,
        price_id=price_id,
    )

    _assert_rejected_credit_pack_event(client, tmp_path, event, user.id)


@pytest.mark.parametrize(
    ("event_id", "price_id", "extra_env"),
    [
        ("evt_pack_unconfigured_price", "price_unconfigured", {}),
        (
            "evt_pack_mismatched_price",
            "price_summary_large",
            {"STRIPE_SUMMARY_LARGE_PACK_PRICE_ID": "price_summary_large"},
        ),
    ],
)
def test_stripe_credit_pack_webhook_rejects_unconfigured_or_mismatched_price(
    monkeypatch,
    tmp_path,
    event_id,
    price_id,
    extra_env,
):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    for key, value in extra_env.items():
        monkeypatch.setenv(key, value)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user(f"{event_id}@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app, raise_server_exceptions=False)
    event = _credit_pack_checkout_event(event_id, user.id, price_id=price_id)

    _assert_rejected_credit_pack_event(client, tmp_path, event, user.id)
