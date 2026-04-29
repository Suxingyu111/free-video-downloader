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
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error);
  }

  return response.json();
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
