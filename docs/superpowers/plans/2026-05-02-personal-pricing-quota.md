# Personal Pricing Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the confirmed personal-only transparent quota model: free visitor limits, richer logged-in free limits, `¥19/月` Pro, AI summary packs, transcription minute packs, and quota-aware UI.

**Architecture:** Add a small backend quota domain around a `PLAN_CATALOG`, period usage rows, anonymous IP usage rows, reservations, and credit packs. Keep existing auth, membership, summary task, and Stripe boundaries, but route analyze/download/summary/question/billing through the quota domain. Update the Vue SPA pricing page from three cards to two personal cards plus credit pack panels, and expose real remaining usage in account and workbench states.

**Tech Stack:** FastAPI, Pydantic, SQLite, Stripe Checkout/Webhooks, pytest, Vue 3 Composition API, Vite, Node test runner.

---

## Scope Check

This plan implements the first stage from `docs/superpowers/specs/2026-05-02-personal-pricing-quota-design.md`: real personal quotas, Pro subscription, credit packs, Stripe/mock purchase flows, and frontend quota UX. It does not implement annual billing, invoices, full usage history pages, historical summary lists, or batch export.

The work is broad but cohesive: all tasks depend on one quota model and must land together for the product to behave consistently. The plan is split by stable integration boundaries so each task is independently testable.

## File Structure

- Create `backend/app/services/plan_catalog.py`
  Defines personal plan limits, credit pack catalog, Stripe price environment mapping, period helpers, and visible quota labels.
- Create `backend/app/services/usage_meter.py`
  Owns anonymous usage, logged-in period usage, quota checks, reservation/refund, credit pack consumption, and entitlement status payloads.
- Modify `backend/app/services/database.py`
  Adds `usage_periods`, `anonymous_usage`, `meter_reservations`, `meter_reservation_pack_uses`, `credit_packs`, and `summary_questions` tables plus migrations.
- Modify `backend/app/services/app_config.py`
  Adds Stripe one-time Price ID config values for four credit packs and an IP hash salt setting.
- Modify `backend/app/services/entitlements.py`
  Converts existing summary usage helpers to call `usage_meter` while preserving `/api/me` compatibility.
- Create `backend/app/services/analysis_store.py`
  Stores short-lived server-side analyze snapshots and returns opaque `analysis_token` values for download duration/count enforcement.
- Modify `backend/app/main.py`
  Applies analyze/download quota checks, returns `analysis_token`, and requires the token or a fresh server-side reanalysis before download.
- Modify `backend/app/summary_routes.py`
  Applies summary duration/count checks, owner binding, transcription reservation/refund, and question login/limit checks.
- Modify `backend/app/services/summary_store.py`
  Persists hidden `owner_user_id`, transcript-needed metadata, and quota reservation metadata without exposing them in public snapshots.
- Modify `backend/app/services/summary_service.py`
  Emits a progress event when speech-to-text is required so `summary_routes` can reserve transcription minutes.
- Modify `backend/app/services/billing_service.py`
  Adds credit pack grant helpers and webhook handling support.
- Modify `backend/app/billing_routes.py`
  Supports subscription checkout and one-time payment checkout for credit packs.
- Modify `backend/config/stripe.env.example`
  Documents new Price ID environment variables.
- Modify `docs/11-membership-stripe-setup.md`
  Updates setup instructions for Pro and pack Prices.
- Modify `frontend/src/services/api.js`
  Adds entitlements status API and passes `analysis_token` through download requests.
- Modify `frontend/src/services/authSession.js`
  Adds richer quota text and real progress helpers while keeping legacy `usage` fields safe.
- Modify `frontend/src/App.vue`
  Removes team plan, changes pricing copy and cards, adds pack panels, quota states, and account usage display.
- Modify `frontend/src/assets/main.css`
  Styles two-card pricing, pack grid, quota meters, and quota-specific alerts using existing design tokens.
- Modify tests:
  `backend/tests/test_plan_catalog.py`, `backend/tests/test_usage_meter.py`, `backend/tests/test_database.py`, `backend/tests/test_entitlements.py`, `backend/tests/test_api.py`, `backend/tests/test_summary_api.py`, `backend/tests/test_billing_mock.py`, `backend/tests/test_billing_stripe_webhook.py`, `backend/tests/test_app_config.py`, `frontend/tests/summary-api.test.js`, `frontend/tests/auth-session.test.js`, `frontend/tests/summary-auto-layout.test.js`, `frontend/tests/chinese-ui-copy.test.js`.

## Context Notes

- Stripe Checkout supports `mode="subscription"` for recurring Prices and `mode="payment"` for one-time Price IDs. The Checkout Session supports `client_reference_id`, `metadata`, `line_items`, `payment_status`, `payment_intent`, `success_url`, and `cancel_url`; webhook event `checkout.session.completed` is the main grant point for one-time packs. This was checked with Context7 against `/websites/stripe`.
- Keep frontend-visible Stripe state server-authoritative. The frontend can request `pack_id`, but the backend must map it to configured Price IDs and granted amounts.
- Existing untracked files in the workspace are unrelated. Do not stage or edit them unless a later user request explicitly asks.

---

### Task 1: Plan Catalog and App Config

**Files:**
- Create: `backend/app/services/plan_catalog.py`
- Modify: `backend/app/services/app_config.py`
- Modify: `backend/config/stripe.env.example`
- Test: `backend/tests/test_plan_catalog.py`
- Test: `backend/tests/test_app_config.py`

- [ ] **Step 1: Add failing plan catalog tests**

Create `backend/tests/test_plan_catalog.py`:

```python
from app.services.plan_catalog import (
    CREDIT_PACK_CATALOG,
    PLAN_CATALOG,
    CreditPackDefinition,
    MeterType,
    PeriodType,
    current_period_key,
    get_credit_pack,
    get_plan_limits,
)


def test_personal_plan_catalog_has_confirmed_limits():
    anonymous = get_plan_limits("anonymous")
    free = get_plan_limits("free")
    pro = get_plan_limits("pro")

    assert anonymous.analyze_daily_limit == 3
    assert anonymous.download_daily_limit == 1
    assert anonymous.download_max_duration_seconds == 30 * 60

    assert free.analyze_daily_limit == 30
    assert free.download_daily_limit == 10
    assert free.summary_daily_limit == 3
    assert free.transcription_monthly_minutes == 30
    assert free.questions_per_summary == 3

    assert pro.analyze_monthly_limit == 300
    assert pro.download_monthly_limit == 100
    assert pro.summary_monthly_limit == 120
    assert pro.transcription_monthly_minutes == 600
    assert pro.questions_per_summary == 20


def test_credit_pack_catalog_has_confirmed_packs():
    assert CREDIT_PACK_CATALOG["summary_small"].amount == 20
    assert CREDIT_PACK_CATALOG["summary_small"].price_label == "¥6"
    assert CREDIT_PACK_CATALOG["summary_small"].valid_days == 90
    assert CREDIT_PACK_CATALOG["summary_large"].amount == 100
    assert CREDIT_PACK_CATALOG["transcription_small"].amount == 120
    assert CREDIT_PACK_CATALOG["transcription_large"].amount == 600
    assert get_credit_pack("summary_small").meter_type == MeterType.SUMMARY
    assert get_credit_pack("transcription_large").meter_type == MeterType.TRANSCRIPTION_MINUTES


def test_current_period_keys_are_stable(monkeypatch):
    class FixedDatetime:
        @classmethod
        def now(cls, timezone):
            from datetime import datetime

            return datetime(2026, 5, 2, 12, 30, tzinfo=timezone)

    monkeypatch.setattr("app.services.plan_catalog.datetime", FixedDatetime)

    assert current_period_key(PeriodType.DAY) == "2026-05-02"
    assert current_period_key(PeriodType.MONTH) == "2026-05"


def test_catalog_rejects_unknown_ids():
    try:
        get_plan_limits("team")
    except KeyError as exc:
        assert "Unknown plan" in str(exc)
    else:
        raise AssertionError("expected unknown plan to fail")

    try:
        get_credit_pack("missing_pack")
    except KeyError as exc:
        assert "Unknown credit pack" in str(exc)
    else:
        raise AssertionError("expected unknown credit pack to fail")
```

Append to `backend/tests/test_app_config.py`:

```python
def test_app_config_loads_credit_pack_price_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    monkeypatch.setenv("STRIPE_SUMMARY_LARGE_PACK_PRICE_ID", "price_summary_large")
    monkeypatch.setenv("STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID", "price_transcription_small")
    monkeypatch.setenv("STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID", "price_transcription_large")
    monkeypatch.setenv("SAVEANY_IP_HASH_SALT", "test-salt")

    config = load_config()

    assert config.stripe_summary_small_pack_price_id == "price_summary_small"
    assert config.stripe_summary_large_pack_price_id == "price_summary_large"
    assert config.stripe_transcription_small_pack_price_id == "price_transcription_small"
    assert config.stripe_transcription_large_pack_price_id == "price_transcription_large"
    assert config.ip_hash_salt == "test-salt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_plan_catalog.py tests/test_app_config.py::test_app_config_loads_credit_pack_price_ids -q
```

Expected: fail because `app.services.plan_catalog` and new config fields do not exist.

- [ ] **Step 3: Create `plan_catalog.py`**

