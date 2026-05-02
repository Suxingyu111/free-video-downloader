from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.services.auth_service import User, get_user_by_id
from app.services.plan_catalog import MeterType
from app.services.usage_meter import (
    MeterExceeded,
    entitlement_status,
    refund_reservation,
    reserve_user_meter,
)


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
    status = entitlement_status(user)
    summary = status["meters"]["summary"]
    membership_active = status["plan"] == "pro"
    limit = summary["limit"]
    used = summary["used"]
    remaining = summary["remaining"]
    if membership_active:
        used_today = 0
        remaining_today = limit
    else:
        used_today = used
        remaining_today = remaining
    return UsageSummary(
        daily_free_limit=limit,
        used_today=used_today,
        remaining_today=remaining_today,
        membership_active=membership_active,
        meters=status["meters"],
        credit_packs=status["credit_packs"],
    )


def reserve_summary_quota(user: User, reservation_id: str) -> UsageSummary:
    try:
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=reservation_id)
    except MeterExceeded as exc:
        raise QuotaExceeded(str(exc)) from exc
    return get_usage_summary(user)


def consume_summary_quota(user: User) -> UsageSummary:
    return reserve_summary_quota(user, f"manual_{secrets.token_urlsafe(10)}")


def refund_summary_quota_reservation(reservation_id: str) -> UsageSummary | None:
    refund = refund_reservation(reservation_id)
    if refund is None:
        return None
    user = get_user_by_id(refund["user_id"])
    return get_usage_summary(user) if user else None
