import pytest

from app.services import database
from app.services.auth_service import create_user
from app.services.plan_catalog import MeterType
from app.services.usage_meter import (
    MeterExceeded,
    add_credit_pack,
    anonymous_usage_summary,
    consume_anonymous_meter,
    entitlement_status,
    refund_reservation,
    reserve_user_meter,
)


def test_anonymous_daily_limits_are_enforced(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_IP_HASH_SALT", "usage-test")
    database.initialize_database(tmp_path / "saveany.db")

    for _ in range(3):
        consume_anonymous_meter("203.0.113.10", MeterType.ANALYZE, reservation_id=None)

    with pytest.raises(MeterExceeded) as exc:
        consume_anonymous_meter("203.0.113.10", MeterType.ANALYZE, reservation_id=None)

    assert "访客解析次数已用完" in str(exc.value)
    summary = anonymous_usage_summary("203.0.113.10")
    assert summary["analyze"]["used"] == 3
    assert summary["analyze"]["remaining"] == 0


def test_free_user_summary_reservation_and_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("meter-free@example.com", "meter-password")

    usage = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="summary_one")
    assert usage["used"] == 1
    assert usage["remaining"] == 2

    refund = refund_reservation("summary_one")
    assert refund is not None

    status = entitlement_status(user)
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["summary"]["remaining"] == 3


def test_credit_pack_is_consumed_after_plan_allowance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-user@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_1")

    for index in range(3):
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=f"plan_{index}")

    usage = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="pack_1")

    assert usage["used"] == 3
    assert usage["remaining"] == 19
    status = entitlement_status(user)
    assert status["credit_packs"]["summary"]["remaining"] == 19


def test_split_credit_pack_refund_restores_each_pack(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("split-pack@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_1")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_2")

    for index in range(3):
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=f"plan_split_{index}")

    reserve_user_meter(user, MeterType.SUMMARY, 25, reservation_id="split_pack")
    mid_status = entitlement_status(user)
    assert mid_status["credit_packs"]["summary"]["remaining"] == 15

    refund_reservation("split_pack")
    status = entitlement_status(user)

    assert status["credit_packs"]["summary"]["remaining"] == 40


def test_transcription_minutes_round_trip_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("transcribe@example.com", "meter-password")

    usage = reserve_user_meter(
        user,
        MeterType.TRANSCRIPTION_MINUTES,
        12,
        reservation_id="transcription_12",
    )
    assert usage["used"] == 12
    assert usage["remaining"] == 18

    refund_reservation("transcription_12")
    status = entitlement_status(user)

    assert status["meters"]["transcription_minutes"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["remaining"] == 30
