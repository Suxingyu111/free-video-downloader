import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const mainCss = readFileSync(new URL("../src/assets/main.css", import.meta.url), "utf8");

test("analyzing a video automatically starts the AI summary task", () => {
  assert.match(appSource, /startSummaryForResult\(result,\s*\{\s*mode:\s*"auto"\s*\}\)/);
  assert.match(appSource, /async function startSummaryForResult/);
  assert.doesNotMatch(appSource, /@click="handleSummary"/);
});

test("video details and AI summary use a left-narrow right-wide workbench layout", () => {
  assert.match(appSource, /class="analysis-workbench"/);
  assert.match(appSource, /class="video-column"/);
  assert.match(appSource, /class="summary-column"/);
  assert.match(appSource, /自动总结中|正在自动总结/);
  assert.match(appSource, /重新总结|重试总结/);
  assert.match(mainCss, /\.analysis-workbench\s*\{/);
  assert.match(mainCss, /grid-template-columns:\s*minmax\(280px,\s*0\.78fr\)\s+minmax\(0,\s*1\.42fr\)/);
  assert.match(mainCss, /@media \(max-width:\s*920px\)[\s\S]*\.analysis-workbench[\s\S]*grid-template-columns:\s*1fr/);
});
