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

    @classmethod
    def from_row(cls, row) -> User:
        return cls(id=row["id"], email=row["email"], status=row["status"])

    def as_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "status": self.status}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row) -> User:
    return User.from_row(row)


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


def get_user_by_id(user_id: str) -> User | None:
    conn = connect()
    try:
        row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return User.from_row(row) if row else None


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
