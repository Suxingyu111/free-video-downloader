# Membership Stripe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add email/password accounts, SQLite-backed membership state, Stripe monthly subscription checkout, mock offline billing, and AI-summary entitlement checks.

**Architecture:** Backend adds focused auth, billing, and entitlement modules around a shared SQLite store at `runtime/saveany.db`. Stripe and mock billing write the same subscription tables, while `summary_routes` only talks to the entitlement layer. Frontend keeps the existing Vue SPA and adds lightweight auth, membership, pricing, and summary-gating UI.

**Tech Stack:** FastAPI, Pydantic, SQLite via Python `sqlite3`, `argon2-cffi`, Stripe Python SDK, Vue 3, Vite, Node test runner, pytest.

---

## File Structure

- Create `backend/app/services/app_config.py`: central runtime config for DB, cookies, app URL, billing mode, Stripe env vars, and free quota.
- Create `backend/app/services/database.py`: SQLite connection factory, schema migration, transactional helpers.
- Create `backend/app/services/auth_service.py`: password hashing, user/session/password reset storage and validation.
- Create `backend/app/auth_routes.py`: `/api/auth/*` and `/api/me` FastAPI routes.
- Create `backend/app/services/billing_service.py`: subscription status, mock billing transitions, Stripe checkout/portal/session helpers.
- Create `backend/app/billing_routes.py`: `/api/billing/*` routes and Stripe webhook raw-body handling.
- Create `backend/app/services/entitlements.py`: AI summary quota checks and atomic daily usage increments.
- Modify `backend/app/main.py`: include auth and billing routers, initialize DB at startup, update CORS cookie support.
- Modify `backend/app/summary_routes.py`: require logged-in user and entitlement before creating a summary.
- Modify `backend/requirements.txt`: add `argon2-cffi` and `stripe`.
- Create backend tests:
  - `backend/tests/test_auth_api.py`
  - `backend/tests/test_billing_mock.py`
  - `backend/tests/test_entitlements.py`
  - `backend/tests/test_billing_stripe_webhook.py`
  - update `backend/tests/test_summary_api.py`
- Modify frontend:
  - `frontend/src/services/api.js`
  - create `frontend/src/services/authSession.js`
  - modify `frontend/src/App.vue`
  - update `frontend/tests/chinese-ui-copy.test.js`
  - create `frontend/tests/auth-session.test.js`
- Update docs:
  - `README.md`
  - `docs/04-api-design.md`
  - create `docs/11-membership-stripe-setup.md`

## Task 1: Backend Config and SQLite Foundation

**Files:**
- Create: `backend/app/services/app_config.py`
- Create: `backend/app/services/database.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Write failing database tests**

Create `backend/tests/test_database.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_database.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` because `database` does not exist.

- [ ] **Step 3: Add config service**

Create `backend/app/services/app_config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_DIR / "runtime"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    billing_mode: str
    free_summary_daily_limit: int
    session_cookie_name: str
    session_days: int
    secure_cookies: bool
    public_app_url: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_pro_monthly_price_id: str


def load_config() -> AppConfig:
    billing_mode = os.getenv("BILLING_MODE", "mock").strip().lower()
    if billing_mode not in {"mock", "stripe"}:
        billing_mode = "mock"
    return AppConfig(
        db_path=Path(os.getenv("SAVEANY_DB_PATH", RUNTIME_DIR / "saveany.db")),
        billing_mode=billing_mode,
        free_summary_daily_limit=int(os.getenv("FREE_SUMMARY_DAILY_LIMIT", "3")),
        session_cookie_name=os.getenv("SAVEANY_SESSION_COOKIE", "saveany_session"),
        session_days=int(os.getenv("SAVEANY_SESSION_DAYS", "30")),
        secure_cookies=_bool_env("SAVEANY_SECURE_COOKIES", False),
        public_app_url=os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/"),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        stripe_pro_monthly_price_id=os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
    )
```

- [ ] **Step 4: Add SQLite schema and helpers**

Create `backend/app/services/database.py`:

```python
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.services.app_config import load_config


