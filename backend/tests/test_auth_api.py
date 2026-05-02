from fastapi.testclient import TestClient

from app.main import app
from app.services import database
from app.services.auth_service import get_user_by_id
from app.services.billing_service import activate_mock_subscription


def test_register_login_me_logout_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    registered = client.post(
        "/api/auth/register",
        json={"email": "USER@example.com", "password": "correct horse battery staple"},
    )
    assert registered.status_code == 200
    assert registered.json()["user"]["email"] == "user@example.com"
    assert "password" not in registered.text

    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert login.cookies.get("saveany_session")

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "user@example.com"
    assert me.json()["membership"]["plan"] == "free"
    assert me.json()["usage"]["daily_free_limit"] == 3

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_login_rejects_wrong_password(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "bad-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


def test_login_rate_limit_blocks_repeated_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "limited@example.com", "password": "correct horse battery staple"},
    )

    first = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "bad-password"},
    )
    second = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "bad-password"},
    )
    blocked = client.post(
        "/api/auth/login",
        json={"email": "limited@example.com", "password": "correct horse battery staple"},
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
    client.post(
        "/api/auth/register",
        json={"email": "clear@example.com", "password": "correct horse battery staple"},
    )

    failed = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "bad-password"},
    )
    success = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "correct horse battery staple"},
    )
    failed_again = client.post(
        "/api/auth/login",
        json={"email": "clear@example.com", "password": "bad-password"},
    )

    assert failed.status_code == 401
    assert success.status_code == 200
    assert failed_again.status_code == 401


def test_register_rejects_duplicate_email(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    first = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert first.status_code == 200

    duplicate = client.post(
        "/api/auth/register",
        json={"email": "USER@example.com", "password": "another correct horse battery staple"},
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
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "old-password-123"},
    )

    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_password_reset_token_is_single_use(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "old-password-123"},
    )

    request = client.post(
        "/api/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    assert request.status_code == 200
    token = request.json()["reset_token"]

    first = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password-123"},
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password-456"},
    )

    assert first.status_code == 200
    assert second.status_code == 400


def test_me_includes_entitlement_status(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "entitlements@example.com", "password": "correct horse battery staple"},
    )

    response = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["plan"] == "free"
    assert response.json()["meters"]["summary"]["limit"] == 3
    assert response.json()["meters"]["transcription_minutes"]["limit"] == 30


def test_me_keeps_legacy_daily_usage_fields_for_pro(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "3")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "pro-usage@example.com", "password": "correct horse battery staple"},
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
