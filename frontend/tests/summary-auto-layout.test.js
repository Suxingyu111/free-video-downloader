import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const mainCss = readFileSync(new URL("../src/assets/main.css", import.meta.url), "utf8");
const summaryPanelSource = readFileSync(new URL("../src/components/summary/SummaryPanel.vue", import.meta.url), "utf8");
const summaryOverviewSource = readFileSync(new URL("../src/components/summary/SummaryOverview.vue", import.meta.url), "utf8");
const summaryMindMapSource = readFileSync(new URL("../src/components/summary/SummaryMindMap.vue", import.meta.url), "utf8");
const summaryCss = readFileSync(new URL("../src/assets/summary.css", import.meta.url), "utf8");

test("analyzing a video automatically starts the AI summary task", () => {
  assert.match(appSource, /startSummaryForResult\(result,\s*\{\s*mode:\s*"auto"\s*\}\)/);
  assert.match(appSource, /async function startSummaryForResult/);
  assert.doesNotMatch(appSource, /@click="handleSummary"/);
});

test("analyzed results appear below the unchanged hero search area", () => {
  assert.doesNotMatch(appSource, /:class="\{\s*'hero-workbench':\s*hasResult\s*\}"/);
  assert.match(appSource, /<p class="hero-copy">粘贴视频链接/);
  assert.doesNotMatch(appSource, /<p v-if="!hasResult" class="hero-copy"/);
  assert.match(appSource, /<form class="search-panel"[\s\S]*<section v-if="hasResult" class="analysis-workbench"/);
  assert.doesNotMatch(mainCss, /\.hero-workbench\b/);
});

