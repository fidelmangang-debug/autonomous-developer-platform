# Autonomous Developer Platform

A phone-first web platform for submitting software projects as ZIP files, inspecting them, building them in isolated workers, repairing issues with AI assistance, testing, and delivering verified artifacts.

## Current status

This repository currently contains the initial Progressive Web App (PWA) interface. It is **not yet a working cloud build service**. ZIP processing, secure build workers, AI repair, persistent job storage, APK signing, and artifact delivery still need to be implemented and tested.

## Design goals

- One simple workflow: upload a ZIP, press **Start build**, follow progress, receive the output.
- Support multiple project types through project detection and pluggable build adapters.
- Preserve the original upload and make repairs on a separate working copy.
- Show build logs, detected issues, applied patches, tests, and clear blockers.
- Never claim a build succeeded unless the artifact has been produced and verified.
- Use free tiers where practical; never trigger paid services or unexpected charges.
- Treat every uploaded archive and build script as untrusted input.

## Planned architecture

1. **PWA frontend** — mobile upload, job progress, logs, reports, and artifact links.
2. **API/orchestrator** — authentication, upload validation, job queue, status and artifact metadata.
3. **Isolated build workers** — disposable environments with strict CPU, memory, time, disk, and network limits.
4. **Project adapters** — Android/Gradle, web, Node, Python, and other supported build systems.
5. **AI repair loop** — analyze logs, propose bounded patches, run tests again, retain a full change history.
6. **Artifact storage** — private, expiring downloads and build reports.

## Security requirements

- Reject path traversal, symlinks, ZIP bombs, oversized archives, and excessive file counts.
- Never execute uploaded scripts on the API host.
- Do not expose host credentials, GitHub tokens, cloud secrets, or container sockets to builds.
- Restrict outbound network access and enforce job timeouts and quotas.
- Require explicit approval for signing keys, secrets, paid services, and destructive actions.

## Development

Open `web/index.html` in a browser for the initial interface. The interface expects a future API implementing:
- `POST /api/jobs` — multipart upload, returns a job ID.
- `GET /api/jobs/:id` — job status and progress.
- `GET /api/jobs/:id/logs` — build log entries.
- `GET /api/jobs/:id/artifact` — verified output download.

Until that backend exists, the interface displays a clear connection message rather than pretending to build projects.
