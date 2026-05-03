from __future__ import annotations

import secrets
from dataclasses import dataclass
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User, get_user_by_id
from app.services.database import transaction
from app.services.plan_catalog import MeterType, PeriodType
from app.services.usage_meter import (
    MeterExceeded,
    allowance_for_user,
    entitlement_status,
    refund_reservation,
    reserve_user_meter,
)


FREE_SUMMARY_QUOTA_EXCEEDED_MESSAGE = "今日免费 AI 总结额度已用完，请开通专业版继续使用。"


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class UsageSummary:
    daily_free_limit: int
    used_today: int
    remaining_today: int
    membership_active: bool
    meters: dict | None = None
    credit_packs: dict | None = None

    def as_dict(self) -> dict:
        payload = {
            "daily_free_limit": self.daily_free_limit,
            "used_today": self.used_today,
            "remaining_today": self.remaining_today,
            "membership_active": self.membership_active,
        }
        if self.meters is not None:
            payload["meters"] = self.meters
        if self.credit_packs is not None:
            payload["credit_packs"] = self.credit_packs
        return payload


def get_usage_summary(user: User) -> UsageSummary:
    status = get_entitlement_status(user)
    summary = status["meters"]["summary"]
    membership_active = status["plan"] == "pro"
    daily_free_limit = load_config().free_summary_daily_limit
    used = summary["used"]
    remaining = summary["plan_remaining"]
    if membership_active:
        used_today = 0
        remaining_today = daily_free_limit
    else:
        used_today = used
        remaining_today = remaining
    return UsageSummary(
        daily_free_limit=daily_free_limit,
        used_today=used_today,
        remaining_today=remaining_today,
        membership_active=membership_active,
        meters=status["meters"],
        credit_packs=status["credit_packs"],
    )


def get_entitlement_status(user: User) -> dict:
    _seed_summary_meter_from_legacy_usage(user)
    return entitlement_status(user)


def reserve_summary_quota(user: User, reservation_id: str) -> UsageSummary:
    _seed_summary_meter_from_legacy_usage(user)
    try:
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=reservation_id)
    except MeterExceeded as exc:
        if _free_summary_quota_exhausted(user):
            raise QuotaExceeded(FREE_SUMMARY_QUOTA_EXCEEDED_MESSAGE) from exc
        raise QuotaExceeded(str(exc)) from exc
    _sync_legacy_summary_quota_reservation(reservation_id)
    return get_usage_summary(user)


def consume_summary_quota(user: User) -> UsageSummary:
    return reserve_summary_quota(user, f"manual_{secrets.token_urlsafe(10)}")


def refund_summary_quota_reservation(reservation_id: str) -> UsageSummary | None:
    refund = refund_reservation(reservation_id)
    if refund is None:
        return _refund_legacy_summary_quota_reservation(reservation_id)
    _sync_legacy_summary_quota_reservation(reservation_id)
    user = get_user_by_id(refund["user_id"])
    return get_usage_summary(user) if user else None


def _free_summary_quota_exhausted(user: User) -> bool:
    _seed_summary_meter_from_legacy_usage(user)
    status = entitlement_status(user)
    if status["plan"] != "free":
        return False
    summary = status["meters"]["summary"]
    return summary["plan_remaining"] <= 0 and summary["pack_remaining"] <= 0