SCHEMA = """
pragma foreign_keys = on;

create table if not exists users (
  id text primary key,
  email text not null unique,
  password_hash text not null,
  status text not null default 'active',
  created_at real not null,
  updated_at real not null
);

create table if not exists sessions (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  session_token_hash text not null unique,
  expires_at real not null,
  created_at real not null,
  last_seen_at real not null,
  revoked_at real
);

create table if not exists password_reset_tokens (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  token_hash text not null unique,
  expires_at real not null,
  used_at real,
  created_at real not null
);

create table if not exists subscriptions (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  plan text not null,
  status text not null,
  stripe_customer_id text,
  stripe_subscription_id text unique,
  stripe_price_id text,
  current_period_start real,
  current_period_end real,
  cancel_at_period_end integer not null default 0,
  created_at real not null,
  updated_at real not null
);

create table if not exists stripe_events (
  event_id text primary key,
  event_type text not null,
  processed_at real not null,
  payload_hash text not null
);

create table if not exists usage_daily (
  user_id text not null references users(id) on delete cascade,
  usage_date text not null,
  summary_count integer not null default 0,
  created_at real not null,
  updated_at real not null,
  primary key (user_id, usage_date)
);

create table if not exists billing_attempts (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  mode text not null,
  status text not null,
  stripe_checkout_session_id text,
  created_at real not null,
  updated_at real not null
);

create table if not exists rate_limits (
  key text primary key,
  count integer not null,
  reset_at real not null
);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else load_config().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def initialize_database(db_path: Path | str | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def transaction(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        conn.execute("begin immediate")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 5: Initialize DB during FastAPI lifespan**

Modify `backend/app/main.py` imports:

```python
from app.services.database import initialize_database
```

Modify the start of `lifespan`:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    prune_download_directories(DOWNLOAD_DIR, keep_completed=MAX_COMPLETED_DOWNLOADS)
    yield
```

- [ ] **Step 6: Run database tests**

Run:

```bash
cd backend
pytest tests/test_database.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/app_config.py backend/app/services/database.py backend/app/main.py backend/tests/test_database.py
git commit -m "feat: add membership database foundation"
```

## Task 2: Auth Service and API

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/auth_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Write failing auth API tests**

Create `backend/tests/test_auth_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.services import database


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


def test_password_reset_token_is_single_use(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_auth_api.py -v
```

Expected: FAIL with 404 for `/api/auth/register`.

- [ ] **Step 3: Add dependencies**

Modify `backend/requirements.txt`:

```text
argon2-cffi>=23.1.0
stripe>=13.0.0
```

Keep existing lines unchanged.

- [ ] **Step 4: Add auth service**

Create `backend/app/services/auth_service.py` with this structure:

```python
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from time import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.services.app_config import load_config
from app.services.database import connect, transaction


ph = PasswordHasher()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    status: str

    def as_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "status": self.status}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row) -> User:
    return User(id=row["id"], email=row["email"], status=row["status"])


def create_user(email: str, password: str) -> User:
    normalized = normalize_email(email)
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    now = time()
    user_id = f"user_{secrets.token_urlsafe(12)}"
    password_hash = ph.hash(password)
    with transaction() as conn:
        conn.execute(
            """
            insert into users (id, email, password_hash, status, created_at, updated_at)
            values (?, ?, ?, 'active', ?, ?)
            """,
            (user_id, normalized, password_hash, now, now),
        )
    return User(id=user_id, email=normalized, status="active")


def authenticate_user(email: str, password: str) -> User | None:
    normalized = normalize_email(email)
    with connect() as conn:
        row = conn.execute("select * from users where email = ?", (normalized,)).fetchone()
    if row is None:
        return None
    try:
        ph.verify(row["password_hash"], password)
    except VerifyMismatchError:
        return None
    return _row_to_user(row)


def create_session(user_id: str) -> str:
    config = load_config()
    now = time()
    token = secrets.token_urlsafe(32)
    with transaction() as conn:
        conn.execute(
            """
            insert into sessions (id, user_id, session_token_hash, expires_at, created_at, last_seen_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{secrets.token_urlsafe(12)}",
                user_id,
                _hash_token(token),
                now + config.session_days * 86400,
                now,
                now,
            ),
        )
    return token


def get_user_by_session_token(token: str | None) -> User | None:
    if not token:
        return None
    now = time()
    with transaction() as conn:
        row = conn.execute(
            """
            select users.* from sessions
            join users on users.id = sessions.user_id
            where sessions.session_token_hash = ?
              and sessions.expires_at > ?
              and sessions.revoked_at is null
              and users.status = 'active'
            """,
            (_hash_token(token), now),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "update sessions set last_seen_at = ? where session_token_hash = ?",
            (now, _hash_token(token)),
        )
    return _row_to_user(row)


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with transaction() as conn:
        conn.execute(
            "update sessions set revoked_at = ? where session_token_hash = ?",
            (time(), _hash_token(token)),
        )


def create_password_reset_token(email: str) -> str | None:
    normalized = normalize_email(email)
    with connect() as conn:
        user = conn.execute("select * from users where email = ?", (normalized,)).fetchone()
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    now = time()
    with transaction() as conn:
        conn.execute(
            """
            insert into password_reset_tokens (id, user_id, token_hash, expires_at, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                f"reset_{secrets.token_urlsafe(12)}",
                user["id"],
                _hash_token(token),
                now + 3600,
                now,
            ),
        )
    return token


def reset_password(token: str, password: str) -> bool:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    now = time()
    token_hash = _hash_token(token)
    with transaction() as conn:
        row = conn.execute(
            """
            select * from password_reset_tokens
            where token_hash = ? and used_at is null and expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "update users set password_hash = ?, updated_at = ? where id = ?",
            (ph.hash(password), now, row["user_id"]),
        )
        conn.execute(
            "update password_reset_tokens set used_at = ? where token_hash = ?",
            (now, token_hash),
        )
    return True
```

- [ ] **Step 5: Add auth routes**

Create `backend/app/auth_routes.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.services.app_config import load_config
from app.services.auth_service import (
    User,
    authenticate_user,
    create_password_reset_token,
    create_session,
    create_user,
    get_user_by_session_token,
    reset_password,
    revoke_session,
)


router = APIRouter(prefix="/api", tags=["auth"])


