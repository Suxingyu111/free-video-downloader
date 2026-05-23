# SEO Optimization Plan

## Goal
Improve search engine visibility for the "万能视频下载总结器 / SaveAny" frontend without changing existing download, analysis, or AI summary behavior.

## Constraints
- Do not break or remove existing features.
- Ask the user before making decisions that require unavailable business information.
- Use the provided SEO audit workflow and TDK writing rules.
- Keep implementation scoped to SEO metadata, crawlability, structured data, and non-invasive content improvements.

## Phases

| Phase | Status | Work |
|---|---|---|
| 1. Context and audit | complete | Read product docs, SEO docs, and current frontend entry points. |
| 2. Decide SEO scope | complete | Identify safe improvements and unclear items requiring confirmation. |
| 3. Implement SEO foundation | complete | Add/update TDK, canonical/OG/Twitter tags, JSON-LD, robots, sitemap, and crawlable fallback content. |
| 4. Verify | complete | Run frontend tests/build and inspect generated static files. |
| 5. Report | complete | Summarize changes, limitations, and any remaining domain/Search Console steps. |
| 6. Iteration audit | complete | Re-verify current state, identify remaining safe SEO improvements. |
| 7. Improve internal links and landing depth | complete | Add crawlable related-page links and richer static landing page content/schema. |
| 8. Re-verify iteration | complete | Run targeted SEO tests, full tests, and production build. |
| 9. Growth SEO system | complete | Add IndexNow script, `/sitemap/` HTML sitemap, and 8 keyword-matrix landing pages. |
| 10. Regenerate assets | complete | Generate static HTML/Markdown pages, XML sitemap, robots, llms files, and remove stale `/sitemap.html`. |
| 11. Full regression | complete | Run SEO tests, full frontend tests/build, IndexNow dry-run, and backend tests. |
| 12. Deployment SEO hardening | complete | Add real 404, trailing-slash redirects, cache headers, static-host headers/redirects, webmaster verification, deployment validation, and SEO access monitoring. |
| 13. Core Web Vitals pass | complete | Split the AI summary workbench into an async chunk so first-load JS is smaller. |

## Open Questions
- Production domain is not present in the repo yet. Canonical URLs and sitemap URLs need either a confirmed domain or a configurable fallback.
- Before production deploy, set `VITE_PUBLIC_SITE_URL` or `PUBLIC_SITE_URL` to the real HTTPS canonical domain and choose one `www` or non-`www` host.
- Search Console, Bing Webmaster Tools, and 百度搜索资源平台 submissions still require account access and verification tokens from the owner.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---|---|
| `npm run build` failed with `EISDIR` in Vite HTML build | Initial canonical used `href="/"` | Root cause: Vite processed the canonical `link href` as an asset path and tried to read `/` as a file. Fixed by using a build-time absolute `__SEO_SITE_URL__/` placeholder. |
