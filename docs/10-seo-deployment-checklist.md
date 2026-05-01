# SEO Deployment Checklist

This checklist turns the code-side SEO system into a production setup.

## Required Environment

Set the canonical production origin before building:

```bash
VITE_PUBLIC_SITE_URL=https://your-domain.example
PUBLIC_SITE_URL=https://your-domain.example
```

Use one host version only, such as `https://example.com` or `https://www.example.com`. Do not mix both in canonical tags, sitemap, Open Graph URLs, IndexNow, or webmaster tools.

For FastAPI self-hosting, enable canonical redirects only after the proxy passes `Host` and `X-Forwarded-Proto` correctly:

```bash
SEO_CANONICAL_REDIRECTS=true
```

This redirects frontend `GET` and `HEAD` requests to the configured HTTPS canonical origin. API and file-token routes are not redirected.

## Build And Validate

```bash
cd frontend
npm run seo:generate
npm run build
npm run seo:validate
```

The validator rejects fallback domains such as `saveany.local`, non-HTTPS origins, missing generated SEO files, and canonical files that still contain the fallback origin.

After deployment:

```bash
npm run seo:validate:remote
```

## Search Platform Verification

Set the token values supplied by each platform:

```bash
GOOGLE_SITE_VERIFICATION=
BING_SITE_VERIFICATION=
BAIDU_SITE_VERIFICATION=
SO_SITE_VERIFICATION=
SOGOU_SITE_VERIFICATION=
YANDEX_SITE_VERIFICATION=
```

If a platform asks for an uploaded verification file, use:

```bash
BAIDU_SITE_VERIFICATION_FILE=baidu_verify_codeva-example.html
BAIDU_SITE_VERIFICATION_FILE_CONTENT=baidu-site-verification: example
```

Then run `npm run seo:generate` again.

Submit `https://your-domain.example/sitemap.xml` in:

- Google Search Console
- Bing Webmaster Tools
- 百度搜索资源平台
- Other Chinese search platforms if needed

## IndexNow

Generate and host the verification key file:

```bash
INDEXNOW_KEY=your-indexnow-key
npm run seo:indexnow:key
```

Preview changed URLs without submitting:

```bash
npm run seo:indexnow:dry-run
```

Submit changed URLs:

```bash
npm run seo:indexnow:submit
```

Submit every SEO URL once after a major launch:

```bash
npm run seo:indexnow:submit:all
```

By default, `seo:indexnow:submit` stores fingerprints under `frontend/.seo/` and only submits URLs whose GEO content changed since the last successful submission.

## Deployment Headers

The SEO generator writes:

- `_headers`
- `_redirects`
- `404.html`

Static hosts that support these files will serve hashed assets with long immutable caching, HTML/discovery files with no-cache behavior, and a real 404 fallback.

For FastAPI self-hosting, the backend also serves:

- `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`
- HTML pages with `Cache-Control: no-cache`
- known directory pages through trailing-slash redirects
- unknown frontend paths as HTTP 404, not soft homepage responses

Compression such as Brotli or gzip should be enabled at the CDN, reverse proxy, or static hosting layer.

## GEO Monitoring

FastAPI writes privacy-light GEO access records to `runtime/geo-access.jsonl`. It records only method, path, status, crawler family, timestamp, and surface type. It does not store IP addresses or query strings.

Generate a local report:

```bash
cd backend
./.venv/bin/python scripts/geo_monitor_report.py
```

Review these weekly:

- AI crawler visits to `/llms.txt`, `/llms-full.txt`, `/facts/`, and task pages
- 404 paths outside `/api/` and `/files/`
- Whether sitemap and Markdown mirror URLs are being requested
