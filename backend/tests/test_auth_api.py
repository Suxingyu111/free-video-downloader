from fastapi.testclient import TestClient

from app.main import app
from app.services import database


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
