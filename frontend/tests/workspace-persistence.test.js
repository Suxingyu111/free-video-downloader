import assert from "node:assert/strict";
import test from "node:test";

import {
  WORKSPACE_STORAGE_KEY,
  applyWorkspaceSnapshot,
  loadWorkspaceSnapshot,
  normalizeWorkspaceSnapshot,
  pickWorkspaceSnapshot,
  saveWorkspaceSnapshot
} from "../src/services/workspacePersistence.js";

test("workspace persistence keeps parsed result and summary task", () => {
  const state = {
    url: "https://example.com/video",
    analyzedUrl: "https://example.com/video",
    selectedFormatId: "best",
    result: { title: "Demo", webpage_url: "https://example.com/video" },
    currentTaskId: "task_1",
    currentSummaryId: "summary_1",
    summaryTask: { id: "summary_1", status: "completed", result: { overview: "Demo" } },
    tasks: [{ id: "task_1", status: "completed" }],
    summaryView: "mindmap",
    summaryQaHistory: [{ question: "讲了什么？", answer: "Demo" }]
  };
  const storage = createMemoryStorage();

  saveWorkspaceSnapshot(pickWorkspaceSnapshot(state), storage);
  const restored = loadWorkspaceSnapshot(storage);

  assert.equal(JSON.parse(storage.getItem(WORKSPACE_STORAGE_KEY)).currentSummaryId, "summary_1");
  assert.deepEqual(restored.result, state.result);
  assert.deepEqual(restored.summaryTask, state.summaryTask);
  assert.equal(restored.summaryView, "mindmap");
});

test("applyWorkspaceSnapshot restores state fields", () => {
  const state = {
    url: "",
    analyzedUrl: "",
    selectedFormatId: "mp4",
    result: null,
    currentTaskId: null,
    currentSummaryId: null,
    summaryTask: null,
    tasks: [],
    summaryView: "summary",
    summaryQaHistory: []
  };

  applyWorkspaceSnapshot(state, {
    url: "https://example.com/video",
    analyzedUrl: "https://example.com/video",
    selectedFormatId: "best",
    result: { title: "Demo" },
    currentTaskId: "task_1",
    currentSummaryId: "summary_1",
    summaryTask: { id: "summary_1", status: "completed" },
    tasks: [{ id: "task_1" }],
    summaryView: "qa",
    summaryQaHistory: [{ question: "Q", answer: "A" }]
  });

  assert.equal(state.url, "https://example.com/video");
  assert.equal(state.currentSummaryId, "summary_1");
  assert.deepEqual(state.summaryTask, { id: "summary_1", status: "completed" });
  assert.equal(state.summaryView, "qa");
});

test("normalizeWorkspaceSnapshot ignores corrupt values", () => {
  const normalized = normalizeWorkspaceSnapshot({
    url: 123,
    result: [],
    currentSummaryId: "",
    summaryTask: "bad",
    tasks: ["bad", { id: "task_1" }],
    summaryView: "bad",
    summaryQaHistory: [{ question: "Q", answer: "A" }, { question: 1, answer: "bad" }]
  });

  assert.equal(normalized.url, "");
  assert.equal(normalized.result, null);
  assert.equal(normalized.currentSummaryId, null);
  assert.deepEqual(normalized.tasks, [{ id: "task_1" }]);
  assert.equal(normalized.summaryView, "summary");
  assert.deepEqual(normalized.summaryQaHistory, [{ question: "Q", answer: "A" }]);
});

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    }
  };
}
