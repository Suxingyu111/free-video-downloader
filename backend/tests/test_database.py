import pytest

from app.services.app_config import RUNTIME_DIR
from app.services.app_config import load_config
from app.services import database


def test_initialize_database_creates_membership_tables(tmp_path, monkeypatch):
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

    assert {
        "users",
        "sessions",
        "password_reset_tokens",
        "subscriptions",
        "stripe_events",
        "usage_daily",
        "billing_attempts",
        "rate_limits",
    }.issubset(tables)


def test_database_uses_row_factory(tmp_path):
    db_path = tmp_path / "saveany.db"
    database.initialize_database(db_path)

    with database.connect(db_path) as conn:
        row = conn.execute("select 1 as value").fetchone()

    assert row["value"] == 1


def test_initialize_database_closes_connection(monkeypatch):
    class FakeConnection:
        closed = False

        def executescript(self, _: str) -> None:
            pass

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
