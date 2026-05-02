# Stripe Checkout Return Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Stripe Checkout return path so a paid user lands back on the pricing page and sees the active Pro plan without waiting on Stripe CLI webhook delivery.

**Architecture:** Keep webhooks as the authoritative async billing path, and add a logged-in server-side confirmation endpoint for successful Checkout return URLs. The frontend parses `checkout=success&session_id=...`, asks the backend to confirm with Stripe, refreshes account state, and renders current plan state directly on pricing cards.

**Tech Stack:** FastAPI, Pydantic, Stripe Python SDK, SQLite, Vue 3 Composition API, Vite, Node test runner, pytest.

---

## File Structure

- Modify `backend/app/services/billing_service.py`: add Checkout confirmation exceptions and a service function that validates session ownership, retrieves subscription data, and reuses existing upsert logic.
- Modify `backend/app/billing_routes.py`: add `POST /api/billing/checkout/confirm` with Stripe retrieval and HTTP error mapping.
- Modify `backend/tests/test_billing_stripe_webhook.py`: add confirm endpoint regression tests.
- Modify `frontend/src/services/api.js`: add `confirmBillingCheckout(sessionId)` and preserve HTTP status on thrown API errors.
- Modify `frontend/src/services/authSession.js`: add membership and plan status text helpers.
- Modify `frontend/src/App.vue`: parse successful Checkout return, confirm payment, refresh membership, and render plan-state badges/copy.
- Modify `frontend/src/assets/main.css`: style current-plan badges and plan status copy.
- Modify frontend tests:
  - `frontend/tests/auth-session.test.js`
  - `frontend/tests/chinese-ui-copy.test.js`
  - `frontend/tests/summary-auto-layout.test.js`

## Task 1: Backend Checkout Confirmation

**Files:**
- Modify: `backend/app/services/billing_service.py`
- Modify: `backend/app/billing_routes.py`
- Test: `backend/tests/test_billing_stripe_webhook.py`

- [ ] **Step 1: Write failing backend tests**

Add tests to `backend/tests/test_billing_stripe_webhook.py`:

```python
class FakeStripeSubscription:
    payloads = {}

    @classmethod
    def retrieve(cls, subscription_id):
        return cls.payloads[subscription_id]


class FakeStripeCheckoutSessionConfirm:
    payloads = {}

    @classmethod
    def retrieve(cls, session_id, expand=None):
        return cls.payloads[session_id]


class FakeStripeCheckoutConfirm:
    Session = FakeStripeCheckoutSessionConfirm
```

Then add:

```python
def test_checkout_confirm_syncs_paid_subscription(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCheckoutSessionConfirm.payloads = {}
    FakeStripeSubscription.payloads = {}
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "confirm-paid@example.com", "password": "stripe-password"},
    ).json()
    user_id = registered["user"]["id"]
    FakeStripeCheckoutSessionConfirm.payloads["cs_paid"] = {
        "id": "cs_paid",
        "customer": "cus_confirm",
        "subscription": "sub_confirm",
        "payment_status": "paid",
        "client_reference_id": user_id,
        "metadata": {"saveany_user_id": user_id},
    }
    FakeStripeSubscription.payloads["sub_confirm"] = {
        "id": "sub_confirm",
        "customer": "cus_confirm",
        "status": "active",
        "current_period_start": 1777600000,
        "current_period_end": 1780278400,
        "cancel_at_period_end": False,
        "metadata": {"saveany_user_id": user_id},
        "items": {"data": [{"price": {"id": "price_monthly"}}]},
    }

    response = client.post(
        "/api/billing/checkout/confirm",
        json={"session_id": "cs_paid"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "stripe"
    assert response.json()["membership"]["active"] is True
    assert response.json()["membership"]["plan"] == "pro"
    assert get_membership(user_id).active is True
```

Also add:

