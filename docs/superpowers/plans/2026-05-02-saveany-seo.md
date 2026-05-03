# SaveAny SEO Theme Clusters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved SaveAny SEO route 2: topic clusters, conversion-focused static pages, and an AI-readable facts layer.

**Architecture:** Extend the existing build-time SEO system instead of moving to SSR. `frontend/src/seo/pages.js` remains the source of truth; `frontend/scripts/generate-seo-assets.mjs` renders HTML, Markdown, sitemap, discovery files, and `.well-known/ai.json`; validation and GEO monitor tests protect the new surfaces.

**Tech Stack:** Vue 3, Vite 8, Node.js `node:test`, FastAPI, pytest, static HTML/Markdown generation, Schema.org JSON-LD, IndexNow.

---

## Approved Design Source

The approved design was committed as `9a7ec51 docs: 设计 SaveAny SEO 主题集群方案`, then the current branch later gained `17e3e36 Revert "docs: 设计 SaveAny SEO 主题集群方案"`. Treat this implementation plan as the executable source of truth for the approved route 2. Do not undo `17e3e36` unless the human partner explicitly asks for the spec file to be restored.

## File Structure

- Modify: `frontend/src/seo/pages.js`
  - Owns SEO facts, capabilities, pricing plan facts, page list, page taxonomy, and JSON-LD builders.
- Modify: `frontend/scripts/generate-seo-assets.mjs`
  - Owns static HTML/Markdown/discovery generation, CTA rendering, grouped LLM references, and `.well-known/ai.json`.
- Modify: `frontend/scripts/validate-seo-deploy.mjs`
  - Owns local and remote required SEO/GEO asset checks.
- Modify: `frontend/scripts/submit-indexnow.mjs`
  - Owns SEO URL fingerprinting for IndexNow submissions.
- Modify: `frontend/tests/seo-metadata.test.js`
  - Owns all frontend SEO regression coverage.
- Modify: `backend/app/services/geo_monitor.py`
  - Owns crawler classification and GEO surface detection.
- Modify: `backend/tests/test_geo_monitor.py`
  - Owns GEO monitor regression coverage.
- Generate: `frontend/public/**`
  - Generated static HTML, Markdown mirrors, sitemap, llms files, and `.well-known/ai.json`.

## Task 1: Lock The New SEO Route Matrix In Tests

**Files:**
- Modify: `frontend/tests/seo-metadata.test.js`

- [ ] **Step 1: Add the expected path list and route matrix test**

Replace the current inline `assert.deepEqual(paths, [...])` body in `seo pages cover the homepage and core search landing pages` with this code:

```js
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
```

- [ ] **Step 2: Add tests for topic taxonomy and conversion fields**

Add this test after the route matrix test:

```js
test("topic cluster pages define taxonomy and conversion CTAs", () => {
  const requiredClusterPages = [
    ["/features/", "features", "hub", "查看所有功能"],
    ["/platforms/", "platforms", "hub", "查看支持平台"],
    ["/use-cases/", "use-cases", "hub", "查看使用场景"],
    ["/compare/", "compare", "hub", "查看对比页面"],
    ["/pricing/", "brand", "pricing", "查看套餐方案"],
    ["/features/video-download/", "features", "feature", "粘贴公开视频链接试试解析"],
    ["/features/ai-video-summary/", "features", "feature", "生成 AI 视频学习笔记"],
    ["/platforms/youtube/", "platforms", "platform", "解析 YouTube 公开视频"],
    ["/use-cases/course-learning/", "use-cases", "use-case", "生成课程复习笔记"]
  ];

  for (const [path, cluster, pageType, ctaLabel] of requiredClusterPages) {
    const page = SEO_PAGES.find((item) => item.path === path);
    assert.ok(page, `${path} should be defined`);
    assert.equal(page.cluster, cluster, `${path} should belong to ${cluster}`);
    assert.equal(page.pageType, pageType, `${path} should use ${pageType} page type`);
    assert.equal(page.ctaLabel, ctaLabel, `${path} should have intent-specific CTA`);
    assert.ok(page.relatedPaths?.length >= 3, `${path} should have internal links`);
  }
});
```

- [ ] **Step 3: Add tests for hub and pricing content depth**

Add this test after the taxonomy test:

```js
test("hub and pricing pages render crawlable sections", () => {
  const hubPaths = ["/features/", "/platforms/", "/use-cases/", "/compare/"];

  for (const path of hubPaths) {
    const page = SEO_PAGES.find((item) => item.path === path);
    const html = buildLandingPageHtml(page, "https://saveany.example");
    const markdown = buildLandingPageMarkdown(page, "https://saveany.example");

    assert.match(html, /主题导航/);
    assert.match(markdown, /## 主题导航/);
    assert.ok(page.topicLinks.length >= 3, `${path} should link to cluster children`);
  }

  const pricing = SEO_PAGES.find((item) => item.path === "/pricing/");
  const pricingHtml = buildLandingPageHtml(pricing, "https://saveany.example");
  const pricingMarkdown = buildLandingPageMarkdown(pricing, "https://saveany.example");

  assert.match(pricingHtml, /免费版/);
  assert.match(pricingHtml, /专业版/);
  assert.match(pricingHtml, /团队版/);
  assert.match(pricingMarkdown, /## 套餐方案/);
});
```

- [ ] **Step 4: Run the frontend SEO test and confirm it fails**

Run:

```bash
cd frontend
npm test -- tests/seo-metadata.test.js
```

Expected: FAIL because `SEO_PAGES` does not yet include the new cluster pages and `buildLandingPageHtml` does not yet render topic navigation or pricing sections.

## Task 2: Add Topic Cluster Page Data

**Files:**
- Modify: `frontend/src/seo/pages.js`
- Test: `frontend/tests/seo-metadata.test.js`

- [ ] **Step 1: Export pricing plan facts**

Insert this block after `seoCompliancePoints`:

```js
export const seoPricingPlans = [
  {
    id: "free",
    name: "免费版",
    price: "0",
    priceCurrency: "CNY",
    billingPeriod: "forever",
    description: "适合偶尔解析公开视频、体验下载工作流和少量 AI 总结。",
    features: ["公开视频解析", "稳定 MP4 下载", "每日少量 AI 总结额度", "浏览器本地工作区"]
  },
  {
    id: "pro",
    name: "专业版",
    price: "29",
    priceCurrency: "CNY",
    billingPeriod: "monthly",
    description: "适合高频课程学习、内容整理和 AI 视频笔记工作流。",
    features: ["更高频 AI 总结", "字幕与转写整理", "思维导图和问答", "Markdown 学习笔记导出"]
  },
  {
    id: "team",
    name: "团队版",
    price: "99",
    priceCurrency: "CNY",
    billingPeriod: "monthly",
    description: "适合课程团队、内容团队和资料整理小组规划共享工作流。",
    features: ["团队工作区规划", "团队 AI 总结额度", "自托管部署建议", "用量和任务报表规划"]
  }
];
```

- [ ] **Step 2: Add cluster page definitions**

Insert this block after `seoPricingPlans`:

