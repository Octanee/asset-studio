# Universal Asset Studio

A local-first, open-source application for creating, organizing, reviewing and exporting visual assets with **locally hosted AI models**. It keeps one consistent style and the same characters across every asset in a project.

> **Status:** MVP in development. Every feature package is built; end-to-end QA (WP-18) is next.

## Quick start (Windows)

Needs Docker Desktop, Git, uv and an NVIDIA GPU. See [`docs/08-Operations/Install-and-Run.md`](docs/08-Operations/Install-and-Run.md).

```powershell
.\asset-studio.cmd setup   # checks, .env, folders, optional ComfyUI and training installs
.\asset-studio.cmd start   # opens http://127.0.0.1:8480
```

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
| `asset-studio.cmd`, `scripts/` | Windows setup and start scripts, pinned native components |
| `docs/` | Requirements, design, architecture, ADRs |

## Licence

Apache-2.0. AI models are not part of this repository. Each model has its own licence, which the app shows per project.
