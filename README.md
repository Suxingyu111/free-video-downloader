# Free Video Downloader

A local/self-hosted video download console built with Vue 3, Vite, Tailwind CSS, FastAPI, yt-dlp, and a public Douyin resolver chain.

## Features

- Analyze video and playlist URLs.
- Show formats and subtitle tracks.
- Create download tasks.
- Stream progress with server-sent events.
- Download completed files through temporary tokens.
- Download public videos without asking users to provide cookies.
- Download public Douyin videos through the dedicated public resolver chain.

## Safety Notes

Respect copyright, platform terms, and account risk. This project does not bypass DRM, paywalls, login-only content, or platform safety protections. Support is limited to public videos and may fail when a video is private, login-gated, region-limited, expired, or blocked by platform risk controls. The app does not provide a manual cookie input flow.

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

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Documentation

Start with `docs/01-requirements.md` and `docs/03-technical-architecture.md` before extending the project.
