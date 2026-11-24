---
title: Infrastructure
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-24
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
| ComfyUI | Official portable build, **pinned** v0.46.0 with its SHA-256, extracted with a pinned and checked `7zr` 26.04 (S-2), plus ComfyUI_IPAdapter_plus at a pinned commit |
| Host agent | `uv`-managed Python environment; started by the startup script with its settings in `host-agent\.env` |
| Training | kohya sd-scripts at a pinned commit, Python 3.11 venv via `uv`, torch 2.6.0 with CUDA 12.4 from the official PyTorch index |

## Startup workflow (MVP)

Built in WP-17 (D-63); the procedure is in [[Install-and-Run]].

1. `asset-studio setup` (`asset-studio.cmd`, Windows PowerShell 5.1):
   - checks prerequisites (Docker, Compose, Git, uv, NVIDIA driver, disk);
   - writes `.env` with generated secrets, never replacing set ones;
   - asks for the native, model, export, backup and training folders;
   - offers to install ComfyUI, training and the DWPose models. Every download is listed with its host, size and licence and needs a yes; pinned files are checked by size and SHA-256 (`scripts/native-components.json`);
   - writes `host-agent\.env`.
2. `asset-studio start`: starts the host agent and asks it to start ComfyUI, then runs `docker compose up -d --build` (so an update rebuilds the images) and opens `http://127.0.0.1:<port>`.
3. `asset-studio stop` / `status` / `logs [service|agent]`; `install-comfyui` / `install-training` install separately.

The native installer replaces the script after the MVP (D-19).

## Local development

- Backend: `uv run` with a hot-reload API; a dev Postgres via compose; set `ASSET_STUDIO_ENGINE_PROVIDER=fake` to work without a GPU.
- Frontend: Vite dev server proxying `/api`.
- Real GPU: `ASSET_STUDIO_ENGINE_PROVIDER=comfyui` (the default). ComfyUI and the host agent listen on the host's 127.0.0.1; the `api` and `worker` containers reach them as `host.docker.internal` (`extra_hosts: host-gateway`). Verified in WP-05 on Docker Desktop for Windows: a container reaches a service bound only to the host's loopback, so neither process has to listen on other interfaces. On a Linux Docker engine `host-gateway` is the bridge address, so loopback-only services are not reachable that way (Windows is the MVP target).
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
