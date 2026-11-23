---
title: Traceability Matrix
type: traceability
status: draft
created: 2026-11-21
updated: 2026-11-23
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
| BR-001 | FR-030 | UC-007 | AC-001 | WP-05 (provider), WP-08 (studio) | `test_fr030_*` |
| BR-001 | FR-031 | UC-007 | AC-001 | — | — |
| BR-001 | FR-034 | UC-007, UC-008 | AC-001 | — | — |
| BR-001 | FR-038 | UC-007 | AC-001 | WP-04 | `test_fr038_*`, `test_jobs_api_*` |
| BR-001 | FR-046 | UC-014 | — | — | — |
| BR-001 | FR-047 | UC-014 | — | — | — |
| BR-001 | FR-049 | — | — | — | — |
| BR-001 | FR-055 | — | — | WP-03 | `test_fr055_*` |
| BR-001 | FR-056 | — | — | — | — |
| BR-001 | FR-057 | — | — | — | — |
| BR-001 | FR-065 | — | — | — | — |
| BR-001 | FR-090 | UC-011 | AC-001 | — | — |
| BR-001 | FR-091 | UC-011 | AC-001 | — | — |
| BR-001 | FR-100 | UC-015 | — | — | — |
| BR-002 | FR-001 | UC-001 | — | WP-02 | `test_fr001_*` |
| BR-002 | FR-002 | — | — | WP-02 | `test_rule005_*` |
| BR-002 | FR-003 | — | AC-005 | WP-02 | `test_fr003_*` |
| BR-002 | FR-007 | UC-001, UC-002 | — | WP-02 | `test_fr007_*, test_rule014_*` |
| BR-003 | FR-010 | UC-004 | — | — | — |
| BR-003 | FR-011 | UC-004 | — | — | — |
| BR-003 | FR-020 | UC-006 | — | — | — |
| BR-003 | FR-021 | UC-006 | — | — | — |
| BR-003 | FR-022 | UC-006 | AC-011 | — | — |
| BR-003 | FR-025 | — | — | — | — |
| BR-003 | FR-032 | UC-007 | AC-001 | — | — |
| BR-003 | FR-033 | UC-007 | AC-001 | — | — |
| BR-004 | FR-015 | UC-005 | — | — | — |
| BR-004 | FR-016 | UC-005 | — | — | — |
| BR-004 | FR-032 | UC-007 | AC-001 | — | — |
| BR-004 | FR-075 | UC-012 | — | — | — |
| BR-005 | FR-004 | UC-003 | — | WP-02 | `test_fr004_*` |
| BR-005 | FR-005 | UC-003 | AC-010, AC-015 | WP-02 | `test_ac010_*` |
| BR-005 | FR-006 | UC-003 | AC-010 | WP-02 | `test_fr006_*, test_ac010_*` |
| BR-005 | FR-010 | UC-004 | — | — | — |
| BR-006 | FR-042 | — | — | WP-04 | `test_rule012_*` (training hand-off in WP-13) |
| BR-006 | FR-043 | — | AC-006 | WP-04, WP-05 | `test_rule013_*`, `test_fr043_*`, host agent `test_gpu_*` |
| BR-006 | FR-081 | UC-013 | — | — | — |
| BR-006 | FR-082 | UC-013 | — | — | — |
| BR-007 | FR-040 | — | — | WP-04 | `test_fr040_*`, `test_claim_*` |
| BR-007 | FR-041 | — | AC-005 | WP-04 | `test_nfr003_*`, `test_failure_requeues_*` |
| BR-007 | FR-050 | — | — | WP-03 | `test_fr050_*` |
| BR-007 | FR-051 | — | — | WP-03 | `test_fr051_*` |
| BR-007 | FR-052 | UC-010 | AC-002 | — | — |
| BR-007 | FR-053 | UC-017 | — | WP-03 | `test_fr053_*` |
| BR-007 | FR-054 | UC-017 | AC-013 | WP-03 | `test_fr054_*`, `test_rule019_*` |
| BR-007 | FR-092 | UC-011 | AC-001 | — | — |
| BR-007 | FR-093 | UC-011 | AC-001 | — | — |
| BR-007 | FR-094 | UC-011 | AC-001, AC-003 | — | — |
| BR-007 | FR-111 | UC-016 | AC-009 | — | — |
| BR-007 | FR-112 | UC-016 | AC-009 | — | — |
| BR-007 | FR-115 | — | — | WP-02 | `test_fr115_* (API; UI in WP-16)` |
| BR-008 | FR-058 | — | — | — | — |
| BR-008 | FR-059 | — | — | — | — |
| BR-008 | FR-060 | UC-009 | — | — | — |
| BR-008 | FR-061 | UC-009 | — | WP-03 | `test_review_flow_*` (API; UI in WP-10) |
| BR-008 | FR-062 | UC-009 | AC-012 | WP-03 | `test_rule020_*` |
| BR-008 | FR-063 | UC-009 | — | WP-03 | `test_fr063_*` |
| BR-008 | FR-064 | UC-009 | — | WP-03 | `test_rule005_mcp_decisions_*` (decisions; comments in WP-10) |
| BR-009 | FR-026 | — | — | — | — |
| BR-009 | FR-035 | UC-007 | AC-001 | — | — |
| BR-009 | FR-037 | UC-007 | AC-001 | — | — |
| BR-009 | FR-051 | — | — | WP-03 | `test_fr051_*` |
| BR-009 | FR-052 | UC-010 | AC-002 | — | — |
| BR-009 | FR-084 | UC-013 | — | — | — |
| BR-010 | FR-002 | — | — | WP-02 | `test_rule005_*` |
| BR-010 | FR-008 | UC-002 | — | WP-02 | `test_fr008_*` |
| BR-010 | FR-064 | UC-009 | — | WP-03 | `test_rule005_mcp_decisions_*` (decisions; comments in WP-10) |
| BR-010 | FR-095 | UC-011 | AC-001 | — | — |
| BR-010 | FR-120 | — | — | — | — |
| BR-010 | FR-121 | — | AC-004 | — | — |
| BR-011 | FR-007 | UC-001, UC-002 | — | WP-02 | `test_fr007_*, test_rule014_*` |
| BR-011 | FR-011 | UC-004 | — | — | — |
| BR-011 | FR-045 | UC-014 | — | — | — |
| BR-012 | FR-005 | UC-003 | AC-010, AC-015 | WP-02 | `test_ac010_*` |
| BR-012 | FR-110 | — | — | — | — |
| BR-013 | FR-016 | UC-005 | — | — | — |
| BR-013 | FR-070 | UC-012 | — | — | — |
| BR-013 | FR-071 | UC-012 | — | — | — |
| BR-013 | FR-072 | UC-012 | AC-007 | — | — |
| BR-013 | FR-073 | UC-012 | AC-007 | — | — |
| BR-013 | FR-074 | UC-012 | — | — | — |
| BR-013 | FR-075 | UC-012 | — | — | — |
| BR-014 | FR-036 | UC-007 | AC-001 | — | — |
| BR-014 | FR-080 | UC-013 | — | — | — |
| BR-014 | FR-083 | UC-013 | AC-008 | — | — |
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
