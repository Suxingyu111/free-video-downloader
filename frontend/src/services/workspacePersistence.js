export const WORKSPACE_STORAGE_KEY = "saveany.workspace.v1";

const MAX_PERSISTED_TASKS = 5;
const SUMMARY_VIEWS = new Set(["summary", "transcript", "mindmap", "qa"]);

export function pickWorkspaceSnapshot(state) {
  return {
    url: state.url || "",
    analyzedUrl: state.analyzedUrl || "",
    selectedFormatId: state.selectedFormatId || "",
    result: state.result || null,
    currentTaskId: state.currentTaskId || null,
    currentSummaryId: state.currentSummaryId || null,
    summaryTask: state.summaryTask || null,
    tasks: Array.isArray(state.tasks) ? state.tasks.slice(0, MAX_PERSISTED_TASKS) : [],
    summaryView: state.summaryView || "summary",
    summaryQaHistory: Array.isArray(state.summaryQaHistory) ? state.summaryQaHistory.slice(0, 20) : []
  };
}

export function applyWorkspaceSnapshot(state, snapshot) {
  if (!snapshot) return;
  state.url = snapshot.url;
  state.analyzedUrl = snapshot.analyzedUrl;
  state.selectedFormatId = snapshot.selectedFormatId || state.selectedFormatId;
  state.result = snapshot.result;
  state.currentTaskId = snapshot.currentTaskId;
  state.currentSummaryId = snapshot.currentSummaryId;
  state.summaryTask = snapshot.summaryTask;
  state.tasks = snapshot.tasks;
  state.summaryView = snapshot.summaryView;
  state.summaryQaHistory = snapshot.summaryQaHistory;
}

export function loadWorkspaceSnapshot(storage = getStorage()) {
  if (!storage) return null;
  try {
    return normalizeWorkspaceSnapshot(JSON.parse(storage.getItem(WORKSPACE_STORAGE_KEY) || "null"));
  } catch {
    return null;
  }
}

export function saveWorkspaceSnapshot(snapshot, storage = getStorage()) {
  if (!storage) return;
  try {
    storage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(normalizeWorkspaceSnapshot(snapshot) || {}));
  } catch {
    // Storage may be disabled or full; the app should keep working without persistence.
  }
}

export function normalizeWorkspaceSnapshot(value) {
  if (!isPlainObject(value)) return null;

  const tasks = Array.isArray(value.tasks) ? value.tasks.filter(isPlainObject).slice(0, MAX_PERSISTED_TASKS) : [];
  const summaryQaHistory = Array.isArray(value.summaryQaHistory)
    ? value.summaryQaHistory
        .filter((item) => isPlainObject(item) && typeof item.question === "string" && typeof item.answer === "string")
        .slice(0, 20)
    : [];

  return {
    url: asString(value.url),
    analyzedUrl: asString(value.analyzedUrl),
    selectedFormatId: asString(value.selectedFormatId),
    result: isPlainObject(value.result) ? value.result : null,
    currentTaskId: asNullableString(value.currentTaskId),
    currentSummaryId: asNullableString(value.currentSummaryId),
    summaryTask: isPlainObject(value.summaryTask) ? value.summaryTask : null,
    tasks,
    summaryView: SUMMARY_VIEWS.has(value.summaryView) ? value.summaryView : "summary",
    summaryQaHistory
  };
}

function getStorage() {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

function asString(value) {
  return typeof value === "string" ? value : "";
}

function asNullableString(value) {
  return typeof value === "string" && value ? value : null;
}

function isPlainObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
