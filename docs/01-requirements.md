# Requirements Analysis

## Background

Many learners want to save videos locally for study, review, subtitle extraction, and batch archiving. Some platforms do not expose a convenient download feature, or their download flow has limits such as low quality, no batch mode, or no subtitle export.

This project builds a self-hosted video download website that wraps mature open-source tooling instead of reimplementing platform extractors. The first implementation uses `yt-dlp` as the core downloader.

## Confirmed Product Decisions

- Frontend stack: Vue 3, Vite, Tailwind CSS.
- Backend stack: Python, FastAPI, yt-dlp.
- Deployment target: local or self-hosted usage.
- MVP scope: video parsing, playlist expansion, format selection, download tasks, subtitle download, temporary `cookies.txt` support, task progress.
- Storage: local temporary directory; no database in v1.
- UI style: Industrial Media Console, not blue/purple AI SaaS styling.
- UI quality process: use `ui-ux-pro-max` and `frontend-design` guidance for design system and polish.

## In Scope for MVP

- Analyze a single video URL.
- Expand playlists into selectable entries.
- List normalized formats and subtitle tracks.
- Create download tasks from selected entries.
- Stream task progress to the frontend.
- Provide temporary file download links.
- Accept `cookies.txt` uploads for a task and clean them up after use.
- Show copyright, platform account, and privacy risk notices.

## Out of Scope for MVP

- User accounts.
- Database-backed task history.
- Real payment integration.
- Cloud storage.
- Video summary.
- Subtitle translation.
- DRM, paywall, or platform safety bypassing.

## Safety Requirements

- Do not log cookie file contents.
- Do not persist uploaded `cookies.txt` beyond task execution.
- Do not expose real filesystem paths to the browser.
- Show clear warnings about copyright, platform terms, and account risk.
- Make failures understandable without exposing sensitive internal data.

