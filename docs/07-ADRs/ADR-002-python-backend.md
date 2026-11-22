---
title: ADR-002 Python 3.12 + FastAPI backend
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-002: Python 3.12 + FastAPI backend

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
The backend integrates with AI tools (ComfyUI API, kohya, ONNX Runtime, Pillow) and needs background jobs and file processing. Brief §8.2 asks us to evaluate Go and Python and to use one backend language.

## Decision
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, uv for dependencies, ruff + mypy.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Go | fast, single binary, strong concurrency | ONNX, imaging and training tooling are Python-first; a second language would be needed anyway |
| Node/TypeScript | one language with the frontend | weaker ML ecosystem |

## Consequences
One language for the backend, worker, MCP server and host agent. Raw performance is lower than Go, but the heavy work runs in ComfyUI and kohya anyway.
