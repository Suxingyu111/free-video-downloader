from app.services.plan_catalog import (
    CREDIT_PACK_CATALOG,
    PLAN_CATALOG,
    CreditPackDefinition,
    MeterType,
    PeriodType,
    current_period_key,
    get_credit_pack,
    get_plan_limits,
)


def test_personal_plan_catalog_has_confirmed_limits():
    anonymous = get_plan_limits("anonymous")
    free = get_plan_limits("free")
    pro = get_plan_limits("pro")

    assert anonymous.analyze_daily_limit == 3
    assert anonymous.download_daily_limit == 1
    assert anonymous.download_max_duration_seconds == 30 * 60

    assert free.analyze_daily_limit == 30
    assert free.download_daily_limit == 10
    assert free.summary_daily_limit == 3
    assert free.transcription_monthly_minutes == 30
    assert free.questions_per_summary == 3

    assert pro.analyze_monthly_limit == 300
    assert pro.download_monthly_limit == 100
    assert pro.summary_monthly_limit == 120
    assert pro.transcription_monthly_minutes == 600
    assert pro.questions_per_summary == 20


def test_credit_pack_catalog_has_confirmed_packs():
    assert CREDIT_PACK_CATALOG["summary_small"].amount == 20
    assert CREDIT_PACK_CATALOG["summary_small"].price_label == "¥6"
    assert CREDIT_PACK_CATALOG["summary_small"].valid_days == 90
    assert CREDIT_PACK_CATALOG["summary_large"].amount == 100
    assert CREDIT_PACK_CATALOG["transcription_small"].amount == 120
    assert CREDIT_PACK_CATALOG["transcription_large"].amount == 600
    assert get_credit_pack("summary_small").meter_type == MeterType.SUMMARY
    assert get_credit_pack("transcription_large").meter_type == MeterType.TRANSCRIPTION_MINUTES


def test_current_period_keys_are_stable(monkeypatch):
    class FixedDatetime:
        @classmethod
        def now(cls, timezone):
            from datetime import datetime

            return datetime(2026, 5, 2, 12, 30, tzinfo=timezone)

    monkeypatch.setattr("app.services.plan_catalog.datetime", FixedDatetime)

    assert current_period_key(PeriodType.DAY) == "2026-05-02"
    assert current_period_key(PeriodType.MONTH) == "2026-05"


def test_catalog_rejects_unknown_ids():
    try:
        get_plan_limits("team")
    except KeyError as exc:
        assert "Unknown plan" in str(exc)
    else:
        raise AssertionError("expected unknown plan to fail")

    try:
        get_credit_pack("missing_pack")
    except KeyError as exc:
        assert "Unknown credit pack" in str(exc)
    else:
        raise AssertionError("expected unknown credit pack to fail")
