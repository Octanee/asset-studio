---
title: Components
type: ux
status: approved
created: 2026-11-22
updated: 2026-11-23
tags:
  - ux
  - components
---

# Components

Defined in the design system (<https://claude.ai/artifact/6TyTSWM4ciWvFK8v8vStwb>) with live previews:

| Component | Purpose | Notes |
|---|---|---|
| Button | primary · secondary · ghost · danger | one primary per panel; a disabled button explains why |
| StatusBadge | lifecycle state | dot + localised label; `data-s` = state |
| AssetTile | image in a grid | checkerboard, status, name, version, age; selection outline; size 120–320 px |
| QueueItem | job row | mono subline, progress, ETA, reason for waiting |
| ConfirmDialog | consequence-naming confirmation | the confirming button repeats the action; Cancel is the default focus |

Navigation rail, top bar (project switcher, Ctrl K palette, queue indicator, engine status, PL/EN) and the phone bottom bar are implemented in WP-06 (`frontend/src/app/Shell.tsx`).

Used on artboards (to be added to the system during implementation):
- navigation rail and top bar;
- inspector panel;
- filter list;
- bulk action bar;
- pose editor canvas;
- comparison viewer (side by side, swipe, overlay, pose overlay);
- file plan table (publish);
- toast;
- empty state;
- skeleton loader;
- inline error.
