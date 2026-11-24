---
title: Data Model
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-24
tags:
  - architecture
  - data
---

# Data Model (PostgreSQL schema proposal)

- Conventions: `id uuid` (v7, time-ordered), `created_at`/`updated_at timestamptz`, soft archive via `archived_at`.
- Large JSON (configuration, parameters) is `jsonb` with schema-version columns.
- Files are referenced by **storage keys**, never stored in the database.

| Table | Key columns | Notes |
|---|---|---|
| `project` | id, slug, name, type, intended_use (`commercial`/`non_commercial`), mcp_can_decide bool default false, current_config_version_id, archived_at | |
| `project_config_version` | id, project_id, version int, schema_version, config jsonb, created_by_actor, note | unique (project_id, version) |
| `style` | id, project_id, name, attributes jsonb, version int, archived_at | unique (project_id, name); `version` is bumped on every change (WP-07) |
| `character` | id, project_id, name, description, attributes jsonb, version int, archived_at | unique (project_id, name) (WP-07) |
| `reference` | id, project_id, role, name, storage_key, sha256, mime, width, height, bytes, archived_at | role enum: style, character, pose, composition, colour, anatomy, equipment, background, other (check constraint); `name` is the original file name, shown only (WP-07) |
| `reference_link` | id, reference_id, target_type, target_id, weight | target_type: style, character, job, asset_version; weight 0–2; unique (reference_id, target_type, target_id) (WP-07) |
| `pose` | id, project_id null (built-in), name, view, aspect, keypoints jsonb (COCO-18), source (`library`/`editor`/`detected`), source_reference_id, archived_at | keypoints: 18 × `[x, y, confidence]` normalised to the canvas (`aspect` = width / height) or null; built-in rows have no project and fixed ids, seeded by migration 0004 (WP-07) |
| `model_family` | id (`sdxl`, `sd15`, …), name | synced from the catalogue (WP-12) |
| `model` | id (catalogue slug or `local-…`), name, kind (checkpoint, lora, controlnet, ip_adapter, clip_vision, vae, pose, segmentation), family_id, licence_id, file_name, source_url, sha256, bytes, origin (`catalogue`/`local`), notes, status (`installed`/`available`/`missing`/`downloading`), file_bytes, verification (`unverified`/`ok`/`mismatch`), verified_at | VRAM need is reported as the weights size (a lower bound); kind `segmentation` (background removal, ComfyUI folder `background_removal`) added in WP-09 (WP-12) |
| `licence` | id, name, commercial_use (`allowed`/`forbidden`/`unknown`), url, notes | synced from the catalogue; `unknown` is used for files found on disk (WP-12) |
| `licence_acknowledgement` | id, project_id, model_id, licence_id, intended_use, actor, note, at | RULE-007: valid while the licence and the project's intended use are unchanged (WP-12) |
| `lora` | id, model_id, project_id, character_id null, style_id null, trigger_word, training_run_id | |
| `workflow` / `workflow_version` | id, name, engine (`comfyui`/`svg`/`builtin`), version, definition jsonb, inputs schema jsonb, required_model_kinds, validated_at | not created yet: the built-in workflows are versioned code templates (WP-08); the tables arrive with workflow import |
| `job` | id, kind (`generate`/`remove_background`/`process`/`validate`/`detect_pose`/`train`/`export`/`download`/`backup`/`restore`), lane (`gpu`/`cpu`), state (`queued`/`running`/`completed`/`failed`/`cancelled`/`interrupted`), priority, params jsonb (frozen), result jsonb, attempts, max_attempts, progress jsonb, error jsonb, wait_reason, cancel_requested, locked_by, locked_until, project_id, enqueued_by_actor, created_at, started_at, finished_at | queue index on (lane, state, priority, id); state and lane are check-constrained (WP-04) |
| `worker_heartbeat` | worker_id, lanes, kinds, started_at, seen_at | live workers for the queue summary (WP-04) |
| `job_event` | id, job_id, at, kind, data jsonb | progress history; SSE source |
| `asset` | id, project_id, category, slug, name, tags text[], favorite_at, archived_at | unique (project_id, slug); GIN index on `tags` (WP-10) |
| `collection` | id, project_id, name, created_at | unique (project_id, name) (WP-10) |
| `collection_item` | collection_id, asset_id, added_at | primary key (collection_id, asset_id); removed with its collection, never with the asset (WP-10) |
| `asset_version` | id, asset_id, number, state, previous_state (for archive), storage_key, sha256, width, height, mime, bytes, generation_job_id, generation_metadata jsonb, first_published_at, deleted_at, processing jsonb, created_at | unique (asset_id, number); `processing` holds the steps, the processed file (key, SHA-256, size), the cut-out, the last error (WP-09) and the difference hash of the processed image for duplicate detection (WP-10); `storage_key` is null after permanent deletion (T-13) and `state` is checked against the lifecycle states (WP-03) |
| `state_transition` | id, asset_version_id, transition_id (`T-05`…), from_state, to_state, actor, reason, at | append-only, enforced by a trigger (WP-03) |
| `validation_result` | id, asset_version_id, run_id, rule, status (`passed`/`failed`/`skipped`), details jsonb, created_at | one row per rule per run; the newest run is the report (WP-09) |
| `review_comment` | id, asset_version_id, actor (`user`/`mcp`), body ≤ 4000, at | append-only, enforced by a trigger (WP-10) |
| `export_preset` | id, project_id, name, definition jsonb (format, sizes with suffixes, naming and folder patterns, background, fit, optimisation, quality, metadata sidecar), archived_at | unique (project_id, name); the definition is validated by `PresetDefinition` (WP-11) |
| `export_target` | id, project_id, name, root, subdir, archived_at | unique (project_id, name); `root` must be a configured export root and `subdir` must stay inside it (WP-11) |
| `publication_plan` | id, project_id, preset_id, target_id, actor, items jsonb (versions and planned files with `exists` and the existing file's SHA-256), skipped jsonb, created_at, used_at, job_id | used once, valid for one hour (WP-11) |
| `publication` | id, asset_version_id, target_id, preset_id, plan_id, job_id, actor, at | (WP-11) |
| `publication_file` | id, publication_id, relative_path, sha256, overwrote_sha256 null, confirmed_overwrite bool | |
| `current_publication` | asset_id, target_id, publication_id | the pointer (D-41) |
| `training_dataset` / `training_item` | dataset: id, project_id, name, trigger_word; item: dataset_id, source (`asset_version`/`upload`), ref id, caption | |
| `training_run` | id, dataset_id, family_id, preset, steps, job_id, output_model_id | |
| `audit_entry` | id, at, actor, project_id null, action, subject_type, subject_id, data jsonb | append-only; the DB role has no UPDATE/DELETE grant |
| `setting` | key, value jsonb, updated_at | settings changed from the app: `queue_paused` (WP-16). Locations, the engine address and tokens stay in the environment (D-58). While the queue is paused, queued jobs wait with `wait_reason = QUEUE_PAUSED`; backup and restore still start |
| `idempotency_key` | id, actor, key, request (hash of method, path and body), status_code, response jsonb, created_at | unique (actor, key); kept 24 hours; written in the request's transaction, so a failed request stores nothing (WP-15) |

Migrations use **Alembic**, forward-only in releases. A migration test runs upgrade on an empty DB and on a seeded fixture, in CI.
