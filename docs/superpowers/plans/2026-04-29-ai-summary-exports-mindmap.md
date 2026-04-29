# AI Summary Exports and Mind Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build frontend-first per-module AI summary downloads, a horizontal SVG mind map with PNG/SVG export, fullscreen viewing, and a cleaner four-module summary UI.

**Architecture:** Keep backend APIs unchanged. Add pure frontend utilities for module exports and SVG mind map rendering, split the AI summary UI into focused Vue components, and keep `App.vue` as the state coordinator.

**Tech Stack:** Vue 3, Vite, Node test runner, browser Blob/canvas/download APIs, lucide-vue-next.

---

## File Map

- Create `frontend/src/services/summaryExports.js`: export file names, Markdown/TXT formatters, Blob download helper.
- Create `frontend/tests/summary-exports.test.js`: pure formatter tests.
- Create `frontend/src/utils/mindMap.js`: normalize map nodes, calculate horizontal tree layout, render SVG string, convert SVG to PNG.
- Create `frontend/tests/mind-map-utils.test.js`: pure mind map utility tests.
- Create `frontend/src/components/summary/SummaryOverview.vue`: overview module UI.
- Create `frontend/src/components/summary/SummaryTranscript.vue`: transcript module UI.
- Create `frontend/src/components/summary/SummaryMindMap.vue`: SVG mind map module, fullscreen overlay, PNG/SVG actions.
- Create `frontend/src/components/summary/SummaryQa.vue`: generated Q&A, follow-up question form, local history.
- Create `frontend/src/components/summary/SummaryPanel.vue`: shell, tabs, status, source badge, Markdown full export link, module composition.
- Create `frontend/src/assets/summary.css`: summary panel, module, export, mind map, fullscreen, transcript, and Q&A styles.
- Modify `frontend/src/assets/main.css`: import `summary.css` and remove the old summary-specific CSS block.
- Modify `frontend/src/App.vue`: import `SummaryPanel`, remove inline summary markup and mind map helper state, pass state/events into the panel.
- Modify `frontend/tests/chinese-ui-copy.test.js`: assert new Chinese controls and structure.

## Task 1: Export Utilities

**Files:**
- Create: `frontend/src/services/summaryExports.js`
- Create: `frontend/tests/summary-exports.test.js`

- [ ] Write tests for summary Markdown, transcript TXT, Q&A Markdown, safe filenames, and fallback empty text.
- [ ] Implement pure formatting helpers and a browser download helper.
- [ ] Run `cd frontend && npm test -- summary-exports`.

## Task 2: Mind Map Utilities

**Files:**
- Create: `frontend/src/utils/mindMap.js`
- Create: `frontend/tests/mind-map-utils.test.js`

- [ ] Write tests for node normalization, horizontal layout coordinates, SVG output, and XML escaping.
- [ ] Implement deterministic tree layout and SVG string generation.
- [ ] Implement `downloadSvg` and async `downloadPngFromSvg` helpers.
- [ ] Run `cd frontend && npm test -- mind-map-utils`.

## Task 3: Summary Components

**Files:**
- Create: `frontend/src/components/summary/SummaryOverview.vue`
- Create: `frontend/src/components/summary/SummaryTranscript.vue`
- Create: `frontend/src/components/summary/SummaryMindMap.vue`
- Create: `frontend/src/components/summary/SummaryQa.vue`
- Create: `frontend/src/components/summary/SummaryPanel.vue`

- [ ] Build each module as a focused Vue component with props and events.
- [ ] Use existing result fields without changing backend contracts.
- [ ] Wire module-level export controls through `summaryExports.js` and mind map helpers.
- [ ] Keep AI Q&A submit behavior emitted to `App.vue`.

## Task 4: Summary Styling

**Files:**
- Create: `frontend/src/assets/summary.css`
- Modify: `frontend/src/assets/main.css`

- [ ] Move summary-specific CSS out of `main.css` into `summary.css`.
- [ ] Style tabs, toolbar, module cards, transcript rows, Q&A, horizontal mind map SVG, and fullscreen overlay.
- [ ] Preserve mobile behavior at 375px and avoid horizontal page overflow.

## Task 5: App Integration and Tests

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/tests/chinese-ui-copy.test.js`

- [ ] Import `SummaryPanel` and replace inline summary markup.
- [ ] Remove obsolete inline mind map computed helpers from `App.vue`.
- [ ] Pass summary result, progress, markdown URL, Q&A history, question state, and submit/update events to `SummaryPanel`.
- [ ] Update Chinese copy tests for new controls.
- [ ] Run `cd frontend && npm test`.
- [ ] Run `cd frontend && npm run build`.

## Task 6: Browser Verification

**Files:**
- No production file ownership.

- [ ] Start backend demo mode and frontend dev server.
- [ ] Open the app in a browser and use the demo AI summary URL path.
- [ ] Verify four module tabs, per-module downloads, PNG/SVG buttons, fullscreen open/close, and mobile layout.
- [ ] Capture and inspect desktop/mobile screenshots.
