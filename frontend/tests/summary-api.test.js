import assert from "node:assert/strict";
import test from "node:test";

import { askSummaryQuestion, connectSummaryEvents, createSummaryTask, getSummary } from "../src/services/api.js";


test("createSummaryTask posts to summary API", async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return {
      ok: true,
      json: async () => ({ summary_id: "summary_123" })
    };
  };

  const result = await createSummaryTask({ url: "https://example.com/video", title: "Demo", language: "zh-CN" });

  assert.deepEqual(result, { summary_id: "summary_123" });
  assert.equal(calls[0][0], "/api/summaries");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(JSON.parse(calls[0][1].body).title, "Demo");
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
      json: async () => ({ answer: "回答内容" })
    };
  };

  const result = await askSummaryQuestion("summary_123", { question: "讲了什么？", language: "zh-CN" });

  assert.deepEqual(result, { answer: "回答内容" });
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
