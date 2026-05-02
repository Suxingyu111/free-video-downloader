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
  csrf_token_hash text,
  expires_at real not null,
  absolute_expires_at real,
  created_at real not null,
  last_seen_at real not null,
  revoked_at real,
  revoked_reason text,
  ip_hash text,
  user_agent_hash text,
  rotated_from_session_id text
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
  status text not null default 'pending',
  processing_started_at real not null default 0,
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

create table if not exists summary_quota_reservations (
  reservation_id text primary key,
  user_id text not null references users(id) on delete cascade,
  usage_date text not null,
  created_at real not null,
  refunded_at real
);

create table if not exists billing_attempts (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  mode text not null,
  status text not null,
  stripe_checkout_session_id text,
  stripe_checkout_url text,
  stripe_return_url text,
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
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _migrate_stripe_events(conn)
        _migrate_billing_attempts(conn)
        _migrate_sessions(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_stripe_events(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("pragma table_info(stripe_events)").fetchall()
    }
    if "status" not in columns:
        conn.execute(
            "alter table stripe_events add column status text not null default 'processed'"
        )
    if "processing_started_at" not in columns:
        conn.execute(
            "alter table stripe_events add column processing_started_at real not null default 0"
        )


def _migrate_billing_attempts(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("pragma table_info(billing_attempts)").fetchall()
    }
    if "stripe_checkout_url" not in columns:
        conn.execute("alter table billing_attempts add column stripe_checkout_url text")
    if "stripe_return_url" not in columns:
        conn.execute("alter table billing_attempts add column stripe_return_url text")


def _migrate_sessions(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("pragma table_info(sessions)").fetchall()
    }
    if "csrf_token_hash" not in columns:
        conn.execute("alter table sessions add column csrf_token_hash text")
    if "absolute_expires_at" not in columns:
        conn.execute("alter table sessions add column absolute_expires_at real")
        conn.execute("update sessions set absolute_expires_at = expires_at where absolute_expires_at is null")
    if "revoked_reason" not in columns:
        conn.execute("alter table sessions add column revoked_reason text")
    if "ip_hash" not in columns:
        conn.execute("alter table sessions add column ip_hash text")
    if "user_agent_hash" not in columns:
        conn.execute("alter table sessions add column user_agent_hash text")
    if "rotated_from_session_id" not in columns:
        conn.execute("alter table sessions add column rotated_from_session_id text")


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
