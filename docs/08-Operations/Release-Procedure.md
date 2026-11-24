---
title: Release Procedure
type: operations
status: proposed
created: 2026-11-24
updated: 2026-11-24
tags:
  - operations
  - release
---

# Release Procedure (gate G-9)

How a version of Universal Asset Studio is numbered, checked and published. Proposed for gate G-9; nothing is tagged or released until the user approves the gate.

## Versioning

- **Semantic Versioning**, tags `vMAJOR.MINOR.PATCH` on `main`.
- **0.x while the MVP is Windows + NVIDIA only** and the configuration schema may still change. `1.0.0` comes when the user decides the schema and the API are stable.
  - **MINOR:** new features, database migrations, a new configuration schema version (with migration).
  - **PATCH:** fixes only, no migration.
- **One version for the whole repository.** It is set in four places, all changed together:
  - `backend/pyproject.toml`;
  - `backend/src/asset_studio/__init__.py` (shown in the API);
  - `host-agent/pyproject.toml`;
  - `frontend/package.json`.
- The first release is **v0.1.0**: the MVP (WP-00–WP-18). These files already say `0.1.0`.

## Release notes

`CHANGELOG.md` in the repository root, in the [Keep a Changelog](https://keepachangelog.com) format:
- an `Unreleased` section collects changes as pull requests merge;
- a release renames it to the version and date;
- the GitHub release uses the same text.

## Checklist before tagging

| # | Check | How |
|---|---|---|
| 1 | CI is green on `main`: `ci` (backend, frontend, docs, scripts), `security` (gitleaks, dependency review), `codeql` | GitHub Actions |
| 2 | Acceptance tests pass | `test_acceptance.py` in CI; [[Acceptance-Coverage]] |
| 3 | No open security alerts or blocking issues | GitHub Security tab, issues |
| 4 | **No confidential data** in tracked files: no host paths, user names, machine or GPU names of a real machine, LAN addresses, e-mail addresses, tokens | gitleaks in CI, plus a search of tracked files (below) |
| 5 | Commits on `main` carry no personal e-mail | `git log --format='%ae' main \| sort -u`: only GitHub `noreply` addresses |
| 6 | Native pins still download and match | `asset-studio.cmd install-comfyui` and `install-training` on a clean folder, or no pin changed since the last check |
| 7 | **Clean install** on Windows from a fresh clone: `setup`, `start`, one generation, one SVG, review, export | reference machine; results in [[QA-Report]] |
| 8 | **Upgrade** from the previous version keeps the data: backup, `git pull`, `start` (the API runs `alembic upgrade head` before it starts) | from v0.2.0 on |
| 9 | `CHANGELOG.md` and the version in all four files agree | review |

Search of tracked files for item 4, run in the repository root:

```powershell
git grep -nIE "C:\\Users|AppData|@gmail|192\.168\.|DESKTOP-" -- . ":!*lock*"
```

An empty result passes. GPU names in test fixtures are made up and allowed.

## Steps

1. A branch `release/vX.Y.Z`: set the version in the four files and move `Unreleased` in `CHANGELOG.md` to `[X.Y.Z] - date`.
2. A pull request with the checklist above in its description. The user reviews and merges it.
3. **Only after the user approves:** tag the merge commit and create the GitHub release from the changelog section:

   ```powershell
   git tag -a vX.Y.Z -m "vX.Y.Z" <merge-commit>
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <changelog-section>
   ```

4. Record the release in the [[Decision-Log]] and, for G-9, in [[Phase-Gates]].

Tags are never moved or deleted. A mistake in a release is fixed with a new PATCH version.

## What a release contains

- The source at the tag; the GitHub release adds no binaries.
- Users install with `asset-studio.cmd setup` and `start` ([[Install-and-Run]]). The app images are built locally from the tag.
- ComfyUI, kohya and models are downloaded on the user's machine from the pinned sources, after the user approves each one. They are never part of the release.

## Upgrading (for users)

1. Back up: Settings → Data and backup ([[Storage-and-Backup]]).
2. `asset-studio.cmd stop`, then `git pull` (or check out the new tag).
3. `asset-studio.cmd start`: it rebuilds the images and applies database migrations.
4. If the version notes say so, run `asset-studio.cmd setup` again for new settings or pins.
