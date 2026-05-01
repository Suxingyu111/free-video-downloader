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
