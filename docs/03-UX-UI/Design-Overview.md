---
title: Design Overview
type: ux
status: approved
created: 2026-11-22
updated: 2026-11-24
tags:
  - ux
  - overview
---

# Design Overview

> [!success] Approved by the user on 2026-11-22 (gate G-4, D-45)
> The design was made **in Claude Design** (Artifact types *Design* and *Design System*):
> - Screens canvas: <https://claude.ai/artifact/U3SWsGmP2QL3h2SHJErAdP> (25 artboards)
> - Design system: <https://claude.ai/artifact/6TyTSWM4ciWvFK8v8vStwb>
>
> Both are private to the owner until shared.

## Experience principles

1. **Images first.** Chrome is neutral graphite (dark by default) so colour judgement stays on the assets.
2. **The lifecycle is visible everywhere.** Every version shows its state as a dot plus a label, using one colour per state.
3. **Consequences are named.** Every irreversible action asks a question that names its effect: overwrite, delete, licence, MCP permission.
4. **Long work is never blocking.** Generation and training run in a persistent queue that you can watch from the top bar on every screen.
5. **The pose is an explicit input.** The prototype showed that references alone copy the reference pose ([[Style-Configuration]]).
6. **Desktop-first, review anywhere.** Dense production views target ≥1280 px; review also works on tablet and phone.

## Screens

| Area | Artboard | Covers |
|---|---|---|
| Produce | Dashboard (`Main`) · Generation Studio · Queue · Review | UC-007, UC-008, UC-009, UC-015 |
| Library | Asset Library · Asset details · Compare · Export and publish | UC-010, UC-011, UC-017 |
| Setup | Projects · New project (Claude draft) · Project settings · Style Studio | UC-001–UC-005 |
| Inputs | References · Pose library and editor · LoRA training · Models | UC-006, UC-012, UC-013 |
| System | Workflows · Settings and backup · System status · States and dialogs | UC-016, RULE-013, RULE-004, RULE-007, RULE-019 |
| Responsive | Review — tablet (1024) · Review — phone (390) | NFR-009 |
| Building blocks | Navigation rail · Top bar · Asset tile | — |

Three artboards are interactive in Play mode:
- Generation Studio: switch between single and batch, change the variant count;
- Review: approve or reject and move through the strip;
- Asset Library: filter by state, multi-select with a bulk action bar.

See [[Screen-Specifications]], [[Navigation]], [[Design-System]], [[Components]] and [[Design-Decisions]].

## Known gaps and open UX questions

| ID | Item | Proposal |
|---|---|---|
| UXQ-01 | No dedicated **SVG generation** screen yet (FR-045–FR-047); SVG templates appear only under Workflows | Add an "SVG Studio" artboard: template picker, parameters, live deterministic preview |
| UXQ-02 | **Audit log** and **MCP connection** pages appear only as settings sections | Resolved in WP-16: Settings has the sections General, Data and backup, MCP connection and Audit log; the audit log is a table filtered by project, actor and action (FR-115) |
| UXQ-03 | Phone and tablet layouts are designed for Review only | Other screens are desktop-only in the MVP; to be confirmed |
| UXQ-04 | Light theme (Daylight) is defined in tokens but not drawn on artboards | It can be checked via theme tokens; no separate artboards planned |