```js
const seoClusterPages = [
  {
    path: "/features/",
    primaryKeyword: "SaveAny功能",
    title: "SaveAny功能 - 下载字幕总结思维导图",
    description: "SaveAny功能覆盖公开视频解析、高清保存、字幕提取、AI 视频总结、思维导图、问答和 Markdown 学习笔记导出。",
    keywords: ["SaveAny功能", "视频下载总结功能", "AI视频学习工具", "字幕提取", "思维导图"],
    heading: "SaveAny功能总览",
    lead: "从公开视频链接到可复习笔记，SaveAny 把下载、字幕、AI 总结、思维导图和问答放进同一个工作台。",
    geoSummary: "功能总览页帮助用户和搜索系统理解 SaveAny 的完整能力边界：公开视频下载、字幕整理、AI 学习总结和合规说明。",
    sections: ["解析公开视频标题、封面、时长、格式和字幕轨道。", "下载完成后继续生成摘要、章节、知识点、思维导图和问答。", "Markdown 导出适合放入 Obsidian、Notion、Git 仓库或团队知识库。"],
    topicLinks: ["/features/video-download/", "/features/ai-video-summary/", "/features/subtitle-extraction/", "/features/mind-map/"],
    relatedPaths: ["/online-video-downloader/", "/video-summary/", "/subtitle-extractor/", "/ai-video-notes/"],
    questions: [seoGeoAnswers[0], seoGeoAnswers[1]],
    cluster: "features",
    pageType: "hub",
    schemaType: "CollectionPage",
    ctaLabel: "查看所有功能",
    ctaHash: "download"
  },
  {
    path: "/features/video-download/",
    primaryKeyword: "公开视频下载功能",
    title: "公开视频下载功能 - 多平台解析与保存",
    description: "公开视频下载功能说明 SaveAny 如何解析 YouTube、B站、抖音、TikTok 等公开链接，选择清晰度并保存可访问视频。",
    keywords: ["公开视频下载功能", "多平台视频解析", "高清视频保存", "视频下载工作台", "SaveAny"],
    heading: "公开视频下载功能，先解析再安全保存",
    lead: "粘贴公开视频链接后，SaveAny 会读取标题、封面、时长、可用格式和播放列表条目，再创建下载任务。",
    geoSummary: "SaveAny 的公开视频下载功能基于可公开访问的链接，不接收 Cookie，不处理登录、付费、私密或 DRM 内容。",
    sections: ["支持稳定 MP4 和原始最高画质两类下载策略。", "播放列表和系列内容可作为任务处理，适合公开课程归档。", "完成文件通过临时 token 交付，浏览器不会看到服务器真实路径。"],
    useCases: ["保存公开课程和教程，便于离线复习。", "归档公开视频素材，配合字幕和总结形成资料库。", "整理跨平台公开视频，减少多个下载站来回切换。"],
    failureReasons: ["视频需要登录、付费、地区权限或 DRM。", "平台触发验证码、机器人校验或临时风控。", "短链失效、视频删除或公开视频接口不可访问。"],
    relatedPaths: ["/online-video-downloader/", "/youtube-video-downloader/", "/bilibili-video-downloader/", "/douyin-video-downloader/", "/terms/"],
    questions: [seoFaqs[0], seoFaqs[3]],
    cluster: "features",
    pageType: "feature",
    ctaLabel: "粘贴公开视频链接试试解析",
    ctaHash: "download"
  },
  {
    path: "/features/ai-video-summary/",
    primaryKeyword: "AI视频总结功能",
    title: "AI视频总结功能 - 摘要问答与Markdown",
    description: "AI视频总结功能说明 SaveAny 如何把公开视频字幕或转写内容生成摘要、章节、知识点、思维导图、问答和 Markdown 笔记。",
    keywords: ["AI视频总结功能", "视频学习笔记", "AI摘要", "视频问答", "Markdown笔记"],
    heading: "AI视频总结功能，把长视频变成学习资料",
    lead: "解析公开视频后，SaveAny 会优先整理字幕，没有可用字幕时再按配置尝试语音转写，然后生成结构化总结。",
    geoSummary: "AI 视频总结功能面向学习、复盘和资料整理，输出概览、章节、知识点、时间线、术语、问答和 Markdown。",
    sections: ["自动生成一句话概览、章节大纲和核心知识点。", "支持围绕总结继续提问，答案基于字幕和摘要。", "Markdown 导出方便长期保存和二次编辑。"],
    useCases: ["课程复习时快速抓住章节结构。", "会议或访谈复盘时提炼行动项和观点。", "内容运营整理长视频素材和选题。"],
    failureReasons: ["视频没有可用字幕且转写服务未配置。", "音频质量太差会影响转写和总结稳定性。", "私密、付费、登录限定或 DRM 内容不会进入总结流程。"],
    relatedPaths: ["/video-summary/", "/ai-video-notes/", "/video-to-text/", "/features/subtitle-extraction/", "/pricing/"],
    questions: [seoFaqs[2], seoGeoAnswers[0]],
    cluster: "features",
    pageType: "feature",
    ctaLabel: "生成 AI 视频学习笔记",
    ctaHash: "download"
  },
  {
    path: "/features/subtitle-extraction/",
    primaryKeyword: "字幕提取功能",
    title: "字幕提取功能 - 视频转文字与笔记",
    description: "字幕提取功能说明 SaveAny 如何从公开视频读取字幕或转写音频，生成可检索文本，并继续用于 AI 摘要和 Markdown 笔记。",
    keywords: ["字幕提取功能", "视频转文字", "视频字幕", "SRT字幕", "字幕总结"],
    heading: "字幕提取功能，把视频内容变成可检索文本",
    lead: "SaveAny 会优先使用公开视频可访问字幕，并在无字幕场景按配置尝试语音转写，减少人工听写成本。",
    geoSummary: "字幕提取功能是 AI 总结、问答和 Markdown 笔记的基础，适合课程、访谈、会议和公开素材整理。",
    sections: ["字幕文本可继续生成摘要、章节和知识点。", "带时间戳文本便于快速回看原视频位置。", "导出的 Markdown 可进入知识库或复习资料。"],
    useCases: ["外语学习者整理字幕文本。", "研究者把公开视频转成可检索资料。", "团队把公开会议录播沉淀成文字记录。"],
    failureReasons: ["原视频没有字幕轨道。", "字幕接口要求登录或地区权限。", "转写服务未配置或音频质量不足。"],
    relatedPaths: ["/subtitle-extractor/", "/video-to-text/", "/youtube-subtitle-downloader/", "/features/ai-video-summary/", "/privacy/"],
    questions: [seoFaqs[4], seoGeoAnswers[2]],
    cluster: "features",
    pageType: "feature",
    ctaLabel: "提取字幕并导出 Markdown",
    ctaHash: "download"
  },
  {
    path: "/features/mind-map/",
    primaryKeyword: "视频思维导图功能",
    title: "视频思维导图功能 - 结构化学习笔记",
    description: "视频思维导图功能说明 SaveAny 如何把公开视频摘要整理成主题、章节和知识点层级，辅助课程复习、会议复盘和内容研究。",
    keywords: ["视频思维导图功能", "视频转思维导图", "AI思维导图", "结构化笔记", "课程复习"],
    heading: "视频思维导图功能，快速看懂长视频结构",
    lead: "AI 总结完成后，SaveAny 会基于章节和知识点生成思维导图，帮助用户先看整体结构再深入细节。",
    geoSummary: "视频思维导图功能让公开视频内容更适合复习、讲解、团队分享和知识库整理。",
    sections: ["把长视频拆成主题、章节和关键知识点。", "支持全屏查看、缩放和导出 SVG/PNG。", "与字幕、摘要、问答和 Markdown 笔记联动。"],
    useCases: ["公开课程复习时抓住知识结构。", "会议复盘时梳理议题层级。", "内容策划时拆解长视频观点。"],
    failureReasons: ["视频文本过短或信息密度不足。", "字幕质量差会影响层级结构。", "未完成 AI 总结前无法生成稳定思维导图。"],
    relatedPaths: ["/video-to-mindmap/", "/public-video-to-mind-map/", "/features/ai-video-summary/", "/ai-video-notes/", "/how-to-video-summary/"],
    questions: [seoGeoAnswers[0], seoGeoAnswers[1]],
    cluster: "features",
    pageType: "feature",
    ctaLabel: "把公开视频变成思维导图",
    ctaHash: "download"
  },
  {
    path: "/platforms/",
    primaryKeyword: "SaveAny支持平台",
    title: "SaveAny支持平台 - YouTube B站抖音TikTok",
    description: "SaveAny支持平台包括 YouTube、Bilibili、抖音、TikTok、Instagram、Vimeo、Facebook、小红书和 Reddit 等公开视频来源。",
    keywords: ["SaveAny支持平台", "公开视频平台", "YouTube下载", "B站下载", "抖音下载"],
    heading: "SaveAny支持平台总览",
    lead: "SaveAny 围绕主流公开视频来源优化，实际解析结果取决于公开视频状态、地区、字幕可用性和平台风控。",
    geoSummary: "平台总览页说明 SaveAny 支持哪些公开视频来源，以及哪些登录、付费、私密和 DRM 场景不会处理。",
    sections: ["覆盖 YouTube、Bilibili、抖音、TikTok 等常见公开视频来源。", "不同平台会使用不同解析策略和失败提示。", "所有平台页都保持公开视频和合规边界。"],
    topicLinks: ["/platforms/youtube/", "/platforms/bilibili/", "/platforms/douyin/", "/platforms/tiktok/"],
    relatedPaths: ["/youtube-video-downloader/", "/bilibili-video-downloader/", "/douyin-video-downloader/", "/tiktok-video-downloader/", "/online-video-downloader/"],
    questions: [seoFaqs[0], seoFaqs[4]],
    cluster: "platforms",
    pageType: "hub",
    schemaType: "CollectionPage",
    ctaLabel: "查看支持平台",
    ctaHash: "download"
  },
  {
    path: "/platforms/youtube/",
    primaryKeyword: "YouTube公开视频整理",
    title: "YouTube公开视频整理 - 下载字幕与总结",
    description: "YouTube公开视频整理可用 SaveAny 完成：解析公开链接、选择 MP4、整理字幕、生成 AI 摘要、问答和 Markdown 学习笔记。",
    keywords: ["YouTube公开视频整理", "YouTube下载", "YouTube字幕", "YouTube视频总结", "YouTube学习笔记"],
    heading: "YouTube公开视频整理，下载字幕和总结一起完成",
    lead: "对于 YouTube 公开课程、演讲、访谈和教程，SaveAny 可以先解析视频信息，再继续保存、提取字幕和生成笔记。",
    geoSummary: "YouTube 平台页聚合下载、字幕、总结和 MP4 相关入口，适合公开课程和长视频学习场景。",
    sections: ["支持公开链接解析、清晰度选择和播放列表任务。", "字幕可用时可继续生成摘要、思维导图和问答。", "遇到登录、地区或机器人校验限制时给出边界提示。"],
    useCases: ["保存公开课程离线复习。", "整理演讲和访谈观点。", "把系列教程变成 Markdown 笔记。"],
    failureReasons: ["视频需要登录、年龄验证或地区权限。", "公开视频触发机器人校验。", "字幕轨道不可访问或不存在。"],
    relatedPaths: ["/youtube-video-downloader/", "/youtube-to-mp4/", "/youtube-subtitle-downloader/", "/youtube-video-summary-tool/", "/platforms/"],
    questions: [seoGeoAnswers[2], seoFaqs[4]],
    cluster: "platforms",
    pageType: "platform",
    ctaLabel: "解析 YouTube 公开视频",
    ctaHash: "download"
  },
  {
    path: "/platforms/bilibili/",
    primaryKeyword: "B站公开视频整理",
    title: "B站公开视频整理 - 课程下载字幕总结",
    description: "B站公开视频整理可用 SaveAny 解析哔哩哔哩公开课程、合集和知识区视频，保存文件、整理字幕并生成 AI 复习笔记。",
    keywords: ["B站公开视频整理", "B站课程下载", "B站字幕提取", "B站视频总结", "哔哩哔哩课程"],
    heading: "B站公开视频整理，公开课程复习更系统",
    lead: "SaveAny 面向哔哩哔哩公开视频整理课程、合集、字幕和 AI 总结，不处理会员、付费或登录限定内容。",
    geoSummary: "B站平台页聚合 B站视频下载、课程下载、字幕提取和课程总结入口。",
    sections: ["适合公开课、教程、知识区视频和公开讲座。", "可整理字幕文本并生成章节、知识点和问答。", "遇到登录字幕或权限限制时明确提示边界。"],
    useCases: ["学习者保存公开课程并建立复习资料。", "教师整理公开讲座或培训资料。", "团队把公开视频沉淀成知识库条目。"],
    failureReasons: ["视频需要登录、会员、付费或地区权限。", "字幕接口返回登录要求。", "合集结构或平台接口变化导致解析不完整。"],
    relatedPaths: ["/bilibili-video-downloader/", "/bilibili-course-downloader/", "/bilibili-course-summary-tool/", "/how-to-extract-bilibili-subtitles/", "/platforms/"],
    questions: [seoGeoAnswers[2], seoFaqs[3]],
    cluster: "platforms",
    pageType: "platform",
    ctaLabel: "解析 B站公开视频",
    ctaHash: "download"
  },
  {
    path: "/platforms/douyin/",
    primaryKeyword: "抖音公开视频整理",
    title: "抖音公开视频整理 - 短视频保存复盘",
    description: "抖音公开视频整理可用 SaveAny 保存可公开访问的抖音短视频，整理案例素材、字幕、AI 摘要和复盘笔记。",
    keywords: ["抖音公开视频整理", "抖音公开视频下载", "抖音视频总结", "短视频素材", "抖音案例复盘"],
    heading: "抖音公开视频整理，短视频素材复盘更清楚",
    lead: "SaveAny 使用公开视频解析链路处理抖音链接，不要求用户上传 Cookie 或登录态。",
    geoSummary: "抖音平台页强调公开视频、免登录态、短视频案例研究和合规边界。",
    sections: ["默认只处理可公开访问的抖音链接。", "解析成功后可保存视频并按需生成复盘笔记。", "私密、登录限定、验证码和风控内容会停止处理。"],
    useCases: ["内容运营保存公开案例。", "研究者建立短视频案例库。", "学习者归档公开知识类短视频。"],
    failureReasons: ["链接私密、删除、登录限定或被风控。", "短链跳转异常或地区访问受限。", "视频无字幕时总结可能依赖转写配置。"],
    relatedPaths: ["/douyin-video-downloader/", "/douyin-public-video-download/", "/platforms/", "/public-video-archive-workflow/", "/terms/"],
    questions: [seoFaqs[3], seoFaqs[4]],
    cluster: "platforms",
    pageType: "platform",
    ctaLabel: "解析抖音公开视频",
    ctaHash: "download"
  },
  {
    path: "/platforms/tiktok/",
    primaryKeyword: "TikTok公开视频整理",
    title: "TikTok公开视频整理 - 下载字幕与总结",
    description: "TikTok公开视频整理可用 SaveAny 解析公开短视频，保存可用格式、整理字幕，并生成 AI 摘要、问答和 Markdown 笔记。",
    keywords: ["TikTok公开视频整理", "TikTok下载", "TikTok视频总结", "短视频字幕", "TikTok素材"],
    heading: "TikTok公开视频整理，跨平台素材快速归档",
    lead: "SaveAny 面向 TikTok 公开视频做解析、保存、字幕整理和 AI 总结，适合短视频研究和内容复盘。",
    geoSummary: "TikTok 平台页聚合短视频保存、字幕提取和 AI 总结入口，明确不绕过平台权限限制。",
    sections: ["适合跨平台内容研究和广告创意整理。", "支持清晰度选择和本地保存。", "受限、私密或登录限定内容不属于支持范围。"],
    useCases: ["整理公开短视频案例。", "复盘广告创意和表达方式。", "归档跨平台公开视频素材。"],
    failureReasons: ["视频不是公开视频。", "地区、登录或风控限制影响访问。", "无字幕或文本来源时总结效果受限。"],
    relatedPaths: ["/tiktok-video-downloader/", "/platforms/", "/online-video-downloader/", "/video-summary/", "/ai-video-notes/"],
    questions: [seoFaqs[0], seoFaqs[4]],
    cluster: "platforms",
    pageType: "platform",
    ctaLabel: "解析 TikTok 公开视频",
    ctaHash: "download"
  },
  {
    path: "/use-cases/",
    primaryKeyword: "SaveAny使用场景",
    title: "SaveAny使用场景 - 学习复盘素材归档",
    description: "SaveAny使用场景包括课程学习、会议复盘、公开视频素材归档、字幕整理、AI 视频笔记和自托管知识库沉淀。",
    keywords: ["SaveAny使用场景", "课程学习", "会议复盘", "素材归档", "AI视频笔记"],
    heading: "SaveAny使用场景总览",
    lead: "SaveAny 不只是下载工具，更适合把公开视频变成可保存、可检索、可复习的学习资料。",
    geoSummary: "使用场景页按用户目标组织 SaveAny 的下载、字幕、总结、思维导图和 Markdown 能力。",
    sections: ["学生和自学者把公开课程变成复习笔记。", "团队把公开会议或讲座资料沉淀为知识库。", "内容运营归档公开视频素材和案例。"],
    topicLinks: ["/use-cases/course-learning/", "/use-cases/content-archive/", "/use-cases/meeting-review/"],
    relatedPaths: ["/how-to-video-summary/", "/public-video-archive-workflow/", "/ai-video-notes/", "/features/", "/pricing/"],
    questions: [seoGeoAnswers[0], seoGeoAnswers[1]],
    cluster: "use-cases",
    pageType: "hub",
    schemaType: "CollectionPage",
    ctaLabel: "查看使用场景",
    ctaHash: "download"
  },
  {
    path: "/use-cases/course-learning/",
    primaryKeyword: "公开视频课程学习",
    title: "公开视频课程学习 - 下载总结复习笔记",
    description: "公开视频课程学习可以用 SaveAny 保存公开课视频、整理字幕、生成 AI 摘要、知识点、思维导图和 Markdown 复习笔记。",
    keywords: ["公开视频课程学习", "课程视频总结", "课程复习笔记", "AI课程笔记", "公开课下载"],
    heading: "公开视频课程学习，把公开课变成复习笔记",
    lead: "公开课程适合先保存和整理字幕，再把章节、知识点和追问沉淀成长期复习资料。",
    geoSummary: "课程学习场景页面向学生和自学者，聚合公开视频下载、字幕、AI 总结、思维导图和 Markdown 导出。",
    sections: ["解析公开课程标题、封面、时长和字幕。", "生成章节大纲、核心知识点和术语解释。", "导出 Markdown 作为复习提纲或知识库条目。"],
    useCases: ["公开课离线复习。", "系列教程按章节整理。", "考前快速回看课程重点。"],
    howToSteps: ["复制公开视频课程链接", "粘贴到 SaveAny 并解析", "检查字幕和可用格式", "生成 AI 课程总结", "导出 Markdown 复习笔记"],
    failureReasons: ["课程需要登录、付费或权限。", "视频没有字幕且转写服务未配置。", "播放列表或合集结构无法完整解析。"],
    relatedPaths: ["/how-to-video-summary/", "/bilibili-course-downloader/", "/youtube-video-summary-tool/", "/features/ai-video-summary/", "/use-cases/"],
    questions: [seoGeoAnswers[2], seoFaqs[2]],
    cluster: "use-cases",
    pageType: "use-case",
    ctaLabel: "生成课程复习笔记",
    ctaHash: "download"
  },
  {
    path: "/use-cases/content-archive/",
    primaryKeyword: "公开视频素材归档",
    title: "公开视频素材归档 - 下载字幕总结流程",
    description: "公开视频素材归档可以用 SaveAny 完成链接解析、视频保存、字幕提取、AI 总结、思维导图和 Markdown 资料沉淀。",
    keywords: ["公开视频素材归档", "视频素材整理", "公开视频下载", "素材总结", "内容复盘"],
    heading: "公开视频素材归档，让案例和资料可检索",
    lead: "内容运营、研究者和资料整理者常常需要同时保存公开视频、整理字幕、提炼观点和沉淀笔记。",
    geoSummary: "素材归档场景页强调公开视频保存、字幕、摘要和知识库沉淀的完整流程。",
    sections: ["按平台和主题收集公开视频链接。", "保存可用视频文件和字幕文本。", "用 AI 总结提炼主题、章节和关键观点。"],
    useCases: ["内容团队整理案例库。", "研究者归档公开视频资料。", "个人知识库沉淀长期素材。"],
    howToSteps: ["收集公开视频链接", "解析视频和可用格式", "选择清晰度并下载", "生成字幕与 AI 总结", "导出 Markdown 并归档"],
    failureReasons: ["链接不是公开视频。", "平台接口或短链跳转失败。", "无字幕时需要可用转写配置。"],
    relatedPaths: ["/public-video-archive-workflow/", "/online-video-downloader/", "/features/video-download/", "/features/subtitle-extraction/", "/use-cases/"],
    questions: [seoGeoAnswers[1], seoFaqs[4]],
    cluster: "use-cases",
    pageType: "use-case",
    ctaLabel: "整理公开视频素材",
    ctaHash: "download"
  },
  {
    path: "/use-cases/meeting-review/",
    primaryKeyword: "公开视频会议复盘",
    title: "公开视频会议复盘 - 字幕摘要行动项",
    description: "公开视频会议复盘可用 SaveAny 整理公开会议或讲座录播，生成字幕文本、AI 摘要、时间线、问答和 Markdown 复盘笔记。",
    keywords: ["公开视频会议复盘", "会议视频总结", "录播总结", "行动项整理", "Markdown复盘"],
    heading: "公开视频会议复盘，把录播变成行动资料",
    lead: "公开会议、讲座和访谈录播可以先转成字幕文本，再生成摘要、时间线和可追问的复盘资料。",
    geoSummary: "会议复盘场景页服务公开录播整理，不处理私密会议、无授权内容或需要登录权限的视频。",
    sections: ["生成会议概览、议题时间线和关键观点。", "围绕字幕和总结继续提问。", "导出 Markdown 复盘笔记，方便团队共享。"],
    useCases: ["公开讲座复盘。", "团队学习公开会议录播。", "访谈和播客观点整理。"],
    howToSteps: ["确认录播是公开可访问内容", "粘贴链接并解析", "整理字幕或转写文本", "生成 AI 复盘摘要", "导出 Markdown 并补充行动项"],
    failureReasons: ["录播需要登录或权限。", "音频质量影响转写。", "内容过长时需要等待完整总结完成。"],
    relatedPaths: ["/video-summary/", "/video-to-text/", "/ai-video-notes/", "/features/ai-video-summary/", "/use-cases/"],
    questions: [seoFaqs[2], seoGeoAnswers[0]],
    cluster: "use-cases",
    pageType: "use-case",
    ctaLabel: "生成会议复盘笔记",
    ctaHash: "download"
  },
  {
    path: "/compare/",
    primaryKeyword: "视频下载总结工具对比",
    title: "视频下载总结工具对比 - SaveAny选择指南",
    description: "视频下载总结工具对比页说明如何从公开视频解析、字幕提取、AI 总结、思维导图、导出和合规边界评估工具。",
    keywords: ["视频下载总结工具对比", "AI视频总结工具对比", "在线视频下载器对比", "SaveAny对比", "视频笔记工具"],
    heading: "视频下载总结工具对比，先看工作流和边界",
    lead: "选择工具时不只看能否下载，还要看字幕来源、总结结构、导出能力、隐私边界和合规说明。",
    geoSummary: "对比 hub 帮用户理解 SaveAny 与普通下载器、单一 AI 总结器和在线工具之间的差异。",
    sections: ["普通下载器通常只解决文件保存。", "单一 AI 总结器未必能保存素材和字幕。", "SaveAny 把公开视频保存、字幕、摘要、思维导图、问答和 Markdown 放在同一流程。"],
    topicLinks: ["/saveany-vs-online-video-downloader/", "/ai-video-summary-tool-comparison/", "/articles/yt-dlp-ai-summary-legal-use-cases/"],
    relatedPaths: ["/saveany-vs-online-video-downloader/", "/ai-video-summary-tool-comparison/", "/features/", "/facts/", "/terms/"],
    questions: [seoGeoAnswers[1], seoFaqs[3]],
    cluster: "compare",
    pageType: "hub",
    schemaType: "CollectionPage",
    ctaLabel: "查看对比页面",
    ctaHash: "download"
  },
  {
    path: "/pricing/",
    primaryKeyword: "SaveAny套餐方案",
    title: "SaveAny套餐方案 - 免费版专业版团队版",
    description: "SaveAny套餐方案说明免费版、专业版和团队版的公开视频下载、AI 总结额度、字幕整理、思维导图和自托管使用边界。",
    keywords: ["SaveAny套餐方案", "SaveAny价格", "AI视频总结价格", "视频下载会员", "专业版"],
    heading: "SaveAny套餐方案，按使用频率选择",
    lead: "下载功能保持轻量可用，AI 总结按账号和额度规划；高频学习、内容整理和团队工作流可选择专业版或团队版。",
    geoSummary: "定价页让搜索引擎和用户直接理解 SaveAny 的免费体验、专业版价值、团队规划和会员合规边界。",
    sections: ["免费版适合体验公开视频解析、下载和少量 AI 总结。", "专业版适合高频 AI 视频笔记、字幕整理和 Markdown 导出。", "团队版面向课程团队、内容团队和自托管协作规划。"],
    useCases: ["偶尔保存公开视频并体验总结。", "长期学习者高频生成课程笔记。", "内容团队整理公开素材和共享知识库。"],
    relatedPaths: ["/features/", "/features/ai-video-summary/", "/use-cases/course-learning/", "/privacy/", "/terms/"],
    questions: [
      {
        question: "SaveAny 免费版可以做什么？",
        answer: "免费版适合体验公开视频解析、稳定 MP4 下载和每日少量 AI 总结额度，具体额度以服务端配置为准。"
      },
      {
        question: "什么时候需要专业版？",
        answer: "当你需要高频生成 AI 视频总结、思维导图、问答和 Markdown 学习笔记时，专业版更适合。"
      }
    ],
    cluster: "brand",
    pageType: "pricing",
    schemaType: "SoftwareApplication",
    ctaLabel: "查看套餐方案",
    ctaHash: "pricing"
  }
];
```

