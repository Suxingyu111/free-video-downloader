import pytest

from app.services import database
from app.services.auth_service import create_user
from app.services.entitlements import (
    QuotaExceeded,
    consume_summary_quota,
    get_usage_summary,
    refund_summary_quota_reservation,
    reserve_summary_quota,
)
from app.services.plan_catalog import PeriodType
from app.services.usage_meter import refund_reservation
from tests.helpers import activate_pro_subscription


def fixed_period_key(period_type: PeriodType) -> str:
    return "2026-05-01" if period_type == PeriodType.DAY else "2026-05"


def test_free_user_gets_three_daily_summary_uses(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("free@example.com", "free-password")

    assert consume_summary_quota(user).remaining_today == 2
    assert consume_summary_quota(user).remaining_today == 1
    assert consume_summary_quota(user).remaining_today == 0

    with pytest.raises(QuotaExceeded, match="今日免费 AI 总结额度已用完"):
        consume_summary_quota(user)


def test_free_summary_daily_limit_env_is_honored(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "1")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("one-free@example.com", "free-password")

    usage = consume_summary_quota(user)

    assert usage.daily_free_limit == 1
    assert usage.used_today == 1
    assert usage.remaining_today == 0
    with pytest.raises(QuotaExceeded, match="今日免费 AI 总结额度已用完"):
        consume_summary_quota(user)


def test_member_does_not_consume_free_daily_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pro@example.com", "pro-password")
    activate_pro_subscription(user)

    for _ in range(5):
        usage = consume_summary_quota(user)

    assert usage.membership_active is True
    assert get_usage_summary(user).used_today == 0


def test_legacy_daily_usage_seeds_new_meter_without_downward_overwrite(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    monkeypatch.setattr("app.services.usage_meter.current_period_key", fixed_period_key)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("legacy-seed@example.com", "legacy-password")

    with database.transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, 3, 1, 1)
            """,
            (user.id, "2026-05-01"),
        )

    usage = get_usage_summary(user)

    assert usage.used_today == 3
    assert usage.remaining_today == 0
    with pytest.raises(QuotaExceeded, match="今日免费 AI 总结额度已用完"):
        reserve_summary_quota(user, "legacy_seed_full")

    with database.connect(tmp_path / "saveany.db") as conn:
        legacy = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()
        seeded = conn.execute(
            """
            select summary_count
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, PeriodType.DAY.value, "2026-05-01"),
        ).fetchone()

    assert legacy["summary_count"] == 3
    assert seeded["summary_count"] == 3


def test_legacy_only_summary_reservation_refund_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    monkeypatch.setattr("app.services.usage_meter.current_period_key", fixed_period_key)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("legacy-refund@example.com", "legacy-password")

    with database.transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, 1, 1, 1)
            """,
            (user.id, "2026-05-01"),
        )
        conn.execute(
            """
            insert into summary_quota_reservations
            (reservation_id, user_id, usage_date, created_at)
            values (?, ?, ?, 1)
            """,
            ("legacy_only_refund", user.id, "2026-05-01"),
        )

    first = refund_summary_quota_reservation("legacy_only_refund")
    second = refund_summary_quota_reservation("legacy_only_refund")

    assert first is not None
    assert first.used_today == 0
    assert second is not None
    assert second.used_today == 0
    with database.connect(tmp_path / "saveany.db") as conn:
        legacy = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()
        reservation = conn.execute(
            """
            select refunded_at
            from summary_quota_reservations
            where reservation_id = ?
            """,
            ("legacy_only_refund",),
        ).fetchone()
        new_reservations = conn.execute(
            """
            select count(*) as reservation_count
            from meter_reservations
            where reservation_id = ?
            """,
            ("legacy_only_refund",),
        ).fetchone()

    assert legacy["summary_count"] == 0
    assert reservation["refunded_at"] is not None
    assert new_reservations["reservation_count"] == 0


def test_refunded_meter_reservation_is_not_reseeded_from_stale_legacy_usage(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    monkeypatch.setattr("app.services.usage_meter.current_period_key", fixed_period_key)
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("refund-race@example.com", "refund-password")
    reserve_summary_quota(user, "summary_refund_race")

    refund_reservation("summary_refund_race")
    usage = get_usage_summary(user)

    assert usage.used_today == 0
    assert usage.remaining_today == 3
    with database.connect(tmp_path / "saveany.db") as conn:
        period = conn.execute(
            """
            select summary_count
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, PeriodType.DAY.value, "2026-05-01"),
        ).fetchone()
        legacy = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()

    assert period["summary_count"] == 0
    assert legacy["summary_count"] == 1


def test_reservation_refund_uses_original_usage_date(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("rollover@example.com", "rollover-password")

    def first_period_key(period_type: PeriodType) -> str:
        return "2026-05-01" if period_type == PeriodType.DAY else "2026-05"

    monkeypatch.setattr("app.services.usage_meter.current_period_key", first_period_key)
    usage = reserve_summary_quota(user, "summary_rollover")

    assert usage.used_today == 1
    with database.connect(tmp_path / "saveany.db") as conn:
        initial_legacy_day = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()
    assert initial_legacy_day["summary_count"] == 1

    def second_period_key(period_type: PeriodType) -> str:
        return "2026-05-02" if period_type == PeriodType.DAY else "2026-05"

    monkeypatch.setattr("app.services.usage_meter.current_period_key", second_period_key)
    refund = refund_summary_quota_reservation("summary_rollover")

    assert refund is not None
    assert refund.used_today == 0
    with database.connect(tmp_path / "saveany.db") as conn:
        original_day = conn.execute(
            """
            select summary_count
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, PeriodType.DAY.value, "2026-05-01"),
        ).fetchone()
        next_day = conn.execute(
            """
            select summary_count
            from usage_periods
            where user_id = ? and period_type = ? and period_key = ?
            """,
            (user.id, PeriodType.DAY.value, "2026-05-02"),
        ).fetchone()
        legacy_original_day = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()
        legacy_next_day = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-02"),
        ).fetchone()
        legacy_reservation = conn.execute(
            """
            select refunded_at
            from summary_quota_reservations
            where reservation_id = ? and usage_date = ?
            """,
            ("summary_rollover", "2026-05-01"),
        ).fetchone()

    assert original_day["summary_count"] == 0
    assert next_day is None
    assert legacy_original_day["summary_count"] == 0
    assert legacy_next_day is None
    assert legacy_reservation["refunded_at"] is not None


def test_entitlement_status_api_shape_for_free_user(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("status@example.com", "status-password")

    usage = consume_summary_quota(user)
    status = get_usage_summary(user).as_dict()

    assert usage.used_today == 1
    assert status["daily_free_limit"] == 3
    assert status["used_today"] == 1
    assert status["remaining_today"] == 2
    assert status["membership_active"] is False
    assert "meters" in status
    assert status["meters"]["summary"]["remaining"] == 2
