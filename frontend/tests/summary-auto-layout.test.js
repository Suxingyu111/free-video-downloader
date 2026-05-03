import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const mainCss = readFileSync(new URL("../src/assets/main.css", import.meta.url), "utf8");
const summaryPanelSource = readFileSync(new URL("../src/components/summary/SummaryPanel.vue", import.meta.url), "utf8");
const summaryQaSource = readFileSync(new URL("../src/components/summary/SummaryQa.vue", import.meta.url), "utf8");
const summaryOverviewSource = readFileSync(new URL("../src/components/summary/SummaryOverview.vue", import.meta.url), "utf8");
const summaryMindMapSource = readFileSync(new URL("../src/components/summary/SummaryMindMap.vue", import.meta.url), "utf8");
const summaryCss = readFileSync(new URL("../src/assets/summary.css", import.meta.url), "utf8");

test("analyzing a video automatically starts the AI summary task", () => {
  assert.match(appSource, /startSummaryForResult\(result,\s*\{\s*mode:\s*"auto"\s*\}\)/);
  assert.match(appSource, /async function startSummaryForResult/);
  assert.match(appSource, /force:\s*true/);
  assert.match(appSource, /analysis_token:\s*result\.analysis_token/);
  assert.doesNotMatch(appSource, /force:\s*mode\s*!==\s*"auto"/);
  assert.doesNotMatch(appSource, /@click="handleSummary"/);
});

test("analyzed results appear below the unchanged hero search area", () => {
  assert.doesNotMatch(appSource, /:class="\{\s*'hero-workbench':\s*hasResult\s*\}"/);
  assert.match(appSource, /<p class="hero-copy">复制链接/);
  assert.doesNotMatch(appSource, /<p v-if="!hasResult" class="hero-copy"/);
  assert.match(appSource, /<form class="search-panel"[\s\S]*<section v-if="hasResult" class="analysis-workbench"/);
  assert.doesNotMatch(mainCss, /\.hero-workbench\b/);
});