def _seed_summary_meter_from_legacy_usage(user: User) -> None:
    allowance = allowance_for_user(user, MeterType.SUMMARY)
    if allowance.plan_id != "free" or allowance.period_type != PeriodType.DAY:
        return

    now = time()
    with transaction() as conn:
        legacy = conn.execute(
            """
            select summary_count
            from usage_daily
            where user_id = ? and usage_date = ?
            """,
            (user.id, allowance.period_key),
        ).fetchone()
        if legacy is None:
            return

        meter_reservation = conn.execute(
            """
            select 1
            from meter_reservations
            where user_id = ? and meter_type = ? and period_type = ? and period_key = ?
            limit 1
            """,
            (
                user.id,
                MeterType.SUMMARY.value,
                allowance.period_type.value,
                allowance.period_key,
            ),
        ).fetchone()
        if meter_reservation is not None:
            return

        legacy_count = int(legacy["summary_count"])
        current = conn.execute(
            f"""
            select {allowance.column}
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, allowance.period_type.value, allowance.period_key),
        ).fetchone()
        current_count = int(current[allowance.column]) if current else 0
        if legacy_count <= current_count:
            return

        conn.execute(
            f"""
            insert into usage_periods
            (user_id, period_type, period_key, {allowance.column}, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(user_id, period_type, period_key)
            do update set {allowance.column} = excluded.{allowance.column},
                          updated_at = excluded.updated_at
            """,
            (
                user.id,
                allowance.period_type.value,
                allowance.period_key,
                legacy_count,
                now,
                now,
            ),
        )


def _refund_legacy_summary_quota_reservation(reservation_id: str) -> UsageSummary | None:
    now = time()
    user_id: str | None = None
    with transaction() as conn:
        reservation = conn.execute(
            """
            select *
            from summary_quota_reservations
            where reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if reservation is None:
            return None

        user_id = reservation["user_id"]
        usage_date = reservation["usage_date"]
        if reservation["refunded_at"] is None:
            row = conn.execute(
                """
                select summary_count
                from usage_daily
                where user_id = ? and usage_date = ?
                """,
                (user_id, usage_date),
            ).fetchone()
            next_used = max((int(row["summary_count"]) if row else 0) - 1, 0)
            if row is not None:
                conn.execute(
                    """
                    update usage_daily
                    set summary_count = ?, updated_at = ?
                    where user_id = ? and usage_date = ?
                    """,
                    (next_used, now, user_id, usage_date),
                )

            meter = conn.execute(
                """
                select summary_count
                from usage_periods
                where user_id = ? and period_type = ? and period_key = ?
                """,
                (user_id, PeriodType.DAY.value, usage_date),
            ).fetchone()
            if meter is not None:
                conn.execute(
                    """
                    update usage_periods
                    set summary_count = ?, updated_at = ?
                    where user_id = ? and period_type = ? and period_key = ?
                    """,
                    (
                        max(int(meter["summary_count"]) - 1, 0),
                        now,
                        user_id,
                        PeriodType.DAY.value,
                        usage_date,
                    ),
                )

            conn.execute(
                """
                update summary_quota_reservations
                set refunded_at = ?
                where reservation_id = ?
                """,
                (now, reservation_id),
            )

    user = get_user_by_id(user_id) if user_id else None
    return get_usage_summary(user) if user else None


def _sync_legacy_summary_quota_reservation(reservation_id: str) -> None:
    now = time()
    with transaction() as conn:
        reservation = conn.execute(
            "select * from meter_reservations where reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if reservation is None:
            return
        if (
            reservation["meter_type"] != MeterType.SUMMARY.value
            or reservation["period_type"] != PeriodType.DAY.value
        ):
            return

        usage = conn.execute(
            """
            select summary_count
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (
                reservation["user_id"],
                reservation["period_type"],
                reservation["period_key"],
            ),
        ).fetchone()
        summary_count = int(usage["summary_count"]) if usage else 0

        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(user_id, usage_date)
            do update set summary_count = excluded.summary_count,
                          updated_at = excluded.updated_at
            """,
            (
                reservation["user_id"],
                reservation["period_key"],
                summary_count,
                reservation["created_at"] or now,
                now,
            ),
        )
        conn.execute(
            """
            insert into summary_quota_reservations
            (reservation_id, user_id, usage_date, created_at, refunded_at)
            values (?, ?, ?, ?, ?)
            on conflict(reservation_id)
            do update set user_id = excluded.user_id,
                          usage_date = excluded.usage_date,
                          refunded_at = coalesce(
                              excluded.refunded_at,
                              summary_quota_reservations.refunded_at
                          )
            """,
            (
                reservation["reservation_id"],
                reservation["user_id"],
                reservation["period_key"],
                reservation["created_at"] or now,
                reservation["refunded_at"],
            ),
        )
