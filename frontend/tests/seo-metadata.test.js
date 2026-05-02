import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  buildHtmlSitemapPage,
  buildLandingPageHtml,
  buildLandingPageMarkdown,
  buildLlmsFullTxt,
  buildLlmsTxt,
  buildNotFoundPage,
  buildRobotsTxt,
  buildSitemapXml,
  buildStaticHeadersFile,
  buildStaticRedirectsFile,
  normalizeSiteUrl
} from "../scripts/generate-seo-assets.mjs";
import {
  buildIndexNowKeyFile,
  buildIndexNowPayload,
  buildIndexNowState,
  selectChangedIndexNowUrls,
  writeIndexNowKeyFile
} from "../scripts/submit-indexnow.mjs";
import { validateGeneratedAssets, validateProductionSiteUrl } from "../scripts/validate-seo-deploy.mjs";
import { getWebmasterMetaTags, getWebmasterVerificationFiles } from "../scripts/webmaster-verification.mjs";
import { SEO_PAGES, getIndexJsonLd, getPageJsonLd, seoRelatedLinks, seoSite } from "../src/seo/pages.js";

const appSource = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const indexHtmlSource = readFileSync(new URL("../index.html", import.meta.url), "utf8");

test("seo pages cover stable route matrix and primary landing metadata", () => {
  const paths = SEO_PAGES.map((page) => page.path);
  const expectedSeoPaths = [
    "/",
    "/video-summary/",
    "/youtube-video-downloader/",
    "/bilibili-video-downloader/",
    "/douyin-video-downloader/",
    "/tiktok-video-downloader/",
    "/subtitle-extractor/",
    "/facts/",
    "/how-to-video-summary/",
    "/how-to-extract-bilibili-subtitles/",
    "/public-video-to-mind-map/",
    "/public-video-archive-workflow/",
    "/saveany-vs-online-video-downloader/",
    "/ai-video-summary-tool-comparison/",
    "/youtube-video-summary-tool/",
    "/bilibili-course-summary-tool/",
    "/youtube-to-mp4/",
    "/youtube-subtitle-downloader/",
    "/bilibili-course-downloader/",
    "/douyin-public-video-download/",
    "/video-to-text/",
    "/video-to-mindmap/",
    "/ai-video-notes/",
    "/online-video-downloader/",
    "/features/",
    "/features/video-download/",
    "/features/ai-video-summary/",
    "/features/subtitle-extraction/",
    "/features/mind-map/",
    "/platforms/",
    "/platforms/youtube/",
    "/platforms/bilibili/",
    "/platforms/douyin/",
    "/platforms/tiktok/",
    "/use-cases/",
    "/use-cases/course-learning/",
    "/use-cases/content-archive/",
    "/use-cases/meeting-review/",
    "/compare/",
    "/pricing/",
    "/articles/public-video-downloader-drm-boundary/",
    "/articles/ai-video-summary-subtitles-markdown/",
    "/articles/self-hosted-video-summary-privacy/",
    "/articles/yt-dlp-ai-summary-legal-use-cases/",
    "/faq/",
    "/privacy/",
    "/terms/"
  ];

  assert.deepEqual(paths, expectedSeoPaths);
});

test("topic cluster pages define taxonomy and conversion CTAs", () => {
  const expectedPages = [
    { path: "/features/", cluster: "features", pageType: "hub", ctaLabel: "查看所有功能" },
    { path: "/features/video-download/", cluster: "features", pageType: "feature", ctaLabel: "粘贴公开视频链接试试解析" },
    { path: "/features/ai-video-summary/", cluster: "features", pageType: "feature", ctaLabel: "生成 AI 视频学习笔记" },
    { path: "/features/subtitle-extraction/", cluster: "features", pageType: "feature", ctaLabel: "提取公开视频字幕" },
    { path: "/features/mind-map/", cluster: "features", pageType: "feature", ctaLabel: "生成视频思维导图" },
    { path: "/platforms/", cluster: "platforms", pageType: "hub", ctaLabel: "查看支持平台" },
    { path: "/platforms/youtube/", cluster: "platforms", pageType: "platform", ctaLabel: "解析 YouTube 公开视频" },
    { path: "/platforms/bilibili/", cluster: "platforms", pageType: "platform", ctaLabel: "解析 Bilibili 公开视频" },
    { path: "/platforms/douyin/", cluster: "platforms", pageType: "platform", ctaLabel: "解析抖音公开视频" },
    { path: "/platforms/tiktok/", cluster: "platforms", pageType: "platform", ctaLabel: "解析 TikTok 公开视频" },
    { path: "/use-cases/", cluster: "use-cases", pageType: "hub", ctaLabel: "查看使用场景" },
    { path: "/use-cases/course-learning/", cluster: "use-cases", pageType: "use-case", ctaLabel: "生成课程复习笔记" },
    { path: "/use-cases/content-archive/", cluster: "use-cases", pageType: "use-case", ctaLabel: "归档公开视频素材" },
    { path: "/use-cases/meeting-review/", cluster: "use-cases", pageType: "use-case", ctaLabel: "生成会议复盘笔记" },
    { path: "/compare/", cluster: "compare", pageType: "hub", ctaLabel: "查看对比页面" },
    { path: "/pricing/", cluster: "brand", pageType: "pricing", ctaLabel: "查看套餐方案" }
  ];

  assert.equal(expectedPages.length, 16);

  for (const expectedPage of expectedPages) {
    const page = SEO_PAGES.find((item) => item.path === expectedPage.path);

    assert.ok(page, `${expectedPage.path} should exist in SEO_PAGES`);
    assert.equal(page.cluster, expectedPage.cluster);
    assert.equal(page.pageType, expectedPage.pageType);
    assert.equal(page.ctaLabel, expectedPage.ctaLabel);
  }
});

