# AI Question Monthly Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-summary AI question limits with account-level monthly AI question quotas: free users get 10/month and Pro users get 200/month.

**Architecture:** Reuse the existing meter system instead of introducing a new quota table. `MeterType.QUESTION` will become a normal monthly meter stored in `usage_periods.question_count`; the question endpoint will reserve one question before calling the LLM, refund on provider failure, and return fresh usage for real-time UI updates. Frontend quota rendering will treat `question` like the existing `summary` and `transcription_minutes` meters.

**Tech Stack:** FastAPI, SQLite, Vue 3, Node test runner, pytest.

---

## File Structure

- Modify `backend/app/services/plan_catalog.py`
  - Replace `questions_per_summary` with `question_monthly_limit`.
  - Configure free = 10/month and Pro = 200/month.
- Modify `backend/app/services/usage_meter.py`
  - Route `MeterType.QUESTION` through the generic monthly `usage_periods` meter.
  - Include `question` in `entitlement_status`.
  - Keep old `summary_questions` helpers unused or remove them only if no tests rely on them.
- Modify `backend/app/summary_routes.py`
  - Replace `reserve_summary_question` / `refund_summary_question` with `reserve_user_meter` / `refund_reservation`.
  - Return `{ answer, usage }` after successful AI question calls.
- Modify `backend/tests/test_usage_meter.py`
  - Add direct meter tests for monthly AI question limits and refund.
- Modify `backend/tests/test_summary_api.py`
  - Add endpoint-level tests for monthly limit, no model call on exhaustion, no per-summary limit, usage response, and refund on provider failure.
- Modify `frontend/src/services/authSession.js`
  - Render `question` quota text as `AI 问答还剩 X 次`.
- Modify `frontend/src/App.vue`
  - Add account-menu question quota row.
  - Add question quota computed values.
  - Apply returned usage after successful question calls.
  - Pass question quota state into `SummaryPanel`.
  - Update pricing plan copy.
- Modify `frontend/src/components/summary/SummaryPanel.vue`
  - Accept question quota props and pass them to `SummaryQa`.
- Modify `frontend/src/components/summary/SummaryQa.vue`
  - Show monthly question quota text.
  - Disable submit when quota is exhausted.
- Modify `frontend/tests/auth-session.test.js`
  - Assert question quota text and ratio behavior.
- Modify `frontend/tests/summary-api.test.js`
  - Assert `askSummaryQuestion` returns usage payload unchanged.
- Modify `frontend/tests/summary-auto-layout.test.js`
  - Assert pricing copy, account display, usage application, and question quota props.

---

### Task 1: Backend Meter Configuration

**Files:**
- Modify: `backend/app/services/plan_catalog.py`
- Modify: `backend/app/services/usage_meter.py`
- Test: `backend/tests/test_usage_meter.py`

- [ ] **Step 1: Write failing tests for question monthly limits**

Add these tests to `backend/tests/test_usage_meter.py` after `test_free_user_summary_reservation_and_refund`:

```python
def test_free_user_question_monthly_limit_and_refund(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("question-free@example.com", "meter-password")

    for index in range(10):
        usage = reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=f"question_free_{index}",
        )

    assert usage["limit"] == 10
    assert usage["used"] == 10
    assert usage["remaining"] == 0

    with pytest.raises(MeterExceeded) as exc:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id="question_free_11",
        )

    assert "AI 问答次数不足" in str(exc.value)

    refund_reservation("question_free_9")
    status = entitlement_status(user)

    assert status["meters"]["question"]["limit"] == 10
    assert status["meters"]["question"]["used"] == 9
    assert status["meters"]["question"]["remaining"] == 1
```

Add this Pro test below it:

```python
def test_pro_user_question_monthly_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    user = create_user("question-pro@example.com", "meter-password")
    activate_mock_subscription(user)

    for index in range(200):
        usage = reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=f"question_pro_{index}",
        )

    assert usage["limit"] == 200
    assert usage["used"] == 200
    assert usage["remaining"] == 0

    with pytest.raises(MeterExceeded) as exc:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id="question_pro_201",
        )

    assert "AI 问答次数不足" in str(exc.value)
```

Update imports at the top of `backend/tests/test_usage_meter.py`:

```python
from app.services.billing_service import activate_mock_subscription
```

