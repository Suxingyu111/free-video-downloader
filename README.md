# Free Video Downloader

A local/self-hosted video download console built with Vue 3, Vite, Tailwind CSS, FastAPI, and yt-dlp.

## Features

- Analyze video and playlist URLs.
- Show formats and subtitle tracks.
- Create download tasks.
- Stream progress with server-sent events.
- Download completed files through temporary tokens.
- Optionally use an uploaded `cookies.txt` for a task.

## Safety Notes

Respect copyright, platform terms, and account risk. This project does not bypass DRM, paywalls, or platform safety protections. Uploaded cookies are sensitive and are intended for local/self-hosted usage only.

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