```python
def test_checkout_confirm_rejects_session_for_another_user(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    other_user = create_user("other-confirm@example.com", "stripe-password")
    FakeStripeCheckoutSessionConfirm.payloads = {
        "cs_other": {
            "id": "cs_other",
            "customer": "cus_other",
            "subscription": "sub_other",
            "payment_status": "paid",
            "client_reference_id": other_user.id,
            "metadata": {"saveany_user_id": other_user.id},
        }
    }
    FakeStripeSubscription.payloads = {
        "sub_other": {
            "id": "sub_other",
            "customer": "cus_other",
            "status": "active",
            "current_period_start": 1777600000,
            "current_period_end": 1780278400,
            "metadata": {"saveany_user_id": other_user.id},
            "items": {"data": [{"price": {"id": "price_monthly"}}]},
        }
    }
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    current = client.post(
        "/api/auth/register",
        json={"email": "current-confirm@example.com", "password": "stripe-password"},
    ).json()

    response = client.post("/api/billing/checkout/confirm", json={"session_id": "cs_other"})

    assert response.status_code == 403
    assert get_membership(current["user"]["id"]).active is False
    assert get_membership(other_user.id).active is False
```

And:

```python
def test_checkout_confirm_waits_for_unpaid_session(monkeypatch, tmp_path):
    _stripe_env(monkeypatch, tmp_path)
    database.initialize_database(tmp_path / "saveany.db")
    FakeStripeCheckoutSessionConfirm.payloads = {}
    FakeStripeSubscription.payloads = {}
    monkeypatch.setattr(billing_routes.stripe, "checkout", FakeStripeCheckoutConfirm)
    monkeypatch.setattr(billing_routes.stripe, "Subscription", FakeStripeSubscription)
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={"email": "confirm-unpaid@example.com", "password": "stripe-password"},
    ).json()
    user_id = registered["user"]["id"]
    FakeStripeCheckoutSessionConfirm.payloads["cs_unpaid"] = {
        "id": "cs_unpaid",
        "customer": "cus_unpaid",
        "subscription": "sub_unpaid",
        "payment_status": "unpaid",
        "client_reference_id": user_id,
        "metadata": {"saveany_user_id": user_id},
    }
    FakeStripeSubscription.payloads["sub_unpaid"] = {
        "id": "sub_unpaid",
        "customer": "cus_unpaid",
        "status": "incomplete",
        "metadata": {"saveany_user_id": user_id},
        "items": {"data": [{"price": {"id": "price_monthly"}}]},
    }

    response = client.post("/api/billing/checkout/confirm", json={"session_id": "cs_unpaid"})

    assert response.status_code == 409
    assert get_membership(user_id).active is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
pytest tests/test_billing_stripe_webhook.py -k "checkout_confirm" -v
```

Expected: FAIL with 404 for `/api/billing/checkout/confirm` or missing service helpers.

- [ ] **Step 3: Add service-layer confirmation logic**

In `backend/app/services/billing_service.py`, add:

```python
class StripeCheckoutOwnershipError(RuntimeError):
    pass


class StripeCheckoutNotReadyError(RuntimeError):
    pass


def _stripe_dict(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value)


def confirm_stripe_checkout_session(user: User, session: dict, retrieve_subscription: Callable[[str], dict]) -> Membership:
    session = _stripe_dict(session) or {}
    session_id = session.get("id")
    if not session_id:
        raise ValueError("Stripe Checkout Session 缺少 ID")
    metadata = session.get("metadata") or {}
    owner_id = metadata.get("saveany_user_id") or session.get("client_reference_id")
    if owner_id != user.id:
        raise StripeCheckoutOwnershipError("Stripe Checkout Session 不属于当前用户")

    subscription = session.get("subscription")
    if isinstance(subscription, dict):
        subscription_payload = subscription
    elif subscription:
        subscription_payload = _stripe_dict(retrieve_subscription(subscription))
    else:
        raise StripeCheckoutNotReadyError("Stripe 订阅仍在创建中，请稍后刷新")

    subscription_payload = subscription_payload or {}
    payment_status = session.get("payment_status")
    subscription_status = subscription_payload.get("status")
    if payment_status != "paid" and subscription_status not in ACTIVE_STATUSES:
        raise StripeCheckoutNotReadyError("Stripe 支付仍在确认中，请稍后刷新")

    subscription_metadata = dict(subscription_payload.get("metadata") or {})
    if not subscription_metadata.get("saveany_user_id"):
        subscription_metadata["saveany_user_id"] = user.id
        subscription_payload = {**subscription_payload, "metadata": subscription_metadata}

    upsert_stripe_checkout_session(session)
    membership = upsert_stripe_subscription(subscription_payload)
    complete_stripe_checkout_attempt(session_id)
    return membership
```

