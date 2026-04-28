# Extension Guide for Future AI Work

## Before Adding Features

Read these files first:

1. `docs/01-requirements.md`
2. `docs/03-technical-architecture.md`
3. `docs/04-api-design.md`
4. `docs/05-ui-design-system.md`

Follow the Industrial Media Console design direction and avoid blue/purple AI styling.

## Adding Video Summary

- Add a post-processing task after download or subtitle extraction.
- Prefer transcript/subtitle input before full video processing.
- Add a new API field on task results for summary state and output.
- Keep provider credentials out of logs and docs.

## Adding Subtitle Translation

- Add translation provider abstraction.
- Store translated subtitle output as a separate file token.
- Expose source language, target language, and translation status in task snapshots.

## Adding Accounts and Billing

- Introduce a database before adding real paid features.
- Store users, quotas, task history, and billing customer IDs.
- Keep billing webhooks isolated from download task execution.

## Adding Cloud Storage

- Add a storage interface with local and object storage implementations.
- Keep file token behavior consistent regardless of storage backend.
- Add lifecycle cleanup for remote objects.

## Adding Public Deployment

- Add authentication.
- Add rate limiting.
- Add job queue isolation.
- Add stricter file retention policies.
- Review legal and platform terms before exposing the service.

