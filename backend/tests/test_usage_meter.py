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
from tests.helpers import activate_pro_subscription


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


def test_free_user_question_monthly_limit_and_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("question-free@example.com", "meter-password")

    for index in range(10):
        usage = reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=f"question_free_{index}",
        )

    assert usage["limit"] == 10
    assert usage["used"] == 10
    assert usage["remaining"] == 0

    with pytest.raises(MeterExceeded) as exc:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id="question_free_11",
        )

    assert "AI 问答次数不足" in str(exc.value)

    refund_reservation("question_free_9")
    status = entitlement_status(user)

    assert status["meters"]["question"]["limit"] == 10
    assert status["meters"]["question"]["used"] == 9
    assert status["meters"]["question"]["remaining"] == 1


def test_pro_user_question_monthly_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("question-pro@example.com", "meter-password")
    activate_pro_subscription(user)

    for index in range(200):
        usage = reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=f"question_pro_{index}",
        )

    assert usage["limit"] == 200
    assert usage["used"] == 200
    assert usage["remaining"] == 0

    with pytest.raises(MeterExceeded) as exc:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id="question_pro_201",
        )

    assert "AI 问答次数不足" in str(exc.value)


def test_credit_pack_is_consumed_after_plan_allowance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-user@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="stripe", payment_reference="pi_pack_1")

    for index in range(3):
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=f"plan_{index}")

    usage = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="pack_1")

    assert usage["used"] == 3
    assert usage["remaining"] == 19
    status = entitlement_status(user)
    assert status["credit_packs"]["summary"]["remaining"] == 19


def test_add_credit_pack_rejects_none_payment_reference(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    user = create_user("pack-none-payment@example.com", "meter-password")

    with pytest.raises(ValueError, match="payment_reference"):
        add_credit_pack(
            user.id,
            pack_id="summary_small",
            source="stripe",
            payment_reference=None,
        )

    with database.connect(db_path) as conn:
        row = conn.execute(
            "select count(*) as pack_count from credit_packs where user_id = ?",
            (user.id,),
        ).fetchone()

    assert row["pack_count"] == 0


@pytest.mark.parametrize("payment_reference", ["", "   "])
def test_add_credit_pack_rejects_blank_payment_reference(
    monkeypatch, tmp_path, payment_reference
):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    user = create_user("pack-blank-payment@example.com", "meter-password")

    with pytest.raises(ValueError, match="payment_reference"):
        add_credit_pack(
            user.id,
            pack_id="summary_small",
            source="stripe",
            payment_reference=payment_reference,
        )

    with database.connect(db_path) as conn:
        row = conn.execute(
            "select count(*) as pack_count from credit_packs where user_id = ?",
            (user.id,),
        ).fetchone()

    assert row["pack_count"] == 0


def test_add_credit_pack_is_idempotent_for_payment_reference(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    user = create_user("pack-idempotent@example.com", "meter-password")

    first = add_credit_pack(
        user.id,
        pack_id="summary_small",
        source="stripe",
        payment_reference="payment_1",
    )
    second = add_credit_pack(
        user.id,
        pack_id="summary_small",
        source="stripe",
        payment_reference="payment_1",
    )

    with database.connect(db_path) as conn:
        row = conn.execute(
            """
            select count(*) as pack_count, coalesce(sum(remaining_amount), 0) as remaining
            from credit_packs
            where user_id = ?
            """,
            (user.id,),
        ).fetchone()

    assert second["id"] == first["id"]
    assert row["pack_count"] == 1
    assert row["remaining"] == 20
    assert entitlement_status(user)["credit_packs"]["summary"]["remaining"] == 20


def test_duplicate_reservation_is_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    user = create_user("reservation-idempotent@example.com", "meter-password")

    first = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="same_summary")
    second = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="same_summary")

    with database.connect(db_path) as conn:
        row = conn.execute(
            """
            select count(*) as reservation_count
            from meter_reservations
            where reservation_id = 'same_summary'
            """
        ).fetchone()

    assert first["used"] == 1
    assert second["used"] == 1
    assert second["remaining"] == 2
    assert row["reservation_count"] == 1
    assert entitlement_status(user)["meters"]["summary"]["used"] == 1

    with pytest.raises(ValueError, match="reservation_id"):
        reserve_user_meter(user, MeterType.SUMMARY, 2, reservation_id="same_summary")


def test_insufficient_credit_pack_reserve_rolls_back_partial_pack_updates(
    monkeypatch, tmp_path
):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    user = create_user("pack-rollback@example.com", "meter-password")
    add_credit_pack(
        user.id,
        pack_id="summary_small",
        source="stripe",
        payment_reference="rollback_1",
    )

    for index in range(3):
        reserve_user_meter(
            user,
            MeterType.SUMMARY,
            1,
            reservation_id=f"rollback_plan_{index}",
        )

    with pytest.raises(MeterExceeded):
        reserve_user_meter(user, MeterType.SUMMARY, 25, reservation_id="too_large_pack")

    with database.connect(db_path) as conn:
        pack = conn.execute(
            """
            select remaining_amount, status
            from credit_packs
            where user_id = ?
            """,
            (user.id,),
        ).fetchone()
        failed_reservation = conn.execute(
            """
            select count(*) as reservation_count
            from meter_reservations
            where reservation_id = 'too_large_pack'
            """
        ).fetchone()

    assert pack["remaining_amount"] == 20
    assert pack["status"] == "active"
    assert failed_reservation["reservation_count"] == 0
    status = entitlement_status(user)
    assert status["meters"]["summary"]["used"] == 3
    assert status["credit_packs"]["summary"]["remaining"] == 20


def test_split_credit_pack_refund_restores_each_pack(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("split-pack@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="stripe", payment_reference="pi_pack_1")
    add_credit_pack(user.id, pack_id="summary_small", source="stripe", payment_reference="pi_pack_2")

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