test("hub and pricing pages define crawlable section contracts", () => {
  const assertCrawlableSections = (page) => {
    assert.ok(Array.isArray(page.sections), `${page.path} should define sections`);
    assert.ok(page.sections.length > 0, `${page.path} should define at least one section`);

    for (const section of page.sections) {
      assert.equal(typeof section.heading, "string", `${page.path} section should include a heading`);
      assert.notEqual(section.heading.trim(), "", `${page.path} section heading should not be empty`);
      assert.equal(typeof section.body, "string", `${page.path} section should include body copy`);
      assert.notEqual(section.body.trim(), "", `${page.path} section body should not be empty`);
    }
  };
  const hubPaths = ["/features/", "/platforms/", "/use-cases/", "/compare/"];

  for (const path of hubPaths) {
    const page = SEO_PAGES.find((item) => item.path === path);

    assert.ok(page, `${path} should exist in SEO_PAGES`);
    assertCrawlableSections(page);
  }

  const pricingPage = SEO_PAGES.find((item) => item.path === "/pricing/");
  assert.ok(pricingPage, "/pricing/ should exist in SEO_PAGES");
  assertCrawlableSections(pricingPage);

  const pricingPlans = Array.isArray(pricingPage.pricingPlans)
    ? pricingPage.pricingPlans
    : pricingPage.pricingPlans?.plans;

  assert.ok(Array.isArray(pricingPlans), "/pricing/ should expose pricingPlans as an array or plans array");
  assert.ok(pricingPlans.length > 0, "/pricing/ should define at least one crawlable pricing plan");

  for (const [index, plan] of pricingPlans.entries()) {
    assert.equal(typeof plan.name, "string", `/pricing/ plan ${index} should include a plan name`);
    assert.notEqual(plan.name.trim(), "", `/pricing/ plan ${index} plan name should not be empty`);
    assert.equal(typeof plan.price, "string", `/pricing/ plan ${index} should include a crawlable price`);
    assert.notEqual(plan.price.trim(), "", `/pricing/ plan ${index} price should not be empty`);
    assert.equal(typeof plan.billingCycle, "string", `/pricing/ plan ${index} should include a billing cycle`);
    assert.notEqual(plan.billingCycle.trim(), "", `/pricing/ plan ${index} billing cycle should not be empty`);
    assert.equal(typeof plan.description, "string", `/pricing/ plan ${index} should include a description`);
    assert.notEqual(plan.description.trim(), "", `/pricing/ plan ${index} description should not be empty`);
    assert.ok(Array.isArray(plan.features), `/pricing/ plan ${index} should include a feature list`);
    assert.ok(plan.features.length > 0, `/pricing/ plan ${index} feature list should not be empty`);

    for (const [featureIndex, feature] of plan.features.entries()) {
      assert.equal(typeof feature, "string", `/pricing/ plan ${index} feature ${featureIndex} should be text`);
      assert.notEqual(feature.trim(), "", `/pricing/ plan ${index} feature ${featureIndex} should not be empty`);
    }
  }
});