- [ ] **Step 3: Spread cluster pages into `SEO_PAGES`**

In `SEO_PAGES`, insert this line immediately after the `/online-video-downloader/` page object and before the first `/articles/` page object:

```js
  ...seoClusterPages,
```

- [ ] **Step 4: Run the targeted frontend SEO test**

Run:

```bash
cd frontend
npm test -- tests/seo-metadata.test.js
```

Expected: The route matrix and taxonomy tests move forward. Hub/pricing rendering tests still fail until generator support is added.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add frontend/src/seo/pages.js frontend/tests/seo-metadata.test.js
git commit -m "feat: 增加 SEO 主题集群页面数据" -m "新增 SaveAny 功能、平台、场景、对比和定价主题页的数据定义，并用单测锁定 URL 顺序、页面分类、内链和转化 CTA。"
```

## Task 3: Render Hub Sections, Pricing Sections, And `.well-known/ai.json`

**Files:**
- Modify: `frontend/scripts/generate-seo-assets.mjs`
- Modify: `frontend/scripts/validate-seo-deploy.mjs`
- Modify: `frontend/tests/seo-metadata.test.js`
- Generate: `frontend/public/.well-known/ai.json`

- [ ] **Step 1: Import pricing facts and add test imports**

In `frontend/scripts/generate-seo-assets.mjs`, add `seoPricingPlans` to the import list from `../src/seo/pages.js`:

```js
  seoPlatforms,
  seoPricingPlans,
  seoRelatedLinks,
  seoSite
