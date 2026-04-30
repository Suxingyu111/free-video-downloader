import assert from "node:assert/strict";
import test from "node:test";

import { diffSummaryStreamLines, normalizeSummaryStreamLines } from "../src/utils/summaryStream.js";

test("normalizeSummaryStreamLines trims empty lines and keeps the latest bounded lines", () => {
  const lines = normalizeSummaryStreamLines(" \n一句话概览：内容\n\n- 第一行\n- 第二行\n", { maxLines: 2 });

  assert.deepEqual(lines, ["- 第一行", "- 第二行"]);
});

test("diffSummaryStreamLines returns only the newly appended stream lines", () => {
  assert.deepEqual(diffSummaryStreamLines(["一句话概览：A", "章节大纲："], ["一句话概览：A", "章节大纲：", "- B"]), ["- B"]);
});

test("diffSummaryStreamLines handles rolling stream windows without duplicating visible lines", () => {
  assert.deepEqual(diffSummaryStreamLines(["A", "B", "C"], ["B", "C", "D", "E"]), ["D", "E"]);
});

test("diffSummaryStreamLines treats a rewritten preview as a fresh line sequence", () => {
  assert.deepEqual(diffSummaryStreamLines(["旧概览"], ["新概览", "章节大纲："]), ["新概览", "章节大纲："]);
});