Add `backend/app/services/plan_catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class PeriodType(StrEnum):
    DAY = "day"
    MONTH = "month"


class MeterType(StrEnum):
    ANALYZE = "analyze"
    DOWNLOAD = "download"
    SUMMARY = "summary"
    TRANSCRIPTION_MINUTES = "transcription_minutes"
    QUESTION = "question"


@dataclass(frozen=True)
class PlanLimits:
    id: str
    name: str
    analyze_daily_limit: int | None = None
    analyze_monthly_limit: int | None = None
    download_daily_limit: int | None = None
    download_monthly_limit: int | None = None
    download_max_duration_seconds: int | None = None
    summary_daily_limit: int | None = None
    summary_monthly_limit: int | None = None
    summary_max_duration_seconds: int | None = None
    transcription_monthly_minutes: int | None = None
    questions_per_summary: int | None = None


@dataclass(frozen=True)
class CreditPackDefinition:
    id: str
    name: str
    meter_type: MeterType
    amount: int
    valid_days: int
    price_label: str
    stripe_config_field: str


PLAN_CATALOG: dict[str, PlanLimits] = {
    "anonymous": PlanLimits(
        id="anonymous",
        name="未登录访客",
        analyze_daily_limit=3,
        download_daily_limit=1,
        download_max_duration_seconds=30 * 60,
    ),
    "free": PlanLimits(
        id="free",
        name="免费版",
        analyze_daily_limit=30,
        download_daily_limit=10,
        download_max_duration_seconds=60 * 60,
        summary_daily_limit=3,
        summary_max_duration_seconds=30 * 60,
        transcription_monthly_minutes=30,
        questions_per_summary=3,
    ),
    "pro": PlanLimits(
        id="pro",
        name="Pro 个人版",
        analyze_monthly_limit=300,
        download_monthly_limit=100,
        download_max_duration_seconds=180 * 60,
        summary_monthly_limit=120,
        summary_max_duration_seconds=120 * 60,
        transcription_monthly_minutes=600,
        questions_per_summary=20,
    ),
}

CREDIT_PACK_CATALOG: dict[str, CreditPackDefinition] = {
    "summary_small": CreditPackDefinition(
        id="summary_small",
        name="总结小包",
        meter_type=MeterType.SUMMARY,
        amount=20,
        valid_days=90,
        price_label="¥6",
        stripe_config_field="stripe_summary_small_pack_price_id",
    ),
    "summary_large": CreditPackDefinition(
        id="summary_large",
        name="总结大包",
        meter_type=MeterType.SUMMARY,
        amount=100,
        valid_days=180,
        price_label="¥19",
        stripe_config_field="stripe_summary_large_pack_price_id",
    ),
    "transcription_small": CreditPackDefinition(
        id="transcription_small",
        name="转写小包",
        meter_type=MeterType.TRANSCRIPTION_MINUTES,
        amount=120,
        valid_days=90,
        price_label="¥8",
        stripe_config_field="stripe_transcription_small_pack_price_id",
    ),
    "transcription_large": CreditPackDefinition(
        id="transcription_large",
        name="转写大包",
        meter_type=MeterType.TRANSCRIPTION_MINUTES,
        amount=600,
        valid_days=180,
        price_label="¥29",
        stripe_config_field="stripe_transcription_large_pack_price_id",
    ),
}


def get_plan_limits(plan_id: str) -> PlanLimits:
    try:
        return PLAN_CATALOG[plan_id]
    except KeyError as exc:
        raise KeyError(f"Unknown plan: {plan_id}") from exc


def get_credit_pack(pack_id: str) -> CreditPackDefinition:
    try:
        return CREDIT_PACK_CATALOG[pack_id]
    except KeyError as exc:
        raise KeyError(f"Unknown credit pack: {pack_id}") from exc


def current_period_key(period_type: PeriodType) -> str:
    today = datetime.now(timezone.utc).date()
    if period_type == PeriodType.DAY:
        return today.isoformat()
    if period_type == PeriodType.MONTH:
        return f"{today.year:04d}-{today.month:02d}"
    raise ValueError(f"Unsupported period type: {period_type}")
```

- [ ] **Step 4: Extend `AppConfig`**

Modify `backend/app/services/app_config.py` dataclass:

```python
@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    billing_mode: str
    dev_mode: bool
    auth_rate_limit_attempts: int
    auth_rate_limit_window_seconds: int
    free_summary_daily_limit: int
    session_cookie_name: str
    session_days: int
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

Modify `load_config()` return:

```python
        stripe_secret_key=config_value("STRIPE_SECRET_KEY").strip(),
        stripe_webhook_secret=config_value("STRIPE_WEBHOOK_SECRET").strip(),
        stripe_pro_monthly_price_id=config_value("STRIPE_PRO_MONTHLY_PRICE_ID").strip(),
        stripe_summary_small_pack_price_id=config_value("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID").strip(),
        stripe_summary_large_pack_price_id=config_value("STRIPE_SUMMARY_LARGE_PACK_PRICE_ID").strip(),
        stripe_transcription_small_pack_price_id=config_value("STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID").strip(),
        stripe_transcription_large_pack_price_id=config_value("STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID").strip(),
        ip_hash_salt=config_value("SAVEANY_IP_HASH_SALT", "saveany-local-ip-meter").strip(),
```

Keep `free_summary_daily_limit` temporarily for compatibility until Task 3 migrates entitlements.

- [ ] **Step 5: Update Stripe env example**

Append to `backend/config/stripe.env.example`:

```dotenv
# One-time credit pack Prices
STRIPE_SUMMARY_SMALL_PACK_PRICE_ID=price_placeholder
STRIPE_SUMMARY_LARGE_PACK_PRICE_ID=price_placeholder
STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID=price_placeholder
STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID=price_placeholder

# Salt used to hash anonymous IPs for daily visitor quotas.
SAVEANY_IP_HASH_SALT=replace_with_random_server_side_salt
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_plan_catalog.py tests/test_app_config.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/plan_catalog.py backend/app/services/app_config.py backend/config/stripe.env.example backend/tests/test_plan_catalog.py backend/tests/test_app_config.py
git commit -m "feat: 添加个人套餐权益目录"
```

---

### Task 2: Database Schema and Usage Meter Core

**Files:**
- Modify: `backend/app/services/database.py`
- Create: `backend/app/services/usage_meter.py`
- Test: `backend/tests/test_database.py`
- Test: `backend/tests/test_usage_meter.py`

- [ ] **Step 1: Add failing database migration tests**

Append to `backend/tests/test_database.py`:

```python
def test_quota_schema_tables_are_created(monkeypatch, tmp_path):
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

    assert "usage_periods" in tables
    assert "anonymous_usage" in tables
    assert "meter_reservations" in tables
    assert "meter_reservation_pack_uses" in tables
    assert "credit_packs" in tables
    assert "summary_questions" in tables
```

- [ ] **Step 2: Add failing usage meter tests**

Create `backend/tests/test_usage_meter.py`:

```python
import pytest

from app.services import database
from app.services.auth_service import create_user
from app.services.plan_catalog import MeterType
from app.services.usage_meter import (
    MeterExceeded,
    add_credit_pack,
    anonymous_usage_summary,
    consume_anonymous_meter,
    entitlement_status,
    refund_reservation,
    reserve_user_meter,
)


def test_anonymous_daily_limits_are_enforced(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_IP_HASH_SALT", "usage-test")
    database.initialize_database(tmp_path / "saveany.db")

    for _ in range(3):
        consume_anonymous_meter("203.0.113.10", MeterType.ANALYZE, reservation_id=None)

    with pytest.raises(MeterExceeded) as exc:
        consume_anonymous_meter("203.0.113.10", MeterType.ANALYZE, reservation_id=None)

    assert "访客解析次数已用完" in str(exc.value)
    summary = anonymous_usage_summary("203.0.113.10")
    assert summary["analyze"]["used"] == 3
    assert summary["analyze"]["remaining"] == 0


def test_free_user_summary_reservation_and_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("meter-free@example.com", "meter-password")

    usage = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="summary_one")
    assert usage["used"] == 1
    assert usage["remaining"] == 2

    refund = refund_reservation("summary_one")
    assert refund is not None

    status = entitlement_status(user)
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["summary"]["remaining"] == 3


def test_credit_pack_is_consumed_after_plan_allowance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-user@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_1")

    for index in range(3):
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=f"plan_{index}")

    usage = reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id="pack_1")

    assert usage["used"] == 3
    assert usage["remaining"] == 19
    status = entitlement_status(user)
    assert status["credit_packs"]["summary"]["remaining"] == 19


def test_split_credit_pack_refund_restores_each_pack(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("split-pack@example.com", "meter-password")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_1")
    add_credit_pack(user.id, pack_id="summary_small", source="mock", payment_reference="mock_2")

    for index in range(3):
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=f"plan_split_{index}")

    reserve_user_meter(user, MeterType.SUMMARY, 25, reservation_id="split_pack")
    mid_status = entitlement_status(user)
    assert mid_status["credit_packs"]["summary"]["remaining"] == 15

    refund_reservation("split_pack")
    status = entitlement_status(user)

    assert status["credit_packs"]["summary"]["remaining"] == 40


def test_transcription_minutes_round_trip_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("transcribe@example.com", "meter-password")

    usage = reserve_user_meter(
        user,
        MeterType.TRANSCRIPTION_MINUTES,
        12,
        reservation_id="transcription_12",
    )
    assert usage["used"] == 12
    assert usage["remaining"] == 18

    refund_reservation("transcription_12")
    status = entitlement_status(user)

    assert status["meters"]["transcription_minutes"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["remaining"] == 30
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_database.py::test_quota_schema_tables_are_created tests/test_usage_meter.py -q
```

Expected: fail because tables and `usage_meter.py` do not exist.

- [ ] **Step 4: Extend database schema**

Modify `SCHEMA` in `backend/app/services/database.py` by adding:

```sql
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
  stripe_payment_intent_id text,
  purchased_amount integer not null,
  remaining_amount integer not null,
  expires_at real not null,
  status text not null,
  created_at real not null,
  updated_at real not null
);

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
```

No extra migration function is needed for new tables because `executescript(SCHEMA)` creates them. Keep existing migration helpers for older tables.

- [ ] **Step 5: Create `usage_meter.py`**

Add `backend/app/services/usage_meter.py`:

```python
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from time import time

