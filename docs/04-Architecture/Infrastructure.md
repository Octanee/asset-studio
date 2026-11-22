---
title: Infrastructure
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - architecture
  - infrastructure
---

# Infrastructure, Startup and Observability

## Docker strategy

`compose.yaml` services: `web`, `api`, `worker`, `mcp`, `db`.

- All published ports bind to `127.0.0.1` (NFR-005).
- `db` data lives in a named volume.
- The **library** lives in the named volume `asset-data` (ADR-013).
- Windows folders are bind-mounted only for export roots, backups, the **model folder** shared with ComfyUI (read-write for approved downloads) and the training exchange folder.
- Containers do **not** use the GPU. GPU work happens natively through the host agent (ADR-005).
- Images are built from pinned base images (`python:3.12-slim`, `node:24` build stage → `nginx` runtime, `postgres:17`). Dependencies are locked: `uv.lock` and `pnpm-lock.yaml`.

## Native components (Windows)

| Component | How it is installed in the MVP |
|---|---|
| ComfyUI | Official portable build, **pinned version** (v0.46.0 at the time of the prototype), extracted with a bundled `7zr` (S-2) |
| Host agent | `uv`-managed Python environment; started by the startup script; optional autostart |
| Training | kohya sd-scripts at a pinned commit, Python 3.11 venv via `uv`, torch with CUDA |

## Startup workflow (MVP)

1. `asset-studio setup`: a PowerShell script that checks prerequisites (Docker, NVIDIA driver, disk), asks for the data and model folders, writes `.env` with generated tokens, and offers to install ComfyUI and training. Every download is listed with its size and needs a yes.
2. `asset-studio start`: starts the host agent, which starts ComfyUI, then runs `docker compose up -d` and opens `http://127.0.0.1:<port>`.
3. `asset-studio stop` / `status` / `logs`.

The native installer replaces the script after the MVP (D-19).

## Local development

- Backend: `uv run` with a hot-reload API; a dev Postgres via compose; `FakeProvider` by default, so no GPU is needed.
- Frontend: Vite dev server proxying `/api`.
- Real GPU: point the worker at the host agent with `ASSET_STUDIO_PROVIDER=comfyui`.
- Seed data: a fixture project "Exerzio illustrations" with generated placeholder images.

## Observability

- Structured JSON logs with a request/job id. Secrets and tokens are redacted, and prompts are logged only at debug level (NFR-012). Files rotate in the data folder.
- `/api/v1/system/status` aggregates the health of `db`, the worker heartbeat, the host agent, ComfyUI, GPU memory, disk space and the queue (the **System status** screen).
- Job events persist in `job_event`, so the history survives restarts (NFR-003).

## Resource estimates (reference machine)

| Item | Estimate |
|---|---|
| Disk — app images | ~2–3 GB |
| Disk — ComfyUI portable | ~6 GB |
| Disk — training env | ~6 GB |
| Disk — minimal models (SD1.5, SDXL, VAE, OpenPose CN, IP-Adapter + CLIP-ViT-H, DWPose, BiRefNet) | ~16 GB |
| Disk — library | ~0.5–1.5 MB per version incl. thumbnails → 10,000 versions ≈ 10–15 GB |
| RAM — app containers | ~1.5 GB |
| RAM — ComfyUI with SDXL | ~6–10 GB |
| VRAM | up to ~5.9 GB during SDXL training; ~5.5 GB during SDXL generation |
| External services / cost | none; only optional model downloads |