- [ ] **Step 2: Run the failing meter tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_usage_meter.py::test_free_user_question_monthly_limit_and_refund tests/test_usage_meter.py::test_pro_user_question_monthly_limit -q
```

Expected before implementation:

```text
FAILED
```

The expected failure is that the current limit still comes from `questions_per_summary` and `entitlement_status` does not expose `meters.question`.

- [ ] **Step 3: Update plan catalog fields**

In `backend/app/services/plan_catalog.py`, replace the `PlanLimits` field:

```python
questions_per_summary: int | None = None
```

with:

```python
question_monthly_limit: int | None = None
```

In the free plan, replace:

```python
questions_per_summary=3,
```

with:

```python
question_monthly_limit=10,
```

In the Pro plan, replace:

```python
questions_per_summary=20,
```

with:

```python
question_monthly_limit=200,
```

- [ ] **Step 4: Update question allowance and entitlement status**

In `backend/app/services/usage_meter.py`, update the `MeterType.QUESTION` branch in `allowance_for_user` to:

```python
    if meter_type == MeterType.QUESTION:
        return MeterAllowance(
            meter_type,
            PeriodType.MONTH,
            current_period_key(PeriodType.MONTH),
            limits.question_monthly_limit or 0,
            "question_count",
            plan_id,
        )
```

In `entitlement_status`, change the `meters` dict to include question:

```python
    meters = {
        MeterType.ANALYZE.value: _meter_status(user, MeterType.ANALYZE),
        MeterType.DOWNLOAD.value: _meter_status(user, MeterType.DOWNLOAD),
        MeterType.SUMMARY.value: _meter_status(user, MeterType.SUMMARY),
        MeterType.TRANSCRIPTION_MINUTES.value: _meter_status(
            user, MeterType.TRANSCRIPTION_MINUTES
        ),
        MeterType.QUESTION.value: _meter_status(user, MeterType.QUESTION),
    }
```

Keep `credit_packs` unchanged:

```python
        "credit_packs": {
            "summary": {"remaining": meters["summary"]["pack_remaining"]},
            "transcription_minutes": {
                "remaining": meters["transcription_minutes"]["pack_remaining"]
            },
        },
```

- [ ] **Step 5: Update insufficient question error label**

In `backend/app/services/usage_meter.py`, update `_consume_credit_packs` label selection so question meters get a clear message:

```python
        label_by_meter = {
            MeterType.SUMMARY: "AI 总结次数",
            MeterType.TRANSCRIPTION_MINUTES: "语音转写分钟",
            MeterType.QUESTION: "AI 问答次数",
        }
        label = label_by_meter.get(meter_type, "额度")
        raise MeterExceeded(f"{label}不足，请购买对应按量包后继续。")
```

If there is no intention to support question credit packs, this label still gives a useful internal exception for `reserve_user_meter`; `summary_routes.py` will translate it into the public monthly quota message in Task 2.

- [ ] **Step 6: Run meter tests again**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_usage_meter.py::test_free_user_question_monthly_limit_and_refund tests/test_usage_meter.py::test_pro_user_question_monthly_limit -q
```

Expected:

```text
2 passed
```

- [ ] **Step 7: Commit backend meter configuration**

Run:

```bash
git add backend/app/services/plan_catalog.py backend/app/services/usage_meter.py backend/tests/test_usage_meter.py
git commit -m "feat: 添加 AI 问答月度额度 meter"
```

---

### Task 2: Question Endpoint Reservation, Refund, and Usage Response

**Files:**
- Modify: `backend/app/summary_routes.py`
- Test: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Write failing endpoint tests**

Add this helper class near `FailingOnceQuestionService` in `backend/tests/test_summary_api.py`:

```python
class CountingQuestionService(FakeSummaryService):
    def __init__(self):
        super().__init__()
        self.answer_calls = 0

    def answer_question(self, *, title, transcript, summary, question, language):
        self.answer_calls += 1
        return super().answer_question(
            title=title,
            transcript=transcript,
            summary=summary,
            question=question,
            language=language,
        )
```

Add this test after `test_summary_question_requires_completed_task`:

