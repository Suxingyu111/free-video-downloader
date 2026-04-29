import assert from "node:assert/strict";
import test from "node:test";

import {
  buildQaMarkdown,
  buildSafeSummaryFilename,
  buildSummaryMarkdown,
  buildTranscriptText
} from "../src/services/summaryExports.js";

const completedSummary = {
  title: "测试视频 / 入门:AI?",
  overview: "这是总览。",
  outline: ["第一章：背景", "第二章：实践"],
  key_points: ["重点 A", "重点 B"],
  highlights: [
    { timestamp: "00:12", text: "重要片段" },
    "没有时间戳的亮点"
  ],
  terms: [
    { term: "Token", definition: "模型处理的文本单位" },
    "上下文窗口"
  ],
  questions: [
    { question: "适合谁？", answer: "适合初学者。" },
    "下一步学什么？"
  ]
};

test("buildSafeSummaryFilename keeps Chinese text and removes dangerous characters", () => {
  assert.equal(
    buildSafeSummaryFilename("测试视频 / 入门:AI?", "summary", "md"),
    "测试视频 入门AI-summary.md"
  );
});

test("buildSafeSummaryFilename falls back when title is empty after trimming", () => {
  assert.equal(buildSafeSummaryFilename("   ", "transcript", "txt"), "video-summary-transcript.txt");
});

test("buildSummaryMarkdown includes summary learning sections", () => {
  const markdown = buildSummaryMarkdown(completedSummary);

  assert.match(markdown, /^# 测试视频 \/ 入门:AI\?/);
  assert.match(markdown, /## 总览\n\n这是总览。/);
  assert.match(markdown, /## 大纲\n\n- 第一章：背景\n- 第二章：实践/);
  assert.match(markdown, /## 关键要点\n\n- 重点 A\n- 重点 B/);
  assert.match(markdown, /## 高光片段\n\n- \[00:12\] 重要片段\n- 没有时间戳的亮点/);
  assert.match(markdown, /## 术语表\n\n- \*\*Token\*\*：模型处理的文本单位\n- 上下文窗口/);
  assert.match(markdown, /## 延伸问题\n\n- \*\*适合谁？\*\* 适合初学者。\n- 下一步学什么？/);
});

test("buildTranscriptText prefers transcript segments over full transcript text", () => {
  const transcript = buildTranscriptText({
    transcript_text: "完整字幕 fallback",
    transcript_segments: [
      { start: "00:01", text: "第一句" },
      { timestamp: "00:04", text: "第二句" }
    ]
  });

  assert.equal(transcript, "[00:01] 第一句\n[00:04] 第二句");
});

test("buildTranscriptText falls back to transcript text and then empty copy", () => {
  assert.equal(buildTranscriptText({ transcript_text: "完整字幕" }), "完整字幕");
  assert.equal(buildTranscriptText({}), "暂无字幕文本");
});

test("buildQaMarkdown merges generated pairs before local history", () => {
  const markdown = buildQaMarkdown(
    {
      title: "AI 课程",
      qa_pairs: [
        { question: "生成问题？", answer: "生成回答。" }
      ]
    },
    [
      { question: "追问？", answer: "追问回答。" }
    ]
  );

  assert.match(markdown, /^# AI 课程 - AI 问答/);
  assert.match(markdown, /## 1\. 生成问题？\n\n生成回答。\n\n## 2\. 追问？\n\n追问回答。/);
});

test("buildQaMarkdown returns empty copy when there are no questions", () => {
  assert.equal(buildQaMarkdown({}, []), "# AI 问答\n\n暂无问答内容");
});
