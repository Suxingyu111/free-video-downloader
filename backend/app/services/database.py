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
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


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
