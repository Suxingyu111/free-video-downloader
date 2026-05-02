# Summary Reparse Usage Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Active user parsing/re-summary actions always create a new AI summary task and count immediately, while refresh recovery only restores persisted content without counting.

**Architecture:** Keep restoration read-only through existing workspace persistence plus `GET /api/summaries/{id}`. Use the existing `force` request flag as the server-side boundary: `force: true` skips cache and reserves quota, while non-forced requests may only reuse completed summaries. Tighten `SummaryStore.get_cached_task` so active tasks are never returned as cache hits.

**Tech Stack:** FastAPI, Python service tests with pytest/TestClient, Vue 3, Vite frontend tests with Node test runner.

---

### Task 1: Backend Cache Boundary And Quota Tests

**Files:**
- Modify: `backend/tests/test_summary_api.py`
- Modify: `backend/app/services/summary_store.py`
- Verify: `backend/tests/test_summary_api.py`

- [ ] **Step 1: Add failing tests for active-task cache bypass and forced reparse counting**

Add these tests to `backend/tests/test_summary_api.py` near the existing cache tests:

```python
def test_non_forced_summary_does_not_reuse_active_task(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    active = isolated_summary_store.create_task(
        "https://example.com/active-cache-video",
        title="Demo",
        language="zh-CN",
        quota_user_id="user_placeholder",
        task_id="summary_active_cache_video",
    )
    isolated_summary_store.update_task(active.id, status="summarizing", stage="summary")

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/active-cache-video", "title": "Demo", "language": "zh-CN"},
    )

    assert response.status_code == 200
    assert response.json()["summary_id"] != active.id
    assert response.json()["cache_hit"] is False
    assert response.json()["usage"]["used_today"] == 1
    assert len(fake.calls) == 1
```

Also extend the existing forced completed-cache test by asserting the second response increments usage and uses a new id:

```python
assert second.json()["summary_id"] != first_summary_id
assert second.json()["cache_hit"] is False
assert second.json()["usage"]["used_today"] == 2
```

- [ ] **Step 2: Run backend test to verify failure**

Run:

```bash
cd backend
pytest tests/test_summary_api.py::test_non_forced_summary_does_not_reuse_active_task tests/test_summary_api.py::test_create_summary_force_skips_completed_cache -q
```

Expected before implementation: the active-task test fails because the existing active task is returned as a cache hit.

- [ ] **Step 3: Implement completed-only cache lookup**

Change `SummaryStore.get_cached_task` in `backend/app/services/summary_store.py`:

```python
    def get_cached_task(self, url: str, *, language: str = "zh-CN") -> SummarySnapshot | None:
        cache_key = build_summary_cache_key(url, language=language)
        with self._lock:
            task_id = self._cache_index.get(cache_key)
            if not task_id:
                return None
            task = self._tasks.get(task_id)
            if task is None or task.status != "completed":
                return None
            return task
```

This keeps non-forced completed cache compatibility while preventing active summary reuse.

- [ ] **Step 4: Run backend cache tests**

Run:

```bash
cd backend
pytest tests/test_summary_api.py::test_non_forced_summary_does_not_reuse_active_task tests/test_summary_api.py::test_create_summary_reuses_completed_file_cache tests/test_summary_api.py::test_cache_hit_does_not_consume_summary_quota tests/test_summary_api.py::test_create_summary_force_skips_completed_cache -q
```

Expected: all selected tests pass.

### Task 2: Frontend Active Summary Request Semantics

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/tests/summary-api.test.js`
- Modify: `frontend/tests/summary-auto-layout.test.js`

- [ ] **Step 1: Add failing frontend API test for active force payload**

In `frontend/tests/summary-api.test.js`, update the existing `createSummaryTask` test so the call includes `force: true` and the posted body is asserted:

```js
const result = await createSummaryTask({ url: "https://example.com/video", title: "Demo", language: "zh-CN", force: true });

assert.deepEqual(JSON.parse(calls[0][1].body), {
  url: "https://example.com/video",
  title: "Demo",
  language: "zh-CN",
  force: true
});
```

In `frontend/tests/summary-auto-layout.test.js`, add an assertion to the automatic summary test:

```js
assert.match(appSource, /force:\s*true/);
assert.doesNotMatch(appSource, /force:\s*mode\s*!==\s*"auto"/);
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend
npm test -- summary-api.test.js summary-auto-layout.test.js
```

Expected before implementation: the source assertion fails because `App.vue` still uses `force: mode !== "auto"`.

- [ ] **Step 3: Make active summary creation always force**

Change `startSummaryForResult` in `frontend/src/App.vue`:

```js
    const summary = await createSummaryTask({
      url: result.webpage_url || state.url.trim(),
      title: result.title,
      language: "zh-CN",
      force: true
    });
```

This applies to auto-after-parse, manual retry, and explicit re-summary. Recovery remains read-only because `restoreWorkspaceSnapshot` calls `resumePersistedWorkspace`, not `startSummaryForResult`.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd frontend
npm test -- summary-api.test.js summary-auto-layout.test.js workspace-persistence.test.js
```

Expected: selected frontend tests pass.

### Task 3: End-To-End Verification With Browser

**Files:**
- Verify: local app only

- [ ] **Step 1: Run backend and frontend dev servers**

Run backend:

```bash
cd backend
SAVEANY_DEMO_MODE=1 FREE_SUMMARY_DAILY_LIMIT=3 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Expected: backend serves API on `http://127.0.0.1:8000`, frontend serves app on `http://127.0.0.1:5173`.

- [ ] **Step 2: Browser test recovery without counting**

Use the in-app browser or Playwright to:

1. Open `http://127.0.0.1:5173`.
2. Register or log in with a local test account.
3. Enter a demo URL such as `https://demo.saveany.local/video`.
4. Click `解析视频`.
5. Wait until the AI summary appears or reaches a draft/completed state.
6. Record the visible remaining free summary count.
7. Reload the page.
8. Click `恢复工作区`.
9. Confirm the previous summary content appears and the remaining count is unchanged.

Expected: recovery does not create a new summary and usage remains unchanged.

- [ ] **Step 3: Browser test active same-video reparse counts**

Continue in the browser:

1. Keep the same URL in the input.
2. Click `解析视频` again.
3. Wait for the summary area to create a new task.
4. Confirm the remaining free summary count decreases by one.

Expected: active reparse creates a new summary and counts immediately.

### Task 4: Final Regression

**Files:**
- Verify: backend and frontend test suites

- [ ] **Step 1: Run targeted backend suite**

Run:

```bash
cd backend
pytest tests/test_summary_api.py tests/test_entitlements.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run targeted frontend suite**

Run:

```bash
cd frontend
npm test -- summary-api.test.js workspace-persistence.test.js summary-auto-layout.test.js auth-session.test.js
```

Expected: all tests pass.

- [ ] **Step 3: Review diff**

Run:

```bash
git diff -- backend/app/services/summary_store.py backend/tests/test_summary_api.py frontend/src/App.vue frontend/tests/summary-api.test.js frontend/tests/summary-auto-layout.test.js docs/superpowers/plans/2026-05-02-summary-reparse-usage-restore.md
```

Expected: diff is limited to the cache/force behavior, tests, and the implementation plan.
