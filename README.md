# Universal Asset Studio

A local-first, open-source application for creating, organizing, reviewing and exporting visual assets with **locally hosted AI models**. It keeps one consistent style and the same characters across every asset in a project.

> **Status:** early development (Phase 7, work package WP-00 — scaffolding). Not usable yet.

- Documentation (Obsidian vault): [`docs/00-Home/Home.md`](docs/00-Home/Home.md)
- Architecture: [`docs/04-Architecture/System-Architecture.md`](docs/04-Architecture/System-Architecture.md)
- Development setup: [`docs/08-Operations/Development-Setup.md`](docs/08-Operations/Development-Setup.md)

## Repository layout

| Path | Content |
|---|---|
| `backend/` | Python 3.12 FastAPI modular monolith (API + worker) |
| `frontend/` | React + TypeScript + Vite web UI |
| `host-agent/` | Native Windows companion for the generation engine and training |
| `compose.yaml` | Docker Compose for the application services (loopback only) |
| `docs/` | Requirements, design, architecture, ADRs |

## Licence

Apache-2.0. AI models are not part of this repository. Each model has its own licence, which the app shows per project.
