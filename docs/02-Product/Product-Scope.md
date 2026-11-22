---
title: Product Scope
type: scope
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - product
  - scope
---

# Product Scope — MVP

Approved by the user on 2026-11-21 (D-41).

## In scope

| Module | Summary | Requirements |
|---|---|---|
| Project management | create, edit, archive, clone, import/export configuration | FR-001–FR-008 |
| Project creation from description | Claude Code drafts via MCP; the user confirms in the UI; a manual path also exists | FR-008 |
| Style Studio | styles from text and/or references | FR-010, FR-011 |
| Characters | own entity with references and an optional LoRA | FR-015, FR-016 |
| Poses | library, skeleton editor, detection from image | FR-020–FR-022 |
| References | role-based references | FR-025, FR-026 |
| Generation Studio | diffusion via a local engine (ComfyUI first) | FR-030–FR-038 |
| Programmatic SVG | template-based vector assets | FR-045–FR-047 |
| Queue | persistent; one GPU job at a time | FR-040–FR-043 |
| Asset library | versions, metadata, search | FR-049–FR-059 |
| Processing and QC | post-processing incl. background removal; technical validation; human review; Claude comments | FR-060–FR-065 |
| LoRA training | SDXL (with warning) and SD1.5 | FR-070–FR-075 |
| Model management | registry, licences, approved downloads | FR-080–FR-084 |
| Export and publishing | presets, targets, overwrite confirmation | FR-090–FR-095 |
| Dashboard | status overview | FR-100 |
| Settings and backup | locations, engine, backup/restore | FR-110–FR-112 |
| Audit and MCP | audit log, MCP server | FR-115, FR-120, FR-121 |
| Localisation | Polish and English | FR-125 |

## Out of scope (MVP)

- Platforms other than Windows + NVIDIA (not ruled out by the architecture).
- Native installer (after the MVP).
- Multiple users, accounts, roles, LAN access.
- An LLM built into the application.
- External image-generation APIs.
- Model files inside backups.

## Accepted unknowns

| ID | Unknown | Handling |
|---|---|---|
| Q-28 | Exerzio output format, sizes and background | set as an export preset when the project is created |
| R-19 | Pose detector licence | chosen in an ADR in Phase 5 |
| R-20 | Background-removal model licence | chosen in an ADR in Phase 5 |
