import assert from "node:assert/strict";
import test from "node:test";

import * as api from "../src/services/api.js";
import {
  askSummaryQuestion,
  connectSummaryEvents,
  createDownloadTask,
  createBillingCheckout,
  createBillingPortal,
  createSummaryTask,
  getBillingStatus,
  getEntitlementStatus,
  getMe,
  getSummary,
  loginAccount,
  logoutAccount,
  registerAccount,
  requestPasswordReset,
  confirmPasswordReset
} from "../src/services/api.js";


test("createSummaryTask posts to summary API", async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return {
      ok: true,
      json: async () => ({ summary_id: "summary_123" })
    };
  };

  const result = await createSummaryTask({ url: "https://example.com/video", title: "Demo", language: "zh-CN", force: true });

  assert.deepEqual(result, { summary_id: "summary_123" });
  assert.equal(calls[0][0], "/api/summaries");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].credentials, "include");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    url: "https://example.com/video",
    title: "Demo",
    language: "zh-CN",
    force: true
  });
});


test("auth API helpers include browser credentials", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return {
      ok: true,
      json: async () => ({ ok: true, user: { email: "user@example.com" } })
    };
  };

  await getMe();
  await registerAccount({ email: "user@example.com", password: "password-123" });
  await loginAccount({ email: "user@example.com", password: "password-123" });
  await logoutAccount();
  await requestPasswordReset({ email: "user@example.com" });
  await confirmPasswordReset({ token: "reset-token", password: "password-456" });

  assert.deepEqual(
    calls.map(([url]) => url),
    [
      "/api/me",
      "/api/csrf",
      "/api/auth/register",
      "/api/csrf",
      "/api/auth/login",
      "/api/auth/logout",
      "/api/csrf",
      "/api/auth/password-reset/request",
      "/api/csrf",
      "/api/auth/password-reset/confirm"
    ]
  );
  assert.equal(calls.every(([, options]) => options.credentials === "include"), true);
});


test("auth helpers attach CSRF tokens for browser login flow", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    if (url === "/api/csrf") {
      return jsonResponse({ csrf_token: "prelogin-csrf" });
    }
    if (url === "/api/auth/register") {
      assert.equal(options.headers["x-csrf-token"], "prelogin-csrf");
      return jsonResponse({ user: { email: "user@example.com" }, csrf_token: "session-csrf" });
    }
    if (url === "/api/auth/logout") {
      assert.equal(options.headers["x-csrf-token"], "session-csrf");
      return jsonResponse({ ok: true });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  await registerAccount({ email: "user@example.com", password: "password-123" });
  await logoutAccount();

  assert.deepEqual(
    calls.map(([url]) => url),
    ["/api/csrf", "/api/auth/register", "/api/auth/logout"]
  );
});


test("session mutation helpers send the latest session CSRF token", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    if (url === "/api/csrf") {
      return jsonResponse({ csrf_token: "prelogin-csrf" });
    }
    if (url === "/api/auth/login") {
      return jsonResponse({ user: { email: "user@example.com" }, csrf_token: "session-csrf-new" });
    }
    if (url === "/api/summaries") {
      assert.equal(options.headers["x-csrf-token"], "session-csrf-new");
      return jsonResponse({ summary_id: "summary_123" });
    }
    if (url === "/api/summaries/summary_123/questions") {
      assert.equal(options.headers["x-csrf-token"], "session-csrf-new");
      return jsonResponse({ answer: "回答内容" });
    }
    if (url === "/api/billing/checkout") {
      assert.equal(options.headers["x-csrf-token"], "session-csrf-new");
      return jsonResponse({ mode: "stripe", url: "https://checkout.stripe.test" });
    }
    if (url === "/api/billing/portal") {
      assert.equal(options.headers["x-csrf-token"], "session-csrf-new");
      return jsonResponse({ mode: "stripe", url: "https://billing.stripe.test" });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  await loginAccount({ email: "user@example.com", password: "password-123" });
  await createSummaryTask({ url: "https://example.com/video", title: "Demo", language: "zh-CN" });
  await askSummaryQuestion("summary_123", { question: "讲了什么？", language: "zh-CN" });
  await createBillingCheckout();
  await createBillingPortal();

  assert.deepEqual(
    calls.map(([url]) => url),
    [
      "/api/csrf",
      "/api/auth/login",
      "/api/summaries",
      "/api/summaries/summary_123/questions",
      "/api/billing/checkout",
      "/api/billing/portal"
    ]
  );
});