```python
def test_free_user_question_quota_is_monthly_not_per_summary(monkeypatch, isolated_summary_store):
    fake = CountingQuestionService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/monthly-question-quota"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    for index in range(10):
        answer = client.post(
            f"/api/summaries/{summary_id}/questions",
            json={"question": f"第 {index + 1} 个问题？", "language": "zh-CN"},
            headers=session_headers,
        )
        assert answer.status_code == 200
        assert answer.json()["answer"] == f"回答：第 {index + 1} 个问题？"
        assert answer.json()["usage"]["meters"]["question"]["remaining"] == 9 - index

    exhausted = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "第 11 个问题？", "language": "zh-CN"},
        headers=session_headers,
    )

    assert exhausted.status_code == 402
    assert exhausted.json()["detail"] == "本月 AI 问答次数已用完，请下月继续使用或升级套餐。"
    assert fake.answer_calls == 10
```

Add this refund test below it:

```python
def test_question_model_failure_refunds_monthly_question_quota(monkeypatch, isolated_summary_store):
    fake = FailingOnceQuestionService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/question-refund"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    failed = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "失败会退回吗？", "language": "zh-CN"},
        headers=session_headers,
    )
    status_after_failure = client.get("/api/entitlements", headers=session_headers).json()

    assert failed.status_code == 400
    assert status_after_failure["meters"]["question"]["used"] == 0
    assert status_after_failure["meters"]["question"]["remaining"] == 10

    successful = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "第二次可以继续吗？", "language": "zh-CN"},
        headers=session_headers,
    )

    assert successful.status_code == 200
    assert successful.json()["usage"]["meters"]["question"]["used"] == 1
    assert successful.json()["usage"]["meters"]["question"]["remaining"] == 9
```

Add this Pro limit test below it:

```python
def test_pro_user_question_quota_allows_200_monthly_questions(monkeypatch, isolated_summary_store):
    fake = CountingQuestionService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)
    user_id = client.get("/api/me").json()["user"]["id"]
    activate_mock_subscription(get_user_by_id(user_id))

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/pro-question-quota"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    for index in range(200):
        answer = client.post(
            f"/api/summaries/{summary_id}/questions",
            json={"question": f"Pro 问题 {index + 1}", "language": "zh-CN"},
            headers=session_headers,
        )
        assert answer.status_code == 200

    exhausted = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "Pro 第 201 个问题", "language": "zh-CN"},
        headers=session_headers,
    )

    assert exhausted.status_code == 402
    assert fake.answer_calls == 200
```

- [ ] **Step 2: Run endpoint tests and verify they fail**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py::test_free_user_question_quota_is_monthly_not_per_summary tests/test_summary_api.py::test_question_model_failure_refunds_monthly_question_quota tests/test_summary_api.py::test_pro_user_question_quota_allows_200_monthly_questions -q
```

Expected before implementation:

```text
FAILED
```

The expected failures are old per-summary limits, missing usage in question responses, and old error wording.

- [ ] **Step 3: Update summary route imports**

In `backend/app/summary_routes.py`, remove these imports from `app.services.usage_meter`:

```python
    refund_summary_question,
    reserve_summary_question,
```

Add these imports if they are not already present:

```python
    reserve_user_meter,
```

Keep these existing imports:

```python
    MeterExceeded,
    MeterType,
    refund_reservation,
```

- [ ] **Step 4: Add a public question quota message constant**

Near the `summary_service` global in `backend/app/summary_routes.py`, add:

```python
QUESTION_QUOTA_EXCEEDED_MESSAGE = "本月 AI 问答次数已用完，请下月继续使用或升级套餐。"
```

- [ ] **Step 5: Replace question reservation logic**

Replace the body of `ask_summary_question` starting at the existing `try: reserve_summary_question` quota block and ending at the final return statement with this code:

```python
    reservation_id = f"question_{summary_id}_{secrets.token_urlsafe(8)}"
    try:
        reserve_user_meter(
            user,
            MeterType.QUESTION,
            1,
            reservation_id=reservation_id,
        )
    except MeterExceeded as exc:
        raise HTTPException(status_code=402, detail=QUESTION_QUOTA_EXCEEDED_MESSAGE) from exc
    transcript = _transcript_from_result(task.result)
    try:
        answer = get_summary_service().answer_question(
            title=task.title or "未命名视频",
            transcript=transcript,
            summary=task.result,
            question=question,
            language=payload.language,
        )
    except Exception as exc:
        try:
            refund_reservation(reservation_id)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=_friendly_summary_error(exc)) from exc
    usage = get_usage_summary(user)
    return {"answer": answer, "usage": usage.as_dict()}
