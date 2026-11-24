# Changelog

All notable changes to Universal Asset Studio are recorded here, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html); see `docs/08-Operations/Release-Procedure.md`.

## [Unreleased]

## [0.1.0] - 2026-11-24

The first release: the MVP. It runs on one Windows machine with an NVIDIA GPU, for a single user, on loopback only.

### Added

- **Projects:** project configuration with a versioned schema, validation, import and export; drafts prepared by Claude open in the same editor.
- **Styles, characters, references and poses:**
  - styles and characters with attributes, versions and archive;
  - references with validated upload and roles;
  - a pose library with built-in poses, a skeleton editor and pose detection from a photo (DWPose on the CPU).
- **Generation Studio and Queue:**
  - text-to-image and image-to-image with pose control (OpenPose ControlNet) and references;
  - compatibility and licence checks before queueing;
  - variants, metadata and regeneration that keeps the approved version.
- **Job queue:** GPU and CPU lanes, live events, recovery after a restart, cancel and retry.
- **Processing and validation:** background removal on the GPU, resize and convert, technical checks.
- **Library and review:**
  - search and filters, tags, favourites, collections, comments;
  - version comparison and duplicate detection;
  - a lifecycle from review to approval, publishing and archive.
- **Export:** presets (format, sizes, naming, background, optimisation) and targets, with a file plan; an overwrite needs a confirmation and is audited.
- **SVG Studio:** deterministic, versioned templates (icons, badges, shapes), sanitising, previews and SVG export.
- **Models:** a versioned catalogue and registry, approved resumable downloads with hash checks, licence warnings and confirmations.
- **LoRA training** with kohya through the host agent: datasets, captions, estimates and warnings for SDXL; LoRAs linked to styles and characters and used in generation.
- **MCP server for Claude:** project, library and generation tools on loopback; approve and publish are refused by default.
- **Dashboard, settings and system status:** audit log, engine control, backup and restore.
- **Interface in Polish and English**, switchable at run time; WCAG 2.2 AA as the target.
- **Windows setup and start:** `asset-studio.cmd` with checked prerequisites, generated secrets, pinned and hash-checked native installs of ComfyUI and training, and a long-path check.

### Security

- Every service listens on `127.0.0.1` only; Host and Origin checks; bearer tokens for MCP, the worker and the host agent.
- Hostile SVG content is removed before it is stored or rendered.
- CI runs gitleaks, dependency review and CodeQL.

### Known limitations

- Windows and NVIDIA only; no installer, no multiple users, no LAN access.
- With the base SDXL checkpoint, images can contain pseudo-text, a background that is not plain white or extra figures; review is where they are rejected. Floor and forward-fold poses are flagged for review (R-12).
- SDXL LoRA training on a 6 GB GPU takes 8–20 h; the app shows the estimate first.
- An interrupted job waits for the user to retry it.