test("hero search area keeps the search box compact while adding vertical breathing room", () => {
  assert.match(mainCss, /\.topbar\s*\{[\s\S]*min-height:\s*76px/);
  assert.match(mainCss, /\.hero\s*\{[\s\S]*min-height:\s*auto/);
  assert.match(mainCss, /\.hero\s*\{[\s\S]*padding:\s*clamp\(30px,\s*4\.4vw,\s*60px\)\s+20px\s+46px/);
  assert.match(mainCss, /\.hero-copy-block\s*\{[\s\S]*width:\s*min\(100%,\s*980px\)/);
  assert.match(mainCss, /\.kicker\s*\{[\s\S]*min-height:\s*34px/);
  assert.match(mainCss, /\.hero h1\s*\{[\s\S]*margin:\s*22px\s+auto\s+0/);
  assert.match(mainCss, /\.hero h1\s*\{[\s\S]*width:\s*min\(100%,\s*1040px\)/);
  assert.match(mainCss, /\.hero h1\s*\{[\s\S]*max-width:\s*1040px/);
  assert.match(mainCss, /\.hero-copy,\s*\n\.section-copy\s*\{[\s\S]*max-width:\s*760px/);
  assert.match(mainCss, /\.hero-copy,\s*\n\.section-copy\s*\{[\s\S]*margin:\s*16px\s+auto\s+0/);
  assert.match(mainCss, /\.console\s*\{[\s\S]*width:\s*min\(100%,\s*1180px\)/);
  assert.match(mainCss, /\.console\s*\{[\s\S]*margin-top:\s*34px/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*width:\s*min\(100%,\s*920px\)/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*margin:\s*0\s+auto/);
  assert.match(mainCss, /\.search-panel\s*\{[\s\S]*gap:\s*14px/);
  assert.match(mainCss, /\.url-field\s*\{[\s\S]*min-height:\s*60px/);
  assert.match(mainCss, /\.url-field\s*\{[\s\S]*grid-template-columns:\s*auto\s+minmax\(0,\s*1fr\)\s+180px/);
  assert.match(mainCss, /\.quick-row\s*\{[\s\S]*min-height:\s*28px/);
  assert.match(mainCss, /\.hero-helper-strip\s*\{[\s\S]*width:\s*min\(100%,\s*860px\)/);
  assert.match(mainCss, /\.hero-helper-strip\s*\{[\s\S]*gap:\s*12px\s+8px/);
  assert.doesNotMatch(mainCss, /\.search-panel\s*\{[\s\S]*width:\s*min\(100%,\s*1240px\)/);
  assert.doesNotMatch(mainCss, /\.url-field\s*\{[\s\S]*min-height:\s*68px/);
  assert.match(mainCss, /\.analysis-workbench\s*\{[\s\S]*margin-top:\s*10px/);
});

test("homepage visual system feels premium instead of beige utility-site", () => {
  assert.match(appSource, /class="hero-product-preview"/);
  assert.match(mainCss, /\.hero-product-preview\s*\{/);
  assert.match(mainCss, /\.preview-window\s*\{[\s\S]*background:[\s\S]*linear-gradient\(180deg,\s*#ffffff,\s*#f8fafc\)/);
  assert.doesNotMatch(mainCss, /\.preview-window\s*\{[\s\S]*linear-gradient\(180deg,\s*#08111f,\s*#101827\)/);
  assert.doesNotMatch(mainCss, /\.preview-link-panel,\s*\n\.preview-format-panel,\s*\n\.preview-mobile-panel\s*\{[\s\S]*background:\s*rgba\(15,\s*23,\s*42/);
  assert.doesNotMatch(mainCss, /#f3efe6|#fffdf7|#faf6ed|#f7f1e6|#fbf8ef|#ebe6dc|#f6efe2/i);
  assert.doesNotMatch(mainCss, /rgba\(245,\s*158,\s*11/);
});

test("top navigation scrolls to homepage sections while pricing remains a separate page", () => {
  assert.match(appSource, /const pageLinks = \[/);
  assert.match(appSource, /const HOME_PAGE_ID = "download"/);
  assert.match(appSource, /const PRICING_PAGE_ID = "pricing"/);
  assert.match(appSource, /const HOME_DOWNLOAD_ANCHOR_ID = "download-console"/);
  assert.match(appSource, /const homeAnchorIds = pageLinks\.filter/);
  assert.match(appSource, /label:\s*"回到下载"/);
  assert.match(appSource, /label:\s*"支持平台"/);
  assert.match(appSource, /label:\s*"下载能力"/);
  assert.match(appSource, /label:\s*"AI 增强"/);
  assert.match(appSource, /label:\s*"适用场景"/);
  assert.match(appSource, /label:\s*"Pro 价值"/);
  assert.match(appSource, /label:\s*"边界 FAQ"/);
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
  assert.match(appSource, /id="home-platforms"/);
  assert.match(appSource, /id="home-download-capabilities"/);
  assert.match(appSource, /id="home-ai-addon"/);
  assert.match(appSource, /id="home-use-cases"/);
  assert.match(appSource, /id="home-pricing"/);
  assert.match(appSource, /id="home-faq"/);
  assert.doesNotMatch(appSource, /id="home-pricing-preview"/);
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

test("homepage content strategy leads with 1800+ download coverage before AI add-ons", () => {
  for (const title of ["1800+ 网站覆盖", "格式与清晰度", "字幕和音频", "手机也能下载"]) {
    assert.match(appSource, new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.match(appSource, /const homeDownloadFeatures = \[/);
  assert.match(appSource, /const homePlatformGroups = \[/);
  assert.match(appSource, /const homeAiAddons = \[/);
  assert.match(appSource, /const homeUseCases = \[/);
  assert.match(appSource, /const downloadPreviewStats = \[/);
  assert.doesNotMatch(appSource, /const homeOutcomeCards = \[/);
  assert.doesNotMatch(appSource, /const homeProofPoints = \[/);
  assert.match(appSource, /class="download-console-preview"/);
  assert.match(appSource, /class="download-preview-strip"/);
  assert.match(appSource, /Universal Download Console/);
  assert.match(appSource, /1080p MP4/);
  assert.match(appSource, /SRT 字幕/);
  assert.match(appSource, /移动端网页/);
  assert.match(appSource, /手机保存/);
  assert.match(appSource, /无需安装 App/);
  assert.match(appSource, /class="platform-coverage"/);
  assert.match(appSource, /class="download-capability-grid"/);
  assert.match(appSource, /class="ai-addon-panel"/);
  assert.match(appSource, /class="use-case-grid"/);
  assert.match(appSource, /class="upgrade-panel"/);
  assert.match(appSource, /离线观看/);
  assert.match(appSource, /素材保存/);
  assert.match(appSource, /家庭共享/);
  assert.match(appSource, /Pro 解锁更多下载额度、长视频和移动端体验/);
  assert.doesNotMatch(appSource, /下载队列|批量队列|download queue/i);
  assert.doesNotMatch(appSource, /用户愿意付费/);
  assert.doesNotMatch(appSource, /class="workflow"/);
  assert.doesNotMatch(appSource, /class="trust-strip"/);
  assert.doesNotMatch(appSource, /class="home-comparison-table"/);
  assert.doesNotMatch(appSource, /视频知识工作台/);
  assert.doesNotMatch(appSource, /Study Pack/);
  assert.doesNotMatch(appSource, /68 分钟公开视频课/);
  assert.doesNotMatch(appSource, /SaveAny 与普通视频下载器对比/);
  assert.doesNotMatch(appSource, /三步完成视频下载和 AI 总结/);
  assert.doesNotMatch(appSource, /先完成下载，再把视频整理成笔记/);
  assert.doesNotMatch(appSource, /长视频与播放列表工作流/);
  assert.doesNotMatch(mainCss, /\.workflow\s*\{/);
  assert.doesNotMatch(mainCss, /\.home-comparison-table\s*\{/);
  assert.match(mainCss, /\.platform-chip-grid\s*\{/);
});

test("pricing page shows personal free and pro plans plus credit packs", () => {
  assert.match(appSource, /const pricingPlans = \[/);
  assert.match(appSource, /name:\s*"免费版"/);
  assert.match(appSource, /name:\s*"Pro 个人版"/);
  assert.doesNotMatch(appSource, /name:\s*"团队版"/);
  assert.doesNotMatch(appSource, /¥99/);
  assert.match(appSource, /const creditPacks = \[/);
  assert.match(appSource, /总结小包/);
  assert.match(appSource, /id:\s*"summary_large"[\s\S]*name:\s*"总结加量包"/);
  assert.doesNotMatch(appSource, /name:\s*"总结大包"/);
  assert.match(appSource, /转写大包/);
  assert.match(appSource, /v-for="plan in pricingPlans"/);
  assert.match(appSource, /class="pricing-grid"/);
  assert.match(appSource, /class="plan-feature-list"/);
  assert.match(mainCss, /\.pricing-grid\s*\{[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(appSource, /class="home-pricing-preview"/);
  assert.match(appSource, /免费版先验证下载能力，Pro 解锁更高下载额度和增强能力/);
  assert.doesNotMatch(appSource, /class="home-plan-card"/);
  assert.match(appSource, /查看套餐方案/);
  assert.match(mainCss, /\.upgrade-panel\s*\{/);
  assert.doesNotMatch(appSource, /每日\s*\d+\s*次解析任务/);
  assert.doesNotMatch(appSource, /任务结果保留\s*\d+\s*天/);
  assert.match(appSource, /每月 10 次 AI 问答/);
  assert.match(appSource, /每月 200 次 AI 问答/);
});

test("homepage keeps SEO content compact while static pages own long-form discovery", () => {
  assert.match(appSource, /compactFaqs = seoFaqs\.slice\(0,\s*2\)/);
  assert.match(appSource, /const homeTrustBoundaries = \[/);
  assert.match(mainCss, /\.home-faq-summary\s*\{/);
  assert.match(mainCss, /\.home-faq-summary\s*\{[\s\S]*width:\s*min\(100%,\s*1180px\)/);
  assert.match(mainCss, /\.trust-boundary-list\s*\{/);
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
  assert.match(appSource, /async function logout\(\)[\s\S]*catch \(error\)[\s\S]*console\.warn\("Logout request failed"/);
  assert.match(appSource, /class="billing-status-panel"/);
  assert.match(appSource, /const questionQuotaText = computed/);
  assert.match(appSource, /quotaMeterText\(auth,\s*"question"\)/);
  assert.match(appSource, /v-if="questionQuotaText" class="account-quota-row"/);
  assert.match(
    appSource,
    /class="billing-status-panel"[\s\S]*:style="\{ width: `\$\{summaryQuotaRatio\}%` \}"[\s\S]*:style="\{ width: `\$\{transcriptionQuotaRatio\}%` \}"/
  );
  assert.match(appSource, /账单状态/);
  assert.match(appSource, /class="current-plan-badge"/);
  assert.match(appSource, /class="plan-status-copy"/);
  assert.doesNotMatch(appSource, /mock-billing-panel|本地模拟支付|runMockBilling|showMockBilling/);
  assert.match(appSource, /开通 Pro ¥19\/月/);
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
  assert.match(appSource, /:question-quota-text="questionQuotaText"/);
  assert.match(appSource, /:question-quota-exhausted="questionQuotaExhausted"/);
  assert.match(summaryPanelSource, /questionQuotaText/);
  assert.match(summaryPanelSource, /questionQuotaExhausted/);
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
  assert.match(summaryQaSource, /本月 AI 问答/);
  assert.match(summaryQaSource, /questionQuotaExhausted/);
  assert.match(summaryQaSource, /本月 AI 问答次数已用完/);
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
