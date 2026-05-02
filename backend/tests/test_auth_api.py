from time import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import database
from app.services.auth_service import get_user_by_id
from app.services.billing_service import activate_mock_subscription
from app.services.plan_catalog import PeriodType


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {
        "x-csrf-token": response.json()["csrf_token"],
        "origin": "http://localhost:5173",
    }


def register_with_csrf(client: TestClient, email: str, password: str):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def set_session_expiry(db_path, expires_at: float, absolute_expires_at: float | None) -> None:
    conn = database.connect(db_path)
    try:
        conn.execute(
            "update sessions set expires_at = ?, absolute_expires_at = ?",
            (expires_at, absolute_expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def session_expiry(db_path) -> float:
    conn = database.connect(db_path)
    try:
        return conn.execute("select expires_at from sessions").fetchone()["expires_at"]
    finally:
        conn.close()


def test_register_login_me_logout_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    registered = register_with_csrf(client, "USER@example.com", "correct horse battery staple")
    assert registered.status_code == 200
    assert registered.json()["user"]["email"] == "user@example.com"
    assert "password" not in registered.text
    assert registered.json()["csrf_token"]

    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
        headers=csrf_headers(client),
    )
    assert login.status_code == 200
    assert login.cookies.get("saveany_session")
    assert login.json()["csrf_token"]

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "user@example.com"
    assert me.json()["membership"]["plan"] == "free"
    assert me.json()["usage"]["daily_free_limit"] == 3

    logout = client.post(
        "/api/auth/logout",
        headers={"x-csrf-token": login.json()["csrf_token"], "origin": "http://localhost:5173"},
    )
    assert logout.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_register_requires_prelogin_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403


def test_register_requires_origin_or_referer_with_prelogin_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    token = client.get("/api/csrf").json()["csrf_token"]

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "请求来源不被允许"


def test_register_rejects_invalid_origin_with_prelogin_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    token = client.get("/api/csrf").json()["csrf_token"]

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
        headers={"x-csrf-token": token, "origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "请求来源不被允许"


def test_login_returns_session_csrf_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "correct horse battery staple")

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"]


def test_me_refreshes_idle_session_expiry(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "correct horse battery staple")
    now = time()
    original_expires_at = now + 60
    absolute_expires_at = now + 30 * 86400
    set_session_expiry(db_path, original_expires_at, absolute_expires_at)

    response = client.get("/api/me")

    assert response.status_code == 200
    refreshed_expires_at = session_expiry(db_path)
    assert refreshed_expires_at > original_expires_at
    assert refreshed_expires_at < absolute_expires_at


def test_me_refreshes_idle_session_expiry_without_exceeding_absolute(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "correct horse battery staple")
    now = time()
    original_expires_at = now + 5
    absolute_expires_at = now + 20
    set_session_expiry(db_path, original_expires_at, absolute_expires_at)

    response = client.get("/api/me")

    assert response.status_code == 200
    refreshed_expires_at = session_expiry(db_path)
    assert refreshed_expires_at > original_expires_at
    assert refreshed_expires_at <= absolute_expires_at


def test_logout_requires_session_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "correct horse battery staple")

    response = client.post("/api/auth/logout")

    assert response.status_code == 403


def test_session_cookie_secure_flag_follows_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = register_with_csrf(client, "user@example.com", "correct horse battery staple")

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_rejects_wrong_password(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "correct horse battery staple")

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "bad-password"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


def test_login_rate_limit_blocks_repeated_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "limited@example.com", "correct horse battery staple")

    first = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "bad-password"},
        headers=csrf_headers(client),
    )
    second = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "bad-password"},
        headers=csrf_headers(client),
    )
    blocked = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "correct horse battery staple"},
        headers=csrf_headers(client),
    )

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "操作太频繁，请稍后再试"


def test_successful_login_clears_failed_login_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "clear@example.com", "correct horse battery staple")

    failed = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "bad-password"},
        headers=csrf_headers(client),
    )
    success = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "correct horse battery staple"},
        headers=csrf_headers(client),
    )
    failed_again = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "bad-password"},
        headers=csrf_headers(client),
    )

    assert failed.status_code == 401
    assert success.status_code == 200
    assert failed_again.status_code == 401


