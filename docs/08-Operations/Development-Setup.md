---
title: Development Setup
type: operations
status: approved
created: 2026-11-22
updated: 2026-11-23
tags:
  - operations
---

# Development Setup

Prerequisites: Git, Docker Desktop (WSL2), **uv** ≥ 0.13, Node 22+ with Corepack (pnpm 9).

## Backend

```powershell
cd backend
uv sync
uv run uvicorn asset_studio.main:app --reload --port 8400
uv run pytest
uv run ruff format --check . ; uv run ruff check . ; uv run mypy ; uv run lint-imports
```

## Frontend

```powershell
cd frontend
corepack pnpm install
corepack pnpm dev      # http://127.0.0.1:5180, proxies /api to 127.0.0.1:8400
corepack pnpm lint ; corepack pnpm typecheck ; corepack pnpm test ; corepack pnpm build
```

## Host agent

```powershell
cd host-agent
uv sync
$env:ASSET_STUDIO_AGENT_TOKEN = "<random token>"
uv run python -m asset_studio_host_agent.app
```

## Everything in Docker

```powershell
Copy-Item .env.example .env   # then set ASSET_STUDIO_DB_PASSWORD
docker compose up -d --build
```

The web UI is at `http://127.0.0.1:8480`. Every port binds to 127.0.0.1 only.

### Model folder

Set `ASSET_STUDIO_MODELS_HOST_DIR` in `.env` to ComfyUI's `models` folder, so the app and ComfyUI see the same files. The Models screen scans it, checks files against the catalogue, and downloads catalogue models only after you confirm file, source and size. The default is `./models` in the repository (git-ignored).

### Pose detection models (DWPose, ADR-009)

Pose detection needs two model files (about 350 MB, Apache-2.0) in the library volume. The installer downloads them from `huggingface.co/yzd-v/DWPose`, checks their SHA-256 and keeps nothing that does not match:

```powershell
docker compose run --rm worker python -m asset_studio.modules.poses.install
```

To copy files you already have instead, mount their folder and add `--from /src` (`-v <folder>:/src:ro`). Without the models, detection jobs fail with `POSE_DETECTOR_NOT_INSTALLED` and poses are set by hand in the editor.

## Checks run in CI

These run without a GPU:
- backend and host agent: format, lint, types, import contracts, tests;
- frontend: format, lint, types, tests, build;
- docs: wikilinks and frontmatter;
- compose: config validation.
