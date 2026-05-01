from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Callable
from time import time

from app.services.auth_service import User
from app.services.database import connect, transaction


ACTIVE_STATUSES = {"active", "trialing"}


@dataclass(frozen=True)
class Membership:
    plan: str
    status: str
    active: bool
    current_period_end: float | None = None
    cancel_at_period_end: bool = False

    def as_dict(self) -> dict:
        return {
            "plan": self.plan,
            "status": self.status,
            "active": self.active,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


def get_membership(user_id: str) -> Membership:
    conn = connect()
    try:
        row = conn.execute(
            """
            select * from subscriptions
            where user_id = ?
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return Membership(plan="free", status="free", active=False)
    active = row["status"] in ACTIVE_STATUSES and (
        row["current_period_end"] is None or row["current_period_end"] >= time()
    )
    return Membership(
        plan=row["plan"],
        status=row["status"],
        active=active,
        current_period_end=row["current_period_end"],
        cancel_at_period_end=bool(row["cancel_at_period_end"]),
    )


def get_latest_stripe_customer_id(user_id: str) -> str | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            select stripe_customer_id from subscriptions
            where user_id = ? and stripe_customer_id is not null
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row["stripe_customer_id"]


def store_stripe_customer_id(user_id: str, customer_id: str) -> None:
    now = time()
    with transaction() as conn:
        row = conn.execute(
            """
            select id from subscriptions
            where user_id = ? and stripe_customer_id is not null
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, stripe_customer_id, created_at, updated_at)
                values (?, ?, 'pro', 'incomplete', ?, ?, ?)
                """,
                (f"sub_{secrets.token_urlsafe(10)}", user_id, customer_id, now, now),
            )
        else:
            conn.execute(
                """
                update subscriptions
                set stripe_customer_id = ?, updated_at = ?
                where id = ?
                """,
                (customer_id, now, row["id"]),
            )


def ensure_stripe_customer_id(user: User, create_customer: Callable[[], str]) -> str:
    existing_customer_id = get_latest_stripe_customer_id(user.id)
    if existing_customer_id:
        return existing_customer_id
    customer_id = create_customer()
    stored_customer_id = get_latest_stripe_customer_id(user.id)
    if stored_customer_id:
        return stored_customer_id
    store_stripe_customer_id(user.id, customer_id)
    return customer_id


def create_mock_checkout(user: User) -> dict:
    now = time()
    with transaction() as conn:
        attempt_id = f"attempt_{secrets.token_urlsafe(10)}"
        conn.execute(
            """
            insert into billing_attempts (id, user_id, mode, status, created_at, updated_at)
            values (?, ?, 'mock', 'created', ?, ?)
            """,
            (attempt_id, user.id, now, now),
        )
    return {"mode": "mock", "url": "/#pricing", "attempt_id": attempt_id}


def activate_mock_subscription(user: User) -> Membership:
    now = time()
    with transaction() as conn:
        existing = conn.execute(
            "select id from subscriptions where user_id = ? order by updated_at desc limit 1",
            (user.id,),
        ).fetchone()
        subscription_id = existing["id"] if existing else f"sub_{secrets.token_urlsafe(10)}"
        if existing:
            conn.execute(
                """
                update subscriptions
                set plan = 'pro', status = 'active', current_period_start = ?,
                    current_period_end = ?, cancel_at_period_end = 0, updated_at = ?
                where id = ?
                """,
                (now, now + 30 * 86400, now, subscription_id),
            )
        else:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, current_period_start, current_period_end,
                 cancel_at_period_end, created_at, updated_at)
                values (?, ?, 'pro', 'active', ?, ?, 0, ?, ?)
                """,
                (subscription_id, user.id, now, now + 30 * 86400, now, now),
            )
    return get_membership(user.id)


def cancel_mock_subscription(user: User) -> Membership:
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set cancel_at_period_end = 1, updated_at = ?
            where user_id = ? and status in ('active', 'trialing')
            """,
            (time(), user.id),
        )
    return get_membership(user.id)


def expire_mock_subscription(user: User) -> Membership:
    now = time()
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set status = 'canceled', current_period_end = ?,
                cancel_at_period_end = 0, updated_at = ?
            where user_id = ?
            """,
            (now - 1, now, user.id),
        )
    return get_membership(user.id)


