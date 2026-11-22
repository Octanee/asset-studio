---
title: Functional Requirements
type: functional-requirements
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - requirements
  - functional
---

# Functional Requirements

Priority: **M** = Must (MVP), **S** = Should (MVP), **C** = Could (MVP if time allows). See [[Feature-Priorities]]. IDs are grouped by module and leave gaps for future additions.

## Projects

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-001 | Create a project manually (name, description, type, languages, categories, presets). | M | BR-002 |
| FR-002 | Edit project settings, including the "MCP may approve/publish" setting (default off). | M | BR-002, BR-010 |
| FR-003 | Archive and restore a project. | M | BR-002 |
| FR-004 | Clone a project's configuration into a new project. | M | BR-005 |
| FR-005 | Export a project configuration to a portable file. | M | BR-005, BR-012 |
| FR-006 | Import a project configuration as a new project, with schema validation and a report of problems. | M | BR-005 |
| FR-007 | Version project configurations, validate them against a schema, and detect incompatible changes. | M | BR-002, BR-011 |
| FR-008 | Accept a configuration draft from MCP, highlight assumptions and missing information, let the user edit it, and create the project only after user confirmation. | M | BR-010 |

## Styles and characters

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-010 | Manage several styles per project. | M | BR-003, BR-005 |
| FR-011 | Define a style by text attributes and/or reference images; the schema allows project-specific attributes. | M | BR-003, BR-011 |
| FR-015 | Manage characters per project: name, description, references. | M | BR-004 |
| FR-016 | Attach a trained LoRA (with its model family) to a character or style. | M | BR-004, BR-013 |

## Poses and references

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-020 | Provide a pose library (built-in and project poses). | M | BR-003 |
| FR-021 | Create and edit pose skeletons in a visual editor. | M | BR-003 |
| FR-022 | Detect a pose skeleton from an uploaded image, then edit and save it. | M | BR-003 |
| FR-025 | Upload references with a role (style, character, pose, composition, colour, other) and validate the files. | M | BR-003 |
| FR-026 | Keep relationships between references and projects, styles, characters, versions and jobs. | M | BR-009 |

## Generation (diffusion)

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-030 | Text-to-image generation. | M | BR-001 |
| FR-031 | Image-to-image generation. | M | BR-001 |
| FR-032 | Reference-based generation (style/character conditioning) where the model and workflow support it. | M | BR-003, BR-004 |
| FR-033 | Pose-controlled generation. | M | BR-003 |
| FR-034 | Variants and batch generation (e.g. one job per item in a list). | M | BR-001 |
| FR-035 | Configurable parameters, seed management, prompt templates, negative prompts where supported. | M | BR-009 |
| FR-036 | Select the model, workflow and LoRA, with compatibility checks (RULE-015) and licence warnings (RULE-007). | M | BR-014 |
| FR-037 | Store full generation metadata for reproducibility (RULE-011). | M | BR-009 |
| FR-038 | Show generation history, progress, errors, and allow cancellation. | M | BR-001 |

## Programmatic SVG

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-045 | Generate SVG assets from reusable templates and parameters, deterministically. | M | BR-011 |
| FR-046 | Sanitize and optimize SVG output. | M | BR-001 |
| FR-047 | Render SVG to raster formats for export. | M | BR-001 |

## Queue and jobs

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-040 | Persistent queue with states queued, running, completed, failed, cancelled, interrupted. | M | BR-007 |
| FR-041 | Retry failed or interrupted jobs; resume the queue after a restart. | M | BR-007 |
| FR-042 | Run GPU jobs one at a time and coordinate the engine for training (RULE-012). | M | BR-006 |
| FR-043 | Report engine and GPU availability; hold GPU jobs while unavailable (RULE-013). | M | BR-006 |

