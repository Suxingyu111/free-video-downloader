from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import get_membership
from app.services.database import connect, transaction


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class UsageSummary:
    daily_free_limit: int
    used_today: int
    remaining_today: int
    membership_active: bool

    def as_dict(self) -> dict:
        return {
            "daily_free_limit": self.daily_free_limit,
            "used_today": self.used_today,
            "remaining_today": self.remaining_today,
            "membership_active": self.membership_active,
        }


def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def get_usage_summary(user: User) -> UsageSummary:
    membership = get_membership(user.id)
    limit = load_config().free_summary_daily_limit
    if membership.active:
        return UsageSummary(limit, 0, limit, True)

    conn = connect()
    try:
        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, _today_key()),
        ).fetchone()
    finally:
        conn.close()

    used = int(row["summary_count"]) if row else 0
    return UsageSummary(limit, used, max(limit - used, 0), False)


def reserve_summary_quota(user: User, reservation_id: str) -> UsageSummary:
    membership = get_membership(user.id)
    limit = load_config().free_summary_daily_limit
    if membership.active:
        return UsageSummary(limit, 0, limit, True)

    now = time()
    usage_date = _today_key()
    with transaction() as conn:
        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, usage_date),
        ).fetchone()
        used = int(row["summary_count"]) if row else 0
        if used >= limit:
            raise QuotaExceeded("今日免费 AI 总结额度已用完，请开通专业版继续使用。")
        next_used = used + 1
        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(user_id, usage_date)
            do update set summary_count = excluded.summary_count, updated_at = excluded.updated_at
            """,
            (user.id, usage_date, next_used, now, now),
        )
        conn.execute(
            """
            insert into summary_quota_reservations (reservation_id, user_id, usage_date, created_at)
            values (?, ?, ?, ?)
            """,
            (reservation_id, user.id, usage_date, now),
        )

    return UsageSummary(limit, next_used, max(limit - next_used, 0), False)


def consume_summary_quota(user: User) -> UsageSummary:
    return reserve_summary_quota(user, f"manual_{secrets.token_urlsafe(10)}")


def refund_summary_quota(user: User) -> UsageSummary:
    return refund_summary_quota_for_user_id(user.id)


def refund_summary_quota_for_user_id(user_id: str) -> UsageSummary:
    usage_date = _today_key()
    now = time()
    with transaction() as conn:
        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user_id, usage_date),
        ).fetchone()
        used = int(row["summary_count"]) if row else 0
        next_used = max(used - 1, 0)
        if row is not None:
            conn.execute(
                """
                update usage_daily
                set summary_count = ?, updated_at = ?
                where user_id = ? and usage_date = ?
                """,
                (next_used, now, user_id, usage_date),
            )

    limit = load_config().free_summary_daily_limit
    return UsageSummary(limit, next_used, max(limit - next_used, 0), False)


def refund_summary_quota_reservation(reservation_id: str) -> UsageSummary | None:
    now = time()
    with transaction() as conn:
        reservation = conn.execute(
            "select * from summary_quota_reservations where reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if reservation is None:
            return None

        user_id = reservation["user_id"]
        usage_date = reservation["usage_date"]
        if reservation["refunded_at"] is not None:
            row = conn.execute(
                "select summary_count from usage_daily where user_id = ? and usage_date = ?",
                (user_id, usage_date),
            ).fetchone()
            used = int(row["summary_count"]) if row else 0
            limit = load_config().free_summary_daily_limit
            return UsageSummary(limit, used, max(limit - used, 0), False)

        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user_id, usage_date),
        ).fetchone()
        used = int(row["summary_count"]) if row else 0
        next_used = max(used - 1, 0)
        if row is not None:
            conn.execute(
                """
                update usage_daily
                set summary_count = ?, updated_at = ?
                where user_id = ? and usage_date = ?
                """,
                (next_used, now, user_id, usage_date),
            )
        conn.execute(
            "update summary_quota_reservations set refunded_at = ? where reservation_id = ?",
            (now, reservation_id),
        )

    limit = load_config().free_summary_daily_limit
    return UsageSummary(limit, next_used, max(limit - next_used, 0), False)
