# SEO Progress

## 2026-04-30

- Loaded `seo-audit` workflow from the user-provided skill.
- Read provided SEO workflow and TDK writing specification documents.
- Inspected product requirements, product design, feature summary, `frontend/index.html`, and `frontend/src/App.vue`.
- Created planning files to track the multi-step SEO optimization.
- Checked official Google/Bing SEO guidance for crawl/index/sitemap/canonical/structured-data strategy before expanding the design plan.
- Added SEO metadata tests, then implemented shared SEO page configuration and generation helpers.
- Added homepage TDK, Open Graph, Twitter card, JSON-LD, noscript fallback, and same-origin runtime canonical/OG URL correction.
- Added crawlable FAQ/use-case/compliance content to the Vue homepage without changing download or summary behavior.
- Added generated SEO assets: `robots.txt`, `sitemap.xml`, `llms.txt`, and static landing pages for AI summary, platform downloaders, subtitles, FAQ, privacy, and terms.
- Fixed Vite build failure caused by relative canonical `href="/"` by using a build-time `__SEO_SITE_URL__` placeholder.
- Verification passed: `npm test` and `npm run build`.
- Iteration pass: verified existing state with `npm test` and `npm run build`.
- Added tests for richer landing pages, FAQ structured data, real internal SEO links, and build-time-only canonical handling.
- Added visible internal links from the Vue homepage to real SEO landing pages.
- Expanded generated static landing pages with use cases, FAQ blocks, related-page links, and FAQPage JSON-LD for `/faq/`.
- Removed runtime canonical/OG URL mutation so canonical URLs are controlled by build-time `VITE_PUBLIC_SITE_URL` or `PUBLIC_SITE_URL`.
- GEO pass: made "万能视频下载总结器" the preferred product name across SEO data, homepage metadata, JSON-LD, `llms.txt`, and generated landing assets.
- Added AI-answer style Q&A content, `llms-full.txt`, and Markdown mirrors (`index.html.md`) for the homepage and each static landing page.
- Added AI crawler handling in `robots.txt`: search/user-request crawlers can access content pages while API/file/runtime paths stay blocked; training-oriented crawlers are blocked by default.
- Final verification passed: `npm test` (54 tests) and `npm run build`.
- Growth SEO iteration: added 8 keyword-matrix pages for YouTube 转 MP4、YouTube 字幕下载、B站课程视频下载、抖音公开视频下载、视频转文字、视频转思维导图、AI 视频笔记、在线视频下载器.
- Added crawlable `/sitemap/` HTML sitemap generation and removed the stale `/sitemap.html` generated artifact to avoid duplicate sitemap entry points.
- Added topic-specific related links for new keyword pages, plus IndexNow tooling with payload generation, same-host validation, verification-key file generation, dry-run support, and npm scripts.
- Regenerated `frontend/public` SEO assets so all 27 canonical pages have HTML and Markdown mirrors.
- Verification passed: targeted SEO test suite (14 tests), full frontend `npm test` (60 tests), frontend `npm run build`, IndexNow dry-run with test env, and backend pytest (99 tests).
- Deployment hardening pass: added generated `_headers`, `_redirects`, `404.html`, webmaster verification meta/file support, and `docs/10-seo-deployment-checklist.md`.
- FastAPI self-hosting pass: unknown frontend paths now return real 404 instead of SPA soft 404, directory pages redirect to trailing slash, HTML responses use `Cache-Control: no-cache`, and hashed assets get long immutable cache headers.
- Canonical host pass: optional `SEO_CANONICAL_REDIRECTS=true` redirects frontend GET/HEAD requests to the configured HTTPS canonical origin while leaving API/file routes alone.
- Performance pass: `SummaryPanel` is now loaded as an async Vue component. Production build split `SummaryPanel-BTL95JGD.js` and reduced the main JS bundle to about 151 KB before gzip.
- Validation pass: `npm test` now covers 65 frontend tests, backend pytest covers 105 tests, production build passes, and a test-domain SEO asset validation passed for 61 generated paths.
