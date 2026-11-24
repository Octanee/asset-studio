---
title: Storage and Backup
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-24
tags:
  - architecture
  - storage
---

# Storage and Backup

## Storage abstraction

The `Storage` interface provides `put(key, stream) -> {sha256, bytes}`, `open(key)`, `exists`, `delete` and `url_for(key)`. The MVP has one implementation, `LocalStorage(root)`.

The library root `<data>` is the Docker named volume `asset-data` (ADR-013, D-47). Keys are server-generated and never contain user input:

```
<data>/
  projects/<project_id>/
    references/<reference_id>.<ext>
    assets/<asset_id>/v<number>/original.<ext>
    assets/<asset_id>/v<number>/processed.<ext>, cutout.png   # post-processing (WP-09)
    assets/<asset_id>/v<number>/thumb-256.webp, preview-1024.webp
    training/<dataset_id>/...
  staging/            # temp files, cleaned on start
  backups/
  logs/
```

Publishing (WP-11) writes outside the library, into export roots: bind mounts of Windows folders (`ASSET_STUDIO_EXPORTS_HOST_DIR` → `/exports`, ADR-013). A target is a subfolder of a root; every path, including those made from a preset's patterns, is resolved and must stay inside its root. Each file is written to a temporary name and renamed into place.

## Rules

- A version directory is written once (temp file → fsync → rename) and is never modified afterwards (RULE-003). The original never changes; post-processing adds its own files once (processed file, cut-out, thumbnail, preview). A failed attempt's leftovers, which no row points to, are removed before the retry writes them again.
- Thumbnails and previews are derived and can be regenerated.
- Permanent deletion removes the version directory and keeps its database rows and audit trail (RULE-019).
- On start, `staging/` is cleaned. A consistency check (`assets.service.consistency_report`) reports orphan files and missing files; System status shows its counts (WP-16).

## Backup and restore (FR-111, FR-112)

Implemented in WP-16 (D-58). Backups live in the backup folder, a bind mount of a Windows folder (`ASSET_STUDIO_BACKUPS_HOST_DIR` → `/backups`), so they are the copy outside Docker (ADR-013).

- **Backup** runs as a `backup` job on the CPU lane, started by the user:
  1. every table is read in one `REPEATABLE READ` snapshot with `COPY ... TO STDOUT` (PostgreSQL text format). Idempotency keys and worker heartbeats are left out. No `pg_dump` is needed, so the image needs no PostgreSQL client;
  2. every file under `projects/` (originals, references, processed files, cut-outs, thumbnails and previews) is copied. Images are stored as they are; table dumps are compressed;
  3. `manifest.json` holds the app version, the schema revision, each table with its columns, row count and SHA-256, each file with its SHA-256, and the installed models with their hashes and sources (no model files, D-41). It never holds host paths;
  4. everything goes into one zip (zip64) named `asset-studio-backup-<date>-<time>.zip`. It is written under a temporary name, read back against the manifest, then renamed.
- **Restore** runs as a `restore` job, only into an **empty** data location (no project and no library file):
  1. the archive is checked first: every member must be in the manifest and match its SHA-256, and file names must be library keys. A damaged or unknown archive changes nothing;
  2. the files are unpacked to `staging/`;
  3. in one transaction, a scratch schema is migrated to the backup's schema revision, the rows are loaded into it, it is migrated to the current schema (data migrations run on the restored rows), and the rows are copied into the live tables. A backup from a newer app version is refused;
  4. jobs that were queued or running when the backup was taken come back `cancelled` (`RESTORED`), so nothing starts by itself;
  5. after the commit the files are moved into the library, and the consistency check runs.
- **Retention:** manual in the MVP. Settings › Data and backup lists the backups with size and contents; the dashboard and System status show the last backup and remind the user after 7 days.
