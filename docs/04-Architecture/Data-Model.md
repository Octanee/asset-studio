---
title: Data Model
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-23
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
| `model_family` | id (`sdxl`, `sd15`, …) | |
| `model` | id, name, kind (checkpoint, lora, controlnet, ip_adapter, clip_vision, vae, segmentation, pose), family_id, licence_id, vram_mb, file_name, sha256, bytes, source_url, status (`installed`/`available`/`missing`/`downloading`) | |
| `licence` | id, spdx_or_name, commercial_use (`allowed`/`forbidden`/`unknown`), url | |
| `lora` | id, model_id, project_id, character_id null, style_id null, trigger_word, training_run_id | |
| `workflow` / `workflow_version` | id, name, engine (`comfyui`/`svg`/`builtin`), version, definition jsonb, inputs schema jsonb, required_model_kinds, validated_at | |
| `job` | id, kind (`generate`/`remove_background`/`process`/`validate`/`detect_pose`/`train`/`export`/`download`/`backup`), lane (`gpu`/`cpu`), state (`queued`/`running`/`completed`/`failed`/`cancelled`/`interrupted`), priority, params jsonb (frozen), result jsonb, attempts, max_attempts, progress jsonb, error jsonb, wait_reason, cancel_requested, locked_by, locked_until, project_id, enqueued_by_actor, created_at, started_at, finished_at | queue index on (lane, state, priority, id); state and lane are check-constrained (WP-04) |
| `worker_heartbeat` | worker_id, lanes, kinds, started_at, seen_at | live workers for the queue summary (WP-04) |
| `job_event` | id, job_id, at, kind, data jsonb | progress history; SSE source |
| `asset` | id, project_id, category, slug, name, archived_at | unique (project_id, slug) |
| `asset_version` | id, asset_id, number, state, previous_state (for archive), storage_key, sha256, width, height, mime, bytes, generation_job_id, generation_metadata jsonb, first_published_at, deleted_at, created_at | unique (asset_id, number); `storage_key` is null after permanent deletion (T-13) and `state` is checked against the lifecycle states (WP-03) |
| `state_transition` | id, asset_version_id, transition_id (`T-05`…), from_state, to_state, actor, reason, at | append-only, enforced by a trigger (WP-03) |
| `validation_result` | id, asset_version_id, rule, passed, details jsonb | |
| `review_comment` | id, asset_version_id, actor, body, at | |
| `export_preset` | id, project_id, name, definition jsonb (formats, sizes, naming, folders, optimisation, metadata) | |
| `export_target` | id, project_id, name, path | the path is validated against allowed roots |
| `publication` | id, asset_version_id, target_id, preset_id, actor, at | |
| `publication_file` | id, publication_id, relative_path, sha256, overwrote_sha256 null, confirmed_overwrite bool | |
| `current_publication` | asset_id, target_id, publication_id | the pointer (D-41) |
| `training_dataset` / `training_item` | dataset: id, project_id, name, trigger_word; item: dataset_id, source (`asset_version`/`upload`), ref id, caption | |
| `training_run` | id, dataset_id, family_id, preset, steps, job_id, output_model_id | |
| `audit_entry` | id, at, actor, project_id null, action, subject_type, subject_id, data jsonb | append-only; the DB role has no UPDATE/DELETE grant |
| `setting` | key, value jsonb | app settings |

Migrations use **Alembic**, forward-only in releases. A migration test runs upgrade on an empty DB and on a seeded fixture, in CI.