```

In `frontend/tests/seo-metadata.test.js`, add `buildAiJson` to the import list from `../scripts/generate-seo-assets.mjs`:

```js
  buildAiJson,
  buildHtmlSitemapPage,
```

- [ ] **Step 2: Add AI facts and CTA tests**

Add these tests after the LLM files test:

```js
test(".well-known ai.json exposes product facts without claiming MCP", () => {
  const payload = JSON.parse(buildAiJson("https://saveany.example"));

  assert.equal(payload.name, "万能视频下载总结器");
  assert.equal(payload.brand, "SaveAny");
  assert.equal(payload.url, "https://saveany.example/");
  assert.ok(payload.capabilities.includes("AI 视频总结"));
  assert.ok(payload.supported_public_sources.includes("YouTube"));
  assert.equal(payload.primary_action.url, "https://saveany.example/#download");
  assert.ok(payload.limitations.some((item) => item.includes("DRM")));
  assert.equal(payload.mcp, undefined);
});

test("landing pages use intent-specific conversion labels", () => {
  const platformPage = SEO_PAGES.find((item) => item.path === "/platforms/youtube/");
  const pricingPage = SEO_PAGES.find((item) => item.path === "/pricing/");

  assert.match(buildLandingPageHtml(platformPage, "https://saveany.example"), /解析 YouTube 公开视频/);
  assert.match(buildLandingPageHtml(pricingPage, "https://saveany.example"), /href="https:\/\/saveany\.example\/#pricing"/);
});
```

- [ ] **Step 3: Add helper renderers**

Insert these helpers after `buildOptionalListSectionHtml` in `frontend/scripts/generate-seo-assets.mjs`:

```js
function buildTopicLinksHtml(page, siteUrl) {
  if (!page.topicLinks?.length) return "";
  const items = page.topicLinks
    .map((path) => seoRelatedLinks.find((link) => link.path === path))
    .filter(Boolean)
    .map(
      (link) => `<li>
            <a href="${pageUrl(siteUrl, link.path)}">${escapeHtml(link.title)}</a>
            <span>${escapeHtml(link.description)}</span>
          </li>`
    )
    .join("\n          ");
  if (!items) return "";
  return `<section aria-labelledby="topic-links">
        <h2 id="topic-links">主题导航</h2>
        <ul>
          ${items}
        </ul>
      </section>`;
}

