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
- 执行个人透明额度：未登录访客解析/下载限额、登录免费版更多额度、Pro 月度 AI 总结和语音转写额度，以及可选按量包。
- 通过 Stripe Checkout 处理真实月付订阅和按量包购买，会员与额度状态只由 Stripe 确认链路写入。
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

启动本地服务前，先复制统一配置模板：

```bash
cp .env.example .env
```

后端运行参数、AI 大模型、Stripe、SEO 和前端开发服务器配置都会从项目根目录 `.env` 读取。部署环境中注入的 shell 环境变量仍会覆盖 `.env`。

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Membership uses Stripe billing only. Local mock billing has been removed because it could mutate membership and credit balances outside the payment provider:

```bash
BILLING_MODE=stripe
```

Stripe test mode 下，在根目录 `.env` 中填写 Stripe key、Pro 订阅 Price ID 和按量包 Price ID，然后重启后端。详见 `docs/11-membership-stripe-setup.md`。

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
npm run build
```

`PUBLIC_SITE_URL` 或 `VITE_PUBLIC_SITE_URL` 应写入根目录 `.env`，生产部署平台也可以通过环境变量覆盖。

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
