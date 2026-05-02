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
  assert.match(appSource, /force:\s*true/);
  assert.doesNotMatch(appSource, /force:\s*mode\s*!==\s*"auto"/);
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
  assert.match(mainCss, /\.console\s*\{[\s\S]*width:\s*min\(100%,\s*1180px\)/);
  assert.match(mainCss, /\.console\s*\{[\s\S]*margin-top:\s*22px/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*width:\s*min\(100%,\s*920px\)/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*margin:\s*0\s+auto/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*gap:\s*8px/);
  assert.match(mainCss, /\.url-field\s*\{[\s\S]*min-height:\s*60px/);
  assert.match(mainCss, /\.quick-row\s*\{[\s\S]*min-height:\s*28px/);
  assert.match(mainCss, /\.analysis-workbench\s*\{[\s\S]*margin-top:\s*10px/);
});

test("top navigation scrolls to homepage sections while pricing remains a separate page", () => {
  assert.match(appSource, /const pageLinks = \[/);
  assert.match(appSource, /const HOME_PAGE_ID = "download"/);
  assert.match(appSource, /const PRICING_PAGE_ID = "pricing"/);
  assert.match(appSource, /const HOME_DOWNLOAD_ANCHOR_ID = "download-console"/);
  assert.match(appSource, /const homeAnchorIds = pageLinks\.filter/);
  assert.match(appSource, /label:\s*"回到下载"/);
  assert.match(appSource, /label:\s*"核心能力"/);
  assert.match(appSource, /label:\s*"套餐方案"/);
  assert.match(appSource, /currentPage:\s*"download"/);
  assert.match(appSource, /activeAnchor:\s*""/);
  assert.match(appSource, /const currentPage = computed\(\(\) => state\.currentPage\)/);
  assert.match(appSource, /function syncCurrentPageFromHash/);
  assert.match(appSource, /window\.addEventListener\("hashchange", syncCurrentPageFromHash\)/);
  assert.match(appSource, /window\.addEventListener\("popstate", syncCurrentPageFromHash\)/);
  assert.match(appSource, /v-for="link in pageLinks"/);
  assert.match(appSource, /:aria-current="isNavLinkCurrent\(link\) \? 'page' : undefined"/);
  assert.match(appSource, /@click\.prevent="navigateToNavLink\(link\)"/);
  assert.match(appSource, /<section[^>]*id="download"[^>]*v-show="currentPage === 'download'"/);
  assert.match(appSource, /id="download-console"/);
  assert.match(appSource, /id="home-highlights"/);
  assert.match(appSource, /id="home-faq"/);
  assert.doesNotMatch(appSource, /home-highlights-title/);
  assert.doesNotMatch(appSource, /home-faq-title/);
  assert.doesNotMatch(appSource, /id="home-pricing-preview"/);
  assert.doesNotMatch(appSource, /id="home-use-cases"/);
  assert.doesNotMatch(appSource, /id="home-ai-answers"/);
  assert.doesNotMatch(appSource, /id="home-compliance"/);
  assert.match(appSource, /<section[^>]*id="pricing"[^>]*v-if="currentPage === 'pricing'"/);
  assert.doesNotMatch(appSource, /const modulePages = \[/);
  assert.doesNotMatch(appSource, /<template v-for="module in modulePages"/);
  assert.match(mainCss, /\.nav-links a\[aria-current="page"\]/);
  assert.match(mainCss, /\.nav-cta:hover,\s*\n\.nav-cta:focus-visible,\s*\n\.nav-cta:active,\s*\n\.nav-cta\[aria-current="page"\]\s*\{[\s\S]*color:\s*var\(--color-accent-strong\)/);
  assert.doesNotMatch(mainCss, /\.nav-cta\[aria-current="page"\]\s*\{[^}]*color:\s*#ffffff/);
  assert.match(mainCss, /@media \(max-width:\s*760px\)[\s\S]*\.nav-links\s*\{[\s\S]*overflow-x:\s*auto/);
  assert.doesNotMatch(mainCss, /\.nav-links a:not\(\.nav-cta\)[\s\S]*display:\s*none/);
});

test("global styles use the Industrial Media Console token system", () => {
  for (const token of [
    "--color-bg",
    "--color-surface",
    "--color-elevated",
    "--color-line",
    "--color-text",
    "--color-muted",
    "--color-accent",
    "--color-accent-strong",
    "--color-success",
    "--color-danger",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
    "--radius-xl",
    "--shadow-sm",
    "--shadow-md",
    "--shadow-lg",
    "--space-2",
    "--space-3",
    "--space-4",
    "--space-5",
    "--space-6",
    "--space-8",
    "--font-body",
    "--font-label"
  ]) {
    assert.match(mainCss, new RegExp(`${token}:`));
  }

  assert.doesNotMatch(mainCss, /--primary:/);
  assert.doesNotMatch(mainCss, /--bg:/);
  assert.doesNotMatch(summaryCss, /--summary-/);
  assert.doesNotMatch(`${mainCss}\n${summaryCss}`, /#2f7df4|#1f6eea|#f7fbff/);
});

test("homepage capability cards are compact and not navigation targets", () => {
  for (const title of ["公开视频平台", "清晰度可选", "解析后自动总结", "手机浏览器可用"]) {
    assert.match(appSource, new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.match(appSource, /v-for="highlight in homeHighlights"/);
  assert.match(appSource, /class="highlight-card"/);
  assert.match(appSource, /解析并自动总结/);
  assert.match(appSource, /选择清晰度下载/);
  assert.match(appSource, /AI 自动总结/);
  assert.doesNotMatch(appSource, /先完成下载，再把视频整理成笔记/);
  assert.doesNotMatch(appSource, /下载并自动总结/);
  assert.doesNotMatch(appSource, /解析并选择清晰度/);
  assert.doesNotMatch(appSource, /播放列表任务/);
  assert.doesNotMatch(appSource, /长视频与播放列表工作流/);
  assert.doesNotMatch(appSource, /:href="`#\$\{highlight\.id\}`"/);
  assert.doesNotMatch(appSource, /@click\.prevent="navigateToPage\(highlight\.id\)"/);
});

test("pricing page keeps a three-tier package plan while homepage preview is removed", () => {
  assert.match(appSource, /const pricingPlans = \[/);
  assert.match(appSource, /name:\s*"免费版"/);
  assert.match(appSource, /name:\s*"专业版"/);
  assert.match(appSource, /name:\s*"团队版"/);
  assert.match(appSource, /v-for="plan in pricingPlans"/);
  assert.match(appSource, /class="pricing-grid"/);
  assert.match(appSource, /class="plan-feature-list"/);
  assert.match(mainCss, /\.pricing-grid\s*\{[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  assert.doesNotMatch(appSource, /class="home-pricing-preview"/);
  assert.doesNotMatch(appSource, /class="home-plan-card"/);
  assert.doesNotMatch(appSource, /查看完整套餐方案/);
  assert.doesNotMatch(mainCss, /\.home-pricing-grid\s*\{/);
  assert.doesNotMatch(appSource, /每日\s*\d+\s*次解析任务/);
  assert.doesNotMatch(appSource, /任务结果保留\s*\d+\s*天/);
});

test("homepage keeps SEO content compact while static pages own long-form discovery", () => {
  assert.match(appSource, /compactFaqs = seoFaqs\.slice\(0,\s*3\)/);
  assert.match(appSource, /compactCompliancePoints = seoCompliancePoints\.slice\(0,\s*3\)/);
  assert.match(mainCss, /\.home-faq-summary\s*\{/);
  assert.match(mainCss, /\.home-faq-summary\s*\{[\s\S]*width:\s*min\(100%,\s*1180px\)/);
  assert.doesNotMatch(appSource, /首页只保留和真实工作流直接相关的信息/);
  assert.doesNotMatch(appSource, /更完整的搜索落地页、AI 可读说明和专题内容继续由静态页面承接/);
  assert.doesNotMatch(appSource, /只留下开始前必须知道的事/);
  assert.doesNotMatch(appSource, /seoGeoAnswers/);
  assert.doesNotMatch(appSource, /seoRelatedLinks/);
  assert.doesNotMatch(appSource, /seoUseCases/);
  assert.doesNotMatch(mainCss, /\.seo-content\s*\{/);
  assert.doesNotMatch(mainCss, /\.seo-related-links\s*\{/);
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

test("restored workspaces are offered above the workbench before applying state", () => {
  assert.match(appSource, /initialWorkspaceSnapshot = loadWorkspaceSnapshot\(\)/);
  assert.match(appSource, /pendingWorkspaceSnapshot:\s*initialWorkspaceSnapshot/);
  assert.match(appSource, /workspaceRestoreVisible:\s*hasPersistedWorkspace\(initialWorkspaceSnapshot\)/);
  assert.match(appSource, /scrollRestoration"\s+in\s+window\.history/);
  assert.match(appSource, /function resetPageScrollOnRefresh/);
  assert.doesNotMatch(appSource, /applyWorkspaceSnapshot\(state,\s*initialWorkspaceSnapshot\)/);
  assert.match(appSource, /const showWorkspaceRestore = computed/);
  assert.match(appSource, /<form class="search-panel"[\s\S]*class="restore-toast"[\s\S]*class="analysis-workbench"/);
  assert.match(appSource, /发现上次解析结果/);
  assert.match(appSource, /恢复工作区/);
  assert.match(appSource, /保持清空/);
  assert.match(appSource, /window\.setTimeout\(\(\)\s*=>\s*\{[\s\S]*dismissWorkspaceRestore\(\);[\s\S]*\},\s*10000\)/);
  assert.match(appSource, /async function restoreWorkspaceSnapshot/);
  assert.match(appSource, /applyWorkspaceSnapshot\(state,\s*snapshot\)/);
  assert.match(appSource, /function dismissWorkspaceRestore/);
  assert.match(mainCss, /\.restore-toast\s*\{[\s\S]*width:\s*min\(100%,\s*760px\)/);
  assert.doesNotMatch(mainCss, /\.restore-toast\s*\{[^}]*position:\s*fixed/);
  assert.doesNotMatch(appSource, /class="restore-banner"/);
});

test("logged-in navigation uses an avatar account menu instead of a full account strip", () => {
  assert.match(appSource, /accountMenuOpen:\s*false/);
  assert.match(appSource, /let accountMenuCloseTimer = null/);
  assert.match(appSource, /const accountAvatarLabel = computed/);
  assert.match(appSource, /function scheduleCloseAccountMenu/);
  assert.match(appSource, /window\.setTimeout\(\(\)\s*=>\s*\{[\s\S]*state\.accountMenuOpen = false/);
  assert.match(appSource, /class="account-avatar-button"/);
  assert.match(appSource, /aria-haspopup="menu"/);
  assert.match(appSource, /class="account-dropdown"/);
  assert.match(appSource, /role="menu"/);
  assert.match(appSource, /个人中心/);
  assert.match(appSource, /退出登录/);
  assert.doesNotMatch(appSource, /class="account-chip"/);
  assert.match(mainCss, /\.account-profile\s*\{/);
  assert.match(mainCss, /\.account-dropdown\s*\{[\s\S]*position:\s*absolute/);
  assert.match(mainCss, /\.account-profile:hover::after,\s*\n\.account-profile:focus-within::after,\s*\n\.account-profile\.open::after/);
  assert.match(mainCss, /\.account-profile:hover \.account-dropdown,\s*\n\.account-profile:focus-within \.account-dropdown,\s*\n\.account-profile\.open \.account-dropdown/);
});

test("logged-out auto summary uses a gate state instead of a failure state", () => {
  assert.match(appSource, /summaryGate:\s*""/);
  assert.match(appSource, /state\.summaryGate = "login"/);
  assert.match(appSource, /state\.summaryError = ""/);
  assert.match(appSource, /state\.summaryGate === 'login'/);
  assert.match(appSource, /AI 总结门禁/);
  assert.match(appSource, /登录后继续自动总结/);
  assert.match(appSource, /先下载视频/);
  assert.match(appSource, /await startSummaryForResult\(state\.result,\s*\{\s*mode:\s*"auto"\s*\}\)/);
  assert.doesNotMatch(appSource, /if \(!auth\.user\)\s*\{\s*openAuth\("login"\);\s*state\.summaryError/);
});

test("quota and billing feedback are unified into status panels", () => {
  assert.match(appSource, /summaryGate === 'quota'/);
  assert.match(appSource, /今日免费额度已用完/);
  assert.match(appSource, /async function goToPricingForUpgrade/);
  assert.match(appSource, /navigateToPage\(PRICING_PAGE_ID\)/);
  assert.match(appSource, /查看套餐方案/);
  assert.match(appSource, /@click="goToPricingForUpgrade"/);
  assert.doesNotMatch(appSource, /summary-upgrade-card[\s\S]{0,500}@click="startCheckout"/);
  assert.match(appSource, /const billingPanelVisible = computed/);
  assert.match(appSource, /confirmBillingCheckout/);
  assert.match(appSource, /checkoutConfirming:\s*false/);
  assert.match(appSource, /state\.checkoutStatus === "success"[\s\S]*await confirmCheckoutReturn\(\{ force: true \}\)/);
  assert.match(appSource, /async function logout\(\)[\s\S]*state\.billingMessage = ""[\s\S]*state\.checkoutStatus = ""/);
  assert.match(appSource, /class="billing-status-panel"/);
  assert.match(appSource, /账单状态/);
  assert.match(appSource, /class="current-plan-badge"/);
  assert.match(appSource, /class="plan-status-copy"/);
  assert.match(appSource, /class="mock-billing-panel"/);
  assert.match(appSource, /选择专业版并支付 ¥29\/月/);
  assert.doesNotMatch(appSource, /class="message pricing-message"/);
  assert.match(mainCss, /\.billing-status-panel\s*\{/);
  assert.match(mainCss, /\.current-plan-badge\s*\{/);
  assert.match(mainCss, /\.plan-status-copy\s*\{/);
  assert.match(mainCss, /\.summary-gate-card\s*\{/);
  assert.match(mainCss, /\.summary-upgrade-card\s*\{/);
});

test("credit pack checkout return skips subscription confirmation", () => {
  assert.match(appSource, /checkoutPurchaseType:\s*""/);
  assert.match(appSource, /state\.checkoutPurchaseType = params\.get\("purchase_type"\) \|\| ""/);
  assert.match(appSource, /async function handleCreditPackCheckoutReturn/);
  assert.match(appSource, /state\.checkoutPurchaseType === "credit_pack"[\s\S]*await handleCreditPackCheckoutReturn\(\)/);
  assert.match(appSource, /if \(state\.checkoutPurchaseType === "credit_pack"\) return/);
  assert.match(appSource, /按量包支付已返回，额度会自动同步。/);
  assert.match(appSource, /已取消按量包支付，可以稍后重新购买。/);
  assert.doesNotMatch(
    appSource,
    /state\.checkoutPurchaseType === "credit_pack"[\s\S]{0,200}confirmBillingCheckout/
  );
});

test("completed downloads stay bound to the selected format", () => {
  assert.match(appSource, /currentTask\.value\.format_id === state\.selectedFormatId/);
  assert.match(appSource, /registerTask\(taskId,\s*state\.selectedFormatId\)/);
  assert.match(appSource, /format_id:\s*formatId/);
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
  assert.match(summaryOverviewSource, /<h5>概括<\/h5>/);
  assert.match(summaryCss, /\.summary-module-grid\s*\{[\s\S]*gap:\s*10px/);
  assert.match(summaryCss, /\.summary-card\s*\{[\s\S]*gap:\s*14px/);
  assert.match(summaryCss, /\.summary-card\s*\{[\s\S]*padding:\s*18px/);
  assert.match(summaryCss, /\.summary-card\s*\{[\s\S]*background:\s*var\(--color-paper-surface\)/);
  assert.match(summaryCss, /\.summary-overview-body\s*\{[\s\S]*background:\s*var\(--color-paper-elevated\)/);
  assert.match(summaryCss, /\.summary-section h5\s*\{[\s\S]*border-bottom:\s*1px solid var\(--color-line\)/);
  assert.match(summaryCss, /\.summary-list\s*\{[\s\S]*list-style:\s*disc/);
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
