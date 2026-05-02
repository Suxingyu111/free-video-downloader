from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import get_membership
from app.services.database import connect, transaction
from app.services.plan_catalog import (
    MeterType,
    PeriodType,
    current_period_key,
    get_credit_pack,
    get_plan_limits,
)


class MeterExceeded(Exception):
    pass


@dataclass(frozen=True)
class MeterAllowance:
    meter_type: MeterType
    period_type: PeriodType
    period_key: str
    limit: int
    column: str
    plan_id: str


def active_plan_id(user: User) -> str:
    return "pro" if get_membership(user.id).active else "free"


def _anonymous_ip_hash(ip: str) -> str:
    raw = f"{load_config().ip_hash_salt}:{ip.strip() or 'unknown'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _column_for_meter(meter_type: MeterType) -> str:
    return {
        MeterType.ANALYZE: "analyze_count",
        MeterType.DOWNLOAD: "download_count",
        MeterType.SUMMARY: "summary_count",
        MeterType.TRANSCRIPTION_MINUTES: "transcription_minutes",
        MeterType.QUESTION: "question_count",
    }[meter_type]


def allowance_for_user(user: User, meter_type: MeterType) -> MeterAllowance:
    plan_id = active_plan_id(user)
    limits = get_plan_limits(plan_id)
    if meter_type == MeterType.ANALYZE and limits.analyze_daily_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.DAY,
            current_period_key(PeriodType.DAY),
            limits.analyze_daily_limit,
            "analyze_count",
            plan_id,
        )
    if meter_type == MeterType.ANALYZE and limits.analyze_monthly_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.analyze_monthly_limit,
            "analyze_count",
            plan_id,
        )
    if meter_type == MeterType.DOWNLOAD and limits.download_daily_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.DAY,
            current_period_key(PeriodType.DAY),
            limits.download_daily_limit,
            "download_count",
            plan_id,
        )
    if meter_type == MeterType.DOWNLOAD and limits.download_monthly_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.download_monthly_limit,
            "download_count",
            plan_id,
        )
    summary_daily_limit = limits.summary_daily_limit
    if plan_id == "free":
        summary_daily_limit = load_config().free_summary_daily_limit
    if meter_type == MeterType.SUMMARY and summary_daily_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.DAY,
            current_period_key(PeriodType.DAY),
            summary_daily_limit,
            "summary_count",
            plan_id,
        )
    if meter_type == MeterType.SUMMARY and limits.summary_monthly_limit is not None:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.summary_monthly_limit,
            "summary_count",
            plan_id,
        )
    if meter_type == MeterType.TRANSCRIPTION_MINUTES:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.transcription_monthly_minutes or 0,
            "transcription_minutes",
            plan_id,
        )
    if meter_type == MeterType.QUESTION:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.questions_per_summary or 0,
            "question_count",
            plan_id,
        )
    raise MeterExceeded("当前套餐不支持该能力。")


def consume_anonymous_meter(
    ip: str,
    meter_type: MeterType,
    reservation_id: str | None = None,
    amount: int = 1,
) -> dict:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if meter_type not in {MeterType.ANALYZE, MeterType.DOWNLOAD}:
        raise MeterExceeded("登录后才能使用该能力。")
    limits = get_plan_limits("anonymous")
    column = _column_for_meter(meter_type)
    limit = (
        limits.analyze_daily_limit
        if meter_type == MeterType.ANALYZE
        else limits.download_daily_limit
    )
    assert limit is not None
    usage_date = current_period_key(PeriodType.DAY)
    now = time()
    ip_hash = _anonymous_ip_hash(ip)
    with transaction() as conn:
        row = conn.execute(
            f"select {column} from anonymous_usage where ip_hash = ? and usage_date = ?",
            (ip_hash, usage_date),
        ).fetchone()
        used = int(row[column]) if row else 0
        if used + amount > limit:
            label = "解析" if meter_type == MeterType.ANALYZE else "下载"
            raise MeterExceeded(f"今天的访客{label}次数已用完，登录后可获得更多免费额度。")
        next_used = used + amount
        conn.execute(
            f"""
            insert into anonymous_usage (ip_hash, usage_date, {column}, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(ip_hash, usage_date)
            do update set {column} = excluded.{column}, updated_at = excluded.updated_at
            """,
            (ip_hash, usage_date, next_used, now, now),
        )
    return {"limit": limit, "used": next_used, "remaining": max(limit - next_used, 0)}


