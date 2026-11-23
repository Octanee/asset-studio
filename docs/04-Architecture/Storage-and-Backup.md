---
title: Storage and Backup
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-23
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
- On start, `staging/` is cleaned. A consistency check (`assets.service.consistency_report`) reports orphan files and missing files; it is exposed in the system status view in WP-16.

## Backup and restore (FR-111, FR-112)

- **Backup** runs as a job:
  1. `pg_dump` (custom format);
  2. a copy of `projects/` (originals and references; derived files optional);
  3. `manifest.json` with the app version, schema version, file list with SHA-256, and the model list with hashes and sources (no model files, D-41).
  4. Everything goes into one `.zip` (zip64) in `backups/` or a folder the user picks, verified after writing.
- **Restore** goes only into an **empty** data location:
  1. verify the manifest hashes;
  2. restore the database and run migrations up to the current schema;
  3. copy the files;
  4. run the consistency check.
- **Retention:** manual in the MVP; the UI shows the last backup and its size.
