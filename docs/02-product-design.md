# Product Design

## Product Positioning

The product is a professional self-hosted media console for saving videos and subtitles locally. The experience should feel like a focused operator workstation: practical, dense, fast, and trustworthy.

## Primary User Flow

1. User opens the console.
2. User pastes a video or playlist URL.
3. User optionally uploads `cookies.txt` for access-restricted content.
4. User clicks Analyze.
5. The console displays video metadata, playlist entries, formats, and subtitle tracks.
6. User selects entries, a format, and subtitle preferences.
7. User starts a download task.
8. The task queue shows progress, speed, state, errors, and completed file links.

## Main Interface Regions

- Header: product name, local mode indicator, backend health state.
- Analyze panel: URL input, cookies upload, Analyze action, risk copy.
- Result panel: metadata, thumbnail, playlist entries, selected count.
- Format selector: recommended format, available quality choices, container notes.
- Subtitle selector: original subtitles, automatic subtitles, SRT preference.
- Task queue: progress, current state, download link, failure recovery.
- Risk notice: copyright, platform terms, account and cookie privacy warnings.

## Conversion and Future Paid Ability Placeholders

The first version does not implement payment, but the UI can reserve upgrade messaging for:

- Batch acceleration.
- Subtitle enhancement.
- Video summaries.
- Translation export.
- Persistent task history.

These must remain non-functional labels or "coming soon" affordances in v1.

## Acceptance Criteria

- A mobile user can complete the full flow at 375px width.
- The primary action is clear on every step.
- Failed states explain how to recover.
- The UI feels like a professional download console, not a generic AI landing page.