- [ ] **Step 4: Add the route**

In `backend/app/billing_routes.py`, import `BaseModel`, `confirm_stripe_checkout_session`, `StripeCheckoutOwnershipError`, and `StripeCheckoutNotReadyError`, then add:

```python
class CheckoutConfirmRequest(BaseModel):
    session_id: str


@router.post("/checkout/confirm")
def billing_checkout_confirm(payload: CheckoutConfirmRequest, user: User = Depends(current_user)) -> dict:
    config = load_config()
    session_id = payload.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 Stripe Checkout Session ID")
    if config.billing_mode != "stripe":
        raise HTTPException(status_code=404, detail="Stripe 支付确认仅在 Stripe 模式可用")
    if not config.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe 支付尚未配置")
    stripe.api_key = config.stripe_secret_key
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
        membership = confirm_stripe_checkout_session(
            user,
            session,
            lambda subscription_id: stripe.Subscription.retrieve(subscription_id),
        )
    except StripeCheckoutOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StripeCheckoutNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe 确认失败，请稍后重试") from exc
    return {"membership": membership.as_dict(), "mode": "stripe"}
```

- [ ] **Step 5: Run backend confirmation tests**

Run:

```bash
cd backend
pytest tests/test_billing_stripe_webhook.py -k "checkout_confirm" -v
```

Expected: PASS.

