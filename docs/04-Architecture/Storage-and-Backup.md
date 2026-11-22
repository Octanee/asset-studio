---
title: Storage and Backup
type: architecture
status: in-review
created: 2026-11-22
updated: 2026-11-22
tags:
  - architecture
  - storage
---

# Storage and Backup

## Storage abstraction

The `Storage` interface provides `put(key, stream) -> {sha256, bytes}`, `open(key)`, `exists`, `delete` and `url_for(key)`. The MVP has one implementation, `LocalStorage(root)`.

Keys are server-generated and never contain user input:

```
<data>/
  projects/<project_id>/
    references/<reference_id>.<ext>
    assets/<asset_id>/v<number>/original.<ext>
    assets/<asset_id>/v<number>/thumb-256.webp, preview-1024.webp
    training/<dataset_id>/...
  staging/            # temp files, cleaned on start
  exports/<job_id>/   # export packages before copying to a target
  backups/
  logs/
```

## Rules

- A version directory is written once (temp file → fsync → rename) and is never modified afterwards (RULE-003).
- Thumbnails and previews are derived and can be regenerated.
- Permanent deletion removes the version directory and keeps its database rows and audit trail (RULE-019).
- On start, a consistency check reports orphan files and missing files.

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