def anonymous_usage_summary(ip: str) -> dict:
    usage_date = current_period_key(PeriodType.DAY)
    ip_hash = _anonymous_ip_hash(ip)
    limits = get_plan_limits("anonymous")
    conn = connect()
    try:
        row = conn.execute(
            """
            select analyze_count, download_count
            from anonymous_usage
            where ip_hash = ? and usage_date = ?
            """,
            (ip_hash, usage_date),
        ).fetchone()
    finally:
        conn.close()
    analyze_used = int(row["analyze_count"]) if row else 0
    download_used = int(row["download_count"]) if row else 0
    return {
        "analyze": {
            "limit": limits.analyze_daily_limit,
            "used": analyze_used,
            "remaining": max((limits.analyze_daily_limit or 0) - analyze_used, 0),
        },
        "download": {
            "limit": limits.download_daily_limit,
            "used": download_used,
            "remaining": max((limits.download_daily_limit or 0) - download_used, 0),
        },
    }


def reserve_user_meter(
    user: User, meter_type: MeterType, amount: int, *, reservation_id: str
) -> dict:
    if amount <= 0:
        raise ValueError("amount must be positive")
    allowance = allowance_for_user(user, meter_type)
    now = time()
    existing_meter_type: MeterType | None = None
    with transaction() as conn:
        existing = conn.execute(
            "select * from meter_reservations where reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if existing is not None:
            if (
                existing["user_id"] != user.id
                or existing["meter_type"] != meter_type.value
                or int(existing["amount"]) != amount
            ):
                raise ValueError("reservation_id 已被其他用量请求使用")
            existing_meter_type = MeterType(existing["meter_type"])
            return _meter_status(user, existing_meter_type)

        row = conn.execute(
            f"""
            select {allowance.column}
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, allowance.period_type.value, allowance.period_key),
        ).fetchone()
        used = int(row[allowance.column]) if row else 0
        plan_remaining = max(allowance.limit - used, 0)
        consume_from_plan = min(plan_remaining, amount)
        consume_from_pack = amount - consume_from_plan
        pack_uses: list[tuple[str, int]] = []

        if consume_from_pack:
            pack_uses = _consume_credit_packs(
                conn, user.id, meter_type, consume_from_pack, now
            )

        credit_pack_id = ",".join(pack_id for pack_id, _ in pack_uses) or None

        next_used = used + consume_from_plan
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
                next_used,
                now,
                now,
            ),
        )
        conn.execute(
            """
            insert into meter_reservations
            (reservation_id, user_id, meter_type, amount, plan_amount, pack_amount,
             period_type, period_key, credit_pack_id, status, created_at, committed_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'committed', ?, ?)
            """,
            (
                reservation_id,
                user.id,
                meter_type.value,
                amount,
                consume_from_plan,
                consume_from_pack,
                allowance.period_type.value,
                allowance.period_key,
                credit_pack_id,
                now,
                now,
            ),
        )
        for pack_id, used_amount in pack_uses:
            conn.execute(
                """
                insert into meter_reservation_pack_uses
                (reservation_id, credit_pack_id, amount)
                values (?, ?, ?)
                """,
                (reservation_id, pack_id, used_amount),
            )
    return _meter_status(user, meter_type)


def _consume_credit_packs(
    conn, user_id: str, meter_type: MeterType, amount: int, now: float
) -> list[tuple[str, int]]:
    remaining = amount
    pack_uses: list[tuple[str, int]] = []
    rows = conn.execute(
        """
        select id, remaining_amount
        from credit_packs
        where user_id = ? and pack_type = ? and status = 'active'
          and expires_at > ? and remaining_amount > 0
        order by expires_at asc, created_at asc
        """,
        (user_id, meter_type.value, now),
    ).fetchall()
    for row in rows:
        if remaining <= 0:
            break
        take = min(int(row["remaining_amount"]), remaining)
        next_remaining = int(row["remaining_amount"]) - take
        status = "depleted" if next_remaining == 0 else "active"
        conn.execute(
            "update credit_packs set remaining_amount = ?, status = ?, updated_at = ? where id = ?",
            (next_remaining, status, now, row["id"]),
        )
        pack_uses.append((row["id"], take))
        remaining -= take
    if remaining > 0:
        label = "AI 总结次数" if meter_type == MeterType.SUMMARY else "语音转写分钟"
        raise MeterExceeded(f"{label}不足，请购买对应按量包后继续。")
    return pack_uses


def refund_reservation(reservation_id: str) -> dict | None:
    now = time()
    with transaction() as conn:
        reservation = conn.execute(
            "select * from meter_reservations where reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if reservation is None:
            return None
        if reservation["status"] == "refunded":
            return dict(reservation)
        plan_amount = int(reservation["plan_amount"] or 0)
        user_id = reservation["user_id"]
        meter_type = MeterType(reservation["meter_type"])
        column = _column_for_meter(meter_type)
        if reservation["period_type"] and reservation["period_key"]:
            row = conn.execute(
                f"""
                select {column}
                from usage_periods
                where user_id = ? and period_type = ? and period_key = ?
                """,
                (user_id, reservation["period_type"], reservation["period_key"]),
            ).fetchone()
            if row is not None:
                next_used = max(int(row[column]) - plan_amount, 0)
                conn.execute(
                    f"""
                    update usage_periods
                    set {column} = ?, updated_at = ?
                    where user_id = ? and period_type = ? and period_key = ?
                    """,
                    (
                        next_used,
                        now,
                        user_id,
                        reservation["period_type"],
                        reservation["period_key"],
                    ),
                )
        pack_rows = conn.execute(
            """
            select credit_pack_id, amount
            from meter_reservation_pack_uses
            where reservation_id = ?
            """,
            (reservation_id,),
        ).fetchall()
        for pack_row in pack_rows:
            conn.execute(
                """
                update credit_packs
                set remaining_amount = remaining_amount + ?,
                    status = 'active',
                    updated_at = ?
                where id = ?
                """,
                (int(pack_row["amount"]), now, pack_row["credit_pack_id"]),
            )
        conn.execute(
            """
            update meter_reservations
            set status = 'refunded', refunded_at = ?
            where reservation_id = ?
            """,
            (now, reservation_id),
        )
    return {"reservation_id": reservation_id, "user_id": user_id, "refunded": True}


def add_credit_pack(
    user_id: str,
    *,
    pack_id: str,
    source: str,
    payment_reference: str,
    stripe_price_id: str | None = None,
) -> dict:
    if not isinstance(payment_reference, str):
        raise ValueError("payment_reference is required")
    payment_reference = payment_reference.strip()
    if not payment_reference:
        raise ValueError("payment_reference is required")

    pack = get_credit_pack(pack_id)
    now = time()
    expires_at = now + pack.valid_days * 86400
    credit_pack_id = f"pack_{secrets.token_urlsafe(10)}"
    with transaction() as conn:
        existing = conn.execute(
            """
            select id, pack_id, remaining_amount, expires_at
            from credit_packs
            where user_id = ? and source = ? and stripe_payment_intent_id = ?
              and pack_id = ?
            """,
            (user_id, source, payment_reference, pack.id),
        ).fetchone()
        if existing is not None:
            return _credit_pack_response(existing)

        conn.execute(
            """
            insert into credit_packs
            (id, user_id, pack_id, pack_type, source, stripe_price_id,
             stripe_payment_intent_id, purchased_amount, remaining_amount, expires_at,
             status, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                credit_pack_id,
                user_id,
                pack.id,
                pack.meter_type.value,
                source,
                stripe_price_id,
                payment_reference,
                pack.amount,
                pack.amount,
                expires_at,
                now,
                now,
            ),
        )
    return {
        "id": credit_pack_id,
        "pack_id": pack.id,
        "remaining_amount": pack.amount,
        "expires_at": expires_at,
    }


def _credit_pack_response(row) -> dict:
    return {
        "id": row["id"],
        "pack_id": row["pack_id"],
        "remaining_amount": int(row["remaining_amount"]),
        "expires_at": row["expires_at"],
    }


def _meter_status(user: User, meter_type: MeterType) -> dict:
    allowance = allowance_for_user(user, meter_type)
    conn = connect()
    try:
        row = conn.execute(
            f"""
            select {allowance.column}
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, allowance.period_type.value, allowance.period_key),
        ).fetchone()
        pack_remaining = conn.execute(
            """
            select coalesce(sum(remaining_amount), 0) as remaining
            from credit_packs
            where user_id = ? and pack_type = ? and status = 'active'
              and expires_at > ?
            """,
            (user.id, meter_type.value, time()),
        ).fetchone()
    finally:
        conn.close()
    used = int(row[allowance.column]) if row else 0
    pack_value = int(pack_remaining["remaining"]) if pack_remaining else 0
    return {
        "meter": meter_type.value,
        "period_type": allowance.period_type.value,
        "period_key": allowance.period_key,
        "limit": allowance.limit,
        "used": used,
        "remaining": max(allowance.limit - used, 0) + pack_value,
        "plan_remaining": max(allowance.limit - used, 0),
        "pack_remaining": pack_value,
    }


def entitlement_status(user: User) -> dict:
    plan_id = active_plan_id(user)
    meters = {
        MeterType.ANALYZE.value: _meter_status(user, MeterType.ANALYZE),
        MeterType.DOWNLOAD.value: _meter_status(user, MeterType.DOWNLOAD),
        MeterType.SUMMARY.value: _meter_status(user, MeterType.SUMMARY),
        MeterType.TRANSCRIPTION_MINUTES.value: _meter_status(
            user, MeterType.TRANSCRIPTION_MINUTES
        ),
    }
    return {
        "plan": plan_id,
        "meters": meters,
        "credit_packs": {
            "summary": {"remaining": meters["summary"]["pack_remaining"]},
            "transcription_minutes": {
                "remaining": meters["transcription_minutes"]["pack_remaining"]
            },
        },
    }
