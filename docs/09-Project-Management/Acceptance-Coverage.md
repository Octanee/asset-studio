---
title: Acceptance Coverage
type: project-management
status: draft
created: 2026-11-24
updated: 2026-11-24
tags:
  - qa
  - acceptance
---

# Acceptance Coverage (WP-18)

How each acceptance criterion in [[Acceptance-Criteria]] is checked:
- **Automated:** tests that run in CI without a GPU, with the fake engine.
- **Live:** checks on the reference machine with the real engine.

Part 1 of WP-18 added the end-to-end journeys in `backend/tests/test_acceptance.py` and the translation checks in `frontend/src/i18n/i18n.test.ts`. Part 2 ran the GPU integration on the reference machine; its results are in [[QA-Report]].

| AC | Criterion (short) | Automated | Live so far | GPU run (part 2) |
|---|---|---|---|---|
| AC-001 | 10 exercises, one style and character, own poses → approve → export | `test_ac001_*`: 10 assets, 10 poses (5 built-in, 5 from the editor), processing, approval, export of 10 files | single generations with pose and reference (WP-08) | ✅ 10 images in 9.4 min, approved, exported (QA-Report) |
| AC-002 | Regenerating an approved asset keeps the approved version | `test_ac002_*`; `test_an_engine_failure_keeps_the_approved_version_*` | — | — (no GPU needed) |
| AC-003 | Overwrite on export asks and is audited | `test_rule004_ac003_*`, `test_rule004_a_file_that_appears_*` | export to a real folder (WP-11, WP-14) | — |
| AC-004 | MCP approve/publish refused by default | `test_ac004_*`, `test_rule005_ac004_*`, `test_rule005_mcp_decisions_*` | MCP tools over HTTP (WP-15) | — |
| AC-005 | History and queued jobs survive a restart | `test_ac005_*`: a new API process and worker, the same database; `test_nfr003_*` (interrupted jobs) | — | ✅ restart of `api`, `worker`, `web` during a generation (QA-Report) |
| AC-006 | Engine stopped: library, review, export and SVG work | `test_ac006_*`: generation held with `ENGINE_UNAVAILABLE`, SVG, processing, approval and export done | — | ✅ engine stopped from the app (QA-Report) |
| AC-007 | SD1.5 LoRA trains and works; SDXL warns first | `test_fr072_fr075_*`, `test_fr073_rule016_*`, `test_lora_generation.py` | SD1.5 LoRA on 10 images in 6 min 45 s, used in generation (WP-13) | ✅ (WP-13) |
| AC-008 | Licence conflict warns and needs an audited confirmation | `test_ac008_*`, `test_licence_gate_*` | — | — |
| AC-009 | Backup → restore into an empty location | `test_ac009_*` | backup, wipe and restore of a stack (WP-16) | ✅ (WP-16) |
| AC-010 | Exported configuration imports as a new valid project | `test_ac010_*` | — | — |
| AC-011 | Pose detection gives an editable, saveable skeleton | `test_ac011_*`, `test_dwpose.py` | DWPose on real images (WP-07) | — |
| AC-012 | No withdrawal of a published version; a reason before that | `test_ac012_ac013_*` (on a version that was really exported), `test_rule020_*` | — | — |
| AC-013 | Published: delete only after archiving; the audit entry stays | `test_ac012_ac013_*`, `test_rule019_*`, `test_fr054_*` | — | — |
| AC-014 | PL/EN with no untranslated strings | `i18n.test.ts`: every key used exists in both languages, no English left in Polish beyond an explicit list of shared terms; `Shell.test.tsx` (switch) | screens checked in PL during live checks | ✅ 20 screens in PL after fixing 42 missing audit labels (F-1); `test_ac014_every_audit_action_has_a_label` |
| AC-015 | Nothing listens outside loopback | `test_ac015_*` (compose ports, settings, Host and Origin checks), `test_http_needs_a_bearer_token_and_a_loopback_host`, host agent `test_start_runs_the_pinned_command_on_loopback` | — | ✅ six ports on 127.0.0.1 only, refused on the network address (QA-Report) |

## Failure scenarios

| Scenario | Test |
|---|---|
| The engine is down when queueing | `test_rule013_*`, `test_ac006_*` |
| The engine fails a job, the user retries | `test_engine_failure_fails_the_job`, `test_an_engine_failure_keeps_the_approved_version_and_a_retry_succeeds` |
| A worker dies during a job | `test_nfr003_expired_lease_becomes_interrupted_and_can_be_retried` |
| Processing fails (missing model), then retry | `test_t04_*`, `test_retry_after_processing_failure` |
| A file appears in the target after planning | `test_rule004_a_file_that_appears_after_planning_is_never_overwritten` |
| A model or setup download does not match its hash | `test_tampered_download_is_discarded` (models), the setup script tests (WP-17) |
| A hostile SVG | `test_fr046_hostile_content_is_removed`, `test_nfr011_*` |
