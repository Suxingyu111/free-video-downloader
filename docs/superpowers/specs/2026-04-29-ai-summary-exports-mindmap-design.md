# AI Summary Exports and Mind Map Design

## Goal

Upgrade the AI video summary panel so each learning module can be downloaded on its own, and replace the current card-style mind map with a horizontal tree visualization that can be viewed fullscreen and exported as PNG or SVG.

## Approved Scope

Use the frontend-first approach for this iteration. The completed summary snapshot already contains the data needed for summary text, transcript text, mind map, and AI Q&A, so this feature should avoid new backend export routes unless a future persistence requirement appears.

This iteration includes:

- Summary module download as Markdown.
- Transcript module download as plain text.
- AI Q&A module download as Markdown, including generated Q&A and current in-browser follow-up history.
- Mind map download as SVG and PNG.
- Mind map fullscreen viewer.
- Visual refresh for the four AI summary modules.

This iteration does not include:

- Server-side per-module export URLs.
- PDF, Word, zip, or account-backed export history.
- Persisting user follow-up Q&A after refresh.
- Changing the current subtitle-only summary limitation.

## Product Direction

Competitors such as BibiGPT, NoteGPT, Mapify, and MyMap make the learning workflow feel complete by grouping summary, transcript, mind map, and chat/Q&A as first-class outputs. SaveAny should keep its tool-console character and make the AI panel feel like a compact study workstation rather than a separate AI landing page.

## Frontend Architecture

Create focused frontend files instead of continuing to grow `App.vue`:

- `frontend/src/services/summaryExports.js`: pure formatting and Blob download helpers for module exports.
- `frontend/src/utils/mindMap.js`: mind map normalization, layout, SVG rendering, and PNG conversion helpers.
- `frontend/src/components/summary/SummaryPanel.vue`: AI summary container, status, tabs, module actions, and composition.
- `frontend/src/components/summary/SummaryOverview.vue`: summary Markdown export data and polished overview UI.
- `frontend/src/components/summary/SummaryTranscript.vue`: transcript display and TXT export.
- `frontend/src/components/summary/SummaryMindMap.vue`: horizontal SVG tree, PNG/SVG export, fullscreen view.
- `frontend/src/components/summary/SummaryQa.vue`: generated Q&A, follow-up form, local history, Markdown export.
- `frontend/src/assets/summary.css`: summary-specific styles imported by `main.css`.

`App.vue` remains responsible for page state, download task state, summary task lifecycle, and passing props/events into `SummaryPanel`.

## Mind Map Design

Render the mind map as a deterministic SVG tree:

- Root node on the left.
- First-level branches fan to the right in a vertical stack.
- Lower levels continue left-to-right.
- Curved connector paths use branch colors.
- Node boxes use stable dimensions, readable text, and accessible labels.
- The normal panel uses horizontal overflow for large maps.
- Fullscreen mode uses a fixed overlay with the same SVG, larger viewport, and close control.

SVG export serializes the generated SVG string. PNG export renders the SVG string into an `Image`, draws it to a `canvas`, and downloads the canvas as `image/png`.

## UI Rules

- Use lucide icons for actions.
- Keep touch targets at least 44px high.
- Do not rely on hover-only controls.
- Use visible focus states and button labels.
- Avoid blue/purple AI gradients and decorative glow blobs.
- Keep the module tabs usable at 375px, 768px, 1024px, and 1440px.

## Testing Strategy

- Frontend unit tests for `summaryExports.js`.
- Frontend unit tests for `mindMap.js` normalization, SVG output, and dimensions.
- Existing Chinese UI copy test updated to cover module-specific downloads, PNG/SVG, and fullscreen copy.
- `npm test` and `npm run build`.
- Browser verification on local Vite app with demo summary data, checking the four tabs, export controls, mind map SVG visibility, fullscreen open/close, and no mobile overflow.
