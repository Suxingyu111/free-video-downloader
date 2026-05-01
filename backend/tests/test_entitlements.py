import pytest

from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import activate_mock_subscription
from app.services.entitlements import (
    QuotaExceeded,
    consume_summary_quota,
    get_usage_summary,
    refund_summary_quota_reservation,
    reserve_summary_quota,
)


def test_free_user_gets_three_daily_summary_uses(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("free@example.com", "free-password")

    assert consume_summary_quota(user).remaining_today == 2
    assert consume_summary_quota(user).remaining_today == 1
    assert consume_summary_quota(user).remaining_today == 0

    with pytest.raises(QuotaExceeded):
        consume_summary_quota(user)


def test_member_does_not_consume_free_daily_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pro@example.com", "pro-password")
    activate_mock_subscription(user)

    for _ in range(5):
        usage = consume_summary_quota(user)

    assert usage.membership_active is True
    assert get_usage_summary(user).used_today == 0


def test_reservation_refund_uses_original_usage_date(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("rollover@example.com", "rollover-password")

    monkeypatch.setattr("app.services.entitlements._today_key", lambda: "2026-05-01")
    usage = reserve_summary_quota(user, "summary_rollover")

    assert usage.used_today == 1

    monkeypatch.setattr("app.services.entitlements._today_key", lambda: "2026-05-02")
    refund = refund_summary_quota_reservation("summary_rollover")

    assert refund is not None
    assert refund.used_today == 0
    with database.connect(tmp_path / "saveany.db") as conn:
        original_day = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-01"),
        ).fetchone()
        next_day = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, "2026-05-02"),
        ).fetchone()

    assert original_day["summary_count"] == 0
    assert next_day is None
