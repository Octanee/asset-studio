---
title: ADR-013 Library storage in a Docker volume
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-013: Library storage in a Docker volume

**Status:** accepted by the user on 2026-11-22 (D-47). Amends [[ADR-007-local-storage-layout]] and narrows D-09.

## Context
WP-01 measured the library workload ([[WP-01-Spike-Report]]). On a bind-mounted NTFS folder, reading 2,000 thumbnails took 14–24 s; on a Docker named volume it took 0.1 s. NFR-010 requires smooth browsing of 10,000 versions.

## Decision
- The **whole library** — originals, references, thumbnails, previews and training datasets — lives in the Docker named volume `asset-data`, which is mounted into `api` and `worker`.
- Folders on the Windows side are used only where the user or a native tool needs them. Each is a bind mount configured at setup:
  - **export roots** (publishing targets live under them);
  - the **backup folder**;
  - the **model folder** shared with ComfyUI;
  - a **training exchange folder** read by the host agent.
- The storage layout inside the volume is unchanged ([[Storage-and-Backup]]).

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Derived files only in a volume, originals on NTFS | originals visible in Explorer | two storage roots to keep consistent; slower writes of originals |
| Everything on an NTFS bind mount | simplest; visible in Explorer | ~150× slower small-file reads; fails NFR-010 |
| Run backend natively on Windows | native disk speed | contradicts ADR-005 and D-17 |

## Consequences
- Library files are not browsable in Windows Explorer. Users reach them through the app, exports and backups.
- The volume lives in Docker Desktop's WSL2 disk. Its size and location are shown in Settings › Data locations.
- Backups are the only copy outside Docker, so the UI reminds the user to back up regularly.
- Export targets must sit under a configured export root. Adding a root restarts the containers.
