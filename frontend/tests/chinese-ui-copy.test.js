import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const authSessionSource = readFileSync(new URL("../src/services/authSession.js", import.meta.url), "utf8");
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
const membershipSource = `${appSource}\n${authSessionSource}`;

test("home page copy is Chinese-first and explains the universal downloader", () => {
  const requiredPhrases = [
    "万能视频下载器",
    "复制链接，一键保存高清视频",
    "支持 YouTube、Bilibili、TikTok、Instagram 等主流平台",
    "粘贴视频链接，自动解析标题、封面、清晰度和音频",
    "解析视频",
    "立即下载",
    "AI 总结",
    "快速版",
    "完整总结正在完善中",
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

test("membership UI exposes account billing and quota copy", () => {
  const requiredPhrases = [
    "登录 / 注册",
    "邮箱",
    "密码",
    "忘记密码",
    "重置密码",
    "退出登录",
    "免费版",
    "Pro 个人版",
    "¥19",
    "120 次 AI 总结",
    "600 分钟语音转写",
    "总结小包",
    "转写小包",
    "今日还可免费总结",
    "今天的访客解析次数已用完",
    "语音转写还剩",
    "查看套餐方案",
    "管理订阅",
    "正在确认会员状态",
    "当前已开通",
    "当前套餐",
    "付款失败，请更新支付方式",
    "已取消续费，本周期内仍可使用",
    "支付已返回，仍在等待 Stripe 确认",
    "模拟开通",
    "模拟取消",
    "模拟过期",
    "模拟付款失败"
  ];

  for (const phrase of requiredPhrases) {
    assert.match(membershipSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.doesNotMatch(appSource, /团队版|团队协作|¥99/);
});
