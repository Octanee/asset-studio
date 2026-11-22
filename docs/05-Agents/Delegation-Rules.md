---
title: Delegation Rules
type: agents
status: approved
created: 2026-11-21
updated: 2026-11-22
tags:
  - agents
---

# Delegation Rules

Every delegated task includes:
- the work-package id;
- the objective;
- context links (vault pages);
- the related requirement ids;
- inputs;
- expected deliverables;
- constraints;
- acceptance criteria;
- required tests;
- documentation updates;
- dependencies;
- the model and the reason for choosing it.

Agents return structured findings:
- what was done;
- files touched;
- tests run with results;
- open questions;
- deviations from the plan.

The orchestrator resolves conflicts, reruns tests, and only then opens or updates the PR.

## Claude Code skills (proposed for Phase 7)

| Skill | Purpose | Approval |
|---|---|---|
| `generate-assets` | drive generation through MCP from a list (e.g. exercises), with poses and the project style | queues jobs only |
| `review-assets` | comment on versions via MCP against the project's style rules | comments; decisions only if the project allows |
| `asset-publishing` | prepare a publish plan and report overwrites to the user | publishing needs the project setting; overwrites are refused |
| `documentation-maintenance` | keep traceability and status pages in sync after a PR | none |

The skills contain no business rules. The platform API enforces them.