```

This preserves the existing model call behavior while changing quota storage to the generic monthly meter.

- [ ] **Step 6: Remove unused per-summary question helpers if no imports remain**

Run:

```bash
rg -n "reserve_summary_question|refund_summary_question|questions_per_summary" backend/app backend/tests
```

If the only remaining definitions are in `backend/app/services/usage_meter.py`, delete the old `reserve_summary_question` and `refund_summary_question` functions from that file.

If tests still reference them, update those tests to call `reserve_user_meter(user, MeterType.QUESTION, 1, reservation_id="question_test")` instead.

- [ ] **Step 7: Run endpoint tests again**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py::test_free_user_question_quota_is_monthly_not_per_summary tests/test_summary_api.py::test_question_model_failure_refunds_monthly_question_quota tests/test_summary_api.py::test_pro_user_question_quota_allows_200_monthly_questions -q
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Run related backend regression tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_summary_api.py tests/test_usage_meter.py tests/test_entitlements.py -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit question endpoint changes**

Run:

```bash
git add backend/app/summary_routes.py backend/app/services/usage_meter.py backend/tests/test_summary_api.py
git commit -m "feat: 按月扣减 AI 问答额度"
```

---

### Task 3: Frontend Quota Text and Account Display

**Files:**
- Modify: `frontend/src/services/authSession.js`
- Modify: `frontend/src/App.vue`
- Test: `frontend/tests/auth-session.test.js`
- Test: `frontend/tests/summary-auto-layout.test.js`

- [ ] **Step 1: Write failing auth-session quota text test**

In `frontend/tests/auth-session.test.js`, update `quotaMeterText renders plan and pack remaining values` by adding `question` to the meters payload:

```javascript
        question: { limit: 10, used: 4, remaining: 6, plan_remaining: 6, pack_remaining: 0 },
```

Add this assertion to the same test:

```javascript
  assert.equal(quotaMeterText(state, "question"), "AI 问答还剩 6 次");
```

- [ ] **Step 2: Write failing layout assertions for pricing and account menu**

In `frontend/tests/summary-auto-layout.test.js`, update `pricing page shows personal free and pro plans plus credit packs` with:

```javascript
  assert.match(appSource, /每月 10 次 AI 问答/);
  assert.match(appSource, /每月 200 次 AI 问答/);
```

Update `quota and billing feedback are unified into status panels` with:

```javascript
  assert.match(appSource, /const questionQuotaText = computed/);
  assert.match(appSource, /quotaMeterText\(auth,\s*"question"\)/);
  assert.match(appSource, /v-if="questionQuotaText" class="account-quota-row"/);
```

- [ ] **Step 3: Run failing frontend tests**

Run:

```bash
cd frontend
npm test -- tests/auth-session.test.js tests/summary-auto-layout.test.js
```

Expected before implementation:

```text
fail
```

- [ ] **Step 4: Update `quotaMeterText` for question meter**

In `frontend/src/services/authSession.js`, add this branch inside `quotaMeterText` after the transcription branch:

```javascript
  if (meter === "question") return `AI 问答还剩 ${remaining} 次`;
```

- [ ] **Step 5: Update pricing copy**

In `frontend/src/App.vue`, update the free plan `features` array so it includes:

```javascript
    features: ["每天 30 次视频解析", "每天 10 次视频下载", "每天 3 次 AI 总结", "每月 30 分钟语音转写试用", "每月 10 次 AI 问答", "单视频总结 30 分钟以内"],
```

Update the Pro plan `features` array so it includes:

```javascript
    features: ["每月 120 次 AI 总结", "每月 600 分钟语音转写", "每月 200 次 AI 问答", "单视频总结 120 分钟以内", "单视频下载 180 分钟以内"],
```

- [ ] **Step 6: Add computed question quota values**

In `frontend/src/App.vue`, add these computed values near `summaryQuotaText` and `transcriptionQuotaText`:

```javascript
const questionQuotaText = computed(() => quotaMeterText(auth, "question"));
const questionQuotaRatio = computed(() => quotaMeterRatio(auth, "question"));
const questionQuotaRemaining = computed(() => {
  const meter = auth.usage?.meters?.question;
  if (!meter) return null;
  return Math.max(Number(meter.remaining ?? 0), 0);
});
const questionQuotaExhausted = computed(() => questionQuotaRemaining.value === 0);
```

- [ ] **Step 7: Add account menu quota row**

In `frontend/src/App.vue`, inside `.account-quota-list`, add this block after the transcription row:

```vue
              <div v-if="questionQuotaText" class="account-quota-row">
                <span>{{ questionQuotaText }}</span>
                <div class="account-quota-track"><span :style="{ width: `${questionQuotaRatio}%` }"></span></div>
              </div>
