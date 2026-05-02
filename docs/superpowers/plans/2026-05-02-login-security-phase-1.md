# Login Security Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现登录安全体系第一阶段，阻断当前最高风险：CSRF、生产 Cookie/配置误用、密码重置后旧 session 有效、AI 总结横向越权。

**Architecture:** 保留现有 FastAPI + SQLite + HttpOnly Cookie session 架构。新增预登录 CSRF token 与 session 绑定 CSRF token，扩展 session 表字段并让所有 Cookie 认证的状态变更接口校验 CSRF，给 summary task 增加 `owner_user_id` 并在读取/问答/SSE/Markdown 下载时强制校验归属。

**Tech Stack:** FastAPI, SQLite, Pydantic, argon2-cffi, pytest, FastAPI TestClient, Vue/Vite frontend only as API contract consumer in this phase.

---

## Scope

本计划只覆盖设计文档第一阶段：

1. Summary ownership 与读取授权。
2. 密码重置成功撤销所有 session。
3. 生产 Cookie 和生产配置启动校验。
4. CSRF token 和 Origin 校验。
5. 后端核心测试。

不在本计划实现前端 `apiFetch` 重构、跨标签页同步、SMTP、审计日志、数据清理任务、弱密码库和完整运营监控。这些属于第二、三阶段计划。

## File Structure

- Modify: `backend/app/services/app_config.py`
  - 增加 `SAVEANY_ENV`、`SAVEANY_ALLOWED_ORIGINS`、`PASSWORD_RESET_TOKEN_MINUTES`、`SAVEANY_SESSION_IDLE_DAYS`、生产启动校验。
- Create: `backend/app/services/csrf.py`
  - 生成和校验预登录 HMAC CSRF token，生成 session CSRF token，校验 Origin/Referer。
- Modify: `backend/app/services/database.py`
  - 扩展 `sessions` 和 `password_reset_tokens` 字段，并添加迁移函数。
- Modify: `backend/app/services/auth_service.py`
  - `create_session()` 返回 session token + csrf token；session 存储 CSRF hash；密码重置撤销旧 session；创建新 reset token 撤销旧 token。
- Modify: `backend/app/auth_routes.py`
  - 新增 `GET /api/csrf`；注册/登录/密码重置请求校验预登录 CSRF；登录后响应返回 session CSRF token；logout 校验 session CSRF。
- Modify: `backend/app/services/summary_store.py`
  - `SummarySnapshot` 增加 `owner_user_id`；支持按 owner 创建、持久化、克隆缓存任务。
- Modify: `backend/app/summary_routes.py`
  - 创建 summary 写入 owner；读取、问答、SSE、Markdown 都校验当前用户归属。
- Modify: `backend/app/billing_routes.py`
  - Checkout、Portal、mock billing、Checkout confirm 校验 session CSRF；webhook 保持 Stripe 签名校验但不要求 CSRF。
- Modify: `backend/tests/test_app_config.py`
  - 生产配置 guardrail 测试。
- Modify: `backend/tests/test_auth_api.py`
  - CSRF、Cookie 属性、密码重置撤销 session、reset confirm 限流测试。
- Modify: `backend/tests/test_summary_api.py`
  - 测试 helper 带 CSRF；新增跨账号 summary 隔离和缓存跨用户克隆测试。
- Modify: `backend/tests/test_billing_mock.py`
  - 测试 helper 带 CSRF；生产 mock billing guardrail 不在该文件执行，以 app config 测试覆盖。
- Modify: `backend/tests/test_billing_stripe_webhook.py`
  - 对 Cookie 认证的 billing 调用带 CSRF；webhook 测试不带 CSRF。

## Shared Test Helpers

在每个后端测试文件中优先使用本地 helper，避免跨文件引入导致测试耦合。核心模式如下：

```python
def csrf_headers(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def register_and_get_csrf(client, email="user@example.com", password="correct horse battery staple"):
    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}
```

登录后所有状态变更请求使用登录/注册响应里的 session CSRF token，而不是重新调用 `/api/csrf` 的预登录 token。

---

### Task 1: App Config Guardrails

**Files:**
- Modify: `backend/app/services/app_config.py`
- Modify: `backend/tests/test_app_config.py`

- [ ] **Step 1: Write failing tests for production guardrails**

Append these tests to `backend/tests/test_app_config.py`:

```python
def test_production_requires_secure_cookies(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "false")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://saveany.example")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://saveany.example")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_x")

    try:
        load_config()
    except ValueError as exc:
        assert "SAVEANY_SECURE_COOKIES=true" in str(exc)
    else:
        raise AssertionError("production without secure cookies should fail")


def test_production_rejects_dev_mode_and_mock_billing(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://saveany.example")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://saveany.example")
    monkeypatch.setenv("BILLING_MODE", "mock")

    try:
        load_config()
    except ValueError as exc:
        assert "SAVEANY_DEV_MODE" in str(exc) or "BILLING_MODE=mock" in str(exc)
    else:
        raise AssertionError("production dev mode or mock billing should fail")


def test_production_requires_https_public_app_url(monkeypatch, tmp_path):
    clear_app_config_env(monkeypatch)
    monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("SAVEANY_ENV", "production")
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    monkeypatch.setenv("PUBLIC_APP_URL", "http://saveany.example")
    monkeypatch.setenv("SAVEANY_ALLOWED_ORIGINS", "https://saveany.example")
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_x")

    try:
        load_config()
    except ValueError as exc:
        assert "PUBLIC_APP_URL" in str(exc)
    else:
        raise AssertionError("production http PUBLIC_APP_URL should fail")
```

