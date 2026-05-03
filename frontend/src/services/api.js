export async function analyzeUrl({ url }) {
  const form = new FormData();
  form.append("url", url);

  const response = await fetch("/api/analyze", {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function createDownloadTask(payload) {
  const response = await fetch("/api/download", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function createSummaryTask(payload) {
  const response = await fetch("/api/summaries", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-csrf-token": sessionCsrfToken()
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function getMe() {
  const response = await fetch("/api/me", { credentials: "include" });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function registerAccount(payload) {
  return postJson("/api/auth/register", payload, { csrf: "prelogin", captureSessionCsrf: true });
}

export async function loginAccount(payload) {
  return postJson("/api/auth/login", payload, { csrf: "prelogin", captureSessionCsrf: true });
}

export async function logoutAccount() {
  return postJson("/api/auth/logout", undefined, { csrf: "session", clearSessionCsrf: true });
}

export async function requestPasswordReset(payload) {
  return postJson("/api/auth/password-reset/request", payload, { csrf: "prelogin" });
}

export async function confirmPasswordReset(payload) {
  return postJson("/api/auth/password-reset/confirm", payload, { csrf: "prelogin" });
}

export async function getBillingStatus() {
  const response = await fetch("/api/billing/status", { credentials: "include" });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function getEntitlementStatus() {
  const response = await fetch("/api/entitlements/status", { credentials: "include" });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function createBillingCheckout(payload) {
  return postJson("/api/billing/checkout", payload, { csrf: "session" });
}

export async function confirmBillingCheckout(sessionId) {
  return postJson("/api/billing/checkout/confirm", { session_id: sessionId }, { csrf: "session" });
}

export async function createBillingPortal() {
  return postJson("/api/billing/portal", undefined, { csrf: "session" });
}

export async function getTask(taskId) {
  const response = await fetch(`/api/tasks/${taskId}`);

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function getSummary(summaryId) {
  const response = await fetch(`/api/summaries/${summaryId}`);

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export async function askSummaryQuestion(summaryId, payload) {
  const response = await fetch(`/api/summaries/${summaryId}/questions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-csrf-token": sessionCsrfToken()
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
}

export function connectTaskEvents(taskId, onTask, onError) {
  const source = new EventSource(`/api/tasks/${taskId}/events`);

  source.addEventListener("task", (event) => {
    onTask(JSON.parse(event.data));
  });

  source.addEventListener("error", () => {
    onError?.("任务进度连接中断，请刷新任务状态。");
    source.close();
  });

  return () => source.close();
}

export function connectSummaryEvents(summaryId, onSummary, onError) {
  const source = new EventSource(`/api/summaries/${summaryId}/events`);

  source.addEventListener("summary", (event) => {
    onSummary(JSON.parse(event.data));
  });

  source.addEventListener("error", () => {
    onError?.("AI 总结进度连接中断，请刷新状态。");
    source.close();
  });

  return () => source.close();
}

async function readApiError(response) {
  try {
    const data = await response.json();
    return data.detail || "请求失败";
  } catch {
    return "请求失败";
  }
}

const SESSION_CSRF_STORAGE_KEY = "saveany_session_csrf";
let currentSessionCsrfToken = "";

function csrfStorage() {
  try {
    return globalThis.sessionStorage || globalThis.window?.sessionStorage || null;
  } catch {
    return null;
  }
}

function sessionCsrfToken() {
  if (currentSessionCsrfToken) return currentSessionCsrfToken;
  const stored = csrfStorage()?.getItem(SESSION_CSRF_STORAGE_KEY) || "";
  currentSessionCsrfToken = stored;
  return currentSessionCsrfToken;
}

function storeSessionCsrfToken(token) {
  currentSessionCsrfToken = token || "";
  const storage = csrfStorage();
  if (!storage) return;
  if (currentSessionCsrfToken) {
    storage.setItem(SESSION_CSRF_STORAGE_KEY, currentSessionCsrfToken);
  } else {
    storage.removeItem(SESSION_CSRF_STORAGE_KEY);
  }
}

async function preloginCsrfToken() {
  const response = await fetch("/api/csrf", { credentials: "include" });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }
  const payload = await response.json();
  return payload.csrf_token || "";
}

async function postJson(url, payload, { csrf = "none", captureSessionCsrf = false, clearSessionCsrf = false } = {}) {
  const options = {
    method: "POST",
    credentials: "include"
  };
  const headers = {};
  if (payload !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  if (csrf === "prelogin") headers["x-csrf-token"] = await preloginCsrfToken();
  if (csrf === "session") headers["x-csrf-token"] = sessionCsrfToken();
  if (Object.keys(headers).length) options.headers = headers;

  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await readApiError(response);
    const apiError = new Error(error);
    apiError.status = response.status;
    throw apiError;
  }
  const data = await response.json();
  if (captureSessionCsrf) storeSessionCsrfToken(data.csrf_token || "");
  if (clearSessionCsrf) storeSessionCsrfToken("");
  return data;
}