from app.services.app_config import load_config
from app.services.auth_service import User
from app.services.billing_service import get_membership
from app.services.database import connect, transaction
from app.services.plan_catalog import (
    CREDIT_PACK_CATALOG,
    MeterType,
    PeriodType,
    current_period_key,
    get_credit_pack,
    get_plan_limits,
)


class MeterExceeded(Exception):
    pass


@dataclass(frozen=True)
class MeterAllowance:
    meter_type: MeterType
    period_type: PeriodType
    period_key: str
    limit: int
    column: str
    plan_id: str


def active_plan_id(user: User) -> str:
    return "pro" if get_membership(user.id).active else "free"


def _anonymous_ip_hash(ip: str) -> str:
    raw = f"{load_config().ip_hash_salt}:{ip.strip() or 'unknown'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _column_for_meter(meter_type: MeterType) -> str:
    return {
        MeterType.ANALYZE: "analyze_count",
        MeterType.DOWNLOAD: "download_count",
        MeterType.SUMMARY: "summary_count",
        MeterType.TRANSCRIPTION_MINUTES: "transcription_minutes",
        MeterType.QUESTION: "question_count",
    }[meter_type]


def allowance_for_user(user: User, meter_type: MeterType) -> MeterAllowance:
    plan_id = active_plan_id(user)
    limits = get_plan_limits(plan_id)
    if meter_type == MeterType.ANALYZE and limits.analyze_daily_limit is not None:
        return MeterAllowance(meter_type, PeriodType.DAY, current_period_key(PeriodType.DAY), limits.analyze_daily_limit, "analyze_count", plan_id)
    if meter_type == MeterType.ANALYZE and limits.analyze_monthly_limit is not None:
        return MeterAllowance(meter_type, PeriodType.MONTH, current_period_key(PeriodType.MONTH), limits.analyze_monthly_limit, "analyze_count", plan_id)
    if meter_type == MeterType.DOWNLOAD and limits.download_daily_limit is not None:
        return MeterAllowance(meter_type, PeriodType.DAY, current_period_key(PeriodType.DAY), limits.download_daily_limit, "download_count", plan_id)
    if meter_type == MeterType.DOWNLOAD and limits.download_monthly_limit is not None:
        return MeterAllowance(meter_type, PeriodType.MONTH, current_period_key(PeriodType.MONTH), limits.download_monthly_limit, "download_count", plan_id)
    if meter_type == MeterType.SUMMARY and limits.summary_daily_limit is not None:
        return MeterAllowance(meter_type, PeriodType.DAY, current_period_key(PeriodType.DAY), limits.summary_daily_limit, "summary_count", plan_id)
    if meter_type == MeterType.SUMMARY and limits.summary_monthly_limit is not None:
        return MeterAllowance(meter_type, PeriodType.MONTH, current_period_key(PeriodType.MONTH), limits.summary_monthly_limit, "summary_count", plan_id)
    if meter_type == MeterType.TRANSCRIPTION_MINUTES:
        return MeterAllowance(meter_type, PeriodType.MONTH, current_period_key(PeriodType.MONTH), limits.transcription_monthly_minutes or 0, "transcription_minutes", plan_id)
    if meter_type == MeterType.QUESTION:
        return MeterAllowance(meter_type, PeriodType.MONTH, current_period_key(PeriodType.MONTH), limits.questions_per_summary or 0, "question_count", plan_id)
    raise MeterExceeded("当前套餐不支持该能力。")


def consume_anonymous_meter(ip: str, meter_type: MeterType, reservation_id: str | None = None) -> dict:
    if meter_type not in {MeterType.ANALYZE, MeterType.DOWNLOAD}:
        raise MeterExceeded("登录后才能使用该能力。")
    limits = get_plan_limits("anonymous")
    column = _column_for_meter(meter_type)
    limit = limits.analyze_daily_limit if meter_type == MeterType.ANALYZE else limits.download_daily_limit
    assert limit is not None
    usage_date = current_period_key(PeriodType.DAY)
    now = time()
    ip_hash = _anonymous_ip_hash(ip)
    with transaction() as conn:
        row = conn.execute(
            f"select {column} from anonymous_usage where ip_hash = ? and usage_date = ?",
            (ip_hash, usage_date),
        ).fetchone()
        used = int(row[column]) if row else 0
        if used >= limit:
            label = "解析" if meter_type == MeterType.ANALYZE else "下载"
            raise MeterExceeded(f"今天的访客{label}次数已用完，登录后可获得更多免费额度。")
        next_used = used + 1
        conn.execute(
            f"""
            insert into anonymous_usage (ip_hash, usage_date, {column}, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(ip_hash, usage_date)
            do update set {column} = excluded.{column}, updated_at = excluded.updated_at
            """,
            (ip_hash, usage_date, next_used, now, now),
        )
    return {"limit": limit, "used": next_used, "remaining": max(limit - next_used, 0)}


def anonymous_usage_summary(ip: str) -> dict:
    usage_date = current_period_key(PeriodType.DAY)
    ip_hash = _anonymous_ip_hash(ip)
    limits = get_plan_limits("anonymous")
    conn = connect()
    try:
        row = conn.execute(
            "select analyze_count, download_count from anonymous_usage where ip_hash = ? and usage_date = ?",
            (ip_hash, usage_date),
        ).fetchone()
    finally:
        conn.close()
    analyze_used = int(row["analyze_count"]) if row else 0
    download_used = int(row["download_count"]) if row else 0
    return {
        "analyze": {"limit": limits.analyze_daily_limit, "used": analyze_used, "remaining": max((limits.analyze_daily_limit or 0) - analyze_used, 0)},
        "download": {"limit": limits.download_daily_limit, "used": download_used, "remaining": max((limits.download_daily_limit or 0) - download_used, 0)},
    }


def reserve_user_meter(user: User, meter_type: MeterType, amount: int, *, reservation_id: str) -> dict:
    if amount <= 0:
        raise ValueError("amount must be positive")
    allowance = allowance_for_user(user, meter_type)
    now = time()
    with transaction() as conn:
        row = conn.execute(
            f"select {allowance.column} from usage_periods where user_id = ? and period_type = ? and period_key = ?",
            (user.id, allowance.period_type.value, allowance.period_key),
        ).fetchone()
        used = int(row[allowance.column]) if row else 0
        plan_remaining = max(allowance.limit - used, 0)
        consume_from_plan = min(plan_remaining, amount)
        consume_from_pack = amount - consume_from_plan
        pack_uses: list[tuple[str, int]] = []

        if consume_from_pack:
            pack_uses = _consume_credit_packs(conn, user.id, meter_type, consume_from_pack, now)

        credit_pack_id = ",".join(pack_id for pack_id, _ in pack_uses) or None

        next_used = used + consume_from_plan
        conn.execute(
            f"""
            insert into usage_periods
            (user_id, period_type, period_key, {allowance.column}, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(user_id, period_type, period_key)
            do update set {allowance.column} = excluded.{allowance.column}, updated_at = excluded.updated_at
            """,
            (user.id, allowance.period_type.value, allowance.period_key, next_used, now, now),
        )
        conn.execute(
            """
            insert into meter_reservations
            (reservation_id, user_id, meter_type, amount, plan_amount, pack_amount, period_type, period_key, credit_pack_id, status, created_at, committed_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'committed', ?, ?)
            """,
            (
                reservation_id,
                user.id,
                meter_type.value,
                amount,
                consume_from_plan,
                consume_from_pack,
                allowance.period_type.value,
                allowance.period_key,
                credit_pack_id,
                now,
                now,
            ),
        )
        for pack_id, used_amount in pack_uses:
            conn.execute(
                """
                insert into meter_reservation_pack_uses (reservation_id, credit_pack_id, amount)
                values (?, ?, ?)
                """,
                (reservation_id, pack_id, used_amount),
            )
    return _meter_status(user, meter_type)


def _consume_credit_packs(conn, user_id: str, meter_type: MeterType, amount: int, now: float) -> list[tuple[str, int]]:
    remaining = amount
    pack_uses: list[tuple[str, int]] = []
    rows = conn.execute(
        """
        select id, remaining_amount
        from credit_packs
        where user_id = ? and pack_type = ? and status = 'active'
          and expires_at > ? and remaining_amount > 0
        order by expires_at asc, created_at asc
        """,
        (user_id, meter_type.value, now),
    ).fetchall()
    for row in rows:
        if remaining <= 0:
            break
        take = min(int(row["remaining_amount"]), remaining)
        next_remaining = int(row["remaining_amount"]) - take
        status = "depleted" if next_remaining == 0 else "active"
        conn.execute(
            "update credit_packs set remaining_amount = ?, status = ?, updated_at = ? where id = ?",
            (next_remaining, status, now, row["id"]),
        )
        pack_uses.append((row["id"], take))
        remaining -= take
    if remaining > 0:
        label = "AI 总结次数" if meter_type == MeterType.SUMMARY else "语音转写分钟"
        raise MeterExceeded(f"{label}不足，请购买对应按量包后继续。")
    return pack_uses


