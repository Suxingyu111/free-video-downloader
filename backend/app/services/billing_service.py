from __future__ import annotations

import secrets
from dataclasses import dataclass
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
    active = row["status"] in ACTIVE_STATUSES
    return Membership(
        plan=row["plan"],
        status=row["status"],
        active=active,
        current_period_end=row["current_period_end"],
        cancel_at_period_end=bool(row["cancel_at_period_end"]),
    )


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
            set status = 'canceled', current_period_end = ?, updated_at = ?
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
            where user_id = ?
            """,
            (time(), user.id),
        )
    return get_membership(user.id)