function buildPricingPlansHtml(page) {
  if (page.pageType !== "pricing") return "";
  const items = seoPricingPlans
    .map(
      (plan) => `<li>
            <strong>${escapeHtml(plan.name)}</strong>
            <span>${escapeHtml(plan.price === "0" ? "免费" : `¥${plan.price}/${plan.billingPeriod === "monthly" ? "月" : "周期"}`)}</span>
            <p>${escapeHtml(plan.description)}</p>
            <small>${escapeHtml(plan.features.join(" / "))}</small>
          </li>`
    )
    .join("\n          ");
  return `<section aria-labelledby="pricing-plans">
        <h2 id="pricing-plans">套餐方案</h2>
        <ul>
          ${items}
        </ul>
      </section>`;
}

function ctaUrlForPage(page, origin) {
  if (page.ctaPath) return pageUrl(origin, page.ctaPath);
  return `${origin}/#${page.ctaHash || "download"}`;
}
```

- [ ] **Step 4: Wire helper renderers into HTML output**

In `buildLandingPageHtml`, replace:

```js
  const appUrl = `${origin}/#download`;
```

with:

```js
  const ctaUrl = ctaUrlForPage(page, origin);
  const ctaLabel = page.ctaLabel || "打开下载总结器";
```

Then replace:

```js
  const optionalSectionsHtml = [useCases, howTo, failureReasons].filter(Boolean).join("\n      ");