test("hero search area uses compact vertical spacing so results enter the first viewport sooner", () => {
  assert.match(mainCss, /\.topbar\s*\{[\s\S]*min-height:\s*76px/);
  assert.match(mainCss, /\.hero\s*\{[\s\S]*min-height:\s*auto/);
  assert.match(mainCss, /\.hero\s*\{[\s\S]*padding:\s*clamp\(24px,\s*4vw,\s*48px\)\s+20px\s+38px/);
  assert.match(mainCss, /\.kicker\s*\{[\s\S]*min-height:\s*34px/);
  assert.match(mainCss, /\.hero h1\s*\{[\s\S]*margin:\s*16px\s+auto\s+0/);
  assert.match(mainCss, /\.hero-copy,\s*\n\.section-copy\s*\{[\s\S]*margin:\s*10px\s+auto\s+0/);
  assert.match(mainCss, /\.console\s*\{[\s\S]*width:\s*min\(85vw,\s*100%\)/);
  assert.match(mainCss, /\.console\s*\{[\s\S]*margin-top:\s*22px/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*width:\s*min\(100%,\s*920px\)/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*margin:\s*0\s+auto/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*gap:\s*8px/);
  assert.match(mainCss, /\.url-field\s*\{[\s\S]*min-height:\s*60px/);
  assert.match(mainCss, /\.quick-row\s*\{[\s\S]*min-height:\s*28px/);
  assert.match(mainCss, /\.analysis-workbench\s*\{[\s\S]*margin-top:\s*10px/);
});

test("top navigation switches between short hash pages instead of one long scrolling page", () => {
  assert.match(appSource, /const pageLinks = \[/);
  assert.match(appSource, /currentPage:\s*"download"/);
  assert.match(appSource, /const currentPage = computed\(\(\) => state\.currentPage\)/);
  assert.match(appSource, /function syncCurrentPageFromHash/);
  assert.match(appSource, /window\.addEventListener\("hashchange", syncCurrentPageFromHash\)/);
  assert.match(appSource, /v-for="link in pageLinks"/);
  assert.match(appSource, /:aria-current="currentPage === link\.id \? 'page' : undefined"/);
  assert.match(appSource, /<section[^>]*id="download"[^>]*v-show="currentPage === 'download'"/);
  assert.match(appSource, /<section[^>]*id="platforms"[^>]*v-if="currentPage === 'platforms'"/);
  assert.match(appSource, /<section[^>]*id="features"[^>]*v-if="currentPage === 'features'"/);
  assert.match(appSource, /<section[^>]*id="pricing"[^>]*v-if="currentPage === 'pricing'"/);
  assert.match(mainCss, /\.nav-links a\[aria-current="page"\]/);
  assert.match(mainCss, /@media \(max-width:\s*760px\)[\s\S]*\.nav-links\s*\{[\s\S]*overflow-x:\s*auto/);
  assert.doesNotMatch(mainCss, /\.nav-links a:not\(\.nav-cta\)[\s\S]*display:\s*none/);
});

test("video details and AI summary use a left-narrow right-wide workbench layout", () => {
  assert.match(appSource, /class="analysis-workbench"/);
  assert.match(appSource, /class="video-column"/);
  assert.match(appSource, /class="summary-column"/);
  assert.match(appSource, /自动总结中|正在自动总结/);
  assert.match(appSource, /重新总结|重试总结/);
  assert.match(mainCss, /\.analysis-workbench\s*\{/);
  assert.match(mainCss, /\.analysis-workbench\s*\{[\s\S]*display:\s*flex/);
  assert.match(mainCss, /\.video-column\s*\{[\s\S]*flex:\s*0\s+1\s+40%/);
  assert.match(mainCss, /\.summary-column\s*\{[\s\S]*flex:\s*1\s+1\s+60%/);
  assert.match(mainCss, /@media \(max-width:\s*920px\)[\s\S]*\.analysis-workbench[\s\S]*flex-direction:\s*column/);
});

test("summary workbench shows module cards before final result and loads selected content", () => {
  assert.match(summaryPanelSource, /class="summary-module-grid"/);
  assert.match(summaryPanelSource, /class="\{ active: summaryView === card\.id \}"/);
  assert.match(summaryPanelSource, /moduleStatus\(card\.id\)/);
  assert.match(summaryPanelSource, /summary-loading-state/);
  assert.doesNotMatch(summaryPanelSource, /<nav v-if="summaryResult" class="summary-tabs"/);
  assert.doesNotMatch(summaryPanelSource, /<div v-if="summaryResult" class="summary-content"/);
  assert.match(summaryOverviewSource, /summary-line-reveal/);
  assert.match(summaryCss, /\.summary-module-grid\s*\{/);
  assert.match(summaryCss, /@keyframes summaryLineReveal/);
});

test("summary workbench does not render progress bars or percentage counters", () => {
  assert.doesNotMatch(summaryPanelSource, /summary-progress/);
  assert.doesNotMatch(summaryPanelSource, /summaryProgressValue/);
  assert.doesNotMatch(summaryPanelSource, /progress-fill/);
  assert.doesNotMatch(summaryPanelSource, /progressWidth/);
  assert.doesNotMatch(summaryPanelSource, /Math\.round\(summaryProgressValue\)/);
  assert.doesNotMatch(summaryCss, /\.summary-progress\s*\{/);
  assert.doesNotMatch(summaryCss, /\.summary-tabs\s*\{/);
  assert.doesNotMatch(appSource, /summary-progress-value/);
});

test("summary module cards and loading state use compact professional controls", () => {
  assert.match(summaryPanelSource, /class="summary-module-card"/);
  assert.match(summaryPanelSource, /class="summary-module-icon"/);
  assert.match(summaryPanelSource, /class="summary-status-pill"/);
  assert.match(summaryPanelSource, /class="summary-loading-shell"/);
  assert.match(summaryPanelSource, /revealedStreamLines/);
  assert.match(summaryPanelSource, /summary-stream-preview/);
  assert.match(summaryPanelSource, /summary-loading-bars/);
  assert.match(summaryCss, /\.summary-module-grid\s*\{[\s\S]*gap:\s*10px/);
  assert.match(summaryCss, /\.summary-card\s*\{[\s\S]*gap:\s*14px/);
  assert.match(summaryCss, /\.summary-card\s*\{[\s\S]*padding:\s*18px/);
  assert.match(summaryCss, /\.summary-module-card\s*\{[\s\S]*min-height:\s*76px/);
  assert.match(summaryCss, /\.summary-module-card\s*\{[\s\S]*padding:\s*10px/);
  assert.match(summaryCss, /\.summary-loading-state\s*\{[\s\S]*min-height:\s*220px/);
  assert.match(summaryCss, /\.summary-status-pill\s*\{/);
  assert.match(summaryCss, /\.summary-loading-shell\s*\{/);
  assert.match(summaryCss, /\.summary-stream-preview\s*\{/);
  assert.match(summaryCss, /@media \(max-width:\s*760px\)[\s\S]*\.summary-module-grid[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
});

test("summary streaming preview reveals generated lines incrementally", () => {
  assert.match(summaryPanelSource, /normalizeSummaryStreamLines/);
  assert.match(summaryPanelSource, /diffSummaryStreamLines/);
  assert.match(summaryPanelSource, /revealedStreamLines/);
  assert.match(summaryPanelSource, /streamRevealQueue/);
  assert.match(summaryPanelSource, /window\.setTimeout\(revealNextStreamLine,\s*STREAM_LINE_REVEAL_MS\)/);
  assert.match(summaryPanelSource, /v-for="\(\s*line,\s*index\s*\) in revealedStreamLines"/);
});

test("mind map view exposes zoom controls and fit-to-screen rendering", () => {
  assert.match(summaryMindMapSource, /calculateMindMapFitZoom/);
  assert.match(summaryMindMapSource, /getMindMapSvgSize/);
  assert.match(summaryMindMapSource, /zoomIn/);
  assert.match(summaryMindMapSource, /zoomOut/);
  assert.match(summaryMindMapSource, /fitInlineMap/);
  assert.match(summaryMindMapSource, /fitFullscreenMap/);
  assert.match(summaryMindMapSource, /minZoom:\s*0\.12/);
  assert.match(summaryMindMapSource, /class="mind-map-zoom-controls"/);
  assert.match(summaryMindMapSource, /:style="canvasStyle/);
  assert.match(summaryCss, /\.mind-map-canvas\s*\{/);
  assert.match(summaryCss, /\.mind-map-overlay\s*\{[\s\S]*inset:\s*0/);
  assert.match(summaryCss, /\.mind-map-overlay-body\s*\{[\s\S]*place-items:\s*center/);
});
