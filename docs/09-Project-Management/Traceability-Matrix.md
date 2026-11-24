---
title: Traceability Matrix
type: traceability
status: draft
created: 2026-11-21
updated: 2026-11-24
tags:
  - traceability
  - requirements
---

# Traceability Matrix

The chain is: **BR → FR → UC → AC → Implementation → Tests**.

- The matrix is **generated from the requirement tables**; do not edit links by hand without also updating the source table.
- "—" in UC means a cross-cutting requirement with no dedicated use case.
- "—" in AC means its feature-level acceptance criteria will be written with its work package in Phase 7 (Definition of Done).
- Implementation and Tests columns are filled per pull request.

| BR | FR | UC | AC | Implementation | Tests |
|---|---|---|---|---|---|
| BR-001 | FR-030 | UC-007 | AC-001 | WP-05 (provider), WP-08 (backend and Generation Studio) | `test_check_composes_*`, `test_fr033_*`, `generation.test.tsx` |
| BR-001 | FR-031 | UC-007 | AC-001 | WP-08 (`img2img` workflows) | `test_every_builtin_workflow_renders` |
| BR-001 | FR-034 | UC-007, UC-008 | AC-001 | WP-08 | `test_fr034_*` |
| BR-001 | FR-038 | UC-007 | AC-001 | WP-04 (jobs), WP-08 (studio jobs and Queue screen) | `test_fr038_*`, `test_jobs_api_*`, `generation.test.tsx` |
| BR-001 | FR-046 | UC-014 | — | — | — |
| BR-001 | FR-047 | UC-014 | — | — | — |
| BR-001 | FR-049 | — | — | WP-10 | `test_fr049_*`, `review.test.tsx` |
| BR-001 | FR-055 | — | — | WP-03, WP-10 (download buttons) | `test_fr055_*` |
| BR-001 | FR-056 | — | — | WP-10 | `test_fr056_*`, `review.test.tsx` |
| BR-001 | FR-057 | — | — | WP-10 | `test_fr057_*`, `review.test.tsx` |
| BR-001 | FR-065 | — | — | WP-09 | `test_fr065_*`, `test_adr010_*`, `test_t04_*`, `generation.test.tsx` |
| BR-001 | FR-090 | UC-011 | AC-001 | WP-11 | `test_fr090_*`, `publish.test.tsx` |
| BR-001 | FR-091 | UC-011 | AC-001 | WP-11 | `test_fr091_*` |
| BR-001 | FR-100 | UC-015 | — | WP-16 | `test_api_settings_status_backups_and_dashboard`, `system.test.tsx` |
| BR-002 | FR-001 | UC-001 | — | WP-02, WP-16 | `test_fr001_*`, `projects.test.tsx` |
| BR-002 | FR-002 | — | — | WP-02, WP-16 | `test_rule005_*`, `projects.test.tsx` |
| BR-002 | FR-003 | — | AC-005 | WP-02, WP-16 | `test_fr003_*`, `projects.test.tsx` |
| BR-002 | FR-007 | UC-001, UC-002 | — | WP-02, WP-16 | `test_fr007_*, test_rule014_*`, `projects.test.tsx` |
| BR-003 | FR-010 | UC-004 | — | WP-07 | `test_fr010_*`, `inputs.test.tsx` (Style Studio) |
| BR-003 | FR-011 | UC-004 | — | WP-07 | `test_fr011_*`, `inputs.test.tsx` (Style Studio) |
| BR-003 | FR-020 | UC-006 | — | WP-07 | `test_fr020_*`, `inputs.test.tsx` (Poses) |
| BR-003 | FR-021 | UC-006 | — | WP-07 | `test_fr021_*`, `test_mirror_*`, `inputs.test.tsx` (Poses) |
| BR-003 | FR-022 | UC-006 | AC-011 | WP-07 (job, DWPose, editor) | `test_ac011_*`, `test_drawn_box_*`, `test_dwpose.py`, `inputs.test.tsx` (Poses) |
| BR-003 | FR-025 | — | — | WP-07 | `test_fr025_*`, `test_sniff_*`, `inputs.test.tsx` (References) |
| BR-003 | FR-032 | UC-007 | AC-001 | WP-08 (IP-Adapter reference) | `test_fr033_*` |
| BR-003 | FR-033 | UC-007 | AC-001 | WP-08 (OpenPose ControlNet) | `test_fr033_*`, `test_pose_image_*` |
| BR-004 | FR-015 | UC-005 | — | WP-07 | `test_fr015_*` |
| BR-004 | FR-016 | UC-005 | — | WP-12, WP-13 (moved from WP-07: needs the model registry) | — |
| BR-004 | FR-032 | UC-007 | AC-001 | WP-08 (IP-Adapter reference) | `test_fr033_*` |
| BR-004 | FR-075 | UC-012 | — | WP-13 | `test_fr072_fr075_*` (registration; linking in part 2) |
| BR-005 | FR-004 | UC-003 | — | WP-02, WP-16 | `test_fr004_*`, `projects.test.tsx` |
| BR-005 | FR-005 | UC-003 | AC-010, AC-015 | WP-02, WP-16 | `test_ac010_*`, `projects.test.tsx` |
| BR-005 | FR-006 | UC-003 | AC-010 | WP-02, WP-16 | `test_fr006_*, test_ac010_*`, `projects.test.tsx` |
| BR-005 | FR-010 | UC-004 | — | WP-07 | `test_fr010_*`, `inputs.test.tsx` (Style Studio) |
| BR-006 | FR-042 | — | — | WP-04 | `test_rule012_*` (training hand-off in WP-13) |
| BR-006 | FR-043 | — | AC-006 | WP-04, WP-05, WP-08 (waiting shown in studio and Queue) | `test_rule013_*`, `test_fr043_*`, host agent `test_gpu_*`, `generation.test.tsx` |
| BR-006 | FR-081 | UC-013 | — | WP-12 | `test_fr081_*`, `test_wrong_size_*` |
| BR-006 | FR-082 | UC-013 | — | WP-12 | `test_fr082_*`, `test_rule008_*`, `test_nfr007_*`, `test_tampered_*`, `models.test.tsx` |
| BR-007 | FR-040 | — | — | WP-04, WP-08 (Queue screen) | `test_fr040_*`, `test_claim_*`, `generation.test.tsx` |
| BR-007 | FR-041 | — | AC-005 | WP-04, WP-08 (retry and resume in Queue) | `test_nfr003_*`, `test_failure_requeues_*`, `generation.test.tsx` |
| BR-007 | FR-050 | — | — | WP-03, WP-10 (filters, sort, Library screen) | `test_fr050_*`, `review.test.tsx` |
| BR-007 | FR-051 | — | — | WP-03, WP-10 (Asset details, audit trail) | `test_fr051_*`, `review.test.tsx` |
| BR-007 | FR-052 | UC-010 | AC-002 | WP-08 | `test_ac002_*`, `generation.test.tsx` |
| BR-007 | FR-053 | UC-017 | — | WP-03, WP-10 (UI) | `test_fr053_*`, `review.test.tsx` |
| BR-007 | FR-054 | UC-017 | AC-013 | WP-03, WP-10 (confirmation dialog) | `test_fr054_*`, `test_rule019_*`, `review.test.tsx` |
| BR-007 | FR-092 | UC-011 | AC-001 | WP-11 | `test_fr092_*`, `publish.test.tsx` |
| BR-007 | FR-093 | UC-011 | AC-001 | WP-11 | `test_fr092_fr093_*` |
| BR-007 | FR-094 | UC-011 | AC-001, AC-003 | WP-11 | `test_rule004_*`, `publish.test.tsx` |
| BR-007 | FR-111 | UC-016 | AC-009 | WP-16 | `test_ac009_*`, `test_backup_names_*`, `system.test.tsx` |
| BR-007 | FR-112 | UC-016 | AC-009 | WP-16 | `test_ac009_*`, `test_restore_*`, `system.test.tsx` |
| BR-007 | FR-115 | — | — | WP-02, WP-16 | `test_fr115_*`, `system.test.tsx` (audit view) |
| BR-008 | FR-058 | — | — | WP-10 | `review.test.tsx` |
| BR-008 | FR-059 | — | — | WP-10 | `test_fr059_*` |
| BR-008 | FR-060 | UC-009 | — | WP-09 | `test_fr060_*`, `test_rule009_*` |
| BR-008 | FR-061 | UC-009 | — | WP-03, WP-10 (Review screen, queue) | `test_review_flow_*`, `test_fr061_*`, `review.test.tsx` |
| BR-008 | FR-062 | UC-009 | AC-012 | WP-03, WP-10 (UI) | `test_rule020_*`, `review.test.tsx` |
| BR-008 | FR-063 | UC-009 | — | WP-03, WP-10 (UI) | `test_fr063_*` |
| BR-008 | FR-064 | UC-009 | — | WP-03, WP-10 (comments) | `test_rule005_mcp_decisions_*`, `test_fr064_*`, `review.test.tsx` |
| BR-009 | FR-026 | — | — | WP-07 | `test_fr026_*`, `test_links_*` |
| BR-009 | FR-035 | UC-007 | AC-001 | WP-08 | `test_check_composes_*` |
| BR-009 | FR-037 | UC-007 | AC-001 | WP-08 | `test_fr033_*` (metadata) |
| BR-009 | FR-051 | — | — | WP-03 | `test_fr051_*` |
| BR-009 | FR-052 | UC-010 | AC-002 | WP-08 | `test_ac002_*` |
| BR-009 | FR-084 | UC-013 | — | WP-12 (models); WP-08 (workflows) | `test_rule015_*` |
| BR-010 | FR-002 | — | — | WP-02, WP-16 | `test_rule005_*`, `projects.test.tsx` |
| BR-010 | FR-008 | UC-002 | — | WP-02, WP-15, WP-16 | `test_fr008_*`, `test_rule010_*`, `projects.test.tsx` |
| BR-010 | FR-064 | UC-009 | — | WP-03, WP-10 (comments) | `test_rule005_mcp_decisions_*`, `test_fr064_*`, `review.test.tsx` |
| BR-010 | FR-095 | UC-011 | AC-001 | WP-11 | `test_rule005_ac004_*` |
| BR-010 | FR-120 | — | — | WP-15 | `test_fr120_*`, `test_mcp.py` |
| BR-010 | FR-121 | — | AC-004 | WP-15 | `test_ac004_*`, `test_rule005_ac004_*`, `test_rule005_mcp_decisions_*` |
| BR-011 | FR-007 | UC-001, UC-002 | — | WP-02, WP-16 | `test_fr007_*, test_rule014_*`, `projects.test.tsx` |
| BR-011 | FR-011 | UC-004 | — | WP-07 | `test_fr011_*`, `inputs.test.tsx` (Style Studio) |
| BR-011 | FR-045 | UC-014 | — | — | — |
| BR-012 | FR-005 | UC-003 | AC-010, AC-015 | WP-02, WP-16 | `test_ac010_*`, `projects.test.tsx` |
| BR-012 | FR-110 | — | — | WP-16 | `test_only_the_user_changes_settings`, `test_a_paused_queue_*`, `system.test.tsx` |
| BR-013 | FR-016 | UC-005 | — | WP-12, WP-13 (moved from WP-07: needs the model registry) | — |
| BR-013 | FR-070 | UC-012 | — | WP-13 | `test_fr070_*`, `test_training.py`, `training.test.tsx` |
| BR-013 | FR-071 | UC-012 | — | WP-13 | `test_fr070_*`, `training.test.tsx` |
| BR-013 | FR-072 | UC-012 | AC-007 | WP-13 | `test_fr072_*`, host agent `test_training.py`, live SD1.5 run |
| BR-013 | FR-073 | UC-012 | AC-007 | WP-13 | `test_fr073_*`, `training.test.tsx` |
| BR-013 | FR-074 | UC-012 | — | WP-13 | `test_fr074_*`, `training.test.tsx` |
| BR-013 | FR-075 | UC-012 | — | WP-13 | `test_fr072_fr075_*` (registration; linking to a style or character in WP-13 part 2) |
| BR-014 | FR-036 | UC-007 | AC-001 | WP-08 (with WP-12) | `test_rule015_*`, `test_rule007_*` |
| BR-014 | FR-080 | UC-013 | — | WP-12 | `test_fr080_*`, `test_the_shipped_catalogue_*`, `models.test.tsx` |
| BR-014 | FR-083 | UC-013 | AC-008 | WP-12 (registry and confirmation); WP-08 (check before queueing) | `test_ac008_*`, `test_licence_gate_*`, `models.test.tsx` |
| BR-015 | FR-125 | — | AC-014 | WP-06 | `Shell.test.tsx`: language switch, i18n key parity |

## Business rules → requirements

| Rule | Enforced by | AC |
|---|---|---|
| RULE-003 | FR-052 | AC-002 |
| RULE-004 | FR-094 | AC-003 |
| RULE-005 | FR-002, FR-064, FR-095, FR-121 | AC-004 |
| RULE-006 | FR-115 | AC-003 |
| RULE-007 | FR-036, FR-083 | AC-008 |
| RULE-012 | FR-042 | — |
| RULE-013 | FR-043 | AC-006 |
| RULE-015 | FR-036, FR-084 | — |
| RULE-016 | FR-073 | AC-007 |
| RULE-018 | NFR-005 | AC-015 |
| RULE-019 | FR-054 | AC-013 |
| RULE-020 | FR-062 | AC-012 |