```

with:

```js
  const topicLinks = buildTopicLinksHtml(page, origin);
  const pricingPlans = buildPricingPlansHtml(page);
  const optionalSectionsHtml = [useCases, howTo, failureReasons, topicLinks, pricingPlans].filter(Boolean).join("\n      ");
```

Then replace:

```html
      <a class="cta" href="${appUrl}">打开下载总结器</a>
```

with:

```html
      <a class="cta" href="${ctaUrl}">${escapeHtml(ctaLabel)}</a>
```

- [ ] **Step 5: Render topic and pricing sections in Markdown**

In `buildLandingPageMarkdown`, add these constants before the returned template:

```js
  const topicLinks = page.topicLinks?.length
    ? `\n## 主题导航\n${page.topicLinks
        .map((path) => seoRelatedLinks.find((link) => link.path === path))
        .filter(Boolean)
        .map((link) => `- [${link.title}](${pageUrl(siteUrl, link.path)}): ${link.description}`)
        .join("\n")}\n`
    : "";
  const pricingPlans =
    page.pageType === "pricing"
      ? `\n## 套餐方案\n${seoPricingPlans
          .map((plan) => `- **${plan.name}**：${plan.price === "0" ? "免费" : `¥${plan.price}/${plan.billingPeriod === "monthly" ? "月" : "周期"}`}。${plan.description} 功能：${plan.features.join("、")}。`)
          .join("\n")}\n`
      : "";
```

Then insert `${topicLinks}` and `${pricingPlans}` between `${failureReasons}` and `## 常见问题` in the Markdown template:

```md
${failureReasons}
${topicLinks}
${pricingPlans}

## 常见问题
```

- [ ] **Step 6: Add grouped LLM page output**

Add these helpers before `buildLlmsTxt`:

```js
function clusterLabel(cluster) {
  return {
    brand: "Brand And Trust",
    features: "Feature Pages",
    platforms: "Platform Pages",
    "use-cases": "Use Case Pages",
    compare: "Comparison Pages"
  }[cluster || ""] || "Task And Article Pages";
}

function buildGroupedPageLines(siteUrl) {
  const origin = normalizeSiteUrl(siteUrl);
  const groups = new Map();
  for (const page of SEO_PAGES) {
    const label = clusterLabel(page.cluster);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(`- [${page.primaryKeyword}](${pageUrl(origin, page.path)}): ${page.description}`);
  }
  return [...groups.entries()].map(([label, lines]) => `### ${label}\n${lines.join("\n")}`).join("\n\n");
}
```

In `buildLlmsTxt`, replace the `pageLines` expression with:

```js
  const pageLines = buildGroupedPageLines(origin);
```

Keep the existing `## Recommended Pages` section; it should now contain grouped headings.

- [ ] **Step 7: Add `.well-known/ai.json` builder**

Add this export before `writeSeoAssets`:

```js
export function buildAiJson(siteUrl = normalizeSiteUrl()) {
  const origin = normalizeSiteUrl(siteUrl);
  return `${JSON.stringify(
    {
      name: seoSite.productName,
      brand: seoSite.brandName,
      description: seoSite.description,
      url: `${origin}/`,
      language: seoSite.language,
      application_category: seoSite.appCategory,
      capabilities: seoCapabilities,
      supported_public_sources: seoPlatforms,
      primary_action: {
        url: `${origin}/#download`,
        method: "paste_public_video_url",
        description: "粘贴公开视频链接，解析视频信息，按需下载、提取字幕或生成 AI 学习笔记。"
      },
      limitations: [
        "不处理私密视频、付费视频、DRM 视频或需要登录的视频。",
        "不提供 Cookie 上传、登录绕过、验证码绕过、地区限制绕过或平台风控绕过。",
        "解析结果会受公开视频状态、平台策略、地区和网络环境影响。"
      ],
      docs: {
        facts: `${origin}/facts/`,
        faq: `${origin}/faq/`,
        privacy: `${origin}/privacy/`,
        terms: `${origin}/terms/`,
        llms: `${origin}/llms.txt`,
        llms_full: `${origin}/llms-full.txt`
      }
    },
    null,
    2
  )}\n`;
}
```