test("getMe stores recovered session CSRF token for later mutations", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    if (url === "/api/me") {
      return jsonResponse({ user: { email: "user@example.com" }, csrf_token: "recovered-session-csrf" });
    }
    if (url === "/api/summaries") {
      assert.equal(options.headers["x-csrf-token"], "recovered-session-csrf");
      return jsonResponse({ summary_id: "summary_456" });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  await getMe();
  await createSummaryTask({ url: "https://example.com/video", title: "Demo", language: "zh-CN" });

  assert.deepEqual(
    calls.map(([url]) => url),
    ["/api/me", "/api/summaries"]
  );
});


test("billing API helpers include browser credentials", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return {
      ok: true,
      json: async () => ({ mode: "stripe", url: "https://checkout.stripe.test" })
    };
  };

  await getBillingStatus();
  await createBillingCheckout();
  await createBillingPortal();

  assert.deepEqual(
    calls.map(([url]) => url),
    ["/api/billing/status", "/api/billing/checkout", "/api/billing/portal"]
  );
  assert.equal(calls.every(([, options]) => options.credentials === "include"), true);
});


test("billing API does not expose mock billing helpers", () => {
  assert.equal("mockBillingAction" in api, false);
});


test("createBillingCheckout sends the current app return origin", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return {
      ok: true,
      json: async () => ({ mode: "stripe", url: "https://checkout.stripe.test" })
    };
  };

  await createBillingCheckout({ return_url: "http://127.0.0.1:5175" });

  assert.equal(calls[0][0], "/api/billing/checkout");
  assert.equal(calls[0][1].credentials, "include");
  assert.deepEqual(JSON.parse(calls[0][1].body), { return_url: "http://127.0.0.1:5175" });
});


test("getSummary fetches summary snapshot", async () => {
  globalThis.fetch = async (url) => {
    assert.equal(url, "/api/summaries/summary_123");
    return {
      ok: true,
      json: async () => ({ id: "summary_123", status: "completed" })
    };
  };

  assert.deepEqual(await getSummary("summary_123"), { id: "summary_123", status: "completed" });
});


test("askSummaryQuestion posts question to summary API", async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
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
  };

  const result = await askSummaryQuestion("summary_123", { question: "讲了什么？", language: "zh-CN" });

  assert.deepEqual(result, {
    answer: "回答内容",
    usage: {
      meters: {
        question: { limit: 10, used: 1, remaining: 9 }
      }
    }
  });
  assert.equal(calls[0][0], "/api/summaries/summary_123/questions");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(JSON.parse(calls[0][1].body).question, "讲了什么？");
});


test("connectSummaryEvents listens for summary event and closes", () => {
  const listeners = {};
  let closed = false;
  globalThis.EventSource = class FakeEventSource {
    constructor(url) {
      this.url = url;
    }

    addEventListener(name, callback) {
      listeners[name] = callback;
    }

    close() {
      closed = true;
    }
  };

  const snapshots = [];
  const disconnect = connectSummaryEvents("summary_123", (snapshot) => snapshots.push(snapshot));
  listeners.summary({ data: JSON.stringify({ id: "summary_123", status: "completed" }) });
  disconnect();

  assert.deepEqual(snapshots, [{ id: "summary_123", status: "completed" }]);
  assert.equal(closed, true);
});

test("getEntitlementStatus calls quota status endpoint with credentials", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({ plan: "free", meters: {} });
  };

  const result = await getEntitlementStatus();

  assert.equal(result.plan, "free");
  assert.equal(calls[0].url, "/api/entitlements/status");
  assert.equal(calls[0].options.credentials, "include");
});

test("createDownloadTask sends analysis token", async () => {
  let body = null;
  globalThis.fetch = async (_url, options = {}) => {
    body = JSON.parse(options.body);
    return jsonResponse({ task_id: "task_1" });
  };

  await createDownloadTask({
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

function jsonResponse(body) {
  return {
    ok: true,
    json: async () => body
  };
}