def fail_mock_payment(user: User) -> Membership:
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set status = 'past_due', updated_at = ?
            where user_id = ? and status in ('active', 'trialing')
            """,
            (time(), user.id),
        )
    return get_membership(user.id)


def upsert_stripe_subscription(subscription: dict) -> Membership:
    items = ((subscription.get("items") or {}).get("data") or [])
    price_id = None
    if items:
        price_id = (items[0].get("price") or {}).get("id")
    now = time()
    with transaction() as conn:
        existing = conn.execute(
            "select id, user_id from subscriptions where stripe_subscription_id = ?",
            (subscription.get("id"),),
        ).fetchone()
        if existing is None and subscription.get("customer"):
            existing = conn.execute(
                """
                select id, user_id from subscriptions
                where stripe_customer_id = ?
                order by updated_at desc
                limit 1
                """,
                (subscription.get("customer"),),
            ).fetchone()
        metadata = subscription.get("metadata") or {}
        user_id = existing["user_id"] if existing else metadata.get("saveany_user_id")
        if not user_id:
            row = conn.execute(
                """
                select user_id from subscriptions
                where stripe_customer_id = ?
                order by updated_at desc
                limit 1
                """,
                (subscription.get("customer"),),
            ).fetchone()
            if row:
                user_id = row["user_id"]
        if not user_id:
            raise ValueError("Stripe subscription is not linked to a SaveAny user")
        values = (
            user_id,
            "pro",
            subscription.get("status") or "incomplete",
            subscription.get("customer"),
            subscription.get("id"),
            price_id,
            subscription.get("current_period_start"),
            subscription.get("current_period_end"),
            1 if subscription.get("cancel_at_period_end") else 0,
            now,
        )
        if existing:
            conn.execute(
                """
                update subscriptions
                set user_id = ?, plan = ?, status = ?, stripe_customer_id = ?,
                    stripe_subscription_id = ?, stripe_price_id = ?,
                    current_period_start = ?, current_period_end = ?,
                    cancel_at_period_end = ?, updated_at = ?
                where id = ?
                """,
                (*values, existing["id"]),
            )
        else:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
                 stripe_price_id, current_period_start, current_period_end,
                 cancel_at_period_end, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"sub_{secrets.token_urlsafe(10)}", *values, now),
            )
    return get_membership(user_id)


def upsert_stripe_checkout_session(session: dict) -> Membership:
    metadata = session.get("metadata") or {}
    user_id = metadata.get("saveany_user_id") or session.get("client_reference_id")
    if not user_id:
        raise ValueError("Stripe checkout session is not linked to a SaveAny user")
    subscription_id = session.get("subscription")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")
    customer_id = session.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    now = time()
    with transaction() as conn:
        existing = None
        if subscription_id:
            existing = conn.execute(
                "select id, user_id from subscriptions where stripe_subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        if existing is None and customer_id:
            existing = conn.execute(
                """
                select id, user_id from subscriptions
                where stripe_customer_id = ?
                order by updated_at desc
                limit 1
                """,
                (customer_id,),
            ).fetchone()
        if existing:
            user_id = existing["user_id"]
        values = (
            user_id,
            "pro",
            "active" if session.get("payment_status") == "paid" else "incomplete",
            customer_id,
            subscription_id,
            None,
            None,
            None,
            0,
            now,
        )
        if existing:
            conn.execute(
                """
                update subscriptions
                set user_id = ?, plan = ?, status = ?, stripe_customer_id = ?,
                    stripe_subscription_id = coalesce(?, stripe_subscription_id),
                    stripe_price_id = coalesce(?, stripe_price_id),
                    current_period_start = coalesce(?, current_period_start),
                    current_period_end = coalesce(?, current_period_end),
                    cancel_at_period_end = ?, updated_at = ?
                where id = ?
                """,
                (*values, existing["id"]),
            )
        else:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
                 stripe_price_id, current_period_start, current_period_end,
                 cancel_at_period_end, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"sub_{secrets.token_urlsafe(10)}", *values, now),
            )
    return get_membership(user_id)


def _first_line_item(subscription_or_invoice: dict) -> dict:
    items = ((subscription_or_invoice.get("lines") or {}).get("data") or [])
    if items:
        return items[0]
    items = ((subscription_or_invoice.get("items") or {}).get("data") or [])
    if items:
        return items[0]
    return {}


def upsert_stripe_invoice_paid(invoice: dict) -> Membership:
    subscription_id = invoice.get("subscription")
    customer_id = invoice.get("customer")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    line_item = _first_line_item(invoice)
    period = line_item.get("period") or {}
    price = line_item.get("price") or {}
    now = time()
    with transaction() as conn:
        existing = None
        if subscription_id:
            existing = conn.execute(
                "select id, user_id from subscriptions where stripe_subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        if existing is None and customer_id:
            existing = conn.execute(
                """
                select id, user_id from subscriptions
                where stripe_customer_id = ?
                order by updated_at desc
                limit 1
                """,
                (customer_id,),
            ).fetchone()
        if existing is None:
            raise ValueError("Stripe invoice is not linked to a SaveAny user")
        conn.execute(
            """
            update subscriptions
            set plan = 'pro', status = 'active', stripe_customer_id = coalesce(?, stripe_customer_id),
                stripe_subscription_id = coalesce(?, stripe_subscription_id),
                stripe_price_id = coalesce(?, stripe_price_id),
                current_period_start = coalesce(?, current_period_start),
                current_period_end = coalesce(?, current_period_end),
                updated_at = ?
            where id = ?
            """,
            (
                customer_id,
                subscription_id,
                price.get("id"),
                period.get("start"),
                period.get("end"),
                now,
                existing["id"],
            ),
        )
    return get_membership(existing["user_id"])


def mark_stripe_invoice_payment_failed(invoice: dict) -> Membership:
    subscription_id = invoice.get("subscription")
    customer_id = invoice.get("customer")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    now = time()
    with transaction() as conn:
        existing = None
        if subscription_id:
            existing = conn.execute(
                "select id, user_id, status from subscriptions where stripe_subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        if existing is None and customer_id:
            existing = conn.execute(
                """
                select id, user_id, status from subscriptions
                where stripe_customer_id = ?
                order by updated_at desc
                limit 1
                """,
                (customer_id,),
            ).fetchone()
        if existing is None:
            raise ValueError("Stripe invoice is not linked to a SaveAny user")
        if existing["status"] != "canceled":
            conn.execute(
                """
                update subscriptions
                set status = 'past_due', updated_at = ?
                where id = ?
                """,
                (now, existing["id"]),
            )
    return get_membership(existing["user_id"])


def begin_stripe_event_processing(event_id: str, event_type: str, payload: bytes) -> bool:
    payload_hash = hashlib.sha256(payload).hexdigest()
    with transaction() as conn:
        row = conn.execute(
            "select status from stripe_events where event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                insert into stripe_events (event_id, event_type, status, processed_at, payload_hash)
                values (?, ?, 'processing', 0, ?)
                """,
                (event_id, event_type, payload_hash),
            )
            return True
        if row["status"] == "processed":
            return False
        if row["status"] == "processing":
            return False
        cursor = conn.execute(
            """
            update stripe_events
            set event_type = ?, payload_hash = ?, status = 'processing'
            where event_id = ? and status = 'pending'
            """,
            (event_type, payload_hash, event_id),
        )
        return cursor.rowcount == 1


def mark_stripe_event_pending(event_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update stripe_events
            set status = 'pending'
            where event_id = ? and status = 'processing'
            """,
            (event_id,),
        )


def mark_stripe_event_processed(event_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update stripe_events
            set status = 'processed', processed_at = ?
            where event_id = ?
            """,
            (time(), event_id),
        )