class AuthRequest(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    config = load_config()
    response.set_cookie(
        config.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=config.secure_cookies,
        max_age=config.session_days * 86400,
        path="/",
    )


def current_user(request: Request) -> User:
    config = load_config()
    user = get_user_by_session_token(request.cookies.get(config.session_cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def optional_user(request: Request) -> User | None:
    config = load_config()
    return get_user_by_session_token(request.cookies.get(config.session_cookie_name))


def _me_payload(user: User) -> dict:
    return {
        "user": user.as_dict(),
        "membership": {"plan": "free", "status": "free", "active": False},
        "usage": {"daily_free_limit": load_config().free_summary_daily_limit, "used_today": 0, "remaining_today": load_config().free_summary_daily_limit},
    }


@router.post("/auth/register")
def register(payload: AuthRequest, response: Response) -> dict:
    try:
        user = create_user(payload.email, payload.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_session_cookie(response, create_session(user.id))
    return _me_payload(user)


@router.post("/auth/login")
def login(payload: AuthRequest, response: Response) -> dict:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _set_session_cookie(response, create_session(user.id))
    return _me_payload(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    config = load_config()
    revoke_session(request.cookies.get(config.session_cookie_name))
    response.delete_cookie(config.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _me_payload(user)


@router.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequest) -> dict:
    token = create_password_reset_token(payload.email)
    response = {"ok": True}
    if token:
        response["reset_token"] = token
    return response


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm) -> dict[str, bool]:
    try:
        changed = reset_password(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    return {"ok": True}
```

- [ ] **Step 6: Mount auth router**

Modify `backend/app/main.py`:

```python
from app.auth_routes import router as auth_router

app.include_router(auth_router)
```

Place it near the existing `summary_router` include.

- [ ] **Step 7: Run auth tests**

Run:

```bash
cd backend
pip install -r requirements.txt
pytest tests/test_auth_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/app/services/auth_service.py backend/app/auth_routes.py backend/app/main.py backend/tests/test_auth_api.py
git commit -m "feat: add email password authentication"
```

## Task 3: Billing Status and Mock Billing

**Files:**
- Create: `backend/app/services/billing_service.py`
- Create: `backend/app/billing_routes.py`
- Modify: `backend/app/auth_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_billing_mock.py`

- [ ] **Step 1: Write failing mock billing tests**

Create `backend/tests/test_billing_mock.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.services import database


def _login(client):
    client.post(
        "/api/auth/register",
        json={"email": "member@example.com", "password": "member-password"},
    )


def test_mock_checkout_activates_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    checkout = client.post("/api/billing/checkout")
    assert checkout.status_code == 200
    assert checkout.json()["mode"] == "mock"
    assert checkout.json()["url"].endswith("#pricing")

    activated = client.post("/api/billing/mock/activate")
    assert activated.status_code == 200
    assert activated.json()["membership"]["active"] is True
    assert activated.json()["membership"]["plan"] == "pro"

    me = client.get("/api/me").json()
    assert me["membership"]["active"] is True


def test_mock_cancel_and_expire_subscription(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)
    client.post("/api/billing/mock/activate")

    canceled = client.post("/api/billing/mock/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["membership"]["cancel_at_period_end"] is True
    assert canceled.json()["membership"]["active"] is True

    expired = client.post("/api/billing/mock/expire")
    assert expired.status_code == 200
    assert expired.json()["membership"]["active"] is False
    assert expired.json()["membership"]["status"] == "canceled"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_billing_mock.py -v
```

Expected: FAIL with 404 for `/api/billing/checkout`.

- [ ] **Step 3: Add billing service**

Create `backend/app/services/billing_service.py`:

```python
from __future__ import annotations

import secrets
from dataclasses import dataclass
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.database import connect, transaction


ACTIVE_STATUSES = {"active", "trialing"}


@dataclass(frozen=True)
class Membership:
    plan: str
    status: str
    active: bool
    current_period_end: float | None = None
    cancel_at_period_end: bool = False

    def as_dict(self) -> dict:
        return {
            "plan": self.plan,
            "status": self.status,
            "active": self.active,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


def get_membership(user_id: str) -> Membership:
    with connect() as conn:
        row = conn.execute(
            """
            select * from subscriptions
            where user_id = ?
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return Membership(plan="free", status="free", active=False)
    active = row["status"] in ACTIVE_STATUSES
    return Membership(
        plan=row["plan"],
        status=row["status"],
        active=active,
        current_period_end=row["current_period_end"],
        cancel_at_period_end=bool(row["cancel_at_period_end"]),
    )


def create_mock_checkout(user: User) -> dict:
    now = time()
    with transaction() as conn:
        attempt_id = f"attempt_{secrets.token_urlsafe(10)}"
        conn.execute(
            """
            insert into billing_attempts (id, user_id, mode, status, created_at, updated_at)
            values (?, ?, 'mock', 'created', ?, ?)
            """,
            (attempt_id, user.id, now, now),
        )
    return {"mode": "mock", "url": "/#pricing", "attempt_id": attempt_id}


def activate_mock_subscription(user: User) -> Membership:
    now = time()
    with transaction() as conn:
        existing = conn.execute(
            "select id from subscriptions where user_id = ? order by updated_at desc limit 1",
            (user.id,),
        ).fetchone()
        subscription_id = existing["id"] if existing else f"sub_{secrets.token_urlsafe(10)}"
        if existing:
            conn.execute(
                """
                update subscriptions
                set plan = 'pro', status = 'active', current_period_start = ?,
                    current_period_end = ?, cancel_at_period_end = 0, updated_at = ?
                where id = ?
                """,
                (now, now + 30 * 86400, now, subscription_id),
            )
        else:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, current_period_start, current_period_end,
                 cancel_at_period_end, created_at, updated_at)
                values (?, ?, 'pro', 'active', ?, ?, 0, ?, ?)
                """,
                (subscription_id, user.id, now, now + 30 * 86400, now, now),
            )
    return get_membership(user.id)


def cancel_mock_subscription(user: User) -> Membership:
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set cancel_at_period_end = 1, updated_at = ?
            where user_id = ? and status in ('active', 'trialing')
            """,
            (time(), user.id),
        )
    return get_membership(user.id)


def expire_mock_subscription(user: User) -> Membership:
    now = time()
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set status = 'canceled', current_period_end = ?, updated_at = ?
            where user_id = ?
            """,
            (now - 1, now, user.id),
        )
    return get_membership(user.id)


def fail_mock_payment(user: User) -> Membership:
    with transaction() as conn:
        conn.execute(
            """
            update subscriptions
            set status = 'past_due', updated_at = ?
            where user_id = ?
            """,
            (time(), user.id),
        )
    return get_membership(user.id)
```

- [ ] **Step 4: Add billing routes**

Create `backend/app/billing_routes.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth_routes import current_user
from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import (
    activate_mock_subscription,
    cancel_mock_subscription,
    create_mock_checkout,
    expire_mock_subscription,
    fail_mock_payment,
    get_membership,
)


router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/status")
def billing_status(user: User = Depends(current_user)) -> dict:
    return {"membership": get_membership(user.id).as_dict(), "mode": load_config().billing_mode}


@router.post("/checkout")
def billing_checkout(user: User = Depends(current_user)) -> dict:
    config = load_config()
    membership = get_membership(user.id)
    if membership.active:
        raise HTTPException(status_code=409, detail="你已经是专业版会员，请前往会员管理。")
    if config.billing_mode == "mock":
        return create_mock_checkout(user)
    raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")


@router.post("/mock/activate")
def mock_activate(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": activate_mock_subscription(user).as_dict()}


@router.post("/mock/cancel")
def mock_cancel(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": cancel_mock_subscription(user).as_dict()}


@router.post("/mock/expire")
def mock_expire(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": expire_mock_subscription(user).as_dict()}


@router.post("/mock/payment-failed")
def mock_payment_failed(user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    return {"membership": fail_mock_payment(user).as_dict()}
```

- [ ] **Step 5: Include membership in `/api/me`**

Modify `_me_payload` in `backend/app/auth_routes.py`:

```python
from app.services.billing_service import get_membership


def _me_payload(user: User) -> dict:
    membership = get_membership(user.id)
    limit = load_config().free_summary_daily_limit
    return {
        "user": user.as_dict(),
        "membership": membership.as_dict(),
        "usage": {"daily_free_limit": limit, "used_today": 0, "remaining_today": limit},
    }
```

- [ ] **Step 6: Mount billing router**

Modify `backend/app/main.py`:

```python
from app.billing_routes import router as billing_router

app.include_router(billing_router)
```

- [ ] **Step 7: Run mock billing tests**

Run:

```bash
cd backend
pytest tests/test_billing_mock.py tests/test_auth_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/billing_service.py backend/app/billing_routes.py backend/app/auth_routes.py backend/app/main.py backend/tests/test_billing_mock.py
git commit -m "feat: add mock billing membership flow"
```

## Task 4: Entitlements and Summary Quotas

**Files:**
- Create: `backend/app/services/entitlements.py`
- Modify: `backend/app/auth_routes.py`
- Modify: `backend/app/summary_routes.py`
- Test: `backend/tests/test_entitlements.py`
- Test: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Write entitlement service tests**

Create `backend/tests/test_entitlements.py`:

```python
import pytest

from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import activate_mock_subscription
from app.services.entitlements import QuotaExceeded, consume_summary_quota, get_usage_summary


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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_entitlements.py -v
```

Expected: FAIL because `entitlements` does not exist.

- [ ] **Step 3: Add entitlement service**

Create `backend/app/services/entitlements.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import get_membership
from app.services.database import connect, transaction


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class UsageSummary:
    daily_free_limit: int
    used_today: int
    remaining_today: int
    membership_active: bool

    def as_dict(self) -> dict:
        return {
            "daily_free_limit": self.daily_free_limit,
            "used_today": self.used_today,
            "remaining_today": self.remaining_today,
            "membership_active": self.membership_active,
        }


def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def get_usage_summary(user: User) -> UsageSummary:
    membership = get_membership(user.id)
    limit = load_config().free_summary_daily_limit
    if membership.active:
        return UsageSummary(limit, 0, limit, True)
    with connect() as conn:
        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, _today_key()),
        ).fetchone()
    used = int(row["summary_count"]) if row else 0
    return UsageSummary(limit, used, max(limit - used, 0), False)


def consume_summary_quota(user: User) -> UsageSummary:
    membership = get_membership(user.id)
    limit = load_config().free_summary_daily_limit
    if membership.active:
        return UsageSummary(limit, 0, limit, True)
    now = time()
    usage_date = _today_key()
    with transaction() as conn:
        row = conn.execute(
            "select summary_count from usage_daily where user_id = ? and usage_date = ?",
            (user.id, usage_date),
        ).fetchone()
        used = int(row["summary_count"]) if row else 0
        if used >= limit:
            raise QuotaExceeded("今日免费 AI 总结额度已用完，请开通专业版继续使用。")
        next_used = used + 1
        conn.execute(
            """
            insert into usage_daily (user_id, usage_date, summary_count, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(user_id, usage_date)
            do update set summary_count = excluded.summary_count, updated_at = excluded.updated_at
            """,
            (user.id, usage_date, next_used, now, now),
        )
    return UsageSummary(limit, next_used, max(limit - next_used, 0), False)
```

- [ ] **Step 4: Return usage from `/api/me`**

Modify `_me_payload` in `backend/app/auth_routes.py`:

```python
from app.services.entitlements import get_usage_summary


def _me_payload(user: User) -> dict:
    membership = get_membership(user.id)
    usage = get_usage_summary(user)
    return {
        "user": user.as_dict(),
        "membership": membership.as_dict(),
        "usage": usage.as_dict(),
    }
```

- [ ] **Step 5: Gate `POST /api/summaries`**

Modify `backend/app/summary_routes.py` imports:

```python
from fastapi import APIRouter, Depends, HTTPException
from app.auth_routes import current_user
from app.services.auth_service import User
from app.services.entitlements import QuotaExceeded, consume_summary_quota
```

Modify route signature and start:

```python
@router.post("")
def create_summary(payload: SummaryRequest, user: User = Depends(current_user)) -> dict[str, object]:
    try:
        usage = consume_summary_quota(user)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
```

Modify response payloads to include usage:

```python
return {
    "summary_id": cached_task.id,
    "cache_hit": True,
    "status": cached_task.status,
    "usage": usage.as_dict(),
}
```

and:

```python
return {"summary_id": task.id, "cache_hit": False, "status": task.status, "usage": usage.as_dict()}
```

- [ ] **Step 6: Update summary API tests for login**

In `backend/tests/test_summary_api.py`, add helper:

```python
def login(client):
    client.post(
        "/api/auth/register",
        json={"email": "summary@example.com", "password": "summary-password"},
    )
```

Call `login(client)` before every successful `client.post("/api/summaries", ...)`.

Add this test:

```python
def test_create_summary_requires_login(isolated_summary_store):
    client = TestClient(app)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/video", "title": "Demo", "language": "zh-CN"},
    )

    assert response.status_code == 401
```

- [ ] **Step 7: Run entitlement and summary tests**

Run:

```bash
cd backend
pytest tests/test_entitlements.py tests/test_summary_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/entitlements.py backend/app/auth_routes.py backend/app/summary_routes.py backend/tests/test_entitlements.py backend/tests/test_summary_api.py
git commit -m "feat: enforce AI summary membership quota"
```

## Task 5: Stripe Checkout, Portal, and Webhook

**Files:**
- Modify: `backend/app/services/billing_service.py`
- Modify: `backend/app/billing_routes.py`
- Test: `backend/tests/test_billing_stripe_webhook.py`

- [ ] **Step 1: Write failing Stripe webhook tests**

Create `backend/tests/test_billing_stripe_webhook.py`:

```python
import json

from fastapi.testclient import TestClient

from app import billing_routes
from app.main import app
from app.services import database
from app.services.auth_service import create_user
from app.services.billing_service import get_membership


class FakeStripeWebhook:
    calls = 0

    @staticmethod
    def construct_event(payload, sig_header, secret):
        FakeStripeWebhook.calls += 1
        if sig_header != "valid":
            raise ValueError("bad signature")
        return json.loads(payload)


def test_webhook_rejects_bad_signature(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "stripe_webhook_placeholder")
    database.initialize_database(tmp_path / "saveany.db")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)

    response = client.post(
        "/api/billing/webhook",
        content=json.dumps({"id": "evt_bad", "type": "customer.subscription.updated"}),
        headers={"Stripe-Signature": "invalid"},
    )

    assert response.status_code == 400


def test_subscription_updated_webhook_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "stripe")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "stripe_webhook_placeholder")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("stripe@example.com", "stripe-password")
    monkeypatch.setattr(billing_routes.stripe, "Webhook", FakeStripeWebhook)
    client = TestClient(app)
    event = {
        "id": "evt_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "active",
                "current_period_start": 1777600000,
                "current_period_end": 1780278400,
                "cancel_at_period_end": False,
                "metadata": {"saveany_user_id": user.id},
                "items": {"data": [{"price": {"id": "price_123"}}]},
            }
        },
    }

    first = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )
    second = client.post(
        "/api/billing/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": "valid"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    membership = get_membership(user.id)
    assert membership.active is True
    with database.connect(tmp_path / "saveany.db") as conn:
        events = conn.execute("select count(*) as count from stripe_events").fetchone()
    assert events["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_billing_stripe_webhook.py -v
```

Expected: FAIL because webhook route is missing.

- [ ] **Step 3: Add Stripe helpers to billing service**

Append to `backend/app/services/billing_service.py`:

```python
import hashlib
import stripe


def upsert_stripe_subscription(subscription: dict) -> Membership:
    metadata = subscription.get("metadata") or {}
    user_id = metadata.get("saveany_user_id")
    if not user_id:
        with connect() as conn:
            row = conn.execute(
                "select user_id from subscriptions where stripe_customer_id = ? order by updated_at desc limit 1",
                (subscription.get("customer"),),
            ).fetchone()
        if row:
            user_id = row["user_id"]
    if not user_id:
        raise ValueError("Stripe subscription is not linked to a SaveAny user")
    items = ((subscription.get("items") or {}).get("data") or [])
    price_id = None
    if items:
        price_id = ((items[0].get("price") or {}).get("id"))
    now = time()
    with transaction() as conn:
        existing = conn.execute(
            "select id from subscriptions where stripe_subscription_id = ?",
            (subscription.get("id"),),
        ).fetchone()
        values = (
            user_id,
            "pro",
            subscription.get("status") or "incomplete",
            subscription.get("customer"),
            subscription.get("id"),
            price_id,
            subscription.get("current_period_start"),
            subscription.get("current_period_end"),
            1 if subscription.get("cancel_at_period_end") else 0,
            now,
        )
        if existing:
            conn.execute(
                """
                update subscriptions
                set user_id = ?, plan = ?, status = ?, stripe_customer_id = ?,
                    stripe_subscription_id = ?, stripe_price_id = ?,
                    current_period_start = ?, current_period_end = ?,
                    cancel_at_period_end = ?, updated_at = ?
                where id = ?
                """,
                (*values, existing["id"]),
            )
        else:
            conn.execute(
                """
                insert into subscriptions
                (id, user_id, plan, status, stripe_customer_id, stripe_subscription_id,
                 stripe_price_id, current_period_start, current_period_end,
                 cancel_at_period_end, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"sub_{secrets.token_urlsafe(10)}", *values, now),
            )
    return get_membership(user_id)


def record_stripe_event_once(event_id: str, event_type: str, payload: bytes) -> bool:
    payload_hash = hashlib.sha256(payload).hexdigest()
    try:
        with transaction() as conn:
            conn.execute(
                """
                insert into stripe_events (event_id, event_type, processed_at, payload_hash)
                values (?, ?, ?, ?)
                """,
                (event_id, event_type, time(), payload_hash),
            )
        return True
    except Exception as exc:
        if "UNIQUE constraint failed: stripe_events.event_id" in str(exc):
            return False
        raise
```

- [ ] **Step 4: Add Stripe webhook route**

Modify `backend/app/billing_routes.py` imports:

```python
import stripe
from fastapi import Request
from app.services.billing_service import record_stripe_event_once, upsert_stripe_subscription
```

Append route:

```python
@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict[str, bool]:
    config = load_config()
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, signature, config.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Stripe webhook 签名验证失败") from exc

    event_id = event.get("id")
    event_type = event.get("type")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Stripe webhook 缺少事件 ID")
    if not record_stripe_event_once(event_id, event_type, payload):
        return {"ok": True}

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        upsert_stripe_subscription(event["data"]["object"])
    return {"ok": True}
```

- [ ] **Step 5: Add Stripe checkout and portal creation**

Modify `billing_checkout` in `backend/app/billing_routes.py`:

```python
if config.billing_mode == "stripe":
    if not config.stripe_secret_key or not config.stripe_pro_monthly_price_id:
        raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")
    stripe.api_key = config.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": config.stripe_pro_monthly_price_id, "quantity": 1}],
        success_url=f"{config.public_app_url}/#pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{config.public_app_url}/#pricing?checkout=cancel",
        client_reference_id=user.id,
        subscription_data={"metadata": {"saveany_user_id": user.id}},
        metadata={"saveany_user_id": user.id},
    )
    return {"mode": "stripe", "url": session.url, "session_id": session.id}
```

Add portal route:

```python
@router.post("/portal")
def billing_portal(user: User = Depends(current_user)) -> dict:
    config = load_config()
    if config.billing_mode == "mock":
        return {"mode": "mock", "url": "/#pricing"}
    membership = get_membership(user.id)
    with connect() as conn:
        row = conn.execute(
            "select stripe_customer_id from subscriptions where user_id = ? order by updated_at desc limit 1",
            (user.id,),
        ).fetchone()
    if row is None or not row["stripe_customer_id"]:
        raise HTTPException(status_code=404, detail="还没有可管理的 Stripe 会员订阅")
    stripe.api_key = config.stripe_secret_key
    session = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=f"{config.public_app_url}/#pricing",
    )
    return {"mode": "stripe", "url": session.url, "membership": membership.as_dict()}
```

- [ ] **Step 6: Run Stripe tests**

Run:

```bash
cd backend
pytest tests/test_billing_stripe_webhook.py tests/test_billing_mock.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/billing_service.py backend/app/billing_routes.py backend/tests/test_billing_stripe_webhook.py
git commit -m "feat: add Stripe subscription webhook handling"
```

## Task 6: Frontend API and Session State

**Files:**
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/services/authSession.js`
- Test: `frontend/tests/auth-session.test.js`

- [ ] **Step 1: Write frontend session tests**

Create `frontend/tests/auth-session.test.js`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import {
  authInitialState,
  membershipLabel,
  remainingSummaryText,
  updateAuthState
} from "../src/services/authSession.js";

test("updateAuthState stores user membership and usage", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: { daily_free_limit: 3, used_today: 2, remaining_today: 1 }
  });

  assert.equal(state.user.email, "user@example.com");
  assert.equal(membershipLabel(state), "免费版");
  assert.equal(remainingSummaryText(state), "今日还可免费总结 1 次");
});

test("membership label describes active pro plan", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "pro@example.com" },
    membership: { active: true, plan: "pro", status: "active" },
    usage: { daily_free_limit: 3, used_today: 0, remaining_today: 3 }
  });

  assert.equal(membershipLabel(state), "专业版会员");
  assert.equal(remainingSummaryText(state), "专业版 AI 总结额度已解锁");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- auth-session
```

Expected: FAIL because `authSession.js` does not exist.

- [ ] **Step 3: Add auth session helpers**

Create `frontend/src/services/authSession.js`:

```javascript
export function authInitialState() {
  return {
    user: null,
    membership: { active: false, plan: "free", status: "anonymous" },
    usage: { daily_free_limit: 3, used_today: 0, remaining_today: 0 },
    loading: false,
    error: ""
  };
}

export function updateAuthState(state, payload) {
  state.user = payload.user || null;
  state.membership = payload.membership || { active: false, plan: "free", status: "free" };
  state.usage = payload.usage || { daily_free_limit: 3, used_today: 0, remaining_today: 3 };
  state.error = "";
}

export function clearAuthState(state) {
  state.user = null;
  state.membership = { active: false, plan: "free", status: "anonymous" };
  state.usage = { daily_free_limit: 3, used_today: 0, remaining_today: 0 };
}

export function membershipLabel(state) {
  if (state.membership?.active) return "专业版会员";
  if (state.user) return "免费版";
  return "未登录";
}

export function remainingSummaryText(state) {
  if (state.membership?.active) return "专业版 AI 总结额度已解锁";
  if (!state.user) return "登录后每天可免费总结 3 次";
  return `今日还可免费总结 ${Math.max(state.usage?.remaining_today || 0, 0)} 次`;
}
```

- [ ] **Step 4: Add API functions**

Modify `frontend/src/services/api.js`:

```javascript
export async function getMe() {
  const response = await fetch("/api/me", { credentials: "include" });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }
  return response.json();
}

export async function registerAccount(payload) {
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function loginAccount(payload) {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function logoutAccount() {
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "include"
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function createBillingCheckout() {
  const response = await fetch("/api/billing/checkout", {
    method: "POST",
    credentials: "include"
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function createBillingPortal() {
  const response = await fetch("/api/billing/portal", {
    method: "POST",
    credentials: "include"
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function mockBillingAction(action) {
  const response = await fetch(`/api/billing/mock/${action}`, {
    method: "POST",
    credentials: "include"
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}
```

Also add `credentials: "include"` to existing `createSummaryTask`.

- [ ] **Step 5: Run frontend session tests**

Run:

```bash
cd frontend
npm test -- auth-session
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/authSession.js frontend/tests/auth-session.test.js
git commit -m "feat: add frontend auth session helpers"
```

## Task 7: Frontend Auth UI

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/tests/chinese-ui-copy.test.js`

- [ ] **Step 1: Add UI copy test**

Modify `frontend/tests/chinese-ui-copy.test.js` to assert these strings are present in `frontend/src/App.vue`:

```javascript
const expectedCopy = [
  "登录 / 注册",
  "邮箱",
  "密码",
  "退出登录",
  "免费版",
  "专业版会员",
  "今日还可免费总结"
];

for (const copy of expectedCopy) {
  assert.match(source, new RegExp(copy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- chinese-ui-copy
```

Expected: FAIL with missing auth copy.

- [ ] **Step 3: Add imports and auth state to `App.vue`**

Modify the script imports:

```javascript
import { clearAuthState, authInitialState, membershipLabel, remainingSummaryText, updateAuthState } from "./services/authSession";
import { getMe, loginAccount, logoutAccount, registerAccount } from "./services/api";
```

Add state fields:

```javascript
const auth = reactive(authInitialState());
const authForm = reactive({
  open: false,
  mode: "login",
  email: "",
  password: "",
  busy: false,
  error: ""
});

const authMembershipLabel = computed(() => membershipLabel(auth));
const authUsageText = computed(() => remainingSummaryText(auth));
```

- [ ] **Step 4: Add auth methods**

Add to `App.vue` script:

```javascript
function openAuth(mode = "login") {
  authForm.mode = mode;
  authForm.open = true;
  authForm.error = "";
}

async function refreshMe({ silent = false } = {}) {
  if (!silent) auth.loading = true;
  try {
    const payload = await getMe();
    updateAuthState(auth, payload);
  } catch {
    clearAuthState(auth);
  } finally {
    auth.loading = false;
  }
}

async function submitAuth() {
  authForm.error = "";
  authForm.busy = true;
  try {
    const payload =
      authForm.mode === "register"
        ? await registerAccount({ email: authForm.email, password: authForm.password })
        : await loginAccount({ email: authForm.email, password: authForm.password });
    updateAuthState(auth, payload);
    authForm.open = false;
    authForm.email = "";
    authForm.password = "";
  } catch (error) {
    authForm.error = error.message;
  } finally {
    authForm.busy = false;
  }
}

async function logout() {
  await logoutAccount();
  clearAuthState(auth);
}
```

Call `refreshMe({ silent: true })` inside `onMounted`.

- [ ] **Step 5: Add header auth UI and modal**

In the topbar template, after nav links:

```vue
<div class="account-menu">
  <button v-if="!auth.user" class="secondary-button account-button" type="button" @click="openAuth('login')">
    <span>登录 / 注册</span>
  </button>
  <div v-else class="account-chip">
    <span>{{ auth.user.email }}</span>
    <strong>{{ authMembershipLabel }}</strong>
    <button type="button" @click="logout">退出登录</button>
  </div>
</div>
```

Near the end of `<main>`:

```vue
<section v-if="authForm.open" class="auth-modal" role="dialog" aria-modal="true" aria-label="账号登录">
  <form class="auth-panel" @submit.prevent="submitAuth">
    <h2>{{ authForm.mode === "register" ? "注册账号" : "登录账号" }}</h2>
    <label>
      <span>邮箱</span>
      <input v-model="authForm.email" type="email" autocomplete="email" required />
    </label>
    <label>
      <span>密码</span>
      <input v-model="authForm.password" type="password" autocomplete="current-password" required />
    </label>
    <p v-if="authForm.error" class="message error">{{ authForm.error }}</p>
    <button class="primary-button" type="submit" :disabled="authForm.busy">
      <span>{{ authForm.mode === "register" ? "注册并登录" : "登录" }}</span>
    </button>
    <button class="secondary-button" type="button" @click="authForm.mode = authForm.mode === 'register' ? 'login' : 'register'">
      <span>{{ authForm.mode === "register" ? "已有账号，去登录" : "没有账号，去注册" }}</span>
    </button>
    <button class="secondary-button" type="button" @click="authForm.open = false">
      <span>关闭</span>
    </button>
  </form>
</section>
```

- [ ] **Step 6: Add minimal CSS in `frontend/src/assets/main.css`**

Add:

```css
.account-menu {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.account-chip {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.875rem;
}

.auth-modal {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgba(10, 15, 20, 0.55);
}

.auth-panel {
  width: min(420px, 100%);
  display: grid;
  gap: 1rem;
  padding: 1.25rem;
  border-radius: 8px;
  background: var(--surface, #101820);
}

.auth-panel label {
  display: grid;
  gap: 0.35rem;
}
```

- [ ] **Step 7: Run UI copy test**

Run:

```bash
cd frontend
npm test -- chinese-ui-copy
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.vue frontend/src/assets/main.css frontend/tests/chinese-ui-copy.test.js
git commit -m "feat: add account login interface"
```

## Task 8: Frontend Billing and Summary Gates

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/services/api.js`
- Test: `frontend/tests/chinese-ui-copy.test.js`

- [ ] **Step 1: Add billing copy test**

Extend the copy list in `frontend/tests/chinese-ui-copy.test.js`:

```javascript
const billingCopy = [
  "开通专业版 ¥29/月",
  "管理订阅",
  "今日免费 AI 总结额度已用完",
  "正在确认会员状态",
  "模拟开通",
  "模拟取消",
  "模拟过期",
  "模拟付款失败"
];
```

Assert each string is present.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- chinese-ui-copy
```

Expected: FAIL with missing billing copy.

- [ ] **Step 3: Add billing methods**

Modify `App.vue` imports:

```javascript
import { createBillingCheckout, createBillingPortal, mockBillingAction } from "./services/api";
```

Add methods:

```javascript
async function startCheckout() {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  try {
    const result = await createBillingCheckout();
    if (result.url) window.location.href = result.url;
  } catch (error) {
    state.error = localizeStatus(error.message);
  }
}

async function openBillingPortal() {
  try {
    const result = await createBillingPortal();
    if (result.url) window.location.href = result.url;
  } catch (error) {
    state.error = localizeStatus(error.message);
  }
}

async function runMockBilling(action) {
  try {
    const result = await mockBillingAction(action);
    auth.membership = result.membership;
    await refreshMe({ silent: true });
  } catch (error) {
    state.error = localizeStatus(error.message);
  }
}
```

- [ ] **Step 4: Gate auto summary creation**

Modify `startSummaryForResult` before creating the summary task:

```javascript
if (!auth.user) {
  openAuth("login");
  state.summaryError = "登录后每天可免费总结 3 次。";
  return;
}
if (!auth.membership?.active && (auth.usage?.remaining_today || 0) <= 0) {
  state.summaryError = "今日免费 AI 总结额度已用完，请开通专业版继续使用。";
  return;
}
```

After `createSummaryTask`, refresh account state:

```javascript
await refreshMe({ silent: true });
```

- [ ] **Step 5: Update pricing card buttons**

In pricing template, for the pro plan button:

```vue
<button
  v-if="plan.id === 'pro' && !auth.membership?.active"
  class="primary-button"
  type="button"
  @click="startCheckout"
>
  <Star :size="20" aria-hidden="true" />
  <span>开通专业版 ¥29/月</span>
</button>
<button
  v-else-if="plan.id === 'pro'"
  class="secondary-button"
  type="button"
  @click="openBillingPortal"
>
  <span>管理订阅</span>
</button>
```

Keep existing buttons for free/team plans.

- [ ] **Step 6: Add mock billing controls in pricing page**

Below `pricing-assurance`:

```vue
<div v-if="auth.user" class="mock-billing-panel" aria-label="本地模拟支付">
  <p>本地 mock billing 可在无外网时验收会员状态。</p>
  <button class="secondary-button" type="button" @click="runMockBilling('activate')">模拟开通</button>
  <button class="secondary-button" type="button" @click="runMockBilling('cancel')">模拟取消</button>
  <button class="secondary-button" type="button" @click="runMockBilling('expire')">模拟过期</button>
  <button class="secondary-button" type="button" @click="runMockBilling('payment-failed')">模拟付款失败</button>
</div>
```

- [ ] **Step 7: Add success confirmation copy**

In `syncCurrentPageFromHash`, detect checkout query:

```javascript
if (typeof window !== "undefined" && window.location.href.includes("checkout=success")) {
  state.error = "";
  state.summaryError = "";
  await refreshMe({ silent: true });
}
```

Add pricing page copy:

```vue
<p v-if="typeof window !== 'undefined' && window.location.href.includes('checkout=success')" class="message">
  正在确认会员状态，请稍等几秒。
</p>
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.vue frontend/src/services/api.js frontend/tests/chinese-ui-copy.test.js
git commit -m "feat: add membership billing interface"
```

## Task 9: Documentation and Setup Guide

**Files:**
- Modify: `README.md`
- Modify: `docs/04-api-design.md`
- Create: `docs/11-membership-stripe-setup.md`

- [ ] **Step 1: Update README feature list**

Add bullets under Features:

```markdown
- Register and log in with email/password accounts.
- Gate AI video summaries with free daily quota and Pro membership.
- Test membership offline with mock billing, or connect Stripe Checkout for real monthly subscriptions.
```

- [ ] **Step 2: Update API docs**

Append to `docs/04-api-design.md`:

```markdown
## Authentication

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `POST /api/auth/password-reset/request`
- `POST /api/auth/password-reset/confirm`

Authentication uses an HttpOnly session cookie. Frontend code must not read the cookie directly.

## Billing

- `GET /api/billing/status`
- `POST /api/billing/checkout`
- `POST /api/billing/portal`
- `POST /api/billing/webhook`

`POST /api/billing/webhook` verifies Stripe signatures and processes events idempotently.
```

- [ ] **Step 3: Add Stripe setup guide**

Create `docs/11-membership-stripe-setup.md`:

````markdown
# 会员与 Stripe 配置

## 本地无外网测试

Use mock billing:

```bash
BILLING_MODE=mock
```

Start backend and frontend, register an account, open the pricing page, and use the mock billing buttons to simulate activation, cancellation, expiration, and payment failure.

## Stripe Test Mode

1. Create a Stripe Product named `SaveAny Pro`.
2. Create a recurring monthly Price for `¥29`, currency `cny`.
3. Configure backend environment variables:

```bash
BILLING_MODE=stripe
STRIPE_SECRET_KEY=stripe_secret_placeholder
STRIPE_WEBHOOK_SECRET=stripe_webhook_placeholder
STRIPE_PRO_MONTHLY_PRICE_ID=price_...
PUBLIC_APP_URL=http://localhost:5173
```

4. Start Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
```

5. Open the pricing page, start Checkout, and pay with a Stripe test card.
6. Return to SaveAny and wait for webhook confirmation.

The frontend success page does not grant membership by itself. Membership becomes active only after the webhook updates the local SQLite database.
````

- [ ] **Step 4: Run docs grep checks**

Run:

```bash
rg -n "BILLING_MODE|STRIPE_PRO_MONTHLY_PRICE_ID|stripe listen|mock billing" README.md docs/04-api-design.md docs/11-membership-stripe-setup.md
```

Expected: command prints matching lines from all three files.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/04-api-design.md docs/11-membership-stripe-setup.md
git commit -m "docs: add membership billing setup guide"
```

## Task 10: Full Verification Pass

**Files:**
- Modify only files needed to fix verification failures.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
pytest
```

Expected: all tests PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: all tests PASS.

- [ ] **Step 3: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite build completes and writes `frontend/dist`.

- [ ] **Step 4: Manual mock billing smoke test**

Start backend:

```bash
cd backend
BILLING_MODE=mock uvicorn app.main:app --reload --port 8000
```

Start frontend:

```bash
cd frontend
npm run dev
```

Manual checks:

- Register a new account.
- Analyze the demo URL with `SAVEANY_DEMO_MODE=true` or any supported public URL.
- Confirm AI summary creates while free quota remains.
- Use mock “模拟开通” and confirm membership label becomes “专业版会员”.
- Use mock “模拟过期” and confirm AI summary gate returns to free quota behavior.

- [ ] **Step 5: Commit verification fixes**

If verification required code changes:

```bash
git add -A
git commit -m "fix: stabilize membership billing verification"
```

If no changes were needed, do not create an empty commit.

## Self-Review

- Spec coverage: Tasks cover account registration/login/logout/password reset, SQLite persistence, membership state, Stripe Checkout, Stripe webhook signature verification and idempotency, Customer Portal, mock billing, AI summary quota, frontend UI, docs, and verification.
- Placeholder scan: This plan contains no unresolved placeholders. Secrets are shown with `stripe_secret_placeholder` and `stripe_webhook_placeholder` only in setup documentation, not as implementation gaps.
- Type consistency: Backend uses `User`, `Membership`, and `UsageSummary` consistently. Frontend auth state uses `user`, `membership`, and `usage` consistently with `/api/me`.
