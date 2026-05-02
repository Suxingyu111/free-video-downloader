from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from time import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.services.app_config import load_config
from app.services.csrf import create_session_csrf_token
from app.services.database import connect, transaction


ph = PasswordHasher()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    status: str

    def as_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "status": self.status}


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str


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
    conn = connect()
    try:
        row = conn.execute("select * from users where email = ?", (normalized,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        ph.verify(row["password_hash"], password)
    except VerifyMismatchError:
        return None
    return _row_to_user(row)


def _hash_context(value: str | None) -> str | None:
    if not value:
        return None
    salted = f"{load_config().ip_hash_salt}:{value}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def create_session(
    user_id: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    rotated_from_session_id: str | None = None,
) -> SessionTokens:
    config = load_config()
    now = time()
    token = secrets.token_urlsafe(32)
    csrf_token = create_session_csrf_token()
    with transaction() as conn:
        conn.execute(
            """
            insert into sessions (
                id,
                user_id,
                session_token_hash,
                csrf_token_hash,
                expires_at,
                absolute_expires_at,
                created_at,
                last_seen_at,
                ip_hash,
                user_agent_hash,
                rotated_from_session_id
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{secrets.token_urlsafe(12)}",
                user_id,
                _hash_token(token),
                _hash_token(csrf_token),
                now + config.session_idle_days * 86400,
                now + config.session_days * 86400,
                now,
                now,
                _hash_context(ip_address),
                _hash_context(user_agent),
                rotated_from_session_id,
            ),
        )
    return SessionTokens(session_token=token, csrf_token=csrf_token)


def get_user_by_session_token(token: str | None) -> User | None:
    if not token:
        return None
    now = time()
    with transaction() as conn:
        row = conn.execute(
            """
            select
              users.*,
              sessions.expires_at as session_expires_at,
              sessions.absolute_expires_at as session_absolute_expires_at
            from sessions
            join users on users.id = sessions.user_id
            where sessions.session_token_hash = ?
              and sessions.expires_at > ?
              and coalesce(sessions.absolute_expires_at, sessions.expires_at) > ?
              and sessions.revoked_at is null
              and users.status = 'active'
            """,
            (_hash_token(token), now, now),
        ).fetchone()
        if row is None:
            return None
        absolute_expires_at = row["session_absolute_expires_at"] or row["session_expires_at"]
        refreshed_expires_at = min(
            now + load_config().session_idle_days * 86400,
            absolute_expires_at,
        )
        conn.execute(
            """
            update sessions
            set last_seen_at = ?, expires_at = ?
            where session_token_hash = ?
            """,
            (now, refreshed_expires_at, _hash_token(token)),
        )
    return _row_to_user(row)


def verify_session_csrf_token(session_token: str | None, csrf_token: str | None) -> bool:
    if not session_token or not csrf_token:
        return False
    conn = connect()
    try:
        row = conn.execute(
            """
            select csrf_token_hash from sessions
            where session_token_hash = ?
              and expires_at > ?
              and coalesce(absolute_expires_at, expires_at) > ?
              and revoked_at is null
            """,
            (_hash_token(session_token), time(), time()),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["csrf_token_hash"]:
        return False
    return hmac.compare_digest(row["csrf_token_hash"], _hash_token(csrf_token))


def revoke_session(token: str | None, reason: str | None = None) -> None:
    if not token:
        return
    with transaction() as conn:
        conn.execute(
            "update sessions set revoked_at = ?, revoked_reason = ? where session_token_hash = ?",
            (time(), reason, _hash_token(token)),
        )


def _revoke_user_sessions(conn, user_id: str, reason: str, revoked_at: float) -> None:
    conn.execute(
        """
        update sessions
        set revoked_at = ?, revoked_reason = ?
        where user_id = ? and revoked_at is null
        """,
        (revoked_at, reason, user_id),
    )


def revoke_user_sessions(user_id: str, reason: str) -> None:
    with transaction() as conn:
        _revoke_user_sessions(conn, user_id, reason, time())


def create_password_reset_token(email: str) -> str | None:
    normalized = normalize_email(email)
    conn = connect()
    try:
        user = conn.execute("select * from users where email = ?", (normalized,)).fetchone()
    finally:
        conn.close()
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    now = time()
    with transaction() as conn:
        conn.execute(
            """
            update password_reset_tokens
            set revoked_at = ?
            where user_id = ?
              and used_at is null
              and revoked_at is null
            """,
            (now, user["id"]),
        )
        conn.execute(
            """
            insert into password_reset_tokens (id, user_id, token_hash, expires_at, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                f"reset_{secrets.token_urlsafe(12)}",
                user["id"],
                _hash_token(token),
                now + load_config().password_reset_token_minutes * 60,
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
            where token_hash = ?
              and used_at is null
              and revoked_at is null
              and expires_at > ?
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
        _revoke_user_sessions(conn, row["user_id"], "password_reset", now)
    return True