```

- [ ] **Step 8: Run frontend quota tests**

Run:

```bash
cd frontend
npm test -- tests/auth-session.test.js tests/summary-auto-layout.test.js
```

Expected:

```text
pass
```

- [ ] **Step 9: Commit frontend quota display**

Run:

```bash
git add frontend/src/services/authSession.js frontend/src/App.vue frontend/tests/auth-session.test.js frontend/tests/summary-auto-layout.test.js
git commit -m "feat: 展示 AI 问答月度额度"
```

---

### Task 4: Frontend Question Flow Usage Updates and Disabled State

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/summary/SummaryPanel.vue`
- Modify: `frontend/src/components/summary/SummaryQa.vue`
- Test: `frontend/tests/summary-api.test.js`
- Test: `frontend/tests/summary-auto-layout.test.js`

- [ ] **Step 1: Write failing API test for usage response**

In `frontend/tests/summary-api.test.js`, update `askSummaryQuestion posts question to summary API` so the mocked response includes usage:

```javascript
    return {
      ok: true,
      json: async () => ({
        answer: "回答内容",
        usage: {
          meters: {
            question: { limit: 10, used: 1, remaining: 9 }
          }
        }
      })
    };
```

Update the assertion for the result to:

```javascript
  assert.deepEqual(result, {
    answer: "回答内容",
    usage: {
      meters: {
        question: { limit: 10, used: 1, remaining: 9 }
      }
    }
  });
```

- [ ] **Step 2: Write failing static assertions for question quota props**

In `frontend/tests/summary-auto-layout.test.js`, add these assertions to `summary workbench shows module cards before final result and loads selected content`:

```javascript
  assert.match(appSource, /:question-quota-text="questionQuotaText"/);
  assert.match(appSource, /:question-quota-exhausted="questionQuotaExhausted"/);
  assert.match(summaryPanelSource, /questionQuotaText/);
  assert.match(summaryPanelSource, /questionQuotaExhausted/);
```

Add these assertions to `summary module cards and loading state use compact professional controls`:

```javascript
  const summaryQaSource = readFileSync(new URL("../src/components/summary/SummaryQa.vue", import.meta.url), "utf8");
  assert.match(summaryQaSource, /本月 AI 问答/);
  assert.match(summaryQaSource, /questionQuotaExhausted/);
  assert.match(summaryQaSource, /本月 AI 问答次数已用完/);
```

Add `summaryQaSource` to the top-level test file constants if you prefer one shared read:

```javascript
const summaryQaSource = readFileSync(new URL("../src/components/summary/SummaryQa.vue", import.meta.url), "utf8");
```

- [ ] **Step 3: Run failing frontend tests**

Run:

```bash
cd frontend
npm test -- tests/summary-api.test.js tests/summary-auto-layout.test.js
```

Expected before implementation:

```text
fail
```

- [ ] **Step 4: Apply usage after successful question response**

In `frontend/src/App.vue`, replace:

```javascript
    const { answer } = await askSummaryQuestion(state.currentSummaryId, {
      question,
      language: "zh-CN"
    });
    state.summaryQaHistory.unshift({ question, answer });
```

with:

```javascript
    const { answer, usage } = await askSummaryQuestion(state.currentSummaryId, {
      question,
      language: "zh-CN"
    });
    if (usage) applyUsageState(auth, usage);
    state.summaryQaHistory.unshift({ question, answer });
```

- [ ] **Step 5: Pass question quota props from App to SummaryPanel**

In the `SummaryPanel` usage in `frontend/src/App.vue`, add:

```vue
              :question-quota-text="questionQuotaText"
              :question-quota-exhausted="questionQuotaExhausted"
```

- [ ] **Step 6: Accept and forward question quota props in SummaryPanel**

In `frontend/src/components/summary/SummaryPanel.vue`, add these props:

