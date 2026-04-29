# AI Video Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent AI video summary task flow that supports subtitle-first summarization and no-subtitle speech-to-text fallback.

**Architecture:** Add backend summary services beside the existing download services. Keep download tasks unchanged, add summary-specific task storage, API routes, SSE events, and a Vue result-card summary panel.

**Tech Stack:** Python, FastAPI, yt-dlp, ffmpeg/ffprobe, httpx, pytest, Vue 3, Vite, node:test.

---

## File Structure

- Create `backend/app/services/summary_store.py`: summary task snapshots, markdown file registration.
- Create `backend/app/services/transcript_service.py`: subtitle download and SRT/VTT parsing.
- Create `backend/app/services/audio_service.py`: audio extraction for speech-to-text fallback.
- Create `backend/app/services/ai_provider.py`: unified OpenAI-compatible AI client.
- Create `backend/app/services/summary_service.py`: end-to-end AI summary orchestration and Markdown rendering.
- Modify `backend/app/main.py`: summary request model, routes, SSE, background thread.
- Create backend tests for each new service and API route.
- Modify `frontend/src/services/api.js`: summary API helpers and SSE helper.
- Modify `frontend/src/App.vue`: AI summary action, progress state, result panel.
- Modify `frontend/src/assets/main.css`: summary panel styles.
- Modify frontend tests for Chinese copy and API helper behavior.

## Tasks

### Task 1: Summary Store

- [ ] Write failing tests in `backend/tests/test_summary_store.py` for create/update/complete/fail snapshots and markdown URL behavior.
- [ ] Implement `backend/app/services/summary_store.py`.
- [ ] Run the focused test and confirm it passes.

### Task 2: Transcript Parsing

- [ ] Write failing tests in `backend/tests/test_transcript_service.py` for SRT and VTT parsing.
- [ ] Implement transcript segment dataclasses and parsers.
- [ ] Run the focused test and confirm it passes.

### Task 3: AI Provider and Summary Rendering

- [ ] Write failing tests in `backend/tests/test_ai_provider.py` and `backend/tests/test_summary_service.py` for provider request shaping, result normalization, and Markdown rendering.
- [ ] Implement `ai_provider.py` and the pure summary rendering parts of `summary_service.py`.
- [ ] Run focused tests and confirm they pass.

### Task 4: Summary API

- [ ] Write failing API tests in `backend/tests/test_summary_api.py` using a fake summary service.
- [ ] Add summary routes to `backend/app/main.py`.
- [ ] Run focused API tests and confirm they pass.

### Task 5: Speech-to-Text Fallback

- [ ] Write failing tests for summary orchestration where subtitle transcript is unavailable and AI speech-to-text is called.
- [ ] Implement `audio_service.py` and the fallback path in `summary_service.py`.
- [ ] Run focused tests and confirm they pass.

### Task 6: Frontend Summary UI

- [ ] Write failing frontend tests for AI summary Chinese copy and API helpers.
- [ ] Implement API helpers in `frontend/src/services/api.js`.
- [ ] Add AI summary state, button, progress, result panel, and Markdown export in `frontend/src/App.vue`.
- [ ] Add responsive styles in `frontend/src/assets/main.css`.
- [ ] Run `npm test` and `npm run build`.

### Task 7: Full Verification

- [ ] Run backend tests from a project virtual environment.
- [ ] Run frontend tests and build.
- [ ] Start FastAPI and Vite locally.
- [ ] Use browser automation to parse a mocked sample URL or live local fake summary path.
- [ ] Verify the AI summary button, progress state, final summary sections, and Markdown export link render correctly.

## Self-Review

- The plan covers subtitle-first and speech-to-text fallback.
- The plan keeps the existing download task lifecycle unchanged.
- The plan includes browser verification before completion.
- No user API key is exposed in the frontend.
