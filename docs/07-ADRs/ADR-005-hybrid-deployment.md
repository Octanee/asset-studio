---
title: ADR-005 Docker Compose for the app; ComfyUI and training native
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-005: Docker Compose for the app; ComfyUI and training native

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
D-17/D-19: Docker Compose in the MVP. The prototype measured ComfyUI and kohya natively on Windows. CUDA works in Docker, but GPU work there was not benchmarked. Containers cannot start native processes.

## Decision
Run web/api/worker/mcp/db in Docker Compose. Run ComfyUI and kohya natively, supervised by a small native **host agent** with a narrow token-protected API.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Everything in Docker incl. GPU | one runtime | unmeasured GPU performance in WSL2; large CUDA images; ComfyUI custom nodes harder to manage |
| Everything native | no Docker | contradicts D-17; Postgres install burden on users |

## Consequences
One extra native component to install and secure. Bind-mount speed for the data folder must be verified (R-21, WP-01).
