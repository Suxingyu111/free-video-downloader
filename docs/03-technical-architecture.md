# Technical Architecture

## Overview

The application is split into a Vue SPA frontend and a FastAPI backend. During development, Vite serves the frontend and proxies `/api` calls to FastAPI. For self-hosted production, FastAPI can serve the built frontend assets from `frontend/dist`.

## Backend Components

- FastAPI app: route registration, CORS, static asset serving, file download endpoint.
- yt-dlp service: metadata extraction, format normalization, subtitle normalization, download execution.
- Douyin public resolver chain: F2 single-video resolver, douyinVd-compatible public page/sidecar resolver, and Playwright browser fallback for public video metadata.
- task store: in-memory task state, progress updates, file token mapping.
- auth and membership services: SQLite-backed email/password users, HttpOnly sessions, password reset tokens, short-window auth rate limits, subscriptions, Stripe events, daily AI summary usage, and quota reservations.
- billing routes: Stripe Checkout, Customer Portal, signed webhook handling, and server-side checkout return confirmation.
- asset proxy store: in-memory mapping from safe asset tokens to remote thumbnails, with source-page `Referer` forwarding.
- file service: temporary workspace paths and safe file response lookup.

## Frontend Components

- Vue 3 SPA.
- Tailwind CSS theme tokens.
- API client for analyze, download, tasks, summaries, auth, billing, and SSE.
- Industrial console UI components.
- Account, quota, pricing, Stripe checkout, and portal controls.

## Data Storage

Runtime data is local by default:

- `runtime/downloads`: completed task outputs.
- `runtime/tmp`: task working files.
- `runtime/summaries`: AI summary snapshots, Markdown output, and cache index.
- `runtime/saveany.db`: SQLite users, sessions, password reset tokens, subscriptions, Stripe events, billing attempts, daily usage, and quota reservations.

The runtime directory is ignored by git. Deleting it resets local task output, cached summaries, accounts, membership state, and usage history.

## Security and Privacy

- API responses use file tokens, never absolute paths.
- Remote thumbnails are exposed as backend-generated asset tokens, not arbitrary proxy URLs, to reduce hotlink failures without opening a public forward proxy.
- The server does not ask users for cookies, does not offer QR login, and does not provide a shared account. Private, login-gated, CAPTCHA-blocked, region-limited, expired, or risk-controlled links fail with a public-video boundary message.
- Account sessions use HttpOnly cookies, password hashes use Argon2, and Stripe webhook processing is based on signed raw request bodies plus idempotent event IDs.
- The service is intended for local/self-hosted use. Public deployment still needs production SMTP, stronger abuse controls, operational monitoring, and legal/compliance review.

## Douyin Resolver Settings

- `DOUYIN_RESOLVER_CHAIN`: default `f2,douyinvd,browser`.
- `DOUYINVD_BASE_URL`: optional sidecar endpoint compatible with `pwh-pwh/douyinVd`.
- `DOUYIN_PUBLIC_ONLY`: default `true`, keeping Douyin URLs on the public resolver chain.

F2 is a dynamically imported optional resolver. If it is not installed or is incompatible with the Python runtime, the resolver chain records the failure and continues to the douyinVd and browser fallbacks.

## Future Architecture Extensions

- Consider Postgres if user, membership, and task history need multi-instance deployment.
- Add Redis/RQ/Celery for durable background jobs.
- Add object storage for completed files.
- Add production SMTP for password reset delivery.
