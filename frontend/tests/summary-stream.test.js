import assert from "node:assert/strict";
import test from "node:test";

import {
  diffSummaryStreamLines,
  normalizeSummaryStreamLines,
  normalizeSummaryStreamPreview
} from "../src/utils/summaryStream.js";

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

test("normalizeSummaryStreamPreview keeps growing sentence as one replaceable draft", () => {
  const preview = normalizeSummaryStreamPreview(
    [
      "一句话",
      "一句话结论：视频推测，",
      "一句话结论：视频推测，如果梅西在东京访问期间前往被称为“三田新地”"
    ].at(-1)
  );

  assert.deepEqual(preview.stableLines, []);
  assert.equal(preview.draftLine, "一句话结论：视频推测，如果梅西在东京访问期间前往被称为“三田新地”");
});

test("normalizeSummaryStreamPreview separates completed lines from current draft", () => {
  const preview = normalizeSummaryStreamPreview(
    "一句话结论：这是完整结论。\n这条视频到底讲什么：\n- 第一条正在生成，",
    { maxStableLines: 4 }
  );

  assert.deepEqual(preview.stableLines, ["一句话结论：这是完整结论。", "这条视频到底讲什么："]);
  assert.equal(preview.draftLine, "- 第一条正在生成，");
});

test("normalizeSummaryStreamPreview keeps the headline even when older lines roll off", () => {
  const preview = normalizeSummaryStreamPreview(
    [
      "一句话结论：这是不能被滚动挤掉的核心结论。",
      "背景/问题：",
      "- 第一条。",
      "- 第二条。",
      "- 第三条。",
      "- 第四条。",
      "- 第五条。"
    ].join("\n"),
    { maxStableLines: 3 }
  );

  assert.equal(preview.headline, "这是不能被滚动挤掉的核心结论。");
  assert.deepEqual(preview.bodyLines, ["- 第三条。", "- 第四条。", "- 第五条。"]);
});
