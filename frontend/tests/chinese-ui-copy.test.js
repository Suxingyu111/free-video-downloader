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
    "立即下载"
  ];

  for (const phrase of requiredPhrases) {
    assert.match(appSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.doesNotMatch(appSource, /Free Video Downloader|Paste link|Video download platform/);
});

test("download console exposes cookies txt upload for restricted platforms", () => {
  const requiredPhrases = [
    "cookies.txt",
    "handleCookieFileChange",
    "cookiesFile: state.cookiesFile",
    "accept=\".txt,text/plain\""
  ];

  for (const phrase of requiredPhrases) {
    assert.match(appSource, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});