- [ ] **Step 8: Write `.well-known/ai.json` during generation**

In `writeSeoAssets`, after writing `llms-full.txt`, insert:

```js
  const wellKnownDir = resolve(resolvedPublicDir, ".well-known");
  await mkdir(wellKnownDir, { recursive: true });
  await writeFile(resolve(wellKnownDir, "ai.json"), buildAiJson(siteUrl), "utf8");
```

- [ ] **Step 9: Update static headers**

In `buildStaticHeadersFile`, add this block after `/llms-full.txt`:

```text

/.well-known/ai.json
  Cache-Control: no-cache
```

- [ ] **Step 10: Update deployment validation**

In `frontend/scripts/validate-seo-deploy.mjs`, add `"/.well-known/ai.json"` to `REQUIRED_GEO_PATHS` after `"/llms-full.txt"`:

```js
  "/llms-full.txt",
  "/.well-known/ai.json",
  "/index.html.md",
```

Also add `.well-known/ai.json` to `filesWithCanonical`:

```js
  const filesWithCanonical = ["404.html", "robots.txt", "sitemap.xml", "llms.txt", "llms-full.txt", ".well-known/ai.json", "index.html.md", "sitemap/index.html"];
```

- [ ] **Step 11: Update validation expected count**

In the last frontend SEO test, replace:

```js
    assert.equal(report.checkedPaths, SEO_PAGES.length * 2 + 7);
```

with:

```js
    assert.equal(report.checkedPaths, SEO_PAGES.length * 2 + 8);
```

- [ ] **Step 12: Run targeted tests**

Run:

```bash
cd frontend
npm test -- tests/seo-metadata.test.js
```

Expected: Hub/pricing rendering and `.well-known/ai.json` tests pass. Structured data tests may still fail until Task 4.

- [ ] **Step 13: Commit Task 3**

Run:

```bash
git add frontend/scripts/generate-seo-assets.mjs frontend/scripts/validate-seo-deploy.mjs frontend/tests/seo-metadata.test.js
git commit -m "feat: 生成 SEO 主题页与 AI 事实文件" -m "扩展静态 SEO 生成器，支持主题导航、定价内容、自定义 CTA、分组 llms 输出和 .well-known/ai.json，同时把新发现文件纳入部署校验。"
```

## Task 4: Add Structured Data For Hubs, Articles, And Pricing

**Files:**
- Modify: `frontend/src/seo/pages.js`
- Modify: `frontend/tests/seo-metadata.test.js`

- [ ] **Step 1: Add structured data tests**

Add this test after `page structured data includes crawlable FAQ and capability lists`:

```js
test("topic, article, and pricing pages expose matching structured data", () => {
  const hub = SEO_PAGES.find((item) => item.path === "/features/");
  const hubGraph = getPageJsonLd(hub, "https://saveany.example")["@graph"];
  assert.ok(hubGraph.some((item) => item["@type"] === "CollectionPage"));

  const article = SEO_PAGES.find((item) => item.path === "/articles/public-video-downloader-drm-boundary/");
  const articleGraph = getPageJsonLd({ ...article, schemaType: "Article" }, "https://saveany.example")["@graph"];
  assert.ok(articleGraph.some((item) => item["@type"] === "Article"));

  const pricing = SEO_PAGES.find((item) => item.path === "/pricing/");
  const pricingGraph = getPageJsonLd(pricing, "https://saveany.example")["@graph"];
  const pricingApp = pricingGraph.find((item) => item["@type"] === "SoftwareApplication" && item["@id"].endsWith("#pricing-software"));

  assert.equal(pricingApp.offers["@type"], "OfferCatalog");
  assert.equal(pricingApp.offers.itemListElement.length, 3);
  assert.match(JSON.stringify(pricingApp), /专业版/);
});
```

- [ ] **Step 2: Import pricing facts into JSON-LD scope**

`seoPricingPlans` is in the same module, so no import is needed inside `frontend/src/seo/pages.js`. Confirm the symbol is exported as written in Task 2.

- [ ] **Step 3: Update `getPageJsonLd` WebPage type**

In `getPageJsonLd`, before `const graph = [`, add:

```js
  const pageSchemaType = page.schemaType || (page.pageType === "hub" ? "CollectionPage" : "WebPage");
```

Then replace the `WebPage` graph node type:

```js
      "@type": "WebPage",
```

with:

```js
      "@type": pageSchemaType === "Article" || pageSchemaType === "SoftwareApplication" ? "WebPage" : pageSchemaType,
```

- [ ] **Step 4: Add Article structured data**

In `getPageJsonLd`, after the `HowTo` block, add:

```js
  if (page.schemaType === "Article" || page.path?.startsWith("/articles/")) {
    graph.push({
      "@type": "Article",
      "@id": `${pageAbsoluteUrl}#article`,
      headline: page.heading,
      description: page.description,
      inLanguage: seoSite.language,
      dateModified: page.lastUpdated || seoSite.lastUpdated,
      author: {
        "@id": `${origin}/#organization`
      },
      publisher: {
        "@id": `${origin}/#organization`
      },
      mainEntityOfPage: {
        "@id": `${pageAbsoluteUrl}#webpage`
      }
    });
  }
```

- [ ] **Step 5: Add pricing SoftwareApplication structured data**

After the Article block, add:

```js
  if (page.pageType === "pricing" || page.path === "/pricing/") {
    graph.push({
      "@type": "SoftwareApplication",
      "@id": `${pageAbsoluteUrl}#pricing-software`,
      name: seoSite.productName,
      alternateName: seoSite.brandName,
      url: pageAbsoluteUrl,
      applicationCategory: seoSite.appCategory,
      operatingSystem: seoSite.operatingSystem,
      inLanguage: seoSite.language,
      description: page.description,
      offers: {
        "@type": "OfferCatalog",
        name: "SaveAny 套餐方案",
        itemListElement: seoPricingPlans.map((plan, index) => ({
          "@type": "Offer",
          position: index + 1,
          name: plan.name,
          description: plan.description,
          price: plan.price,
          priceCurrency: plan.priceCurrency,
          availability: "https://schema.org/InStock",
          url: pageAbsoluteUrl
        }))
      },
      publisher: {
        "@id": `${origin}/#organization`
      }
    });
  }
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
cd frontend
npm test -- tests/seo-metadata.test.js
```

Expected: All frontend SEO tests pass.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add frontend/src/seo/pages.js frontend/tests/seo-metadata.test.js
git commit -m "feat: 补充 SEO 结构化数据" -m "为主题 hub、文章页和定价页补充 CollectionPage、Article 与套餐 OfferCatalog 结构化数据，确保静态 HTML 中包含可抓取 JSON-LD。"
```

## Task 5: Extend GEO Monitor For New Surfaces

**Files:**
- Modify: `backend/app/services/geo_monitor.py`
- Modify: `backend/tests/test_geo_monitor.py`

- [ ] **Step 1: Add GEO monitor tests for new surfaces**

In `test_geo_monitor_classifies_ai_crawlers_and_surfaces`, add these assertions after `assert is_geo_surface_path("/facts/")`:

