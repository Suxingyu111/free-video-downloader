import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const summarySource = [
  "../src/components/summary/SummaryPanel.vue",
  "../src/components/summary/SummaryOverview.vue",
  "../src/components/summary/SummaryTranscript.vue",
  "../src/components/summary/SummaryMindMap.vue",
  "../src/components/summary/SummaryQa.vue"
]
  .map((path) => readFileSync(new URL(path, import.meta.url), "utf8"))
  .join("\n");
const uiSource = `${appSource}\n${summarySource}`;

test("home page copy is Chinese-first and explains the universal downloader", () => {
  const requiredPhrases = [
    "万能视频下载器",
    "复制链接，一键保存高清视频",
    "支持 YouTube、Bilibili、TikTok、Instagram 等主流平台",
    "粘贴视频链接，自动解析标题、封面、清晰度和音频",
    "解析视频",
    "立即下载",
    "AI 总结",
    "视频学习笔记",
    "总结内容",
    "字幕文本",
    "思维导图",
    "AI 问答",
    "核心知识点",
    "Markdown",
    "下载总结",
    "下载字幕",
    "PNG",
    "SVG",
    "全屏",
    "下载问答"
  ];

  for (const phrase of requiredPhrases) {
    assert.match(uiSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.doesNotMatch(appSource, /Free Video Downloader|Paste link|Video download platform/);
});

test("download console does not expose manual cookie input", () => {
  const forbiddenPhrases = [
    "cookies.txt",
    "handleCookieFileChange",
    "cookiesFile",
    "accept=\".txt,text/plain\"",
    "type=\"file\""
  ];

  for (const phrase of forbiddenPhrases) {
    assert.doesNotMatch(appSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("douyin copy promises public video support without asking for cookies", () => {
  assert.match(appSource, /抖音公开视频免登录下载/);
  assert.match(appSource, /受平台风控影响，少数链接可能失败/);
  assert.doesNotMatch(appSource, /抖音[^。；\n]*cookies/i);
  assert.doesNotMatch(appSource, /抖音[^。；\n]*登录态/);
});

test("mind map view keeps hierarchy and distinct visual structure", () => {
  assert.match(summarySource, /renderMindMapSvg/);
  assert.match(summarySource, /mind-map-viewport/);
  assert.match(summarySource, /mind-map-overlay/);
  assert.match(summarySource, /下载思维导图 PNG/);
  assert.match(summarySource, /下载思维导图 SVG/);
  assert.match(summarySource, /全屏查看思维导图/);
});