- [ ] **Step 2: Run config tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_app_config.py -q
```

Expected: the three new tests fail because `SAVEANY_ENV`, allowed origins, and production validation do not exist yet.

- [ ] **Step 3: Extend `AppConfig` fields**

In `backend/app/services/app_config.py`, update `AppConfig`:

```python
@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    billing_mode: str
    dev_mode: bool
    environment: str
    allowed_origins: tuple[str, ...]
    auth_rate_limit_attempts: int
    auth_rate_limit_window_seconds: int
    password_reset_token_minutes: int
    free_summary_daily_limit: int
    session_cookie_name: str
    session_days: int
    session_idle_days: int
    secure_cookies: bool
    public_app_url: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_pro_monthly_price_id: str
    stripe_summary_small_pack_price_id: str
    stripe_summary_large_pack_price_id: str
    stripe_transcription_small_pack_price_id: str
    stripe_transcription_large_pack_price_id: str
    ip_hash_salt: str
```

- [ ] **Step 4: Add allowed origin parser and production validation**

Add these helpers above `load_config()`:

```python
def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


def _validate_production_config(config: AppConfig) -> None:
    if config.environment != "production":
        return
    if not config.secure_cookies:
        raise ValueError("SAVEANY_ENV=production requires SAVEANY_SECURE_COOKIES=true")
    if config.dev_mode:
        raise ValueError("SAVEANY_ENV=production forbids SAVEANY_DEV_MODE=true")
    if config.billing_mode == "mock":
        raise ValueError("SAVEANY_ENV=production forbids BILLING_MODE=mock")
    if not config.public_app_url.startswith("https://"):
        raise ValueError("SAVEANY_ENV=production requires HTTPS PUBLIC_APP_URL")
    if not config.allowed_origins or "*" in config.allowed_origins:
        raise ValueError("SAVEANY_ENV=production requires explicit SAVEANY_ALLOWED_ORIGINS")
    if config.billing_mode == "stripe":
        missing = [
            name
            for name, value in {
                "STRIPE_SECRET_KEY": config.stripe_secret_key,
                "STRIPE_WEBHOOK_SECRET": config.stripe_webhook_secret,
                "STRIPE_PRO_MONTHLY_PRICE_ID": config.stripe_pro_monthly_price_id,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Stripe production config missing: {', '.join(missing)}")
```

- [ ] **Step 5: Build and validate config before returning**

Replace the current direct `return` statement that constructs `AppConfig` in `load_config()` with the following block, which stores the constructed config in a local variable and validates it before returning:

```python
    public_app_url = config_value("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    allowed_origins = _split_csv(
        config_value("SAVEANY_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )
    environment = config_value("SAVEANY_ENV", "development").strip().lower()
    if environment not in {"development", "production"}:
        raise ValueError("SAVEANY_ENV must be one of: development, production")
    config = AppConfig(
        db_path=Path(os.getenv("SAVEANY_DB_PATH", RUNTIME_DIR / "saveany.db")),
        billing_mode=billing_mode,
        dev_mode=_bool_env("SAVEANY_DEV_MODE", False),
        environment=environment,
        allowed_origins=allowed_origins,
        auth_rate_limit_attempts=int(os.getenv("AUTH_RATE_LIMIT_ATTEMPTS", "5")),
        auth_rate_limit_window_seconds=int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")),
        password_reset_token_minutes=int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30")),
        free_summary_daily_limit=int(os.getenv("FREE_SUMMARY_DAILY_LIMIT", "3")),
        session_cookie_name=os.getenv(
            "SAVEANY_SESSION_COOKIE",
            "__Host-saveany_session" if environment == "production" else "saveany_session",
        ),
        session_days=int(os.getenv("SAVEANY_SESSION_DAYS", "30")),
        session_idle_days=int(os.getenv("SAVEANY_SESSION_IDLE_DAYS", "7")),
        secure_cookies=_bool_env("SAVEANY_SECURE_COOKIES", environment == "production"),
        public_app_url=public_app_url,
        stripe_secret_key=config_value("STRIPE_SECRET_KEY").strip(),
        stripe_webhook_secret=config_value("STRIPE_WEBHOOK_SECRET").strip(),
        stripe_pro_monthly_price_id=config_value("STRIPE_PRO_MONTHLY_PRICE_ID").strip(),
        stripe_summary_small_pack_price_id=config_value("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID").strip(),
        stripe_summary_large_pack_price_id=config_value("STRIPE_SUMMARY_LARGE_PACK_PRICE_ID").strip(),
        stripe_transcription_small_pack_price_id=config_value("STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID").strip(),
        stripe_transcription_large_pack_price_id=config_value("STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID").strip(),
        ip_hash_salt=config_value("SAVEANY_IP_HASH_SALT", "saveany-local-ip-meter").strip(),
    )
    _validate_production_config(config)
    return config
```

- [ ] **Step 6: Run config tests**

Run:

```bash
python -m pytest backend/tests/test_app_config.py -q
```

Expected: all app config tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/app_config.py backend/tests/test_app_config.py
git commit -m "test: 增加生产登录安全配置校验" -m "新增 SAVEANY_ENV、生产 Secure Cookie、HTTPS、allowed origins、dev mode 和 mock billing 的配置验收，防止登录安全配置误上生产。"
```

---

### Task 2: CSRF Service And Auth Route Integration

**Files:**
- Create: `backend/app/services/csrf.py`
- Modify: `backend/app/services/database.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/auth_routes.py`
- Modify: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Write failing CSRF tests**

At the top of `backend/tests/test_auth_api.py`, add:

```python
def csrf_headers(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def register_with_csrf(client, email="user@example.com", password="correct horse battery staple"):
    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response
```

Append these tests:

```python
def test_register_requires_prelogin_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
        json={"email": "csrf@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF 校验失败"


def test_login_returns_session_csrf_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register = register_with_csrf(client)

    login = client.post(
        "/api/auth/login",
        headers=csrf_headers(client),
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    assert "csrf_token" in register.json()
    assert "csrf_token" in login.json()
    assert login.json()["csrf_token"] != csrf_headers(client)["X-CSRF-Token"]


def test_logout_requires_session_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register = register_with_csrf(client)

    missing = client.post("/api/auth/logout")
    wrong = client.post("/api/auth/logout", headers={"X-CSRF-Token": "bad-token"})
    ok = client.post("/api/auth/logout", headers={"X-CSRF-Token": register.json()["csrf_token"]})

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert ok.status_code == 200


def test_session_cookie_secure_flag_follows_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_SECURE_COOKIES", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={"email": "secure@example.com", "password": "correct horse battery staple"},
    )

    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie
    assert "secure" in set_cookie
```

- [ ] **Step 2: Run auth tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_auth_api.py -q
```

Expected: new tests fail because `/api/csrf` and CSRF validation are not implemented.

- [ ] **Step 3: Add session columns to schema and migration**

In `backend/app/services/database.py`, update `sessions` table in `SCHEMA`:

```sql
  csrf_token_hash text,
  absolute_expires_at real,
  revoked_reason text,
  ip_hash text,
  user_agent_hash text,
  rotated_from_session_id text
```

Add a migration function:

```python
def _migrate_sessions(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("pragma table_info(sessions)").fetchall()}
    additions = {
        "csrf_token_hash": "alter table sessions add column csrf_token_hash text",
        "absolute_expires_at": "alter table sessions add column absolute_expires_at real",
        "revoked_reason": "alter table sessions add column revoked_reason text",
        "ip_hash": "alter table sessions add column ip_hash text",
        "user_agent_hash": "alter table sessions add column user_agent_hash text",
        "rotated_from_session_id": "alter table sessions add column rotated_from_session_id text",
    }
    for column, statement in additions.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute(
        """
        update sessions
        set absolute_expires_at = expires_at
        where absolute_expires_at is null
        """
    )
```

Call it in `initialize_database()` after `conn.executescript(SCHEMA)`:

```python
        _migrate_sessions(conn)
```

- [ ] **Step 4: Create CSRF service**

Create `backend/app/services/csrf.py`:

```python
from __future__ import annotations

import base64
import hmac
import secrets
from hashlib import sha256
from time import time
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException, Request

from app.services.app_config import load_config


PRELOGIN_TTL_SECONDS = 30 * 60
CSRF_HEADER_NAME = "x-csrf-token"


def _secret() -> bytes:
    config = load_config()
    raw = f"{config.ip_hash_salt}:{config.session_cookie_name}:csrf"
    return raw.encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def create_prelogin_csrf_token() -> str:
    issued_at = str(int(time()))
    nonce = secrets.token_urlsafe(18)
    body = f"prelogin:{issued_at}:{nonce}"
    signature = hmac.new(_secret(), body.encode("utf-8"), sha256).digest()
    return f"{_b64(body.encode('utf-8'))}.{_b64(signature)}"


def verify_prelogin_csrf_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body_b64, signature_b64 = token.split(".", 1)
    try:
        body = _unb64(body_b64).decode("utf-8")
        signature = _unb64(signature_b64)
    except Exception:
        return False
    expected = hmac.new(_secret(), body.encode("utf-8"), sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return False
    parts = body.split(":")
    if len(parts) != 3 or parts[0] != "prelogin":
        return False
    try:
        issued_at = int(parts[1])
    except ValueError:
        return False
    return 0 <= time() - issued_at <= PRELOGIN_TTL_SECONDS


def create_session_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def allowed_origins() -> set[str]:
    config = load_config()
    origins = {origin for origin in config.allowed_origins if origin}
    public_origin = _origin(config.public_app_url)
    if public_origin:
        origins.add(public_origin)
    return origins


def assert_same_origin(request: Request) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    source = _origin(request.headers.get("origin")) or _origin(request.headers.get("referer"))
    if source is None:
        return
    if source not in allowed_origins():
        raise HTTPException(status_code=403, detail="请求来源不被允许")


def csrf_header(request: Request) -> str | None:
    return request.headers.get(CSRF_HEADER_NAME)
```

- [ ] **Step 5: Update auth service session token return type**

In `backend/app/services/auth_service.py`, add:

```python
@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
```

Change `create_session()`:

```python
def create_session(user_id: str) -> SessionTokens:
    config = load_config()
    now = time()
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    absolute_expires_at = now + config.session_days * 86400
    idle_expires_at = now + config.session_idle_days * 86400
    expires_at = min(idle_expires_at, absolute_expires_at)
    with transaction() as conn:
        conn.execute(
            """
            insert into sessions (
              id, user_id, session_token_hash, csrf_token_hash,
              expires_at, absolute_expires_at, created_at, last_seen_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{secrets.token_urlsafe(12)}",
                user_id,
                _hash_token(token),
                _hash_token(csrf_token),
                expires_at,
                absolute_expires_at,
                now,
                now,
            ),
        )
    return SessionTokens(session_token=token, csrf_token=csrf_token)
```

Update `get_user_by_session_token()` query with `absolute_expires_at`:

```sql
              and coalesce(sessions.absolute_expires_at, sessions.expires_at) > ?
```

and parameters:

```python
(_hash_token(token), now, now)
```

Add:

```python
def verify_session_csrf_token(session_token: str | None, csrf_token: str | None) -> bool:
    if not session_token or not csrf_token:
        return False
    conn = connect()
    try:
        row = conn.execute(
            """
            select csrf_token_hash from sessions
            where session_token_hash = ?
              and revoked_at is null
              and expires_at > ?
              and coalesce(absolute_expires_at, expires_at) > ?
            """,
            (_hash_token(session_token), time(), time()),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["csrf_token_hash"]:
        return False
    return hmac.compare_digest(row["csrf_token_hash"], _hash_token(csrf_token))
```

Also import `hmac`.

- [ ] **Step 6: Add auth route CSRF helpers**

In `backend/app/auth_routes.py`, import:

```python
from app.services.csrf import assert_same_origin, create_prelogin_csrf_token, csrf_header, verify_prelogin_csrf_token
from app.services.auth_service import verify_session_csrf_token
```

Add:

```python
@router.get("/csrf")
def csrf() -> dict[str, str]:
    return {"csrf_token": create_prelogin_csrf_token()}


def _assert_prelogin_csrf(request: Request) -> None:
    assert_same_origin(request)
    if not verify_prelogin_csrf_token(csrf_header(request)):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")


def assert_session_csrf(request: Request) -> None:
    assert_same_origin(request)
    config = load_config()
    if not verify_session_csrf_token(request.cookies.get(config.session_cookie_name), csrf_header(request)):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
```

- [ ] **Step 7: Return session CSRF token from auth payload**

Change `_me_payload()`:

```python
def _me_payload(user: User, csrf_token: str | None = None) -> dict:
    membership = get_membership(user.id)
    usage = get_usage_summary(user)
    payload = {
        "user": user.as_dict(),
        "membership": membership.as_dict(),
        "usage": usage.as_dict(),
    }
    if csrf_token:
        payload["csrf_token"] = csrf_token
    return payload
```

Update `register()`:

```python
@router.post("/auth/register")
def register(payload: AuthRequest, request: Request, response: Response) -> dict:
    _assert_prelogin_csrf(request)
    keys = _assert_auth_rate_limit("register", request, payload.email)
    _record_auth_rate_limit(keys)
    try:
        user = create_user(payload.email, payload.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="邮箱已被注册") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="注册失败") from exc
    session = create_session(user.id)
    _set_session_cookie(response, session.session_token)
    return _me_payload(user, session.csrf_token)
```

Update `login()`:

```python
@router.post("/auth/login")
def login(payload: AuthRequest, request: Request, response: Response) -> dict:
    _assert_prelogin_csrf(request)
    keys = _assert_auth_rate_limit("login", request, payload.email)
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        _record_auth_rate_limit(keys)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _clear_auth_rate_limit(keys)
    session = create_session(user.id)
    _set_session_cookie(response, session.session_token)
    return _me_payload(user, session.csrf_token)
```

Update `logout()`:

```python
def logout(request: Request, response: Response, _: User = Depends(current_user)) -> dict[str, bool]:
    assert_session_csrf(request)
    config = load_config()
    revoke_session(request.cookies.get(config.session_cookie_name), reason="logout")
    response.delete_cookie(config.session_cookie_name, path="/")
    return {"ok": True}
```

- [ ] **Step 8: Update revoke_session signature**

In `auth_service.py`:

```python
def revoke_session(token: str | None, *, reason: str = "logout") -> None:
    if not token:
        return
    with transaction() as conn:
        conn.execute(
            "update sessions set revoked_at = ?, revoked_reason = ? where session_token_hash = ?",
            (time(), reason, _hash_token(token)),
        )
```

- [ ] **Step 9: Update existing auth tests to use CSRF**

For each existing `client.post` call whose first argument is `"/api/auth/register"`, pass `headers=csrf_headers(client)`.

For each existing `client.post` call whose first argument is `"/api/auth/login"`, pass `headers=csrf_headers(client)`.

For each existing logged-in logout request, use the response token:

```python
registered = register_with_csrf(client)
logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": registered.json()["csrf_token"]})
```

For password reset request and confirm, pass `headers=csrf_headers(client)` because they use prelogin CSRF in phase 1.

- [ ] **Step 10: Run auth tests**

Run:

```bash
python -m pytest backend/tests/test_auth_api.py -q
```

Expected: all auth tests pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/csrf.py backend/app/services/database.py backend/app/services/auth_service.py backend/app/auth_routes.py backend/tests/test_auth_api.py
git commit -m "feat: 增加登录 CSRF 防护" -m "新增预登录与 session 绑定 CSRF token，扩展 session 表字段，并让注册、登录、密码重置和登出具备 CSRF 与来源校验。"
```

---

### Task 3: Password Reset Revokes Sessions And Limits Confirm Attempts

**Files:**
- Modify: `backend/app/services/database.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/auth_routes.py`
- Modify: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Write failing password reset revocation tests**

Append to `backend/tests/test_auth_api.py`:

```python
def test_password_reset_revokes_existing_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEV_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    register = register_with_csrf(client, email="reset-revoke@example.com", password="old-password-123")

    request = client.post(
        "/api/auth/password-reset/request",
        headers=csrf_headers(client),
        json={"email": "reset-revoke@example.com"},
    )
    token = request.json()["reset_token"]

    changed = client.post(
        "/api/auth/password-reset/confirm",
        headers=csrf_headers(client),
        json={"token": token, "password": "new-password-123"},
    )
    me = client.get("/api/me")

    assert changed.status_code == 200
    assert me.status_code == 401
    with database.connect() as conn:
        revoked = conn.execute(
            "select revoked_reason from sessions where user_id = (select id from users where email = ?)",
            ("reset-revoke@example.com",),
        ).fetchone()
    assert revoked["revoked_reason"] == "password_reset"


def test_password_reset_confirm_is_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "2")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    first = client.post(
        "/api/auth/password-reset/confirm",
        headers=csrf_headers(client),
        json={"token": "bad-token", "password": "new-password-123"},
    )
    second = client.post(
        "/api/auth/password-reset/confirm",
        headers=csrf_headers(client),
        json={"token": "bad-token", "password": "new-password-123"},
    )
    blocked = client.post(
        "/api/auth/password-reset/confirm",
        headers=csrf_headers(client),
        json={"token": "bad-token", "password": "new-password-123"},
    )

    assert first.status_code == 400
    assert second.status_code == 400
    assert blocked.status_code == 429
```

- [ ] **Step 2: Run auth tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_auth_api.py::test_password_reset_revokes_existing_sessions backend/tests/test_auth_api.py::test_password_reset_confirm_is_rate_limited -q
```

Expected: tests fail because reset does not revoke sessions and confirm is not rate-limited.

- [ ] **Step 3: Add reset token revocation column**

In `backend/app/services/database.py`, update `password_reset_tokens` schema:

```sql
  revoked_at real,
```

Add migration:

```python
def _migrate_password_reset_tokens(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("pragma table_info(password_reset_tokens)").fetchall()}
    if "revoked_at" not in columns:
        conn.execute("alter table password_reset_tokens add column revoked_at real")
```

Call it in `initialize_database()`:

```python
        _migrate_password_reset_tokens(conn)
```

- [ ] **Step 4: Revoke old reset tokens when creating a new one**

In `auth_service.create_password_reset_token()` before insert:

```python
        conn.execute(
            """
            update password_reset_tokens
            set revoked_at = ?
            where user_id = ? and used_at is null and revoked_at is null
            """,
            (now, user["id"]),
        )
```

Use configurable TTL:

```python
now + load_config().password_reset_token_minutes * 60
```

- [ ] **Step 5: Add helper to revoke all user sessions**

In `auth_service.py`:

```python
def revoke_user_sessions(user_id: str, *, reason: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            update sessions
            set revoked_at = ?, revoked_reason = ?
            where user_id = ? and revoked_at is null
            """,
            (time(), reason, user_id),
        )
```

- [ ] **Step 6: Update reset_password query and revocation**

In `reset_password()` change select:

```sql
            select * from password_reset_tokens
            where token_hash = ?
              and used_at is null
              and revoked_at is null
              and expires_at > ?
```

After marking token used:

```python
        conn.execute(
            """
            update sessions
            set revoked_at = ?, revoked_reason = 'password_reset'
            where user_id = ? and revoked_at is null
            """,
            (now, row["user_id"]),
        )
```

- [ ] **Step 7: Rate limit reset confirm**

In `auth_routes.py`, add:

```python
def _reset_confirm_rate_limit_keys(request: Request, token: str) -> list[str]:
    token_prefix = token.strip()[:16] or "empty"
    return [f"auth:password-reset-confirm:ip:{_client_ip(request)}", f"auth:password-reset-confirm:token:{token_prefix}"]
```

Update `confirm_password_reset()`:

```python
def confirm_password_reset(payload: PasswordResetConfirm, request: Request) -> dict[str, bool]:
    _assert_prelogin_csrf(request)
    keys = _reset_confirm_rate_limit_keys(request, payload.token)
    try:
        for key in keys:
            assert_rate_limit_allowed(
                key,
                limit=load_config().auth_rate_limit_attempts,
                window_seconds=load_config().auth_rate_limit_window_seconds,
            )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    try:
        changed = reset_password(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        _record_auth_rate_limit(keys)
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    _clear_auth_rate_limit(keys)
    return {"ok": True}
```

- [ ] **Step 8: Run auth tests**

Run:

```bash
python -m pytest backend/tests/test_auth_api.py -q
```

Expected: all auth tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/database.py backend/app/services/auth_service.py backend/app/auth_routes.py backend/tests/test_auth_api.py
git commit -m "fix: 重置密码后撤销旧会话" -m "密码重置 token 改为可撤销，创建新 token 时撤销旧 token，并在重置成功后撤销用户所有已有 session，同时为重置确认增加限流。"
```

---

### Task 4: Summary Ownership And Cross-Account Isolation

**Files:**
- Modify: `backend/app/services/summary_store.py`
- Modify: `backend/app/summary_routes.py`
- Modify: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Update summary test helpers for CSRF**

In `backend/tests/test_summary_api.py`, replace `login(client)` with:

```python
def csrf_headers(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def login(client, email="summary@example.com"):
    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={"email": email, "password": "summary-password"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}
```

Then update all summary-creating POSTs and question POSTs to pass the returned header:

```python
headers = login(client)
response = client.post(
    "/api/summaries",
    headers=headers,
    json={"url": "https://example.com/video", "title": "Demo", "language": "zh-CN"},
)
answer = client.post(
    f"/api/summaries/{summary_id}/questions",
    headers=headers,
    json={"question": "这一段讲了什么？", "language": "zh-CN"},
)
```

- [ ] **Step 2: Write failing cross-account ownership tests**

Append:

```python
def test_summary_result_is_private_to_owner(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    owner = TestClient(app)
    owner_headers = login(owner, email="owner@example.com")
    response = owner.post(
        "/api/summaries",
        headers=owner_headers,
        json={"url": "https://example.com/private-summary", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(owner, summary_id, "completed")

    intruder = TestClient(app)
    intruder_headers = login(intruder, email="intruder@example.com")

    assert intruder.get(f"/api/summaries/{summary_id}").status_code == 404
    assert intruder.get(f"/api/summaries/{summary_id}/markdown").status_code == 404
    question = intruder.post(
        f"/api/summaries/{summary_id}/questions",
        headers=intruder_headers,
        json={"question": "能看到吗？", "language": "zh-CN"},
    )
    assert question.status_code == 404


def test_cached_summary_creates_owned_task_for_second_user(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    first_client = TestClient(app)
    first_headers = login(first_client, email="first-cache@example.com")
    first = first_client.post(
        "/api/summaries",
        headers=first_headers,
        json={"url": "https://example.com/shared-cache", "title": "Demo", "language": "zh-CN"},
    )
    first_id = first.json()["summary_id"]
    wait_for_status(first_client, first_id, "completed")

    second_client = TestClient(app)
    second_headers = login(second_client, email="second-cache@example.com")
    second = second_client.post(
        "/api/summaries",
        headers=second_headers,
        json={"url": "https://example.com/shared-cache", "title": "Demo", "language": "zh-CN"},
    )
    second_id = second.json()["summary_id"]

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second_id != first_id
    assert second_client.get(f"/api/summaries/{second_id}").status_code == 200
    assert second_client.get(f"/api/summaries/{first_id}").status_code == 404
    assert len(fake.calls) == 1
```

- [ ] **Step 3: Run ownership tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_summary_api.py::test_summary_result_is_private_to_owner backend/tests/test_summary_api.py::test_cached_summary_creates_owned_task_for_second_user -q
```

Expected: tests fail because summary resources are public and cached tasks reuse the first owner task id.

- [ ] **Step 4: Add owner field to SummarySnapshot**

In `backend/app/services/summary_store.py`, add to dataclass:

```python
    owner_user_id: str | None = None
```

In `from_dict()`:

```python
            owner_user_id=data.get("owner_user_id") if isinstance(data.get("owner_user_id"), str) else None,
```

Do not include `owner_user_id` in `as_dict()`.

- [ ] **Step 5: Accept owner in create_task and persist it**

Update `create_task()` signature:

```python
        owner_user_id: str | None = None,
```

Set it on `SummarySnapshot`:

```python
            owner_user_id=owner_user_id,
```

In `_save_task_unlocked()` record:

```python
            "owner_user_id": task.owner_user_id,
```

- [ ] **Step 6: Add clone method for completed cached task**

In `SummaryStore`:

```python
    def clone_completed_task_for_owner(
        self,
        source: SummarySnapshot,
        *,
        owner_user_id: str,
        task_id: str | None = None,
    ) -> SummarySnapshot:
        if source.status != "completed" or source.result is None:
            raise ValueError("Only completed summary tasks can be cloned")
        markdown_path = self._markdown_files.get(source.id)
        cloned = SummarySnapshot(
            id=task_id or f"summary_{secrets.token_urlsafe(10)}",
            url=source.url,
            title=source.title,
            language=source.language,
            cache_key=source.cache_key,
            status="completed",
            stage="completed",
            progress=100.0,
            message="Summary complete",
            result=source.result,
            streamed_text=source.streamed_text,
            markdown_url=None,
            owner_user_id=owner_user_id,
        )
        cloned.markdown_url = f"/api/summaries/{cloned.id}/markdown"
        with self._lock:
            self._tasks[cloned.id] = cloned
            if cloned.cache_key:
                self._cache_index[cloned.cache_key] = cloned.id
            if markdown_path is not None:
                self._markdown_files[cloned.id] = markdown_path
            self._save_task_locked(cloned, markdown_path=markdown_path)
            self._save_index_locked()
        return cloned
```

- [ ] **Step 7: Add route owner helper**

In `backend/app/summary_routes.py`:

```python
def _get_owned_summary_task(summary_id: str, user: User):
    task = summary_store.get_task(summary_id)
    if task is None or task.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Summary task not found")
    return task
```

- [ ] **Step 8: Write owner during create_summary and clone cross-user cache**

In `create_summary()` cached branch:

```python
        usage = get_usage_summary(user)
        if cached_task.owner_user_id == user.id:
            return {
                "summary_id": cached_task.id,
                "cache_hit": True,
                "status": cached_task.status,
                "usage": usage.as_dict(),
            }
        owned_cached_task = summary_store.clone_completed_task_for_owner(cached_task, owner_user_id=user.id)
        return {
            "summary_id": owned_cached_task.id,
            "cache_hit": True,
            "status": owned_cached_task.status,
            "usage": usage.as_dict(),
        }
```

In `summary_store.create_task()` call:

```python
            owner_user_id=user.id,
```

- [ ] **Step 9: Protect summary read routes**

Change signatures and bodies:

```python
@router.get("/{summary_id}")
def get_summary(summary_id: str, user: User = Depends(current_user)) -> dict:
    return _get_owned_summary_task(summary_id, user).as_dict()
```

```python
@router.post("/{summary_id}/questions")
def ask_summary_question(
    summary_id: str,
    payload: SummaryQuestionRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, str]:
    assert_session_csrf(request)
    task = _get_owned_summary_task(summary_id, user)
    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=409, detail="Summary task is not completed")
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    transcript = _transcript_from_result(task.result)
    answer = get_summary_service().answer_question(
        title=task.title or "未命名视频",
        transcript=transcript,
        summary=task.result,
        question=question,
        language=payload.language,
    )
    return {"answer": answer}
```

Import `Request` and `assert_session_csrf` from `app.auth_routes`.

For events:

```python
@router.get("/{summary_id}/events")
async def summary_events(summary_id: str, user: User = Depends(current_user)) -> StreamingResponse:
    _get_owned_summary_task(summary_id, user)
    async def event_stream():
        last_payload = None
        while True:
            task = summary_store.get_task(summary_id)
            if task is None or task.owner_user_id != user.id:
                yield "event: error\ndata: {\"error\":\"Summary task not found\"}\n\n"
                break
            payload = json.dumps(task.as_dict(), ensure_ascii=False)
            if payload != last_payload:
                yield f"event: summary\ndata: {payload}\n\n"
                last_payload = payload
            if task.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

For markdown:

```python
@router.get("/{summary_id}/markdown")
def download_summary_markdown(summary_id: str, user: User = Depends(current_user)) -> FileResponse:
    _get_owned_summary_task(summary_id, user)
    path = summary_store.resolve_markdown(summary_id)
    if path is None or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Summary markdown not found")
    return FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")
```

- [ ] **Step 10: Update wait_for_status helper**

Because `GET /api/summaries/{id}` now requires login, make sure `wait_for_status(client, summary_id, status)` is only called with the same authenticated `client`. Existing tests already do this; no header is required for GET because Cookie is sent by TestClient.

- [ ] **Step 11: Run summary tests**

Run:

```bash
python -m pytest backend/tests/test_summary_api.py -q
```

Expected: all summary tests pass.

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/summary_store.py backend/app/summary_routes.py backend/tests/test_summary_api.py
git commit -m "fix: 隔离用户 AI 总结资源" -m "为 summary task 增加 owner_user_id，保护总结状态、问答、SSE 和 Markdown 下载，并让跨用户缓存命中创建当前用户自己的任务记录。"
```

---

### Task 5: Apply Session CSRF To Billing And Remaining Mutations

**Files:**
- Modify: `backend/app/billing_routes.py`
- Modify: `backend/tests/test_billing_mock.py`
- Modify: `backend/tests/test_billing_stripe_webhook.py`

- [ ] **Step 1: Add billing CSRF test helpers**

In both billing test files, add local helpers:

```python
def csrf_headers(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def register_and_get_csrf(client, email="billing@example.com"):
    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}
```

- [ ] **Step 2: Write failing billing CSRF test**

Append to `backend/tests/test_billing_mock.py`:

```python
def test_mock_billing_requires_session_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    headers = register_and_get_csrf(client)

    missing = client.post("/api/billing/mock/activate")
    ok = client.post("/api/billing/mock/activate", headers=headers)

    assert missing.status_code == 403
    assert ok.status_code == 200
```

- [ ] **Step 3: Run billing CSRF test and verify failure**

Run:

```bash
python -m pytest backend/tests/test_billing_mock.py::test_mock_billing_requires_session_csrf -q
```

Expected: missing-CSRF request currently succeeds, so test fails.

- [ ] **Step 4: Protect billing routes**

In `backend/app/billing_routes.py`, import:

```python
from app.auth_routes import assert_session_csrf, current_user
```

Call `assert_session_csrf(request)` as the first line after the function signature in Cookie-authenticated mutation routes, before reading or changing billing state.

```python
def billing_checkout(request: Request, payload: CheckoutRequest | None = Body(default=None), user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
```

For confirm:

```python
def billing_checkout_confirm(payload: CheckoutConfirmRequest, request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
```

For portal:

```python
def billing_portal(request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
```

For mock routes, add `request: Request` and call `assert_session_csrf(request)`:

```python
def mock_activate(request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": activate_mock_subscription(user).as_dict()}

def mock_cancel(request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": cancel_mock_subscription(user).as_dict()}


def mock_expire(request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": expire_mock_subscription(user).as_dict()}


def mock_payment_failed(request: Request, user: User = Depends(current_user)) -> dict:
    assert_session_csrf(request)
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": fail_mock_payment(user).as_dict()}
```

Do not add CSRF to `stripe_webhook()`.

- [ ] **Step 5: Update existing billing tests to pass CSRF**

In billing tests, every authenticated POST to:

- `/api/billing/checkout`
- `/api/billing/checkout/confirm`
- `/api/billing/portal`
- `/api/billing/mock/activate`
- `/api/billing/mock/cancel`
- `/api/billing/mock/expire`
- `/api/billing/mock/payment-failed`

must include `headers=headers` from `register_and_get_csrf()`.

Do not add CSRF headers to `/api/billing/webhook`.

- [ ] **Step 6: Run billing tests**

Run:

```bash
python -m pytest backend/tests/test_billing_mock.py backend/tests/test_billing_stripe_webhook.py -q
```

Expected: billing tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/billing_routes.py backend/tests/test_billing_mock.py backend/tests/test_billing_stripe_webhook.py
git commit -m "fix: 为会员变更接口增加 CSRF 校验" -m "Checkout、Portal、Checkout confirm 和 mock billing mutation 统一校验 session CSRF，Stripe webhook 保持签名验签链路。"
```

---

### Task 6: Final Phase 1 Verification

**Files:**
- Verify only; no expected source edits.

- [ ] **Step 1: Run focused backend security tests**

Run:

```bash
python -m pytest backend/tests/test_auth_api.py backend/tests/test_summary_api.py backend/tests/test_billing_mock.py backend/tests/test_billing_stripe_webhook.py backend/tests/test_app_config.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
python -m pytest backend/tests -q
```

Expected: all backend tests pass. If unrelated environment-only tests fail because optional browser/media dependencies are missing, record exact failures and rerun the focused security tests from Step 1.

- [ ] **Step 3: Run frontend unit tests**

Run:

```bash
npm --prefix frontend test
```

Expected: frontend tests pass. This phase does not change frontend code, so failures should be investigated as possible pre-existing environment issues.

- [ ] **Step 4: Run git diff review**

Run:

```bash
git diff --stat
git diff -- backend/app backend/tests
```

Expected: diff only contains login security phase 1 changes. No unrelated files such as `.vscode/`, `findings.md`, `progress.md`, `skills-lock.json`, or `task_plan.md` are staged or committed.

- [ ] **Step 5: Commit verification docs only if needed**

If test command notes need to be documented, add a short note to the implementation summary in the final response. Do not create a separate docs commit unless the user asks for release documentation.

---

## Self-Review Notes

- Spec coverage: This plan covers first-stage requirements from the approved design: Summary ownership, password reset session revocation, production Cookie/config guardrails, CSRF token/Origin checks, and backend tests.
- Deferred by design: frontend `apiFetch`, cross-tab sync, SMTP, audit events, data cleanup, weak password checking, and monitoring are phase 2/3 work and should get separate plans.
- Type consistency: `create_session()` changes from `str` to `SessionTokens`; all callers in `auth_routes.py` must be updated in Task 2 before tests can pass.
- CSRF consistency: prelogin token is accepted only for unauthenticated auth forms; session-bound token is required for logged-in mutations.
- Ownership consistency: `owner_user_id` is persisted but never exposed by `SummarySnapshot.as_dict()`.
