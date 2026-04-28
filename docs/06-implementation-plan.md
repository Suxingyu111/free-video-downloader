# Implementation Plan

## Phase 0: Documentation and Project Skeleton

- Create the documentation corpus and Mermaid diagrams.
- Initialize backend and frontend folders.
- Add dependency manifests and local run instructions.

## Phase 1: UI Design System and Static Console

- Implement Vue 3 SPA shell.
- Add Tailwind theme tokens.
- Build the Industrial Media Console layout.
- Add static states for analyze, format selection, subtitle selection, and task queue.

## Phase 2: Video Analysis

- Implement yt-dlp metadata extraction.
- Normalize formats, subtitles, and playlist entries.
- Connect frontend Analyze action to `POST /api/analyze`.

## Phase 3: Download Tasks

- Implement in-memory task store.
- Implement download task execution and progress hooks.
- Add SSE progress streaming.
- Add file token download.

## Phase 4: Subtitles

- Enable original and automatic subtitle options.
- Prefer SRT output where yt-dlp/ffmpeg can provide it.

## Phase 5: Verification and Delivery

- Run backend tests.
- Run frontend build.
- Run browser smoke test.
- Update README with setup, usage, and risk notes.
