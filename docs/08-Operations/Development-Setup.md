---
title: Development Setup
type: operations
status: approved
created: 2026-11-22
updated: 2026-11-22
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

## Checks run in CI

These run without a GPU:
- backend and host agent: format, lint, types, import contracts, tests;
- frontend: format, lint, types, tests, build;
- docs: wikilinks and frontmatter;
- compose: config validation.