```javascript
  questionQuotaText: {
    type: String,
    default: ""
  },
  questionQuotaExhausted: {
    type: Boolean,
    default: false
  },
```

In the `<SummaryQa>` component call, pass:

```vue
        :question-quota-text="questionQuotaText"
        :question-quota-exhausted="questionQuotaExhausted"
```

- [ ] **Step 7: Render question quota and disabled state in SummaryQa**

In `frontend/src/components/summary/SummaryQa.vue`, add props:

```javascript
  questionQuotaText: {
    type: String,
    default: ""
  },
  questionQuotaExhausted: {
    type: Boolean,
    default: false
  },
```

Replace:

```javascript
const canSubmit = computed(() => props.summaryQuestion.trim() && !props.askingSummaryQuestion);
```

with:

```javascript
const canSubmit = computed(
  () => props.summaryQuestion.trim() && !props.askingSummaryQuestion && !props.questionQuotaExhausted
);
```

Inside the form, after the textarea and before the submit button, add:

```vue
      <p v-if="questionQuotaText" class="summary-module-eyebrow">本月 {{ questionQuotaText }}</p>
      <p v-if="questionQuotaExhausted" class="message error" role="alert">
        <XCircle :size="18" aria-hidden="true" />
        <span>本月 AI 问答次数已用完</span>
      </p>
```

- [ ] **Step 8: Run frontend question tests**

Run:

```bash
cd frontend
npm test -- tests/summary-api.test.js tests/summary-auto-layout.test.js
```

Expected:

```text
pass
```

- [ ] **Step 9: Commit frontend question flow**

Run:

```bash
git add frontend/src/App.vue frontend/src/components/summary/SummaryPanel.vue frontend/src/components/summary/SummaryQa.vue frontend/tests/summary-api.test.js frontend/tests/summary-auto-layout.test.js
git commit -m "feat: 同步 AI 问答额度到问答区"
```

---

### Task 5: Full Regression and Browser Verification

**Files:**
- No production file changes expected.
- Test evidence only.

- [ ] **Step 1: Run backend full test suite**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run frontend full test suite**

Run:

```bash
cd frontend
npm test
```

Expected:

```text
pass
```

- [ ] **Step 3: Run frontend production build**

Run:

```bash
cd frontend
npm run build
```

Expected:

```text
✓ built
```

- [ ] **Step 4: Start local services if needed**

If the backend is not listening on port 8000, run:

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the frontend is not listening on port 5173, run:

```bash
cd frontend
npm run dev -- --port 5173
```

- [ ] **Step 5: Browser verify question quota**

Use the in-app browser at:

```text
http://127.0.0.1:5173/#download-console
```

Manual verification path:

1. Register a new free test user.
2. Generate or reuse one completed AI summary.
3. Open the AI 问答 tab.
4. Confirm the UI shows `本月 AI 问答还剩 10 次` or `AI 问答还剩 10 次`.
5. Ask 10 questions.
6. Confirm the remaining count decrements to 0.
7. Submit an 11th question.
8. Confirm the UI shows the backend quota error:

```text
本月 AI 问答次数已用完，请下月继续使用或升级套餐。
```

- [ ] **Step 6: Database verification**

Find the test user id:

```bash
sqlite3 runtime/saveany.db "select id,email from users where email like 'your-test-prefix%';"
```

Check monthly question usage:

```bash
sqlite3 runtime/saveany.db "select period_type,period_key,question_count from usage_periods where user_id='USER_ID' and period_type='month';"
```

Expected:

```text
month|YYYY-MM|10
```

- [ ] **Step 7: Final status**

Run:

```bash
git status --short
```

Expected:

```text
no uncommitted changes from this implementation
```

If unrelated pre-existing changes are present, list them separately and do not revert them.

---

## Self-Review Notes

- Spec coverage:
  - Free 10/month and Pro 200/month are covered in Task 1 and Task 2.
  - Pre-model quota blocking is covered in Task 2.
  - Failure refund is covered in Task 2.
  - Frontend display and real-time usage update are covered in Task 3 and Task 4.
  - Browser verification is covered in Task 5.
- Placeholder scan:
  - No placeholder markers or unspecified implementation steps are intended in this plan.
- Type consistency:
  - Backend uses `question_monthly_limit`, `MeterType.QUESTION`, and `usage_periods.question_count`.
  - Frontend uses meter key `"question"` consistently.
