from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Callable
from time import time

from app.services.auth_service import User
from app.services.database import connect, transaction


ACTIVE_STATUSES = {"active", "trialing"}
STRIPE_EVENT_PROCESSING_LEASE_SECONDS = 300
STRIPE_CHECKOUT_ATTEMPT_TTL_SECONDS = 30 * 60


class StripeEventInProgress(RuntimeError):
    pass


class StripeCheckoutOwnershipError(RuntimeError):
    pass


class StripeCheckoutNotReadyError(RuntimeError):
    pass


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
        row["current_period_end"] is not None and row["current_period_end"] >= time()
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


def get_open_stripe_checkout_attempt(user_id: str, return_url: str | None = None) -> dict | None:
    now = time()
    cutoff = now - STRIPE_CHECKOUT_ATTEMPT_TTL_SECONDS
    with transaction() as conn:
        conn.execute(
            """
            update billing_attempts
            set status = 'expired', updated_at = ?
            where user_id = ? and mode = 'stripe' and status = 'open'
              and updated_at < ?
            """,
            (now, user_id, cutoff),
        )
        if return_url is not None:
            conn.execute(
                """
                update billing_attempts
                set status = 'expired', updated_at = ?
                where user_id = ? and mode = 'stripe' and status = 'open'
                  and (stripe_return_url is null or stripe_return_url != ?)
                """,
                (now, user_id, return_url),
            )
        row = conn.execute(
            """
            select id, stripe_checkout_session_id, stripe_checkout_url, stripe_return_url
            from billing_attempts
            where user_id = ? and mode = 'stripe' and status = 'open'
              and updated_at >= ?
              and stripe_checkout_session_id is not null
              and stripe_checkout_url is not null
              and (? is null or stripe_return_url = ?)
            order by updated_at desc
            limit 1
            """,
            (user_id, cutoff, return_url, return_url),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def record_stripe_checkout_attempt(
    user_id: str,
    session_id: str,
    session_url: str,
    return_url: str | None = None,
) -> None:
    now = time()
    with transaction() as conn:
        existing = conn.execute(
            """
            select id from billing_attempts
            where stripe_checkout_session_id = ?
            limit 1
            """,
            (session_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                insert into billing_attempts
                (id, user_id, mode, status, stripe_checkout_session_id, stripe_checkout_url, stripe_return_url,
                 created_at, updated_at)
                values (?, ?, 'stripe', 'open', ?, ?, ?, ?, ?)
                """,
                (
                    f"attempt_{secrets.token_urlsafe(10)}",
                    user_id,
                    session_id,
                    session_url,
                    return_url,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                update billing_attempts
                set user_id = ?, mode = 'stripe', status = 'open',
                    stripe_checkout_url = ?, stripe_return_url = ?, updated_at = ?
                where id = ?
                """,
                (user_id, session_url, return_url, now, existing["id"]),
            )


def complete_stripe_checkout_attempt(session_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update billing_attempts
            set status = 'completed', updated_at = ?
            where stripe_checkout_session_id = ? and status != 'completed'
            """,
            (time(), session_id),
        )


def _stripe_dict(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    if hasattr(value, "_to_dict_recursive"):
        return value._to_dict_recursive()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value)


def confirm_stripe_checkout_session(
    user: User,
    session: dict,
    retrieve_subscription: Callable[[str], dict],
) -> Membership:
    session = _stripe_dict(session) or {}
    session_id = session.get("id")
    if not session_id:
        raise ValueError("Stripe Checkout Session 缺少 ID")

    metadata = session.get("metadata") or {}
    owner_id = metadata.get("saveany_user_id") or session.get("client_reference_id")
    if owner_id != user.id:
        raise StripeCheckoutOwnershipError("Stripe Checkout Session 不属于当前用户")

    subscription = session.get("subscription")
    if isinstance(subscription, dict):
        subscription_payload = subscription
    elif subscription:
        subscription_payload = _stripe_dict(retrieve_subscription(subscription))
    else:
        raise StripeCheckoutNotReadyError("Stripe 订阅仍在创建中，请稍后刷新")

    subscription_payload = subscription_payload or {}
    payment_status = session.get("payment_status")
    subscription_status = subscription_payload.get("status")
    if payment_status != "paid" and subscription_status not in ACTIVE_STATUSES:
        raise StripeCheckoutNotReadyError("Stripe 支付仍在确认中，请稍后刷新")

    subscription_metadata = dict(subscription_payload.get("metadata") or {})
    if not subscription_metadata.get("saveany_user_id"):
        subscription_metadata["saveany_user_id"] = user.id
        subscription_payload = {**subscription_payload, "metadata": subscription_metadata}

    upsert_stripe_checkout_session(session)
    membership = upsert_stripe_subscription(subscription_payload)
    complete_stripe_checkout_attempt(session_id)
    return membership


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
    item_period_start = None
    item_period_end = None
    if items:
        price_id = (items[0].get("price") or {}).get("id")
        item_period_start = items[0].get("current_period_start")
        item_period_end = items[0].get("current_period_end")
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
            subscription.get("current_period_start") or item_period_start,
            subscription.get("current_period_end") or item_period_end,
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
        if existing:
            conn.execute(
                """
                update subscriptions
                set user_id = ?, plan = 'pro',
                    stripe_customer_id = coalesce(?, stripe_customer_id),
                    stripe_subscription_id = coalesce(?, stripe_subscription_id),
                    updated_at = ?
                where id = ?
                """,
                (user_id, customer_id, subscription_id, now, existing["id"]),
            )
        else:
            values = (
                user_id,
                "pro",
                "incomplete",
                customer_id,
                subscription_id,
                None,
                None,
                None,
                0,
                now,
            )
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
    now = time()
    with transaction() as conn:
        row = conn.execute(
            "select status, processing_started_at, payload_hash from stripe_events where event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                insert into stripe_events
                (event_id, event_type, status, processing_started_at, processed_at, payload_hash)
                values (?, ?, 'processing', ?, 0, ?)
                """,
                (event_id, event_type, now, payload_hash),
            )
            return True
        if row["status"] == "processed":
            return False
        if row["status"] == "processing":
            if now - row["processing_started_at"] < STRIPE_EVENT_PROCESSING_LEASE_SECONDS:
                raise StripeEventInProgress(event_id)
            cursor = conn.execute(
                """
                update stripe_events
                set event_type = ?, payload_hash = ?, status = 'processing',
                    processing_started_at = ?
                where event_id = ? and status = 'processing'
                  and processing_started_at = ?
                """,
                (event_type, payload_hash, now, event_id, row["processing_started_at"]),
            )
            if cursor.rowcount == 1:
                return True
            raise StripeEventInProgress(event_id)
        cursor = conn.execute(
            """
            update stripe_events
            set event_type = ?, payload_hash = ?, status = 'processing',
                processing_started_at = ?
            where event_id = ? and status = 'pending'
            """,
            (event_type, payload_hash, now, event_id),
        )
        return cursor.rowcount == 1


def mark_stripe_event_pending(event_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update stripe_events
            set status = 'pending', processing_started_at = 0
            where event_id = ? and status = 'processing'
            """,
            (event_id,),
        )


def mark_stripe_event_processed(event_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update stripe_events
            set status = 'processed', processing_started_at = 0, processed_at = ?
            where event_id = ?
            """,
            (time(), event_id),
        )
