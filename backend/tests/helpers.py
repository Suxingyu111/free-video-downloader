from __future__ import annotations

from time import time

from app.services import database
from app.services.auth_service import User


def activate_pro_subscription(user: User, db_path=None) -> None:
    now = time()
    with database.transaction(db_path) as conn:
        conn.execute(
            """
            insert into subscriptions
            (id, user_id, plan, status, current_period_start, current_period_end,
             cancel_at_period_end, created_at, updated_at)
            values (?, ?, 'pro', 'active', ?, ?, 0, ?, ?)
            on conflict(id) do update set
                plan = excluded.plan,
                status = excluded.status,
                current_period_start = excluded.current_period_start,
                current_period_end = excluded.current_period_end,
                cancel_at_period_end = excluded.cancel_at_period_end,
                updated_at = excluded.updated_at
            """,
            (f"test_sub_{user.id}", user.id, now, now + 30 * 86400, now, now),
        )
