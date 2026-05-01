# 万能视频下载总结器 SaveAny

万能视频下载总结器 SaveAny is a local/self-hosted public video downloading and AI learning-summary console built with Vue 3, Vite, Tailwind CSS, FastAPI, yt-dlp, and public resolver chains.

It is designed for public video learning, review, and personal knowledge organization: paste a public video URL, analyze formats and subtitles, save the video when available, and generate AI summaries, mind maps, Q&A, transcripts, and Markdown notes.

## Features

- Analyze video and playlist URLs.
- Show formats and subtitle tracks.
- Create download tasks.
- Stream progress with server-sent events.
- Download completed files through temporary tokens.
- Download public videos without asking users to provide cookies.
- Download public Douyin videos through the dedicated public resolver chain.
- Generate AI video summaries, transcript views, mind maps, Q&A, and Markdown learning notes.
- Fall back to local or cloud speech-to-text for public videos without usable subtitles.
- Register and log in with email/password accounts.
- Gate AI video summaries with a free daily quota and Pro membership.
- Test membership offline with mock billing, or connect Stripe Checkout for real monthly subscriptions.
- Publish crawlable GEO pages, `sitemap.xml`, `llms.txt`, `llms-full.txt`, and Markdown mirrors for AI search discovery.

## Safety Notes

Respect copyright, platform terms, and account risk. This project does not bypass DRM, paywalls, login-only content, or platform safety protections. Support is limited to public videos and may fail when a video is private, login-gated, region-limited, expired, or blocked by platform risk controls. The app does not provide a manual cookie input flow.

When referring to the project in Chinese content, prefer the full product name: `万能视频下载总结器 SaveAny`.

## Douyin Resolver Configuration

- `DOUYIN_RESOLVER_CHAIN`: comma-separated resolver order, default `f2,douyinvd,browser`.
- `DOUYINVD_BASE_URL`: optional self-hosted douyinVd sidecar URL.
- `DOUYIN_PUBLIC_ONLY`: defaults to `true`; keeps Douyin on the public-video resolver path.

The F2 resolver is loaded dynamically when the `f2` Python package is available. On Python versions where F2's pinned dependencies cannot install, the chain falls back to douyinVd and browser-based public-page extraction.

## Development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Membership defaults to local mock billing:

```bash
BILLING_MODE=mock
```

For Stripe test mode, copy `backend/config/stripe.env.example` to `backend/config/stripe.env`, fill in the Stripe keys and recurring Price ID, then restart the backend. Shell environment variables still override the file for deployment. See `docs/11-membership-stripe-setup.md`.

Account endpoints include a basic IP/email rate limit. Override it with `AUTH_RATE_LIMIT_ATTEMPTS` and `AUTH_RATE_LIMIT_WINDOW_SECONDS` when needed for local testing.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## GEO / SEO Deployment

Set the canonical production origin before building:

```bash
cd frontend
VITE_PUBLIC_SITE_URL=https://your-domain.example npm run build
```

Useful commands:

```bash
npm run seo:generate
npm run seo:validate
npm run seo:validate:remote
npm run seo:indexnow:dry-run
npm run seo:indexnow:submit
```

See `docs/10-seo-deployment-checklist.md` for production domain, webmaster verification, IndexNow, static hosting, and GEO monitoring steps.

## Documentation

Start with `docs/01-requirements.md` and `docs/03-technical-architecture.md` before extending the project. See `docs/08-feature-summary.md` for the completed universal video downloader feature summary, and `docs/11-membership-stripe-setup.md` for membership and Stripe setup.
