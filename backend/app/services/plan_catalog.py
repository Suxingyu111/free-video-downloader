from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class PeriodType(StrEnum):
    DAY = "day"
    MONTH = "month"


class MeterType(StrEnum):
    ANALYZE = "analyze"
    DOWNLOAD = "download"
    SUMMARY = "summary"
    TRANSCRIPTION_MINUTES = "transcription_minutes"
    QUESTION = "question"


@dataclass(frozen=True)
class PlanLimits:
    id: str
    name: str
    analyze_daily_limit: int | None = None
    analyze_monthly_limit: int | None = None
    download_daily_limit: int | None = None
    download_monthly_limit: int | None = None
    download_max_duration_seconds: int | None = None
    summary_daily_limit: int | None = None
    summary_monthly_limit: int | None = None
    summary_max_duration_seconds: int | None = None
    transcription_monthly_minutes: int | None = None
    question_monthly_limit: int | None = None


@dataclass(frozen=True)
class CreditPackDefinition:
    id: str
    name: str
    meter_type: MeterType
    amount: int
    valid_days: int
    price_label: str
    stripe_config_field: str


PLAN_CATALOG: dict[str, PlanLimits] = {
    "anonymous": PlanLimits(
        id="anonymous",
        name="未登录访客",
        analyze_daily_limit=3,
        download_daily_limit=1,
        download_max_duration_seconds=30 * 60,
    ),
    "free": PlanLimits(
        id="free",
        name="免费版",
        analyze_daily_limit=30,
        download_daily_limit=10,
        download_max_duration_seconds=60 * 60,
        summary_daily_limit=3,
        summary_max_duration_seconds=30 * 60,
        transcription_monthly_minutes=30,
        question_monthly_limit=10,
    ),
    "pro": PlanLimits(
        id="pro",
        name="Pro 个人版",
        analyze_monthly_limit=300,
        download_monthly_limit=100,
        download_max_duration_seconds=180 * 60,
        summary_monthly_limit=120,
        summary_max_duration_seconds=120 * 60,
        transcription_monthly_minutes=600,
        question_monthly_limit=200,
    ),
}

CREDIT_PACK_CATALOG: dict[str, CreditPackDefinition] = {
    "summary_small": CreditPackDefinition(
        id="summary_small",
        name="总结小包",
        meter_type=MeterType.SUMMARY,
        amount=20,
        valid_days=90,
        price_label="¥6",
        stripe_config_field="stripe_summary_small_pack_price_id",
    ),
    "summary_large": CreditPackDefinition(
        id="summary_large",
        name="总结大包",
        meter_type=MeterType.SUMMARY,
        amount=100,
        valid_days=180,
        price_label="¥19",
        stripe_config_field="stripe_summary_large_pack_price_id",
    ),
    "transcription_small": CreditPackDefinition(
        id="transcription_small",
        name="转写小包",
        meter_type=MeterType.TRANSCRIPTION_MINUTES,
        amount=120,
        valid_days=90,
        price_label="¥8",
        stripe_config_field="stripe_transcription_small_pack_price_id",
    ),
    "transcription_large": CreditPackDefinition(
        id="transcription_large",
        name="转写大包",
        meter_type=MeterType.TRANSCRIPTION_MINUTES,
        amount=600,
        valid_days=180,
        price_label="¥29",
        stripe_config_field="stripe_transcription_large_pack_price_id",
    ),
}


def get_plan_limits(plan_id: str) -> PlanLimits:
    try:
        return PLAN_CATALOG[plan_id]
    except KeyError as exc:
        raise KeyError(f"Unknown plan: {plan_id}") from exc


def get_credit_pack(pack_id: str) -> CreditPackDefinition:
    try:
        return CREDIT_PACK_CATALOG[pack_id]
    except KeyError as exc:
        raise KeyError(f"Unknown credit pack: {pack_id}") from exc


def current_period_key(period_type: PeriodType) -> str:
    today = datetime.now(timezone.utc).date()
    if period_type == PeriodType.DAY:
        return today.isoformat()
    if period_type == PeriodType.MONTH:
        return f"{today.year:04d}-{today.month:02d}"
    raise ValueError(f"Unsupported period type: {period_type}")
