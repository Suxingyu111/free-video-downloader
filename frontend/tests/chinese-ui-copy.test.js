import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");

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
    "总结摘要",
    "字幕文本",
    "思维导图",
    "AI 问答",
    "核心知识点",
    "Markdown"
  ];

  for (const phrase of requiredPhrases) {
    assert.match(appSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
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
  assert.match(appSource, /mindMapBranches/);
  assert.match(appSource, /mind-map-canvas/);
  assert.match(appSource, /mind-map-branch-header/);
  assert.match(appSource, /mind-map-node-list/);
  assert.match(appSource, /mind-map-leaves/);
});