def test_register_rejects_duplicate_email(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    first = register_with_csrf(client, "user@example.com", "correct horse battery staple")
    assert first.status_code == 200

    duplicate = client.post(
        "/api/auth/register",
        json={"email": "USER@example.com", "password": "another correct horse battery staple"},
        headers=csrf_headers(client),
    )

    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "邮箱已被注册"
    assert "UNIQUE" not in duplicate.text


def test_logout_requires_authentication(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post("/api/auth/logout")

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_password_reset_request_hides_token_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_password_reset_token_is_single_use(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )
    assert request.status_code == 200
    token = request.json()["reset_token"]

    first = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password-456"},
        headers=csrf_headers(client),
    )

    assert first.status_code == 200
    assert second.status_code == 400


def test_password_reset_token_ttl_follows_config(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    monkeypatch.setenv("PASSWORD_RESET_TOKEN_MINUTES", "2")
    database.initialize_database(db_path)
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    conn = database.connect(db_path)
    try:
        row = conn.execute(
            "select created_at, expires_at from password_reset_tokens"
        ).fetchone()
    finally:
        conn.close()
    assert row["expires_at"] - row["created_at"] == 120


def test_password_reset_revokes_existing_sessions(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(db_path)
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )
    assert request.status_code == 200
    token = request.json()["reset_token"]

    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password-123"},
        headers=csrf_headers(client),
    )

    assert confirm.status_code == 200
    assert client.get("/api/me").status_code == 401
    conn = database.connect(db_path)
    try:
        row = conn.execute(
            "select revoked_at, revoked_reason from sessions"
        ).fetchone()
    finally:
        conn.close()
    assert row["revoked_at"] is not None
    assert row["revoked_reason"] == "password_reset"


def test_password_reset_confirm_is_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    first = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token", "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token", "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    blocked = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token", "password": "new-password-123"},
        headers=csrf_headers(client),
    )

    assert first.status_code == 400
    assert second.status_code == 400
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "操作太频繁，请稍后再试"


def test_password_reset_confirm_ip_limit_blocks_different_bad_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    first = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token-one", "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token-two", "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    blocked = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "bad-token-three", "password": "new-password-123"},
        headers=csrf_headers(client),
    )

    assert first.status_code == 400
    assert second.status_code == 400
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "操作太频繁，请稍后再试"


def test_password_reset_confirm_strips_token_whitespace(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )
    assert request.status_code == 200
    token = request.json()["reset_token"]

    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": f"  {token}\n", "password": "new-password-123"},
        headers=csrf_headers(client),
    )

    assert confirm.status_code == 200


def test_password_reset_request_revokes_previous_unused_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "user@example.com", "old-password-123")

    first_request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )
    second_request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
        headers=csrf_headers(client),
    )
    assert first_request.status_code == 200
    assert second_request.status_code == 200

    revoked_confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": first_request.json()["reset_token"], "password": "new-password-123"},
        headers=csrf_headers(client),
    )
    current_confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": second_request.json()["reset_token"], "password": "new-password-123"},
        headers=csrf_headers(client),
    )

    assert revoked_confirm.status_code == 400
    assert current_confirm.status_code == 200


def test_me_includes_entitlement_status(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register_with_csrf(client, "entitlements@example.com", "correct horse battery staple")

    response = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["plan"] == "free"
    assert response.json()["meters"]["summary"]["limit"] == 3
    assert response.json()["meters"]["transcription_minutes"]["limit"] == 30


def test_entitlement_status_seeds_legacy_daily_usage(monkeypatch, tmp_path):
    def fixed_period_key(period_type: PeriodType) -> str:
        return "2026-05-01" if period_type == PeriodType.DAY else "2026-05"

    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setattr("app.services.usage_meter.current_period_key", fixed_period_key)
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    registered = register_with_csrf(
        client,
        "legacy-status@example.com",
        "correct horse battery staple",
    )
    user_id = registered.json()["user"]["id"]
    with database.transaction(tmp_path / "saveany.db") as conn:
        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, 3, 1, 1)
            """,
            (user_id, "2026-05-01"),
        )

    response = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["meters"]["summary"]["used"] == 3
    assert response.json()["meters"]["summary"]["remaining"] == 0


def test_me_keeps_legacy_daily_usage_fields_for_pro(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    registered = register_with_csrf(
        client,
        "pro-usage@example.com",
        "correct horse battery staple",
    )
    user = get_user_by_id(registered.json()["user"]["id"])
    assert user is not None
    activate_mock_subscription(user)

    response = client.get("/api/me")

    assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["daily_free_limit"] == 3
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3
    assert usage["membership_active"] is True
    assert usage["meters"]["summary"]["limit"] == 120
