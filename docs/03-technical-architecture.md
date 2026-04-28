# Technical Architecture

## Overview

The application is split into a Vue SPA frontend and a FastAPI backend. During development, Vite serves the frontend and proxies `/api` calls to FastAPI. For self-hosted production, FastAPI can serve the built frontend assets from `frontend/dist`.

## Backend Components

- FastAPI app: route registration, CORS, static asset serving, file download endpoint.
- yt-dlp service: metadata extraction, format normalization, subtitle normalization, download execution.
- Douyin public resolver chain: F2 single-video resolver, douyinVd-compatible public page/sidecar resolver, and Playwright browser fallback for public video metadata.
- task store: in-memory task state, progress updates, file token mapping.
- asset proxy store: in-memory mapping from safe asset tokens to remote thumbnails, with source-page `Referer` forwarding.
- file service: temporary workspace paths and safe file response lookup.
- cookie handling: temporary task cookie file and cleanup.

## Frontend Components

- Vue 3 SPA.
- Tailwind CSS theme tokens.
- API client for analyze, download, tasks, and SSE.
- Industrial console UI components.

## Data Storage

V1 uses only local temporary files:

- `runtime/downloads`: completed task outputs.
- `runtime/tmp`: task working files and temporary cookies.

The runtime directory is ignored by git and can be safely deleted between sessions.

## Security and Privacy

- API responses use file tokens, never absolute paths.
- Remote thumbnails are exposed as backend-generated asset tokens, not arbitrary proxy URLs, to reduce hotlink failures without opening a public forward proxy.
- Uploaded cookies are kept in a task-specific temporary file.
- Cookie files are deleted after task completion or failure.
- Douyin defaults to public-only resolution. The server does not ask users for Douyin cookies, does not offer QR login, and does not provide a shared account. Private, login-gated, CAPTCHA-blocked, region-limited, expired, or risk-controlled Douyin links fail with a public-video boundary message.
- The service is intended for local/self-hosted use and should not be exposed publicly without authentication, rate limits, and stronger cleanup.

## Douyin Resolver Settings

- `DOUYIN_RESOLVER_CHAIN`: default `f2,douyinvd,browser`.
- `DOUYINVD_BASE_URL`: optional sidecar endpoint compatible with `pwh-pwh/douyinVd`.
- `DOUYIN_PUBLIC_ONLY`: default `true`, causing Douyin URLs to ignore uploaded cookies and stay on the public resolver chain.

F2 is a dynamically imported optional resolver. If it is not installed or is incompatible with the Python runtime, the resolver chain records the failure and continues to the douyinVd and browser fallbacks.

## Future Architecture Extensions

- Add SQLite/Postgres for task history and user accounts.
- Add Redis/RQ/Celery for durable background jobs.
- Add object storage for completed files.
- Add model providers for video summary and subtitle translation.
