import pytest

from app.services.app_config import RUNTIME_DIR
from app.services.app_config import load_config
from app.services import database


def test_initialize_database_creates_membership_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))

    database.initialize_database(db_path)

    conn = database.connect(db_path)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "users",
        "sessions",
        "password_reset_tokens",
        "subscriptions",
        "stripe_customers",
        "stripe_events",
        "usage_daily",
        "summary_quota_reservations",
        "billing_attempts",
        "rate_limits",
    }.issubset(tables)


def test_database_uses_row_factory(tmp_path):
    db_path = tmp_path / "saveany.db"
    database.initialize_database(db_path)

    conn = database.connect(db_path)
    try:
        row = conn.execute("select 1 as value").fetchone()
    finally:
        conn.close()

    assert row["value"] == 1


def test_initialize_database_closes_connection(monkeypatch):
    class FakeConnection:
        closed = False

        def executescript(self, _: str) -> None:
            pass

        def execute(self, _: str):
            class Result:
                def fetchall(self):
                    return [{"name": "status"}]

            return Result()

        def commit(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    conn = FakeConnection()
    monkeypatch.setattr(database, "connect", lambda db_path=None: conn)

    database.initialize_database()

    assert conn.closed is True


def test_load_config_defaults_db_path_to_runtime_dir(monkeypatch):
    monkeypatch.delenv("SAVEANY_DB_PATH", raising=False)
    monkeypatch.delenv("BILLING_MODE", raising=False)

    config = load_config()

    assert config.db_path == RUNTIME_DIR / "saveany.db"


def test_load_config_rejects_invalid_billing_mode(monkeypatch):
    monkeypatch.setenv("BILLING_MODE", "invalid")

    with pytest.raises(ValueError, match="BILLING_MODE must be one of: mock, stripe"):
        load_config()


def test_quota_schema_tables_are_created(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)

    with database.connect(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert "usage_periods" in tables
    assert "anonymous_usage" in tables
    assert "meter_reservations" in tables
    assert "meter_reservation_pack_uses" in tables
    assert "credit_packs" in tables
    assert "summary_questions" in tables


def test_stripe_customer_schema_table_is_created(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)

    with database.connect(db_path) as conn:
        columns = {
            row["name"]
            for row in conn.execute("pragma table_info(stripe_customers)").fetchall()
        }
        unique_index_columns = []
        for index in conn.execute("pragma index_list(stripe_customers)").fetchall():
            if index["unique"]:
                unique_index_columns.append(
                    [
                        row["name"]
                        for row in conn.execute(
                            f"pragma index_info({index['name']})"
                        ).fetchall()
                    ]
                )

    assert {
        "user_id",
        "stripe_customer_id",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert ["stripe_customer_id"] in unique_index_columns


def test_billing_attempts_migration_adds_purchase_metadata(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    with database.connect(db_path) as conn:
        conn.execute(
            """
            create table billing_attempts (
              id text primary key,
              user_id text not null,
              mode text not null,
              status text not null,
              stripe_checkout_session_id text,
              stripe_checkout_url text,
              stripe_return_url text,
              created_at real not null,
              updated_at real not null
            )
            """
        )
        conn.execute(
            """
            insert into billing_attempts
            (id, user_id, mode, status, created_at, updated_at)
            values ('attempt_old', 'user_old', 'stripe', 'open', 1, 1)
            """
        )

    database.initialize_database(db_path)

    with database.connect(db_path) as conn:
        columns = {
            row["name"]
            for row in conn.execute("pragma table_info(billing_attempts)").fetchall()
        }
        row = conn.execute(
            "select purchase_type, pack_id, stripe_price_id from billing_attempts where id = 'attempt_old'"
        ).fetchone()

    assert {"purchase_type", "pack_id", "stripe_price_id"}.issubset(columns)
    assert row["purchase_type"] == "subscription"
    assert row["pack_id"] is None
    assert row["stripe_price_id"] is None
