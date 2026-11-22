---
title: Publishing
type: business-process
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - workflow
  - publishing
---

# Publishing

**Publishing = exporting an approved version to a target through a preset** (D-28).

1. Select approved versions: one, a selection, a collection, or the whole project.
2. Choose a preset (format, sizes, naming, folders, optimization, metadata) and a target.
3. The system computes the planned files. If a file already exists in the target, the user must explicitly confirm the overwrite (RULE-004).
4. The system writes the files and records a publication (version, preset, target, hash, time). The asset's **currently published version** pointer for that target is updated.

Only versions in `approved` or `published` state can be published. MCP may publish only where the project allows it (RULE-005).

Requirements: FR-090–FR-095
