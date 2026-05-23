# SEO Findings

## Source Material
- Product name/context: "万能视频下载器", "万能视频下载总结器", brand shown as SaveAny.
- Product value: paste public video links, analyze metadata, choose quality, download locally, and generate AI video summaries.
- Supported platforms in current UI: YouTube, Bilibili, TikTok, Instagram, X / Twitter, Vimeo, Facebook, 小红书, 抖音, Reddit.
- Safety positioning: public/self-hosted use, no login bypass, no DRM/paywall bypass, clear copyright/platform-risk notices.

## Provided SEO/TDK Rules
- Title should be unique, relevant, concise, and place primary keywords early.
- Recommended title structure: core keyword - long-tail modifier/value point | brand.
- Description should combine keyword + user pain/need + solution/value + CTA.
- Keywords meta is not a modern ranking factor, but may be kept for internal planning/smaller engines with 3-5 keywords.

## Current Frontend Audit
- `frontend/index.html` has a basic Chinese `description` and title.
- App is a Vue 3/Vite SPA.
- Navigation uses hash states: `#download`, `#features`, `#platforms`, `#pricing`.
- `App.vue` renders the main download page with `v-show`, and other views with `v-if`.
- Existing content is user-facing and conversion-oriented, but most SEO metadata is static and minimal.

## Initial SEO Risks
- Hash routes are usually not treated as separate indexable pages.
- Search engines may not reliably see route-specific `v-if` content before hydration.
- No robots.txt or sitemap.xml was found in the current file list.
- No structured data detected in current `index.html`.
- Production domain/canonical host is unknown.

## Official Guidance Checked
- Google Search works through crawling, indexing, and serving. Sitemaps help URL discovery, but indexing/ranking is not guaranteed.
- Google recommends accessible CSS/JS/images for rendering, descriptive URLs, canonicalization for duplicate content, useful text content, and alt text.
- Google technical SEO guidance treats robots.txt and sitemaps differently: robots controls crawling, sitemap encourages crawling of important URLs.
- Structured data helps search engines understand page content; Bing supports JSON-LD and warns against inaccurate/spam markup.

## Implementation Findings
- Added real static SEO landing pages under `frontend/public/*/index.html`; these avoid relying on hash routes for search discovery.
- Added `frontend/scripts/generate-seo-assets.mjs`; it uses `PUBLIC_SITE_URL` or `VITE_PUBLIC_SITE_URL` and falls back to `https://saveany.local`.
- `npm run build` runs the SEO generator through `prebuild`.
- Homepage SEO URL placeholders are replaced by a Vite `transformIndexHtml` plugin.
- Production deployments must set `VITE_PUBLIC_SITE_URL` or `PUBLIC_SITE_URL` to avoid fallback canonical/sitemap URLs.

## Iteration Findings
- Static SEO pages were discoverable by sitemap, but the Vue homepage did not visibly link to the real SEO URLs. Added related-page internal links to improve crawl paths and PageRank flow.
- Static landing pages had enough metadata but relatively thin body content. Expanded them with use cases, FAQ content, and related-page links.
- The FAQ static page now includes `FAQPage` JSON-LD in addition to `WebPage` and breadcrumbs.
- Runtime canonical rewriting was removed. Canonical and `og:url` are now controlled by the build-time site URL only, avoiding accidental staging/mirror-domain canonicals.
- Remaining off-code work: set the production domain, submit sitemap in Google Search Console/Bing Webmaster/百度搜索资源平台, and optionally add IndexNow after a real domain exists.

## GEO Implementation Findings
- Preferred product naming is now "万能视频下载总结器"; SaveAny remains the brand alias in metadata and structured data.
- `robots.txt` explicitly allows AI search/user-request crawlers such as OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Googlebot, and Bingbot while blocking `/api/`, `/files/`, and `/runtime/`.
- Training-oriented crawlers are blocked by default through `GPTBot`, `ClaudeBot`, and `CCBot` groups.
- `llms.txt` now acts as a compact AI-readable content map, and `llms-full.txt` provides a longer product reference with page summaries, capabilities, FAQ, and compliance boundaries.
- Every SEO landing page now has a generated `index.html.md` Markdown mirror for cleaner AI extraction.
- Structured data now includes `Organization`, `WebSite`, `WebApplication`, `SoftwareApplication`, `WebPage`, `ItemList`, and `FAQPage` graph entries.

## Growth SEO Implementation Findings
- The SEO matrix now has 27 canonical pages, including 8 new tool/intent pages: `/youtube-to-mp4/`, `/youtube-subtitle-downloader/`, `/bilibili-course-downloader/`, `/douyin-public-video-download/`, `/video-to-text/`, `/video-to-mindmap/`, `/ai-video-notes/`, and `/online-video-downloader/`.
- New matrix pages include visible use cases, supported capabilities, concrete steps, common failure reasons, compliance text, topic-specific related internal links, Markdown mirrors, and page-specific FAQ JSON-LD.
- The HTML sitemap is now generated at `/sitemap/`, while XML discovery remains `/sitemap.xml`. The old `/sitemap.html` artifact was removed to keep one canonical HTML sitemap URL.
- IndexNow support is implemented in `frontend/scripts/submit-indexnow.mjs`: it builds a same-host payload, writes the verification key file, supports dry-run checks, and avoids submitting when the canonical domain is still the local fallback.
- Production deployment still requires `VITE_PUBLIC_SITE_URL` or `PUBLIC_SITE_URL`, a real `INDEXNOW_KEY`, and search platform submission in Google Search Console, Bing Webmaster Tools, and 百度搜索资源平台.

## Deployment Hardening Findings
- Static hosts now receive generated `_headers`, `_redirects`, and `404.html`; FastAPI self-hosting also returns true 404 responses for unknown frontend paths.
- Known directory pages such as `/video-summary` now redirect to `/video-summary/`, matching canonical and sitemap URL format.
- HTML responses are served with `Cache-Control: no-cache`; hashed Vite assets are served with `Cache-Control: public, max-age=31536000, immutable`.
- Optional canonical redirects can be enabled with `SEO_CANONICAL_REDIRECTS=true` after `PUBLIC_SITE_URL` or `VITE_PUBLIC_SITE_URL` is set to the real HTTPS domain.
- Webmaster verification is configurable through environment variables for Google, Bing, 百度, 360, Sogou, and Yandex, including both meta-token and upload-file modes.
- `frontend/scripts/validate-seo-deploy.mjs` validates generated SEO assets and rejects fallback or non-HTTPS production origins. Remote validation is available after deployment.
- `backend/app/services/geo_monitor.py` records safe aggregate access data for SEO/GEO surfaces, crawler families, and 404 paths without storing query strings or IP addresses.
- The AI summary workbench is lazy-loaded as a separate Vite chunk, reducing first-load JavaScript while preserving existing user workflows.
