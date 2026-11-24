---
title: Install and Run
type: operations
status: approved
created: 2026-11-24
updated: 2026-11-24
tags:
  - operations
  - install
---

# Install and Run (Windows)

The MVP runs the app in Docker Compose and the generation engine and training natively on Windows (NFR-013, [[ADR-005-hybrid-deployment]]). One script sets it up and runs it: `asset-studio.cmd` in the repository root. It runs on the Windows PowerShell 5.1 that ships with Windows.

## Prerequisites

| Item | Why | Install |
|---|---|---|
| Docker Desktop (WSL2) | the app services | docker.com |
| Git | the pinned ComfyUI node and kohya | `winget install Git.Git` |
| uv | the host agent and the training environment | `winget install astral-sh.uv` |
| NVIDIA GPU and driver | generation and training (the app runs without one, generation does not) | nvidia.com |
| About 30 GB free | ComfyUI (about 6 GB), training (about 6 GB), models | — |

## Set up

```powershell
.\asset-studio.cmd setup
```

1. Checks the prerequisites and stops when a required one is missing.
2. Writes `.env` from `.env.example` and generates every empty secret: database password, session secret, MCP, worker and host agent tokens. Values that are already set are kept, so running setup again never locks out an existing database.
3. Asks for the folder for ComfyUI and training (default `data\native`).
4. Offers to install **ComfyUI** and **training**. Each offer lists every download with its name, host, size and licence, and installs only after you type `y`.
5. Asks for the model, export, backup and training exchange folders. When ComfyUI was installed, the model folder defaults to ComfyUI's own `models` folder, so the app and ComfyUI see the same files.
6. Writes `host-agent\.env`, which points the host agent at ComfyUI, kohya and the shared folders.
7. Offers the pose detection models (DWPose, about 350 MB).

Both `.env` files are git-ignored. Run setup again at any time to change folders or install what was skipped.

## Pinned native components

`scripts/native-components.json` pins every native download:

| Component | Pin | Check |
|---|---|---|
| 7-Zip `7zr` (extracts ComfyUI) | 26.04 | size and SHA-256 |
| ComfyUI portable for NVIDIA | v0.46.0 (about 2 GB) | size and SHA-256 |
| ComfyUI_IPAdapter_plus | commit `a0f451a` | git checkout |
| kohya sd-scripts | commit `8c088eb`, Python 3.11, torch 2.6.0 + CUDA 12.4 | git checkout, official PyTorch index |

Downloads resume after an interruption: run the same command again. A file whose size or SHA-256 does not match is deleted and never used.

Change a pin only after testing it on the reference machine.

## Run

```powershell
.\asset-studio.cmd start     # host agent → ComfyUI → app; opens http://127.0.0.1:8480
.\asset-studio.cmd status    # containers, host agent, engine
.\asset-studio.cmd logs api  # or worker, web, mcp, db, agent
.\asset-studio.cmd stop      # app, ComfyUI, host agent
```

- `start` rebuilds the app images when the code changed, for example after `git pull`. Otherwise the cache makes this quick.
- Generation jobs wait in the queue while ComfyUI is still starting (RULE-013).
- The host agent and ComfyUI logs are in `data\run`.

## Install later or separately

```powershell
.\asset-studio.cmd install-comfyui
.\asset-studio.cmd install-training
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "The folder … has N characters; … at most M" | ComfyUI's embedded Python and the training environment nest deeply. With Windows long paths off, a full path has at most 260 characters. Choose a short folder (for example `C:\AssetStudio`) or enable long paths in Windows. |
| "Checksum mismatch" or "Unexpected size" | The download was damaged or the source changed. The file was removed; run the command again. If it persists, do not use the file: the pin needs a review. |
| `[MISSING] Docker: installed but not running` | Start Docker Desktop, then run setup again. |
| The engine shows as stopped | Run `asset-studio status`. Read `data\run\comfyui.log`. Start the engine from System status or with `asset-studio start`. |

See also [[Development-Setup]] for working on the code, and [[Infrastructure]] for the architecture.