## Task 2: Frontend Checkout Return and Plan Status

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/services/authSession.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/assets/main.css`
- Test: `frontend/tests/auth-session.test.js`
- Test: `frontend/tests/chinese-ui-copy.test.js`
- Test: `frontend/tests/summary-auto-layout.test.js`

- [ ] **Step 1: Write failing frontend tests**

In `frontend/tests/auth-session.test.js`, import `membershipStatusText` and add:

```javascript
test("membershipStatusText explains pro edge states", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "past-due@example.com" },
    membership: { active: false, plan: "pro", status: "past_due" },
    usage: { daily_free_limit: 3, used_today: 3, remaining_today: 0 }
  });

  assert.equal(membershipStatusText(state), "付款失败，请更新支付方式");
  assert.equal(membershipLabel(state), "专业版付款失败");
  assert.equal(remainingSummaryText(state), "付款失败后 AI 总结额度已暂停");
});
```

In `frontend/tests/chinese-ui-copy.test.js`, add required phrases:

```javascript
"当前已开通",
"当前套餐",
"重新开通专业版 ¥29/月",
"付款失败，请更新支付方式",
"已取消续费，本周期内仍可使用",
"支付已返回，仍在等待 Stripe 确认",
"专业版已开通"
```

In `frontend/tests/summary-auto-layout.test.js`, add assertions:

```javascript
assert.match(appSource, /confirmBillingCheckout/);
assert.match(appSource, /checkoutConfirming:\s*false/);
assert.match(appSource, /class="current-plan-badge"/);
assert.match(appSource, /class="plan-status-copy"/);
assert.match(mainCss, /\.current-plan-badge\s*\{/);
assert.match(mainCss, /\.plan-status-copy\s*\{/);
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- auth-session chinese-ui-copy summary-auto-layout
```

Expected: FAIL because helpers, API call, and UI copy do not exist yet.

- [ ] **Step 3: Add frontend API support**

In `frontend/src/services/api.js`, add:

```javascript
export async function confirmBillingCheckout(sessionId) {
  return postJson("/api/billing/checkout/confirm", { session_id: sessionId });
}
```

Change `postJson` error handling to:

```javascript
  if (!response.ok) {
    const error = await readApiError(response);
    const apiError = new Error(error);
    apiError.status = response.status;
    throw apiError;
  }
```

- [ ] **Step 4: Add membership text helpers**

In `frontend/src/services/authSession.js`, add:

```javascript
export function membershipStatusText(state) {
  const membership = state.membership || {};
  if (!state.user) return "登录后查看套餐状态";
  if (membership.active && membership.cancel_at_period_end) return "已取消续费，本周期内仍可使用";
  if (membership.active) return "当前已开通";
  if (membership.status === "past_due") return "付款失败，请更新支付方式";
  if (membership.plan === "pro") return "专业版已过期";
  return "当前套餐";
}
```

Update `membershipLabel` and `remainingSummaryText` so `past_due` and expired Pro states are not shown as ordinary free accounts.

- [ ] **Step 5: Add checkout confirmation state to App.vue**

In `frontend/src/App.vue`, import `confirmBillingCheckout` and `membershipStatusText`. Add state:

```javascript
checkoutConfirming: false,
checkoutConfirmedSessionId: "",
```

Add:

```javascript
const billingStateText = computed(() => membershipStatusText(auth));
const proPlanButtonLabel = computed(() => {
  if (auth.membership?.active || auth.membership?.status === "past_due") return "管理订阅";
  if (auth.membership?.plan === "pro") return "重新开通专业版 ¥29/月";
  return "开通专业版 ¥29/月";
});
```

Add functions `pricingPlanStateLabel(plan)`, `pricingPlanStatusCopy(plan)`, `shouldManageProPlan()`, `handleProPlanAction()`, and `confirmCheckoutReturn()` using the backend confirm API and 409 retry loop.

- [ ] **Step 6: Update pricing template and CSS**

In the Pro pricing card, render:

```vue
<span v-if="pricingPlanStateLabel(plan)" class="current-plan-badge">{{ pricingPlanStateLabel(plan) }}</span>
<p v-if="pricingPlanStatusCopy(plan)" class="plan-status-copy">{{ pricingPlanStatusCopy(plan) }}</p>
```

Use one Pro action button:

```vue
<button
  v-if="plan.id === 'pro'"
  :class="shouldManageProPlan() ? 'secondary-button' : 'primary-button'"
  type="button"
  :disabled="state.billingBusy"
  @click="handleProPlanAction"
>
  <Loader2 v-if="state.billingBusy" :size="20" class="animate-spin" aria-hidden="true" />
  <CreditCard v-else-if="shouldManageProPlan()" :size="20" aria-hidden="true" />
  <Star v-else :size="20" aria-hidden="true" />
  <span>{{ proPlanButtonLabel }}</span>
</button>
```

Add CSS:

```css
.current-plan-badge {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  border: 1px solid rgba(22, 163, 74, 0.24);
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.12);
  padding: 0 10px;
  color: #166534;
  font-family: var(--font-label);
  font-size: 12px;
  font-weight: 900;
}

.plan-status-copy {
  min-height: 46px;
  border-radius: var(--radius-md);
  background: rgba(248, 250, 252, 0.82);
  padding: 10px 12px;
  color: var(--color-paper-text);
  font-size: 13px;
  font-weight: 800;
  line-height: 1.45;
}
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd frontend
npm test -- auth-session chinese-ui-copy summary-auto-layout
```

Expected: PASS.

## Task 3: Full Verification

**Files:**
- Verify: backend and frontend tests
- Verify: local browser flow

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
pytest tests/test_billing_stripe_webhook.py tests/test_billing_mock.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- auth-session chinese-ui-copy summary-auto-layout
```

Expected: PASS.

- [ ] **Step 3: Run builds or startup checks**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Browser verification**

Start backend and frontend:

```bash
cd backend
BILLING_MODE=mock uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173/#pricing`, register/login, use mock activation when real Stripe secrets are not configured, and confirm the pricing page shows “当前已开通”, account menu shows “专业版会员”, and the Pro button changes to “管理订阅”.

When Stripe test credentials are configured, set `BILLING_MODE=stripe`, click “开通专业版 ¥29/月”, pay with `4242 4242 4242 4242`, a future expiration date, any CVC, and confirm the return URL activates Pro through `/api/billing/checkout/confirm`.

## Self-Review

- Spec coverage: The plan covers return confirmation, server-side ownership/payment validation, frontend return parsing, pricing-card current plan display, edge-state copy, automated tests, and browser verification.
- Placeholder scan: No placeholders or deferred implementation instructions remain.
- Type consistency: Backend uses `session_id`, `Membership`, `User`, and existing `upsert_stripe_subscription`; frontend uses `checkoutConfirming`, `confirmBillingCheckout`, `membershipStatusText`, and existing `auth.membership` consistently.
