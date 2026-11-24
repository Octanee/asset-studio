---
title: Acceptance Criteria
type: acceptance-criteria
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - product
  - acceptance
---

# Acceptance Criteria (MVP level)

Feature-level criteria are added with each work package in Phase 7.

| ID | Criterion | Verifies |
|---|---|---|
| AC-001 | In an exercise-illustration project, the user generates ≥ 10 illustrations of different exercises with one style and one character, each with its own pose, then approves and exports them with a preset. | BR-003, BR-004, UC-007, UC-008, UC-011 |
| AC-002 | Regenerating an approved asset creates a new version; the approved version stays unchanged. | RULE-003, FR-052 |
| AC-003 | Exporting to a target where the file exists asks for confirmation and leaves an audit entry. | RULE-004, RULE-006, FR-094 |
| AC-004 | With default project settings, an MCP approve/publish attempt is refused with a clear error. | RULE-005, FR-121 |
| AC-005 | After a backend restart, job history and queued jobs are preserved. | NFR-003, FR-041 |
| AC-006 | With the engine stopped, library, review, export and SVG work, and generation reports it is unavailable. | RULE-013, FR-043 |
| AC-007 | SD1.5 LoRA training on 10 images completes on the reference machine and the LoRA works in a generation; SDXL training shows the time warning first. | FR-072, FR-073, RULE-016 |
| AC-008 | Selecting a model whose licence conflicts with the project's intended use shows a warning and requires an audited confirmation. | RULE-007, FR-083 |
| AC-009 | Backup then restore into an empty data location reproduces projects, versions and the audit log. | FR-111, FR-112 |
| AC-010 | A configuration exported from one project imports as a new project and passes validation. | FR-005, FR-006 |
| AC-011 | Pose detection from an image produces a skeleton that can be edited and saved to the library. | FR-022 |
| AC-012 | Withdrawing approval from a published version is not possible; for an unpublished one it requires a reason. | RULE-020, FR-062 |
| AC-013 | A published version cannot be permanently deleted until it is archived; after deletion the audit entry remains. | RULE-019, FR-054 |
| AC-014 | The UI can be switched between Polish and English with no untranslated strings on MVP screens. | FR-125 |
| AC-015 | The backend, engine adapter and MCP server do not accept connections from outside the loopback interface. | NFR-005, RULE-018 |

How each criterion is checked, automated and live: [[Acceptance-Coverage]].
