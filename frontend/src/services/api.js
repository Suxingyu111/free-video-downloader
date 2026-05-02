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
      "Content-Type": "application/json"
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
  return postJson("/api/auth/register", payload);
}

export async function loginAccount(payload) {
  return postJson("/api/auth/login", payload);
}

export async function logoutAccount() {
  return postJson("/api/auth/logout");
}

export async function requestPasswordReset(payload) {
  return postJson("/api/auth/password-reset/request", payload);
}

export async function confirmPasswordReset(payload) {
  return postJson("/api/auth/password-reset/confirm", payload);
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
  return postJson("/api/billing/checkout", payload);
}

export async function confirmBillingCheckout(sessionId) {
  return postJson("/api/billing/checkout/confirm", { session_id: sessionId });
}

export async function createBillingPortal() {
  return postJson("/api/billing/portal");
}

export async function mockBillingAction(action) {
  return postJson(`/api/billing/mock/${action}`);
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

async function postJson(url, payload) {
  const options = {
    method: "POST",
    credentials: "include"
  };
  if (payload !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }

  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await readApiError(response);
    const apiError = new Error(error);
    apiError.status = response.status;
    throw apiError;
  }
  return response.json();
}