## Asset library

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-050 | Browse, search and filter assets and versions by project, category, status, style, character. | M | BR-007 |
| FR-051 | Show previews, metadata and version history for an asset. | M | BR-007, BR-009 |
| FR-052 | Regenerate an asset as a new version from stored parameters, with changes. | M | BR-007, BR-009 |
| FR-053 | Archive and restore assets and versions (the previous state is remembered). | M | BR-007 |
| FR-054 | Permanently delete rejected or archived versions after confirmation, keeping the audit entry (RULE-019). | M | BR-007 |
| FR-055 | Download individual files. | M | BR-001 |
| FR-056 | Collections. | S | BR-001 |
| FR-057 | Favorites. | S | BR-001 |
| FR-058 | Side-by-side version comparison. | S | BR-008 |
| FR-059 | Duplicate detection. | S | BR-008 |
| FR-049 | Tags with auto-suggest. | C | BR-001 |

## Processing and quality control

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-065 | Post-processing steps per project workflow: resize, convert, optimize, optional background removal. | M | BR-001 |
| FR-060 | Automatic technical validation with project rules (dimensions, aspect ratio, format, file size, transparency, naming, integrity). | M | BR-008 |
| FR-061 | Visual review in the UI: approve, reject (optional reason), comment. | M | BR-008 |
| FR-062 | Withdraw approval from a never-published version, with a required reason (RULE-020). | M | BR-008 |
| FR-063 | Return a rejected version to review. | M | BR-008 |
| FR-064 | Accept review comments from MCP; accept MCP decisions only where the project allows (RULE-005). | M | BR-008, BR-010 |

## Training

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-070 | Build a training dataset from approved project assets and/or uploaded files (RULE-017). | M | BR-013 |
| FR-071 | Edit captions for dataset images. | M | BR-013 |
| FR-072 | Train a LoRA on SDXL or SD1.5 with presets suited to the available VRAM. | M | BR-013 |
| FR-073 | Show a time estimate and a warning before SDXL training on weak hardware (RULE-016). | M | BR-013 |
| FR-074 | Show training progress and allow cancellation. | M | BR-013 |
| FR-075 | Register the trained LoRA with its family and link it to a style or character. | M | BR-004, BR-013 |

## Models

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-080 | Model registry: type, family, version, hash, source, licence, VRAM needs, supported workflows, availability. | M | BR-014 |
| FR-081 | Detect installed models in configured folders. | M | BR-006 |
| FR-082 | Download a model only after explicit approval; resumable and verified by SHA-256. | M | BR-006 |
| FR-083 | Per-project intended use (commercial / non-commercial) and licence-conflict warning with audited confirmation (RULE-007). | M | BR-014 |
| FR-084 | Compatibility checks between models, LoRAs and workflows. | M | BR-009 |

## Export and publishing

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-090 | Export presets: format, sizes, naming pattern, folder structure, optimization, metadata export. | M | BR-001 |
| FR-091 | Export targets (folders) per project. | M | BR-001 |
| FR-092 | Publish approved versions (single, selection, collection, whole project) through a preset. | M | BR-007 |
| FR-093 | Record publications: version, preset, target, file hash, time; keep the "currently published version" pointer. | M | BR-007 |
| FR-094 | Ask for explicit confirmation before overwriting an existing file in a target (RULE-004). | M | BR-007 |
| FR-095 | Allow MCP publishing only where the project allows (RULE-005). | M | BR-010 |

## Dashboard, settings, audit, MCP, localisation

| ID | Requirement | Pri | BR |
|---|---|---|---|
| FR-100 | Dashboard: project overview, queue status, pending reviews, failed jobs, recent activity, quick actions. | M | BR-001 |
| FR-110 | Settings: data locations chosen by the user, engine connection, model folders, language. | M | BR-012 |
| FR-111 | Manual backup to an archive (database, files, configurations, model list with hashes and sources — no model files). | M | BR-007 |
| FR-112 | Restore from a backup archive into an empty data location, with an integrity check. | M | BR-007 |
| FR-115 | Audit log view, filterable by project, actor and action. | M | BR-007 |
| FR-120 | MCP server exposing narrow, validated tools for projects, styles, references, generation, assets and review. It calls the backend API and never bypasses rules. | M | BR-010 |
| FR-121 | MCP tools refuse operations not permitted by project settings, with a clear error. | M | BR-010 |
| FR-125 | UI available in Polish and English, switchable at runtime. | M | BR-015 |
