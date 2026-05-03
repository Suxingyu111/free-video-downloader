import assert from "node:assert/strict";
import test from "node:test";

import { diffSummaryStreamLines, normalizeSummaryStreamLines } from "../src/utils/summaryStream.js";

test("normalizeSummaryStreamLines trims empty lines and keeps the latest bounded lines", () => {
  const lines = normalizeSummaryStreamLines(" \n一句话概览：内容\n\n- 第一行\n- 第二行\n", { maxLines: 2 });

  assert.deepEqual(lines, ["- 第一行", "- 第二行"]);
});

test("normalizeSummaryStreamLines splits long readable lines for steady reveal", () => {
  const text = "一句话概览：这是一段很长的 AI 总结预览内容，需要拆成多行逐步显示，让用户在等待完整总结时持续看到可读内容。";
  const lines = normalizeSummaryStreamLines(
    text,
    { maxLines: 10, maxLineLength: 24 }
  );

  assert.equal(lines.length, 3);
  assert.equal(lines.join(""), text);
  assert.equal(lines.every((line) => line.length <= 24), true);
  assert.match(lines[0], /AI 总结预览内容，$/);
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
