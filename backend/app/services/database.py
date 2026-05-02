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
  revoked_at real,
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

create table if not exists stripe_customers (
  user_id text primary key references users(id) on delete cascade,
  stripe_customer_id text not null unique,
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
  purchase_type text not null default 'subscription',
  pack_id text,
  stripe_price_id text,
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

create table if not exists usage_periods (
  user_id text not null references users(id) on delete cascade,
  period_type text not null,
  period_key text not null,
  analyze_count integer not null default 0,
  download_count integer not null default 0,
  summary_count integer not null default 0,
  transcription_minutes integer not null default 0,
  question_count integer not null default 0,
  created_at real not null,
  updated_at real not null,
  primary key (user_id, period_type, period_key)
);

create table if not exists anonymous_usage (
  ip_hash text not null,
  usage_date text not null,
  analyze_count integer not null default 0,
  download_count integer not null default 0,
  created_at real not null,
  updated_at real not null,
  primary key (ip_hash, usage_date)
);

create table if not exists meter_reservations (
  reservation_id text primary key,
  user_id text references users(id) on delete cascade,
  meter_type text not null,
  amount integer not null,
  plan_amount integer not null default 0,
  pack_amount integer not null default 0,
  period_type text,
  period_key text,
  credit_pack_id text,
  status text not null,
  created_at real not null,
  committed_at real,
  refunded_at real
);

create table if not exists credit_packs (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  pack_id text not null,
  pack_type text not null,
  source text not null,
  stripe_price_id text,
  stripe_payment_intent_id text not null,
  purchased_amount integer not null,
  remaining_amount integer not null,
  expires_at real not null,
  status text not null,
  created_at real not null,
  updated_at real not null
);

create unique index if not exists idx_credit_packs_payment_idempotency
on credit_packs (user_id, source, stripe_payment_intent_id, pack_id);

create table if not exists meter_reservation_pack_uses (
  reservation_id text not null references meter_reservations(reservation_id) on delete cascade,
  credit_pack_id text not null references credit_packs(id) on delete cascade,
  amount integer not null,
  primary key (reservation_id, credit_pack_id)
);

create table if not exists summary_questions (
  summary_id text not null,
  user_id text not null references users(id) on delete cascade,
  question_count integer not null default 0,
  created_at real not null,
  updated_at real not null,
  primary key (summary_id, user_id)
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
        _migrate_password_reset_tokens(conn)
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
    if "purchase_type" not in columns:
        conn.execute(
            "alter table billing_attempts add column purchase_type text not null default 'subscription'"
        )
    if "pack_id" not in columns:
        conn.execute("alter table billing_attempts add column pack_id text")
    if "stripe_price_id" not in columns:
        conn.execute("alter table billing_attempts add column stripe_price_id text")


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


def _migrate_password_reset_tokens(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("pragma table_info(password_reset_tokens)").fetchall()
    }
    if "revoked_at" not in columns:
        conn.execute("alter table password_reset_tokens add column revoked_at real")


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