test("seo pages have unique, keyword-led TDK metadata", () => {
  const titles = new Set();
  const descriptions = new Set();

  for (const page of SEO_PAGES) {
    assert.ok(page.title.startsWith(page.primaryKeyword), `${page.path} title should start with primary keyword`);
    assert.ok(page.title.length <= 60, `${page.path} title should stay SERP-friendly`);
    assert.ok(page.description.includes(page.primaryKeyword), `${page.path} description should include primary keyword`);
    assert.ok(page.description.length >= 70, `${page.path} description should be specific`);
    assert.ok(page.description.length <= 170, `${page.path} description should avoid truncation`);
    assert.ok(page.keywords.length >= 3, `${page.path} should include planning keywords`);
    assert.ok(!titles.has(page.title), `${page.path} title should be unique`);
    assert.ok(!descriptions.has(page.description), `${page.path} description should be unique`);
    titles.add(page.title);
    descriptions.add(page.description);
  }
});

test("robots and sitemap use the configured production site url", () => {
  const siteUrl = normalizeSiteUrl("https://saveany.example/");
  const robotsTxt = buildRobotsTxt(siteUrl);
  const sitemapXml = buildSitemapXml(siteUrl, "2026-04-30");

  assert.match(robotsTxt, /User-agent: \*/);
  assert.match(robotsTxt, /Allow: \//);
  assert.match(robotsTxt, /User-agent: OAI-SearchBot/);
  assert.match(robotsTxt, /User-agent: ChatGPT-User/);
  assert.match(robotsTxt, /User-agent: Claude-SearchBot/);
  assert.match(robotsTxt, /User-agent: PerplexityBot/);
  assert.match(robotsTxt, /Disallow: \/api\//);
  assert.match(robotsTxt, /User-agent: GPTBot[\s\S]*User-agent: CCBot\nDisallow: \//);
  assert.match(robotsTxt, /Sitemap: https:\/\/saveany\.example\/sitemap\.xml/);

  for (const page of SEO_PAGES) {
    assert.match(sitemapXml, new RegExp(`<loc>https://saveany\\.example${page.path}</loc>`));
  }

  assert.match(sitemapXml, /<lastmod>2026-04-30<\/lastmod>/);
  assert.doesNotMatch(sitemapXml, /#/);
});

test("HTML sitemap exposes crawlable links to every SEO page", () => {
  const html = buildHtmlSitemapPage("https://saveany.example");

  assert.match(html, /<h1>网站地图/);
  assert.match(html, /rel="canonical" href="https:\/\/saveany\.example\/sitemap\/"/);
  assert.doesNotMatch(html, /sitemap\.html/);
  for (const page of SEO_PAGES) {
    assert.match(html, new RegExp(`href="https://saveany\\.example${page.path}"`));
    assert.match(html, new RegExp(page.primaryKeyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("static hosting files define cache policy and true 404 fallback", () => {
  const headers = buildStaticHeadersFile();
  const redirects = buildStaticRedirectsFile();
  const notFound = buildNotFoundPage("https://saveany.example");

  assert.match(headers, /\/assets\/\*/);
  assert.match(headers, /Cache-Control: public, max-age=31536000, immutable/);
  assert.match(headers, /Cache-Control: no-cache/);
  assert.match(headers, /X-Content-Type-Options: nosniff/);
  assert.match(redirects, /\/\* \/404\.html 404/);
  assert.match(notFound, /<meta name="robots" content="noindex,follow/);
  assert.match(notFound, /href="https:\/\/saveany\.example\/sitemap\/"/);
});

test("keyword matrix pages contain real crawlable content depth", () => {
  const keywordPaths = [
    "/youtube-to-mp4/",
    "/youtube-subtitle-downloader/",
    "/bilibili-course-downloader/",
    "/douyin-public-video-download/",
    "/video-to-text/",
    "/video-to-mindmap/",
    "/ai-video-notes/",
    "/online-video-downloader/"
  ];

  for (const path of keywordPaths) {
    const page = SEO_PAGES.find((item) => item.path === path);
    const html = buildLandingPageHtml(page, "https://saveany.example");
    const markdown = buildLandingPageMarkdown(page, "https://saveany.example");

    assert.ok(page.useCases.length >= 3, `${path} should define specific use cases`);
    assert.ok(page.howToSteps.length >= 5, `${path} should define concrete steps`);
    assert.ok(page.failureReasons.length >= 3, `${path} should define common failure reasons`);
    assert.ok(page.questions.length >= 2, `${path} should define independent FAQ content`);
    assert.ok(page.relatedPaths.length >= 5, `${path} should define topic-specific related links`);
    assert.match(html, /适用场景/);
    assert.match(html, /常见失败原因/);
    assert.match(markdown, /## 适用场景/);
    assert.match(markdown, /## 常见失败原因/);
    for (const relatedPath of page.relatedPaths.slice(0, 3)) {
      assert.match(html, new RegExp(`href="https://saveany\\.example${relatedPath}"`));
    }
  }
});

test("landing pages render crawlable content and route users back to the app", () => {
  const page = SEO_PAGES.find((item) => item.path === "/youtube-video-downloader/");
  const html = buildLandingPageHtml(page, "https://saveany.example");

  assert.match(html, /<!doctype html>/);
  assert.match(html, /<h1>YouTube视频下载器/);
  assert.match(html, /application\/ld\+json/);
  assert.match(html, /type="text\/markdown"/);
  assert.match(html, /常见问题/);
  assert.match(html, /更新时间：2026-04-30/);
  assert.match(html, /href="https:\/\/saveany\.example\/#download"/);
  assert.match(html, /仅支持公开视频/);
  assert.match(html, /相关页面/);
  assert.ok((html.match(/<li/g) || []).length >= 8, "landing page should include enough crawlable body content");
  assert.ok((html.match(/<a href="https:\/\/saveany\.example\//g) || []).length >= 5, "landing page should include internal links");
});

test("index structured data describes the app, site, FAQ, and organization", () => {
  const graph = getIndexJsonLd("https://saveany.example")["@graph"];
  const types = graph.map((item) => item["@type"]);

  assert.ok(types.includes("Organization"));
  assert.ok(types.includes("WebSite"));
  assert.ok(types.includes("WebApplication"));
  assert.ok(types.includes("SoftwareApplication"));
  assert.ok(types.includes("WebPage"));
  assert.ok(types.includes("ItemList"));
  assert.ok(types.includes("FAQPage"));
  assert.equal(seoSite.name, "万能视频下载总结器");
  assert.equal(seoSite.brandName, "SaveAny");
});

test("FAQ landing page includes FAQPage structured data", () => {
  const page = SEO_PAGES.find((item) => item.path === "/faq/");
  const html = buildLandingPageHtml(page, "https://saveany.example");

  assert.match(html, /"@type":"FAQPage"/);
  assert.match(html, /万能视频下载总结器支持哪些平台/);
});

test("page structured data includes crawlable FAQ and capability lists", () => {
  const page = SEO_PAGES.find((item) => item.path === "/how-to-video-summary/");
  const graph = getPageJsonLd(page, "https://saveany.example")["@graph"];
  const faqPage = graph.find((item) => item["@type"] === "FAQPage");
  const itemList = graph.find((item) => item["@type"] === "ItemList");
  const howTo = graph.find((item) => item["@type"] === "HowTo");

  assert.ok(faqPage.mainEntity.length >= 2);
  assert.ok(itemList.itemListElement.length >= 3);
  assert.ok(howTo.step.length >= 5);
  assert.match(JSON.stringify(graph), /如何把视频总结成笔记/);
});

test("llms files and markdown mirrors expose AI-readable product facts", () => {
  const siteUrl = "https://saveany.example";
  const llmsTxt = buildLlmsTxt(siteUrl);
  const fullTxt = buildLlmsFullTxt(siteUrl);
  const page = SEO_PAGES.find((item) => item.path === "/video-summary/");
  const markdown = buildLandingPageMarkdown(page, siteUrl);

  assert.match(llmsTxt, /^# 万能视频下载总结器/);
  assert.match(llmsTxt, /preferred product name/);
  assert.match(llmsTxt, /llms-full\.txt/);
  assert.match(fullTxt, /SaveAny does not provide login bypass/);
  assert.match(fullTxt, /Markdown: https:\/\/saveany\.example\/video-summary\/index\.html\.md/);
  assert.match(markdown, /Canonical URL: https:\/\/saveany\.example\/video-summary\//);
  assert.match(markdown, /Last updated: 2026-04-30/);
  assert.match(markdown, /## 常见问题/);
});

test("static SEO landing pages remain real URLs outside the compact Vue homepage", () => {
  assert.doesNotMatch(appSource, /seoRelatedLinks/);
  assert.doesNotMatch(appSource, /:href="link\.path"/);

  for (const link of seoRelatedLinks) {
    assert.ok(!link.path.includes("#"), `${link.path} should be a real URL, not a hash route`);
  }
});

test("homepage canonical is controlled by build-time site URL only", () => {
  assert.match(indexHtmlSource, /<link rel="canonical" href="__SEO_SITE_URL__\/" \/>/);
  assert.match(indexHtmlSource, /<meta property="og:url" content="__SEO_SITE_URL__\/" \/>/);
  assert.match(indexHtmlSource, /__SEO_WEBMASTER_META__/);
  assert.doesNotMatch(indexHtmlSource, /window\.location\.origin/);
  assert.doesNotMatch(indexHtmlSource, /querySelector\('link\[rel="canonical"\]'\)/);
});

test("webmaster verification supports meta and file based search platform setup", () => {
  const env = {
    GOOGLE_SITE_VERIFICATION: "google-token",
    BING_SITE_VERIFICATION: "bing-token",
    BAIDU_SITE_VERIFICATION_FILE: "baidu_verify_codeva-demo.html",
    BAIDU_SITE_VERIFICATION_FILE_CONTENT: "baidu-site-verification: demo"
  };
  const meta = getWebmasterMetaTags(env);
  const files = getWebmasterVerificationFiles(env);

  assert.match(meta, /google-site-verification/);
  assert.match(meta, /msvalidate\.01/);
  assert.deepEqual(files, [
    {
      fileName: "baidu_verify_codeva-demo.html",
      content: "baidu-site-verification: demo"
    }
  ]);
});

test("IndexNow payload uses one host, key location, and all SEO URLs", () => {
  const siteUrl = "https://www.saveany.example/";
  const key = "1234567890abcdef1234567890abcdef";
  const payload = buildIndexNowPayload({ siteUrl, key });

  assert.equal(payload.host, "www.saveany.example");
  assert.equal(payload.key, key);
  assert.equal(payload.keyLocation, `https://www.saveany.example/indexnow-${key}.txt`);
  assert.equal(payload.urlList.length, SEO_PAGES.length);
  assert.ok(payload.urlList.includes("https://www.saveany.example/facts/"));
  assert.ok(payload.urlList.every((url) => new URL(url).host === payload.host));
});

test("IndexNow changed URL selection submits only changed pages", () => {
  const siteUrl = "https://www.saveany.example/";
  const previousState = buildIndexNowState({ siteUrl });
  const unchanged = selectChangedIndexNowUrls({ siteUrl, previousState });
  const changedPage = { ...SEO_PAGES[0], description: `${SEO_PAGES[0].description} 新增能力说明。` };
  const changed = selectChangedIndexNowUrls({ siteUrl, previousState, pages: [changedPage, ...SEO_PAGES.slice(1)] });

  assert.deepEqual(unchanged.urlList, []);
  assert.deepEqual(changed.urlList, ["https://www.saveany.example/"]);
});

test("IndexNow key file contains only the verification key", async () => {
  const publicDir = await mkdtemp(join(tmpdir(), "saveany-indexnow-"));
  const key = "abcdef1234567890abcdef1234567890";

  try {
    const keyFilePath = await writeIndexNowKeyFile({ publicDir, key });
    const content = await readFile(keyFilePath, "utf8");

    assert.equal(buildIndexNowKeyFile(` ${key} `), key);
    assert.equal(content, key);
  } finally {
    await rm(publicDir, { recursive: true, force: true });
  }
});

test("webmaster verification config renders meta tags and upload files", () => {
  const env = {
    GOOGLE_SITE_VERIFICATION: "google-token",
    BING_SITE_VERIFICATION: "bing-token",
    BAIDU_SITE_VERIFICATION_FILE: "baidu_verify_codeva-test.html",
    BAIDU_SITE_VERIFICATION_FILE_CONTENT: "baidu-site-verification: test"
  };
  const tags = getWebmasterMetaTags(env);
  const files = getWebmasterVerificationFiles(env);

  assert.match(tags, /name="google-site-verification" content="google-token"/);
  assert.match(tags, /name="msvalidate\.01" content="bing-token"/);
  assert.deepEqual(files, [{ fileName: "baidu_verify_codeva-test.html", content: "baidu-site-verification: test" }]);
});

test("SEO deployment validator rejects fallback domains and accepts generated assets", async () => {
  const publicDir = await mkdtemp(join(tmpdir(), "saveany-seo-assets-"));
  const siteUrl = "https://www.saveany.example";

  try {
    assert.equal(validateProductionSiteUrl("https://saveany.local").ok, false);
    await import("../scripts/generate-seo-assets.mjs").then(({ writeSeoAssets }) => writeSeoAssets({ publicDir, siteUrl, lastmod: "2026-04-30" }));
    const report = await validateGeneratedAssets({ publicDir, siteUrl, allowReserved: true });

    assert.equal(report.ok, true);
    assert.equal(report.checkedPaths, SEO_PAGES.length * 2 + 7);
  } finally {
    await rm(publicDir, { recursive: true, force: true });
  }
});
