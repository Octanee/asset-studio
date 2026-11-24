---
title: Screen Specifications
type: ux
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - ux
  - screens
---

# Screen Specifications

Each row is one artboard on the Claude Design canvas. "Data" lists what the screen shows; "Actions" lists what the user can do there.

| Screen | Data | Actions | Rules / FR |
|---|---|---|---|
| Dashboard | attention cards (awaiting review, processing failed, licence), versions by state, latest versions, recent activity | open library, batch, new generation | FR-100 |
| Generation Studio | mode (single / batch), asset, style, character, pose, prompt template, variants, model, workflow, seed, steps; running job; versions of the asset; checks before queueing | queue N images, cancel, change pose | FR-030–FR-038, RULE-015, RULE-007 |
| SVG Studio (UXQ-01) | asset (new or a new version), template picker with versions, parameters from the template (glyph, palette colours, numbers), style whose palette limits the colours; live preview of the real output at 240, 64, 48, 24 and 16 px on transparent, light or dark; output checks (sanitised, optimised size, palette), fingerprint (template version and parameter hash), SVG source; running job; versions of the asset | create a version for review (CPU job), switch template, change parameters | FR-045–FR-047, UC-014 |
| Queue | jobs with state (running, queued, failed, interrupted, done), GPU usage, reason for waiting | pause, retry, resume, cancel, reorder | FR-040–FR-043, RULE-012 |
| Review | large preview, strip of pending versions, technical validation, comments incl. Claude's, generation metadata | approve, reject (optional reason), comment, compare | FR-060–FR-064 |
| Asset Library | filters (state, category, character, collections), tile grid with adjustable size, sort | multi-select → add to collection, compare, archive, publish | FR-049–FR-059 |
| Asset details | currently published version, version history with states, audit trail | regenerate as next version, archive | FR-051–FR-053, RULE-003 |
| Compare | two versions, linked zoom; modes side by side, swipe, overlay, pose overlay; parameter diff | approve or reject candidate | FR-058 |
| Export and publish | approved selection, preset, target, optional background removal, planned files with overwrite flags | export only, publish N versions (overwrites need confirmation) | FR-090–FR-095, RULE-004, RULE-005 |
| Projects | projects with type, counts, pending reviews, intended use | open, clone, export config, archive, import, new | FR-001–FR-006 |
| New project | the user's description, Claude's proposed configuration, assumptions, missing items, schema check | edit, ask Claude to revise, create project | FR-008, RULE-010 |
| Project settings | general, intended use, MCP permission (off), configuration versions | save as new version, diff, restore, clone, export, archive | FR-002, FR-007, RULE-005 |
| Style Studio | styles and characters list, text attributes, palette, avoid list, style references | test style, save, add references | FR-010–FR-016 |
| References | references by role, upload rules, details | upload, change role, detect pose, remove | FR-025, FR-026 |
| Poses | library (built-in, project), skeleton editor, view, strength, quick preview | drag joints, mirror, save, detect from image | FR-020–FR-022 |
| LoRA training | dataset from approved assets and uploads, captions, family choice with time estimate, trained models | start, stop | FR-070–FR-075, RULE-016, RULE-017 |
| Models | installed / available / missing, type, family, licence, VRAM, size, hash verification | download (after confirmation), rescan, choose model | FR-080–FR-084, RULE-007, RULE-008 |
| Workflows | workflows by engine, steps, exposed inputs, validation | import, inspect | brief §6.9 |
| Settings and backup | data locations, model folders, backup and restore, theme, language | create backup, restore, change paths | FR-110–FR-112, FR-125 |
| System status | engine stopped banner, component health, events | start engine, show log | RULE-013, NFR-003 |
| States and dialogs | empty, loading, long-running, inline error, disabled with reason, toast, overwrite, licence warning, permanent delete | — | RULE-004, RULE-007, RULE-019 |