def refund_reservation(reservation_id: str) -> dict | None:
    now = time()
    with transaction() as conn:
        reservation = conn.execute(
            "select * from meter_reservations where reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if reservation is None:
            return None
        if reservation["status"] == "refunded":
            return dict(reservation)
        plan_amount = int(reservation["plan_amount"] or 0)
        user_id = reservation["user_id"]
        meter_type = MeterType(reservation["meter_type"])
        column = _column_for_meter(meter_type)
        if reservation["period_type"] and reservation["period_key"]:
            row = conn.execute(
                f"select {column} from usage_periods where user_id = ? and period_type = ? and period_key = ?",
                (user_id, reservation["period_type"], reservation["period_key"]),
            ).fetchone()
            if row is not None:
                next_used = max(int(row[column]) - plan_amount, 0)
                conn.execute(
                    f"update usage_periods set {column} = ?, updated_at = ? where user_id = ? and period_type = ? and period_key = ?",
                    (next_used, now, user_id, reservation["period_type"], reservation["period_key"]),
                )
        pack_rows = conn.execute(
            """
            select credit_pack_id, amount
            from meter_reservation_pack_uses
            where reservation_id = ?
            """,
            (reservation_id,),
        ).fetchall()
        for pack_row in pack_rows:
            conn.execute(
                """
                update credit_packs
                set remaining_amount = remaining_amount + ?, status = 'active', updated_at = ?
                where id = ?
                """,
                (int(pack_row["amount"]), now, pack_row["credit_pack_id"]),
            )
        conn.execute(
            "update meter_reservations set status = 'refunded', refunded_at = ? where reservation_id = ?",
            (now, reservation_id),
        )
    return {"reservation_id": reservation_id, "user_id": user_id, "refunded": True}


def add_credit_pack(user_id: str, *, pack_id: str, source: str, payment_reference: str, stripe_price_id: str | None = None) -> dict:
    pack = get_credit_pack(pack_id)
    now = time()
    expires_at = now + pack.valid_days * 86400
    credit_pack_id = f"pack_{secrets.token_urlsafe(10)}"
    with transaction() as conn:
        conn.execute(
            """
            insert into credit_packs
            (id, user_id, pack_id, pack_type, source, stripe_price_id, stripe_payment_intent_id,
             purchased_amount, remaining_amount, expires_at, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                credit_pack_id,
                user_id,
                pack.id,
                pack.meter_type.value,
                source,
                stripe_price_id,
                payment_reference,
                pack.amount,
                pack.amount,
                expires_at,
                now,
                now,
            ),
        )
    return {"id": credit_pack_id, "pack_id": pack.id, "remaining_amount": pack.amount, "expires_at": expires_at}


def _meter_status(user: User, meter_type: MeterType) -> dict:
    allowance = allowance_for_user(user, meter_type)
    conn = connect()
    try:
        row = conn.execute(
            f"select {allowance.column} from usage_periods where user_id = ? and period_type = ? and period_key = ?",
            (user.id, allowance.period_type.value, allowance.period_key),
        ).fetchone()
        pack_remaining = conn.execute(
            """
            select coalesce(sum(remaining_amount), 0) as remaining
            from credit_packs
            where user_id = ? and pack_type = ? and status = 'active'
              and expires_at > ?
            """,
            (user.id, meter_type.value, time()),
        ).fetchone()
    finally:
        conn.close()
    used = int(row[allowance.column]) if row else 0
    pack_value = int(pack_remaining["remaining"]) if pack_remaining else 0
    return {
        "meter": meter_type.value,
        "period_type": allowance.period_type.value,
        "period_key": allowance.period_key,
        "limit": allowance.limit,
        "used": used,
        "remaining": max(allowance.limit - used, 0) + pack_value,
        "plan_remaining": max(allowance.limit - used, 0),
        "pack_remaining": pack_value,
    }


def entitlement_status(user: User) -> dict:
    plan_id = active_plan_id(user)
    meters = {
        MeterType.ANALYZE.value: _meter_status(user, MeterType.ANALYZE),
        MeterType.DOWNLOAD.value: _meter_status(user, MeterType.DOWNLOAD),
        MeterType.SUMMARY.value: _meter_status(user, MeterType.SUMMARY),
        MeterType.TRANSCRIPTION_MINUTES.value: _meter_status(user, MeterType.TRANSCRIPTION_MINUTES),
    }
    return {
        "plan": plan_id,
        "meters": meters,
        "credit_packs": {
            "summary": {"remaining": meters["summary"]["pack_remaining"]},
            "transcription_minutes": {"remaining": meters["transcription_minutes"]["pack_remaining"]},
        },
    }
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_database.py::test_quota_schema_tables_are_created tests/test_usage_meter.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/database.py backend/app/services/usage_meter.py backend/tests/test_database.py backend/tests/test_usage_meter.py
git commit -m "feat: 添加用量额度底座"
```

---

### Task 3: Entitlements Compatibility and Status API

**Files:**
- Modify: `backend/app/services/entitlements.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/auth_routes.py`
- Create: `backend/app/entitlement_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_entitlements.py`
- Test: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Add failing compatibility tests**

Append to `backend/tests/test_entitlements.py`:

```python
def test_entitlement_status_api_shape_for_free_user(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("status@example.com", "status-password")

    usage = consume_summary_quota(user)
    status = get_usage_summary(user).as_dict()

    assert usage.used_today == 1
    assert status["daily_free_limit"] == 3
    assert status["used_today"] == 1
    assert status["remaining_today"] == 2
    assert status["membership_active"] is False
    assert "meters" in status
    assert status["meters"]["summary"]["remaining"] == 2
```

Append to `backend/tests/test_auth_api.py`:

```python
def test_me_includes_entitlement_status(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "entitlements@example.com", "password": "correct horse battery staple"},
    )

    response = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["plan"] == "free"
    assert response.json()["meters"]["summary"]["limit"] == 3
    assert response.json()["meters"]["transcription_minutes"]["limit"] == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_entitlements.py tests/test_auth_api.py::test_me_includes_entitlement_status -q
```

Expected: fail because `get_usage_summary()` still uses `usage_daily` and `/api/entitlements/status` does not exist.

- [ ] **Step 3: Update entitlements wrapper**

Replace `backend/app/services/entitlements.py` with a compatibility wrapper:

```python
from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.services.auth_service import User, get_user_by_id
from app.services.plan_catalog import MeterType
from app.services.usage_meter import (
    MeterExceeded,
    entitlement_status,
    refund_reservation,
    reserve_user_meter,
)


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class UsageSummary:
    daily_free_limit: int
    used_today: int
    remaining_today: int
    membership_active: bool
    meters: dict | None = None
    credit_packs: dict | None = None

    def as_dict(self) -> dict:
        payload = {
            "daily_free_limit": self.daily_free_limit,
            "used_today": self.used_today,
            "remaining_today": self.remaining_today,
            "membership_active": self.membership_active,
        }
        if self.meters is not None:
            payload["meters"] = self.meters
        if self.credit_packs is not None:
            payload["credit_packs"] = self.credit_packs
        return payload


def get_usage_summary(user: User) -> UsageSummary:
    status = entitlement_status(user)
    summary = status["meters"]["summary"]
    membership_active = status["plan"] == "pro"
    limit = summary["limit"]
    used = summary["used"]
    remaining = summary["remaining"]
    if membership_active:
        used_today = 0
        remaining_today = limit
    else:
        used_today = used
        remaining_today = remaining
    return UsageSummary(
        daily_free_limit=limit,
        used_today=used_today,
        remaining_today=remaining_today,
        membership_active=membership_active,
        meters=status["meters"],
        credit_packs=status["credit_packs"],
    )


def reserve_summary_quota(user: User, reservation_id: str) -> UsageSummary:
    try:
        reserve_user_meter(user, MeterType.SUMMARY, 1, reservation_id=reservation_id)
    except MeterExceeded as exc:
        raise QuotaExceeded(str(exc)) from exc
    return get_usage_summary(user)


def consume_summary_quota(user: User) -> UsageSummary:
    return reserve_summary_quota(user, f"manual_{secrets.token_urlsafe(10)}")


def refund_summary_quota_reservation(reservation_id: str) -> UsageSummary | None:
    refund = refund_reservation(reservation_id)
    if refund is None:
        return None
    user = get_user_by_id(refund["user_id"])
    return get_usage_summary(user) if user else None
```

Add `get_user_by_id()` to `backend/app/services/auth_service.py`:

```python
def get_user_by_id(user_id: str) -> User | None:
    conn = connect()
    try:
        row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return User.from_row(row) if row else None
```

- [ ] **Step 4: Add entitlements route**

Create `backend/app/entitlement_routes.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth_routes import current_user
from app.services.auth_service import User
from app.services.usage_meter import entitlement_status


router = APIRouter(prefix="/api/entitlements", tags=["entitlements"])


@router.get("/status")
def status(user: User = Depends(current_user)) -> dict:
    return entitlement_status(user)
```

Modify `backend/app/main.py` imports and router registration:

```python
from app.entitlement_routes import router as entitlement_router
```

and near other routers:

```python
app.include_router(entitlement_router)
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_entitlements.py tests/test_auth_api.py -q
```

Expected: pass with the new entitlement status route and existing auth API compatibility.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/entitlements.py backend/app/services/auth_service.py backend/app/entitlement_routes.py backend/app/main.py backend/tests/test_entitlements.py backend/tests/test_auth_api.py
git commit -m "feat: 暴露个人额度状态"
```

---

### Task 4: Analyze and Download Quotas with Analysis Tokens

**Files:**
- Create: `backend/app/services/analysis_store.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_api.py`:

```python
def test_analyze_returns_analysis_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"})

    assert response.status_code == 200
    assert response.json()["analysis_token"].startswith("analysis_")
    assert response.json()["duration"] == 618


def test_anonymous_analyze_limit_blocks_fourth_request(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    for _ in range(3):
        assert client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"}).status_code == 200

    blocked = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"})

    assert blocked.status_code == 429
    assert "访客解析次数已用完" in blocked.json()["detail"]


def test_download_uses_analysis_token_and_anonymous_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    analyzed = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"}).json()
    first = client.post(
        "/api/download",
        json={
            "url": analyzed["webpage_url"],
            "analysis_token": analyzed["analysis_token"],
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )
    second = client.post(
        "/api/download",
        json={
            "url": analyzed["webpage_url"],
            "analysis_token": analyzed["analysis_token"],
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert "访客下载次数已用完" in second.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_api.py::test_analyze_returns_analysis_token tests/test_api.py::test_anonymous_analyze_limit_blocks_fourth_request tests/test_api.py::test_download_uses_analysis_token_and_anonymous_limit -q
```

Expected: fail because analyze response has no token and quota checks are not applied.

- [ ] **Step 3: Create analysis store**

Add `backend/app/services/analysis_store.py`:

```python
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from time import time


ANALYSIS_TOKEN_TTL_SECONDS = 30 * 60


@dataclass
class AnalysisSnapshot:
    token: str
    url: str
    result: dict
    created_at: float


class AnalysisStore:
    def __init__(self) -> None:
        self._items: dict[str, AnalysisSnapshot] = {}
        self._lock = threading.Lock()

    def create(self, url: str, result: dict) -> str:
        token = f"analysis_{secrets.token_urlsafe(18)}"
        now = time()
        with self._lock:
            self._prune_locked(now)
            self._items[token] = AnalysisSnapshot(token=token, url=url, result=dict(result), created_at=now)
        return token

    def get(self, token: str | None) -> AnalysisSnapshot | None:
        if not token:
            return None
        now = time()
        with self._lock:
            self._prune_locked(now)
            return self._items.get(token)

    def _prune_locked(self, now: float) -> None:
        expired = [token for token, item in self._items.items() if now - item.created_at > ANALYSIS_TOKEN_TTL_SECONDS]
        for token in expired:
            self._items.pop(token, None)


analysis_store = AnalysisStore()
```

- [ ] **Step 4: Modify request models and helpers in `main.py`**

Update imports:

```python
from fastapi import Depends
from app.auth_routes import optional_user
from app.services.analysis_store import analysis_store
from app.services.auth_service import User
from app.services.plan_catalog import MeterType
from app.services.usage_meter import MeterExceeded, consume_anonymous_meter, reserve_user_meter
```

Add helper:

```python
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"
```

Extend `DownloadRequest`:

```python
class DownloadRequest(BaseModel):
    url: str
    analysis_token: str | None = None
    entry_ids: list[str] = Field(default_factory=list)
    format_id: str = DEFAULT_FORMAT
    subtitle_langs: list[str] = Field(default_factory=list)
    write_auto_subs: bool = False
    prefer_srt: bool = True
```

- [ ] **Step 5: Apply analyze quota and return token**

Change analyze signature:

```python
@app.post("/api/analyze")
async def analyze(
    request: Request,
    url: str = Form(...),
    user: User | None = Depends(optional_user),
) -> dict:
```

At the start after empty URL validation:

```python
    try:
        if user:
            reserve_user_meter(user, MeterType.ANALYZE, 1, reservation_id=f"analyze_{secrets.token_urlsafe(10)}")
        else:
            consume_anonymous_meter(_client_ip(request), MeterType.ANALYZE)
    except MeterExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
```

Before returning a successful result:

```python
        result = proxy_media_assets(result)
        result["analysis_token"] = analysis_store.create(url, result)
        return result
```

Also add the token to demo results using the same path after `demo_result` is produced.

- [ ] **Step 6: Apply download quota**

Change `create_download` signature:

```python
@app.post("/api/download")
def create_download(
    payload: DownloadRequest,
    request: Request,
    user: User | None = Depends(optional_user),
) -> dict[str, str]:
```

At the top:

```python
    snapshot = analysis_store.get(payload.analysis_token)
    result = snapshot.result if snapshot and snapshot.url == payload.url else None
    if result is None:
        try:
            demo_result = demo_analyze_result(payload.url)
            result = demo_result if demo_result is not None else service.analyze(payload.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=friendly_error_message(exc)) from exc
    entry_count = len(payload.entry_ids) if payload.entry_ids else max(len(result.get("entries") or []), 1)
    duration = float(result.get("duration") or 0)
    try:
        if user:
            reserve_user_meter(user, MeterType.DOWNLOAD, entry_count, reservation_id=f"download_{secrets.token_urlsafe(10)}")
        else:
            for _ in range(entry_count):
                consume_anonymous_meter(_client_ip(request), MeterType.DOWNLOAD)
    except MeterExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
```

Duration enforcement will be completed in Task 5 after `usage_meter` exposes max-duration helpers. For now this task establishes token and count enforcement.

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_api.py::test_analyze_returns_analysis_token tests/test_api.py::test_anonymous_analyze_limit_blocks_fourth_request tests/test_api.py::test_download_uses_analysis_token_and_anonymous_limit -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/analysis_store.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat: 限制访客解析下载额度"
```

---

### Task 5: Duration Limits and Summary Ownership

**Files:**
- Modify: `backend/app/services/usage_meter.py`
- Modify: `backend/app/services/summary_store.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/summary_routes.py`
- Test: `backend/tests/test_api.py`
- Test: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Add failing tests for duration and ownership**

Append to `backend/tests/test_summary_api.py`:

```python
def test_summary_task_records_owner_and_question_requires_login(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/owned-video", "title": "Demo", "language": "zh-CN", "duration": 120},
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    client.post("/api/auth/logout")

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "这一段讲了什么？", "language": "zh-CN"},
    )

    assert answer.status_code == 401


def test_free_user_summary_duration_limit(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/long-free-video", "title": "Demo", "language": "zh-CN", "duration": 31 * 60},
    )

    assert response.status_code == 402
    assert "30 分钟" in response.json()["detail"]


def test_free_user_question_limit(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)
    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/questions", "title": "Demo", "language": "zh-CN", "duration": 120},
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    for index in range(3):
        assert client.post(
            f"/api/summaries/{summary_id}/questions",
            json={"question": f"问题 {index}", "language": "zh-CN"},
        ).status_code == 200

    blocked = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "第四个问题", "language": "zh-CN"},
    )

    assert blocked.status_code == 402
    assert "追问次数" in blocked.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py::test_summary_task_records_owner_and_question_requires_login tests/test_summary_api.py::test_free_user_summary_duration_limit tests/test_summary_api.py::test_free_user_question_limit -q
```

Expected: fail because `duration` is not in `SummaryRequest`, summary owner is not recorded, and questions are public.

- [ ] **Step 3: Add max duration helpers**

Append to `usage_meter.py`:

```python
def max_duration_for_user(user: User | None, *, capability: str) -> int | None:
    plan_id = active_plan_id(user) if user else "anonymous"
    limits = get_plan_limits(plan_id)
    if capability == "download":
        return limits.download_max_duration_seconds
    if capability == "summary":
        return limits.summary_max_duration_seconds
    raise ValueError(f"Unknown duration capability: {capability}")


def assert_duration_allowed(user: User | None, *, capability: str, duration_seconds: float | int | None) -> None:
    max_seconds = max_duration_for_user(user, capability=capability)
    if not max_seconds or not duration_seconds:
        return
    if float(duration_seconds) <= max_seconds:
        return
    minutes = max_seconds // 60
    if capability == "download":
        raise MeterExceeded(f"当前套餐单个下载视频最长支持 {minutes} 分钟。")
    raise MeterExceeded(f"当前套餐单个 AI 总结视频最长支持 {minutes} 分钟。")
```

- [ ] **Step 4: Store summary owner**

Modify `SummarySnapshot` in `backend/app/services/summary_store.py`:

```python
    owner_user_id: str | None = None
```

In `from_dict()`:

```python
            owner_user_id=data.get("owner_user_id") if isinstance(data.get("owner_user_id"), str) else None,
```

In `create_task()` signature:

```python
        owner_user_id: str | None = None,
```

In constructed `SummarySnapshot`:

```python
            owner_user_id=owner_user_id,
```

In `_serialize()`:

```python
            "owner_user_id": task.owner_user_id,
```

Do not expose `owner_user_id` in `as_dict()`.

- [ ] **Step 5: Extend summary request and enforce limits**

Modify `SummaryRequest` in `summary_routes.py`:

```python
class SummaryRequest(BaseModel):
    url: str
    title: str | None = None
    language: str = "zh-CN"
    force: bool = False
    duration: float | None = None
```

Import:

```python
from app.services.usage_meter import MeterExceeded, assert_duration_allowed
from app.services.plan_catalog import MeterType
from app.services.usage_meter import reserve_summary_question
```

Before reserving summary quota:

```python
    try:
        assert_duration_allowed(user, capability="summary", duration_seconds=payload.duration)
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
```

When creating task:

```python
            owner_user_id=user.id,
            quota_user_id=user.id,
```

Remove the old `quota_user_id = None if usage.membership_active else user.id` behavior in `create_summary()`. Every created summary task should carry `quota_user_id=user.id` because both free and Pro users now have metered summary allowances that must be refunded on task failure or restart interruption.

- [ ] **Step 6: Require login and enforce question limits**

Change question route signature:

```python
@router.post("/{summary_id}/questions")
def ask_summary_question(
    summary_id: str,
    payload: SummaryQuestionRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
```

After loading task:

```python
    if task.owner_user_id and task.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问这个 AI 总结。")
    try:
        reserve_summary_question(user, summary_id)
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=f"这个总结的追问次数已用完，请升级 Pro 后继续。") from exc
```

Add a dedicated per-summary helper in `usage_meter.py`:

```python
def reserve_summary_question(user: User, summary_id: str) -> dict:
    limits = get_plan_limits(active_plan_id(user))
    limit = limits.questions_per_summary or 0
    now = time()
    with transaction() as conn:
        row = conn.execute(
            "select question_count from summary_questions where summary_id = ? and user_id = ?",
            (summary_id, user.id),
        ).fetchone()
        used = int(row["question_count"]) if row else 0
        if used >= limit:
            raise MeterExceeded("这个总结的追问次数已用完，请升级 Pro 后继续。")
        next_used = used + 1
        conn.execute(
            """
            insert into summary_questions (summary_id, user_id, question_count, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(summary_id, user_id)
            do update set question_count = excluded.question_count, updated_at = excluded.updated_at
            """,
            (summary_id, user.id, next_used, now, now),
        )
    return {"limit": limit, "used": next_used, "remaining": max(limit - next_used, 0)}
```

Use `reserve_summary_question(user, summary_id)` in the route instead of `reserve_user_meter(... QUESTION ...)`. Do not route questions through `usage_periods`; question limits are per summary, not monthly.

- [ ] **Step 7: Enforce download duration in `main.py`**

Import `assert_duration_allowed` and add after resolving analyze result:

```python
    try:
        assert_duration_allowed(user, capability="download", duration_seconds=duration)
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_api.py tests/test_summary_api.py -q
```

Expected: pass after updating existing test payloads only where duration is intentionally needed.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/usage_meter.py backend/app/services/summary_store.py backend/app/main.py backend/app/summary_routes.py backend/tests/test_api.py backend/tests/test_summary_api.py
git commit -m "feat: 校验视频时长和追问额度"
```

---

### Task 6: Transcription Minute Reservations

**Files:**
- Modify: `backend/app/services/summary_service.py`
- Modify: `backend/app/summary_routes.py`
- Test: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Add failing transcription reservation test**

Append to `backend/tests/test_summary_api.py`:

```python
class SpeechToTextSummaryService(FakeSummaryService):
    def generate_summary(self, *, url, title, language, output_dir, progress_hook=None, seed_result=None):
        if progress_hook:
            progress_hook(
                "speech_to_text",
                30,
                "Extracting audio for speech-to-text",
                transcription_seconds=125,
            )
        return super().generate_summary(
            url=url,
            title=title,
            language=language,
            output_dir=output_dir,
            progress_hook=progress_hook,
            seed_result=seed_result,
        )


def test_speech_to_text_reserves_transcription_minutes(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", SpeechToTextSummaryService())
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/no-subtitles", "title": "Demo", "language": "zh-CN", "duration": 125},
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    usage = client.get("/api/entitlements/status").json()

    assert usage["meters"]["transcription_minutes"]["used"] == 3
    assert usage["meters"]["transcription_minutes"]["remaining"] == 27
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py::test_speech_to_text_reserves_transcription_minutes -q
```

Expected: fail because transcription minutes are not reserved.

- [ ] **Step 3: Emit transcription seconds from summary service**

In `SummaryService.generate_summary()`, where audio extraction path begins, add a progress hook call after `audio_path` is known and before full transcription:

```python
            transcription_seconds = estimate_audio_duration_seconds(audio_path)
            if progress_hook:
                emit_summary_progress(
                    progress_hook,
                    "speech_to_text",
                    46,
                    "Speech-to-text minutes required",
                    transcription_seconds=transcription_seconds,
                )
```

Add helper near `create_audio_preview_clip()`:

```python
def estimate_audio_duration_seconds(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        return max(float(result.stdout.strip() or "0"), 1.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1.0
```

- [ ] **Step 4: Reserve minutes in route progress hook**

Change `_run_summary()` in `summary_routes.py` so it receives the metered user id instead of a boolean:

```python
def _run_summary(
    summary_id: str,
    payload: SummaryRequest,
    seed_result: dict | None = None,
    quota_user_id: str | None = None,
) -> None:
```

When starting the worker in `create_summary()`, pass the user id:

```python
args=(task.id, payload, seed_result, user.id)
```

Inside `_run_summary()`, add a mutable state:

```python
    transcription_reservation_id = {"value": None}
```

Inside `progress_hook`, before `summary_store.update_task()`:

```python
        transcription_seconds = changes.pop("transcription_seconds", None)
        if transcription_seconds and quota_user_id and transcription_reservation_id["value"] is None:
            minutes = max(1, int((float(transcription_seconds) + 59) // 60))
            reservation_id = f"{summary_id}_transcription"
            reserve_user_meter_by_id(quota_user_id, MeterType.TRANSCRIPTION_MINUTES, minutes, reservation_id=reservation_id)
            transcription_reservation_id["value"] = reservation_id
```

Add `reserve_user_meter_by_id()` to `usage_meter.py`:

```python
def reserve_user_meter_by_id(user_id: str, meter_type: MeterType, amount: int, *, reservation_id: str) -> dict:
    from app.services.auth_service import get_user_by_id

    user = get_user_by_id(user_id)
    if user is None:
        raise MeterExceeded("用户不存在，无法扣减额度。")
    return reserve_user_meter(user, meter_type, amount, reservation_id=reservation_id)
```

- [ ] **Step 5: Refund transcription reservation on failure**

In `_run_summary()` exception handler:

```python
            if transcription_reservation_id["value"]:
                refund_reservation(transcription_reservation_id["value"])
```

Import `refund_reservation`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py::test_speech_to_text_reserves_transcription_minutes tests/test_usage_meter.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/summary_service.py backend/app/summary_routes.py backend/app/services/usage_meter.py backend/app/services/auth_service.py backend/tests/test_summary_api.py
git commit -m "feat: 统计语音转写分钟"
```

---

### Task 7: Stripe and Mock Credit Pack Purchases

**Files:**
- Modify: `backend/app/services/billing_service.py`
- Modify: `backend/app/billing_routes.py`
- Modify: `backend/config/stripe.env.example`
- Modify: `docs/11-membership-stripe-setup.md`
- Test: `backend/tests/test_billing_mock.py`
- Test: `backend/tests/test_billing_stripe_webhook.py`

- [ ] **Step 1: Add failing mock and Stripe tests**

Append to `backend/tests/test_billing_mock.py`:

```python
def test_mock_credit_pack_purchase_grants_balance(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("BILLING_MODE", "mock")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)
    _login(client)

    response = client.post("/api/billing/mock/credit-pack/summary_small")
    status = client.get("/api/entitlements/status")

    assert response.status_code == 200
    assert response.json()["credit_pack"]["pack_id"] == "summary_small"
    assert status.json()["credit_packs"]["summary"]["remaining"] == 20
```

Append to `backend/tests/test_billing_stripe_webhook.py`:

```python
def test_stripe_checkout_payment_pack_grants_credit(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SUMMARY_SMALL_PACK_PRICE_ID", "price_summary_small")
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("pack-webhook@example.com", "stripe-password")
    client = TestClient(app)
    event = {
        "id": "evt_pack_completed",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_pack",
                "mode": "payment",
                "payment_status": "paid",
                "payment_intent": "pi_pack",
                "client_reference_id": user.id,
                "metadata": {"saveany_user_id": user.id, "purchase_type": "credit_pack", "pack_id": "summary_small"},
                "line_items": {"data": [{"price": {"id": "price_summary_small"}}]},
            }
        },
    }

    response = _post_event(client, event)

    assert response.status_code == 200
    with database.connect(tmp_path / "saveany.db") as conn:
        pack = conn.execute("select * from credit_packs where user_id = ?", (user.id,)).fetchone()
    assert pack["pack_id"] == "summary_small"
    assert pack["remaining_amount"] == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_billing_mock.py::test_mock_credit_pack_purchase_grants_balance tests/test_billing_stripe_webhook.py::test_stripe_checkout_payment_pack_grants_credit -q
```

Expected: fail because routes and webhook grant logic do not exist.

- [ ] **Step 3: Add billing service helpers**

Append to `billing_service.py`:

```python
from app.services.app_config import load_config
from app.services.plan_catalog import CREDIT_PACK_CATALOG, get_credit_pack
from app.services.usage_meter import add_credit_pack


def grant_credit_pack(user_id: str, pack_id: str, *, source: str, payment_reference: str, stripe_price_id: str | None = None) -> dict:
    return add_credit_pack(
        user_id,
        pack_id=pack_id,
        source=source,
        payment_reference=payment_reference,
        stripe_price_id=stripe_price_id,
    )


def credit_pack_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    config = load_config()
    for pack_id, pack in CREDIT_PACK_CATALOG.items():
        if getattr(config, pack.stripe_config_field) == price_id:
            return pack_id
    return None
```

- [ ] **Step 4: Support checkout purchase type**

In `billing_routes.py`, extend `CheckoutRequest`:

```python
class CheckoutRequest(BaseModel):
    return_url: str | None = None
    purchase_type: str = "subscription"
    pack_id: str | None = None
```

In `billing_checkout()`, before existing subscription logic:

```python
    purchase_type = payload.purchase_type if payload else "subscription"
    if purchase_type == "credit_pack":
        if not payload or not payload.pack_id:
            raise HTTPException(status_code=400, detail="缺少按量包类型")
        pack = get_credit_pack(payload.pack_id)
        if config.billing_mode == "mock":
            credit_pack = grant_credit_pack(user.id, pack.id, source="mock", payment_reference=f"mock_{pack.id}")
            return {"mode": "mock", "credit_pack": credit_pack, "url": "/#pricing"}
        price_id = getattr(config, pack.stripe_config_field)
        if not config.stripe_secret_key or not price_id:
            raise HTTPException(status_code=503, detail="Stripe 按量包支付尚未配置")
        return_base_url = _checkout_return_base_url(config.public_app_url, request, payload.return_url)
        stripe.api_key = config.stripe_secret_key
        customer_id = ensure_stripe_customer_id(
            user,
            lambda: stripe.Customer.create(email=user.email, metadata={"saveany_user_id": user.id}).id,
        )
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{return_base_url}/#pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_base_url}/#pricing?checkout=cancel",
            client_reference_id=user.id,
            metadata={"saveany_user_id": user.id, "purchase_type": "credit_pack", "pack_id": pack.id},
        )
        record_stripe_checkout_attempt(user.id, session.id, session.url, return_base_url)
        return {"mode": "stripe", "url": session.url, "session_id": session.id}
```

Import `get_credit_pack` and `grant_credit_pack`.

- [ ] **Step 5: Add mock route**

Add to `billing_routes.py`:

```python
@router.post("/mock/credit-pack/{pack_id}")
def mock_credit_pack(pack_id: str, user: User = Depends(current_user)) -> dict:
    if load_config().billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock billing is disabled")
    pack = get_credit_pack(pack_id)
    return {"credit_pack": grant_credit_pack(user.id, pack.id, source="mock", payment_reference=f"mock_{pack.id}")}
```

- [ ] **Step 6: Grant pack from webhook**

In `stripe_webhook()` inside `checkout.session.completed` branch, after `upsert_stripe_checkout_session(checkout_session)`:

```python
            metadata = checkout_session.get("metadata") or {}
            if checkout_session.get("mode") == "payment" and metadata.get("purchase_type") == "credit_pack":
                pack_id = metadata.get("pack_id")
                user_id = metadata.get("saveany_user_id") or checkout_session.get("client_reference_id")
                if not pack_id or not user_id:
                    raise ValueError("Stripe credit pack checkout is missing metadata")
                price_id = None
                line_items = ((checkout_session.get("line_items") or {}).get("data") or [])
                if line_items:
                    price_id = ((line_items[0].get("price") or {}).get("id"))
                configured_pack_id = credit_pack_from_price_id(price_id)
                if configured_pack_id and configured_pack_id != pack_id:
                    raise ValueError("Stripe credit pack price does not match pack metadata")
                grant_credit_pack(
                    user_id,
                    pack_id,
                    source="stripe",
                    payment_reference=checkout_session.get("payment_intent") or checkout_session["id"],
                    stripe_price_id=price_id,
                )
```

Import `credit_pack_from_price_id`.

- [ ] **Step 7: Update docs**

In `docs/11-membership-stripe-setup.md`, replace the single Price instruction with:

```markdown
2. 在 Stripe Dashboard 创建以下 Prices：
   - `SaveAny Pro`：月度 recurring Price，`¥19`，currency 为 `cny`。
   - `总结小包`：one-time Price，`¥6`，currency 为 `cny`。
   - `总结大包`：one-time Price，`¥19`，currency 为 `cny`。
   - `转写小包`：one-time Price，`¥8`，currency 为 `cny`。
   - `转写大包`：one-time Price，`¥29`，currency 为 `cny`。
```

Update env block with the five Price IDs.

- [ ] **Step 8: Run focused tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_billing_mock.py tests/test_billing_stripe_webhook.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/billing_service.py backend/app/billing_routes.py backend/config/stripe.env.example docs/11-membership-stripe-setup.md backend/tests/test_billing_mock.py backend/tests/test_billing_stripe_webhook.py
git commit -m "feat: 支持购买个人按量包"
```

---

### Task 8: Frontend API and Session State

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/services/authSession.js`
- Test: `frontend/tests/summary-api.test.js`
- Test: `frontend/tests/auth-session.test.js`

- [ ] **Step 1: Add failing frontend API tests**

Append to `frontend/tests/summary-api.test.js`:

```javascript
test("getEntitlementStatus calls quota status endpoint with credentials", async () => {
  const calls = [];
  global.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({ plan: "free", meters: {} });
  };

  const result = await api.getEntitlementStatus();

  assert.equal(result.plan, "free");
  assert.equal(calls[0].url, "/api/entitlements/status");
  assert.equal(calls[0].options.credentials, "include");
});

test("createDownloadTask sends analysis token", async () => {
  let body = null;
  global.fetch = async (_url, options = {}) => {
    body = JSON.parse(options.body);
    return jsonResponse({ task_id: "task_1" });
  };

  await api.createDownloadTask({
    url: "https://example.com/video",
    analysis_token: "analysis_123",
    entry_ids: [],
    format_id: "best",
    subtitle_langs: [],
    write_auto_subs: false,
    prefer_srt: true
  });

  assert.equal(body.analysis_token, "analysis_123");
});
```

Append to `frontend/tests/auth-session.test.js`:

```javascript
test("quotaMeterText renders plan and pack remaining values", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: {
      daily_free_limit: 3,
      used_today: 1,
      remaining_today: 2,
      membership_active: false,
      meters: {
        summary: { limit: 3, used: 1, remaining: 2, plan_remaining: 2, pack_remaining: 0 },
        transcription_minutes: { limit: 30, used: 5, remaining: 25, plan_remaining: 25, pack_remaining: 0 }
      }
    }
  });

  assert.equal(quotaMeterText(state, "summary"), "AI 总结还剩 2 次");
  assert.equal(quotaMeterText(state, "transcription_minutes"), "语音转写还剩 25 分钟");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- summary-api.test.js auth-session.test.js
```

Expected: fail because new exports do not exist.

- [ ] **Step 3: Update API service**

Add to `frontend/src/services/api.js`:

```javascript
export async function getEntitlementStatus() {
  const response = await fetch("/api/entitlements/status", { credentials: "include" });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}
```

No special code is needed for `analysis_token` because `createDownloadTask(payload)` already stringifies the payload. Keep the test to prevent future stripping.

- [ ] **Step 4: Update auth session helpers**

Modify `frontend/src/services/authSession.js` default `usage` to include empty `meters` and `credit_packs`:

```javascript
const DEFAULT_USAGE = {
  daily_free_limit: 3,
  used_today: 0,
  remaining_today: 0,
  membership_active: false,
  meters: {},
  credit_packs: {}
};
```

Use it in `authInitialState`, `updateAuthState`, and `clearAuthState`.

Add:

```javascript
export function quotaMeterText(state, meter) {
  const value = state.usage?.meters?.[meter];
  if (!value) return "";
  if (meter === "summary") return `AI 总结还剩 ${Math.max(value.remaining || 0, 0)} 次`;
  if (meter === "transcription_minutes") return `语音转写还剩 ${Math.max(value.remaining || 0, 0)} 分钟`;
  if (meter === "analyze") return `解析还剩 ${Math.max(value.remaining || 0, 0)} 次`;
  if (meter === "download") return `下载还剩 ${Math.max(value.remaining || 0, 0)} 次`;
  return "";
}

export function quotaMeterRatio(state, meter) {
  const value = state.usage?.meters?.[meter];
  if (!value || !value.limit) return 0;
  return Math.max(0, Math.min(100, Math.round(((value.limit - value.used) / value.limit) * 100)));
}
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd frontend
npm test -- summary-api.test.js auth-session.test.js
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/authSession.js frontend/tests/summary-api.test.js frontend/tests/auth-session.test.js
git commit -m "feat: 前端读取个人额度状态"
```

---

### Task 9: Frontend Pricing Page and Quota UX

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/assets/main.css`
- Test: `frontend/tests/summary-auto-layout.test.js`
- Test: `frontend/tests/chinese-ui-copy.test.js`

- [ ] **Step 1: Add failing layout and copy tests**

Modify `frontend/tests/summary-auto-layout.test.js` pricing test:

```javascript
test("pricing page shows personal free and pro plans plus credit packs", () => {
  assert.match(appSource, /const pricingPlans = \[/);
  assert.match(appSource, /name:\s*"免费版"/);
  assert.match(appSource, /name:\s*"Pro 个人版"/);
  assert.doesNotMatch(appSource, /name:\s*"团队版"/);
  assert.doesNotMatch(appSource, /¥99/);
  assert.match(appSource, /const creditPacks = \[/);
  assert.match(appSource, /总结小包/);
  assert.match(appSource, /转写大包/);
  assert.match(mainCss, /\.pricing-grid\s*\{[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
});
```

Modify `frontend/tests/chinese-ui-copy.test.js` membership copy expectations to include:

```javascript
[
  "Pro 个人版",
  "¥19",
  "120 次 AI 总结",
  "600 分钟语音转写",
  "总结小包",
  "转写小包",
  "今天的访客解析次数已用完",
  "语音转写还剩"
].forEach((text) => assert.match(appSource, new RegExp(text)));

assert.doesNotMatch(appSource, /团队版|团队协作|¥99/);
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- summary-auto-layout.test.js chinese-ui-copy.test.js
```

Expected: fail because current UI still has team plan and `¥29` Pro.

- [ ] **Step 3: Update imports and API calls**

In `App.vue`, import:

```javascript
  getEntitlementStatus,
```

and from auth session:

```javascript
import { authInitialState, clearAuthState, membershipLabel, membershipStatusText, quotaMeterRatio, quotaMeterText, remainingSummaryText, updateAuthState } from "./services/authSession";
```

In `refreshMe()`, after billing status:

```javascript
      try {
        const entitlements = await getEntitlementStatus();
        auth.usage = {
          ...(auth.usage || {}),
          meters: entitlements.meters || {},
          credit_packs: entitlements.credit_packs || {}
        };
      } catch {
        // Keep legacy /api/me usage when entitlement status is unavailable.
      }
```

- [ ] **Step 4: Replace pricing plans**

Replace `pricingPlans` with:

```javascript
const pricingPlans = [
  {
    id: "free",
    badge: "免费开始",
    name: "免费版",
    price: "¥0",
    cycle: "登录后额度更多",
    description: "适合偶尔保存公开视频、试用 AI 总结，把几个视频整理成可复习笔记。",
    features: ["每天 30 次视频解析", "每天 10 次视频下载", "每天 3 次 AI 总结", "每月 30 分钟语音转写试用", "单视频总结 30 分钟以内"],
    cta: "开始免费使用",
    target: "download"
  },
  {
    id: "pro",
    badge: "推荐",
    name: "Pro 个人版",
    price: "¥19",
    cycle: "/月",
    description: "适合高频学习、课程整理、播客复习和创作者素材笔记。",
    features: ["每月 120 次 AI 总结", "每月 600 分钟语音转写", "单视频总结 120 分钟以内", "单视频下载 180 分钟以内", "每个总结 20 次 AI 追问"],
    cta: "开通 Pro",
    target: "download",
    featured: true
  }
];
```

Add:

```javascript
const creditPacks = [
  { id: "summary_small", group: "AI 总结次数包", name: "总结小包", price: "¥6", amount: "20 次 AI 总结", validity: "90 天有效" },
  { id: "summary_large", group: "AI 总结次数包", name: "总结大包", price: "¥19", amount: "100 次 AI 总结", validity: "180 天有效" },
  { id: "transcription_small", group: "语音转写分钟包", name: "转写小包", price: "¥8", amount: "120 分钟语音转写", validity: "90 天有效" },
  { id: "transcription_large", group: "语音转写分钟包", name: "转写大包", price: "¥29", amount: "600 分钟语音转写", validity: "180 天有效" }
];
```

- [ ] **Step 5: Update checkout labels**

Replace `proPlanButtonLabel`:

```javascript
const proPlanButtonLabel = computed(() => {
  if (auth.membership?.active || auth.membership?.status === "past_due") return "管理订阅";
  if (auth.membership?.plan === "pro") return "重新选择 Pro ¥19/月";
  return "开通 Pro ¥19/月";
});
```

Add pack checkout:

```javascript
async function startCreditPackCheckout(packId) {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  state.billingBusy = true;
  state.billingMessage = "";
  try {
    const returnOrigin = typeof window !== "undefined" ? window.location.origin : undefined;
    const result = await createBillingCheckout({
      return_url: returnOrigin,
      purchase_type: "credit_pack",
      pack_id: packId
    });
    if (result.credit_pack) {
      state.billingMessage = "按量包已加入账号。";
      await refreshMe({ silent: true });
      return;
    }
    if (result.url && typeof window !== "undefined") window.location.href = result.url;
  } catch (error) {
    state.billingMessage = localizeStatus(error.message);
  } finally {
    state.billingBusy = false;
  }
}
```

- [ ] **Step 6: Pass analysis token to download**

In `handleDownload()`, add:

```javascript
      analysis_token: state.result.analysis_token,
```

to the `createDownloadTask` payload.

- [ ] **Step 7: Add quota meters in account panel**

Add computed helpers:

```javascript
const summaryQuotaText = computed(() => quotaMeterText(auth, "summary") || authUsageText.value);
const transcriptionQuotaText = computed(() => quotaMeterText(auth, "transcription_minutes"));
const summaryQuotaRatio = computed(() => quotaMeterRatio(auth, "summary"));
const transcriptionQuotaRatio = computed(() => quotaMeterRatio(auth, "transcription_minutes"));
```

In account dropdown, render two real tracks:

```vue
<div class="account-quota-list">
  <div class="account-quota-row">
    <span>{{ summaryQuotaText }}</span>
    <div class="account-quota-track"><span :style="{ width: `${summaryQuotaRatio}%` }"></span></div>
  </div>
  <div v-if="transcriptionQuotaText" class="account-quota-row">
    <span>{{ transcriptionQuotaText }}</span>
    <div class="account-quota-track"><span :style="{ width: `${transcriptionQuotaRatio}%` }"></span></div>
  </div>
</div>
```

- [ ] **Step 8: Replace pricing template**

Keep the existing `v-for="plan in pricingPlans"` structure, but remove any team-specific branch. After `pricing-assurance`, add:

```vue
<section class="credit-pack-section" aria-label="按量包">
  <div class="credit-pack-head">
    <p class="section-eyebrow">额度不够时再买</p>
    <h3>按量包不会强迫升级，更适合偶尔的长视频和课程整理高峰</h3>
  </div>
  <div class="credit-pack-grid">
    <article v-for="pack in creditPacks" :key="pack.id" class="credit-pack-card">
      <span class="plan-badge">{{ pack.group }}</span>
      <h4>{{ pack.name }}</h4>
      <strong>{{ pack.price }}</strong>
      <p>{{ pack.amount }}</p>
      <small>{{ pack.validity }}</small>
      <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="startCreditPackCheckout(pack.id)">
        <CreditCard :size="18" aria-hidden="true" />
        <span>购买按量包</span>
      </button>
    </article>
  </div>
</section>
```

- [ ] **Step 9: Update CSS**

In `frontend/src/assets/main.css`, change pricing grid:

```css
.pricing-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
```

Add:

```css
.credit-pack-section {
  width: min(100%, 1180px);
  margin: 28px auto 0;
}

.credit-pack-head {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}

.credit-pack-head h3 {
  margin: 0;
  font-size: 1.15rem;
  color: var(--color-ink);
}

.credit-pack-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.credit-pack-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  background: var(--color-paper-surface);
}

.credit-pack-card h4,
.credit-pack-card p {
  margin: 0;
}

.credit-pack-card strong {
  font-size: 1.55rem;
  color: var(--color-ink);
}

.credit-pack-card small {
  color: var(--color-muted);
}

.account-quota-list {
  display: grid;
  gap: 10px;
}

.account-quota-row {
  display: grid;
  gap: 6px;
}

@media (max-width: 900px) {
  .pricing-grid,
  .credit-pack-grid {
    grid-template-columns: 1fr;
  }
}
```

Remove fixed `width: 62%` from `.account-quota-track span`; the inline width now controls it.

- [ ] **Step 10: Run frontend tests**

Run:

```bash
cd frontend
npm test -- summary-auto-layout.test.js chinese-ui-copy.test.js auth-session.test.js summary-api.test.js
```

Expected: pass.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/App.vue frontend/src/assets/main.css frontend/tests/summary-auto-layout.test.js frontend/tests/chinese-ui-copy.test.js
git commit -m "feat: 更新个人套餐与按量包界面"
```

---

### Task 10: Final Integration, Docs, and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/04-api-design.md`
- Modify: `docs/08-feature-summary.md`
- Verify: backend and frontend test suites

- [ ] **Step 1: Update docs**

In `README.md` feature list, replace:

```markdown
- Gate AI video summaries with a free daily quota and Pro membership.
```

with:

```markdown
- Gate personal usage with transparent quotas: visitor analyze/download limits, richer logged-in free usage, Pro monthly AI summary and transcription allowances, and optional credit packs.
```

In `docs/04-api-design.md`, add `/api/entitlements/status` and document `analysis_token` in `/api/analyze` response and `/api/download` request.

In `docs/08-feature-summary.md`, update “已覆盖验证” and “配置项” to mention personal quotas and pack Prices.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest
```

Expected: all backend tests pass.

- [ ] **Step 3: Run full frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: all frontend tests pass.

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 5: Manual smoke with demo mode**

Run backend:

```bash
cd backend
SAVEANY_DEMO_MODE=true BILLING_MODE=mock ./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev
```

Manual checks:

- Open `http://localhost:5173`.
- Analyze `https://demo.saveany.local/video` three times as visitor; the fourth request shows visitor analyze limit.
- Register/login and confirm quota display.
- Open pricing page and confirm no team copy appears.
- Use mock credit pack purchase and confirm balance increases.

- [ ] **Step 6: Commit docs and final polish**

```bash
git add README.md docs/04-api-design.md docs/08-feature-summary.md
git commit -m "docs: 更新个人额度套餐说明"
```

- [ ] **Step 7: Review final diff**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only unrelated pre-existing untracked files remain; new commits are visible.

---

## Self-Review

- Spec coverage: This plan covers personal-only package removal, free/Pro limits, two credit pack types, anonymous analyze/download limits, logged-in usage, summary and transcription metering, question limits, Stripe/mock billing, frontend cards, account quota display, docs, and verification.
- Completeness scan: No planned step relies on unspecified filler text; where code snippets are partial integration points, they name the exact file and surrounding function.
- Type consistency: Meter names use `analyze`, `download`, `summary`, `transcription_minutes`, and `question` consistently across catalog, meter service, database, API, and frontend.
- Scope: Annual plans, invoice history, usage detail pages, historical summary lists, and batch export remain outside this first implementation.
