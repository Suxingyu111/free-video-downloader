from __future__ import annotations

from time import time

from app.services.database import transaction


class RateLimitExceeded(Exception):
    pass


def assert_rate_limit_allowed(key: str, *, limit: int, window_seconds: int) -> None:
    now = time()
    with transaction() as conn:
        row = conn.execute(
            "select count, reset_at from rate_limits where key = ?",
            (key,),
        ).fetchone()
        if row is None or row["reset_at"] <= now:
            conn.execute(
                """
                insert into rate_limits (key, count, reset_at)
                values (?, 0, ?)
                on conflict(key) do update set count = 0, reset_at = excluded.reset_at
                """,
                (key, now + window_seconds),
            )
            return
        if row["count"] >= limit:
            raise RateLimitExceeded("操作太频繁，请稍后再试")


def record_rate_limit_hit(key: str, *, window_seconds: int) -> None:
    now = time()
    with transaction() as conn:
        row = conn.execute(
            "select count, reset_at from rate_limits where key = ?",
            (key,),
        ).fetchone()
        if row is None or row["reset_at"] <= now:
            conn.execute(
                """
                insert into rate_limits (key, count, reset_at)
                values (?, 1, ?)
                on conflict(key) do update set count = 1, reset_at = excluded.reset_at
                """,
                (key, now + window_seconds),
            )
            return
        conn.execute(
            "update rate_limits set count = count + 1 where key = ?",
            (key,),
        )


def clear_rate_limit(key: str) -> None:
    with transaction() as conn:
        conn.execute("delete from rate_limits where key = ?", (key,))
