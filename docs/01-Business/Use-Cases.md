---
title: Use Cases
type: use-cases
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - business
  - use-cases
---

# Use Cases

| ID | Use case | Primary actor | Related FR |
|---|---|---|---|
| UC-001 | Create a project manually | user | FR-001, FR-007 |
| UC-002 | Create a project from a natural-language description (MCP draft → review and confirm in the UI) | mcp + user | FR-008, FR-007 |
| UC-003 | Clone a project; export or import a project configuration | user | FR-004, FR-005, FR-006 |
| UC-004 | Define a style from text and/or references | user (mcp draft) | FR-010, FR-011 |
| UC-005 | Define a character with references and an optional LoRA | user | FR-015, FR-016 |
| UC-006 | Add a pose from the library, the editor, or detection from an image | user | FR-020–FR-022 |
| UC-007 | Generate an illustration (style + character + pose + prompt) with variants | user, mcp | FR-030–FR-038 |
| UC-008 | Batch-generate a list of assets (e.g. exercises) | user, mcp | FR-034 |
| UC-009 | Review a version: approve, reject, comment, withdraw approval | user; mcp (comments; decisions if allowed) | FR-060–FR-064 |
| UC-010 | Regenerate an asset as a new version | user, mcp | FR-052 |
| UC-011 | Publish (export with a preset), including re-export with overwrite confirmation | user; mcp if allowed | FR-090–FR-095 |
| UC-012 | Train a style/character LoRA (SDXL or SD1.5) | user | FR-070–FR-075 |
| UC-013 | Register a model and check its licence and compatibility | user | FR-080–FR-084 |
| UC-014 | Generate an SVG asset | user, mcp | FR-045–FR-047 |
| UC-015 | Check status on the dashboard (queue, reviews, failures) | user | FR-100 |
| UC-016 | Back up and restore | user | FR-111, FR-112 |
| UC-017 | Archive, restore or permanently delete an asset or version | user | FR-053, FR-054 |

## UC-007 — Generate an illustration (main success scenario)

1. The user opens a project and picks an asset, or creates one in a category.
2. The user selects a style, character(s), a pose, a prompt template and a model/workflow.
3. The system checks compatibility (model family, LoRA, workflow, licence warning).
4. The system queues a persistent job and shows its progress.
5. On completion the system creates version(s) in `generated`, runs post-processing and technical validation, and moves them to `awaiting_review`.

**Alternatives:** the engine is unavailable → the job waits in the queue with a status message (RULE-013); the user cancels → the job is `cancelled`; processing fails → `processing_failed`, which can be retried.