```python
    assert is_geo_surface_path("/.well-known/ai.json")
    assert is_geo_surface_path("/features/")
    assert is_geo_surface_path("/platforms/youtube/")
    assert is_geo_surface_path("/use-cases/course-learning/index.html.md")
    assert is_geo_surface_path("/pricing/")
```

- [ ] **Step 2: Update `GEO_ROOT_PATHS`**

In `backend/app/services/geo_monitor.py`, add `"/.well-known/ai.json"` to `GEO_ROOT_PATHS`:

```python
    "/llms-full.txt",
    "/.well-known/ai.json",
    "/index.html.md",
```

- [ ] **Step 3: Update `GEO_PAGE_PREFIXES`**

Add these prefixes to `GEO_PAGE_PREFIXES` after `"/online-video-downloader/"`:

```python
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
```

- [ ] **Step 4: Run backend GEO monitor tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_geo_monitor.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add backend/app/services/geo_monitor.py backend/tests/test_geo_monitor.py
git commit -m "feat: 扩展 GEO 访问监控范围" -m "将新增主题集群页、定价页和 .well-known/ai.json 纳入 GEO surface 检测，确保搜索和 AI crawler 访问能进入隐私轻量日志。"
```

## Task 6: Regenerate Static Assets And Verify End To End

**Files:**
- Generate: `frontend/public/**`
- Verify: `frontend/dist/**` is build output and should not be committed unless the repository already tracks it.

- [ ] **Step 1: Generate static SEO assets**

Run:

```bash
cd frontend
npm run seo:generate
```

Expected: generated files include:

```text
frontend/public/.well-known/ai.json
frontend/public/features/index.html
frontend/public/features/index.html.md
frontend/public/features/video-download/index.html
frontend/public/features/video-download/index.html.md
frontend/public/features/ai-video-summary/index.html
frontend/public/features/ai-video-summary/index.html.md
frontend/public/features/subtitle-extraction/index.html
frontend/public/features/subtitle-extraction/index.html.md
frontend/public/features/mind-map/index.html
frontend/public/features/mind-map/index.html.md
frontend/public/platforms/index.html
frontend/public/platforms/index.html.md
frontend/public/platforms/youtube/index.html
frontend/public/platforms/youtube/index.html.md
frontend/public/platforms/bilibili/index.html
frontend/public/platforms/bilibili/index.html.md
frontend/public/platforms/douyin/index.html
frontend/public/platforms/douyin/index.html.md
frontend/public/platforms/tiktok/index.html
frontend/public/platforms/tiktok/index.html.md
frontend/public/use-cases/index.html
frontend/public/use-cases/index.html.md
frontend/public/use-cases/course-learning/index.html
frontend/public/use-cases/course-learning/index.html.md
frontend/public/use-cases/content-archive/index.html
frontend/public/use-cases/content-archive/index.html.md
frontend/public/use-cases/meeting-review/index.html
frontend/public/use-cases/meeting-review/index.html.md
frontend/public/compare/index.html
frontend/public/compare/index.html.md
frontend/public/pricing/index.html
frontend/public/pricing/index.html.md
```

- [ ] **Step 2: Run frontend SEO tests**

Run:

```bash
cd frontend
npm test -- tests/seo-metadata.test.js
```

Expected: PASS with all SEO tests green.

- [ ] **Step 3: Run backend GEO monitor tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_geo_monitor.py
```

Expected: PASS.

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. Vite writes production assets to `frontend/dist`. Do not stage `frontend/dist` unless `git status --short frontend/dist` shows it is already tracked by this repository.

- [ ] **Step 5: Dry-run IndexNow payload**

Run:

```bash
cd frontend
INDEXNOW_KEY=abcdef1234567890abcdef1234567890 PUBLIC_SITE_URL=https://www.saveany.example npm run seo:indexnow:dry-run -- --all
```

Expected: JSON output includes `"host": "www.saveany.example"` and URLs for `/features/`, `/platforms/`, `/use-cases/`, `/compare/`, and `/pricing/`.

- [ ] **Step 6: Confirm production validation behavior**

Run:

```bash
cd frontend
npm run seo:validate
```

Expected: FAIL while local config still uses `https://saveany.local`, with messages about fallback domain. This is correct until a real production domain is supplied.

Then run this temp-directory validation:

```bash
cd frontend
node --input-type=module -e "import { mkdtemp, rm } from 'node:fs/promises'; import { tmpdir } from 'node:os'; import { join } from 'node:path'; import { writeSeoAssets } from './scripts/generate-seo-assets.mjs'; import { validateGeneratedAssets } from './scripts/validate-seo-deploy.mjs'; const publicDir = await mkdtemp(join(tmpdir(), 'saveany-seo-plan-')); await writeSeoAssets({ publicDir, siteUrl: 'https://www.saveany.example', lastmod: '2026-05-02' }); const report = await validateGeneratedAssets({ publicDir, siteUrl: 'https://www.saveany.example', allowReserved: true }); console.log(JSON.stringify({ ok: report.ok, checkedPaths: report.checkedPaths, errors: report.errors }, null, 2)); await rm(publicDir, { recursive: true, force: true }); if (!report.ok) process.exit(1);"
```

Expected: PASS and prints `"ok": true`.

- [ ] **Step 7: Inspect generated public assets**

Run:

```bash
git status --short frontend/public frontend/src/seo/pages.js frontend/scripts/generate-seo-assets.mjs frontend/scripts/validate-seo-deploy.mjs frontend/scripts/submit-indexnow.mjs frontend/tests/seo-metadata.test.js backend/app/services/geo_monitor.py backend/tests/test_geo_monitor.py
```

Expected: generated `frontend/public` files and source/test files are visible. `frontend/scripts/submit-indexnow.mjs` should only appear if Task 3 intentionally updated fingerprint fields; if it did not change, do not stage it.

- [ ] **Step 8: Commit Task 6**

Run:

```bash
git add frontend/public frontend/src/seo/pages.js frontend/scripts/generate-seo-assets.mjs frontend/scripts/validate-seo-deploy.mjs frontend/tests/seo-metadata.test.js backend/app/services/geo_monitor.py backend/tests/test_geo_monitor.py
git commit -m "feat: 完成 SaveAny SEO 主题集群与 AI 事实层" -m "生成新增主题集群页、定价页、Markdown mirror、sitemap、llms 文件和 .well-known/ai.json，并通过前端 SEO 单测、后端 GEO monitor 单测、Vite 构建、IndexNow dry-run 和临时生产域名校验。"
```

## Self-Review Checklist

- Spec coverage: Tasks 1-6 cover route matrix, topic clusters, conversion CTA, `.well-known/ai.json`, structured data, generation, validation, IndexNow dry-run, GEO monitor, generated assets, and production-domain validation.
- No ambiguous new URLs: duplicate `/compare/saveany-vs-online-video-downloader/` is intentionally not created in this implementation; existing `/saveany-vs-online-video-downloader/` remains canonical until a later redirect/canonical migration is explicitly approved.
- Type consistency: page metadata uses `cluster`, `pageType`, `schemaType`, `ctaLabel`, `ctaHash`, `topicLinks`, and existing `relatedPaths`; generator helpers read those exact names.
- Verification commands: every task has a concrete command and expected result.
