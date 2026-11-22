---
title: Design System
type: ux
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - ux
  - design-system
---

# Design System

Source of truth: the **Asset Studio** design system in Claude Design (<https://claude.ai/artifact/6TyTSWM4ciWvFK8v8vStwb>).

| Foundation | Decision |
|---|---|
| Themes | *Studio* (dark, default) and *Daylight* (light), with the same structure |
| Neutrals | `surface-0` ground · `surface-1` panels · `surface-2` hover/inputs · `line` dividers · `line-strong` control borders |
| Accent | `accent` (process cyan): primary action, focus ring, selection, progress. Never a status |
| Status | `st-generated`, `st-processing`, `st-review`, `st-approved`, `st-rejected`, `st-published`, `st-failed`, `st-archived`. Always dot plus label |
| Type | IBM Plex Sans (UI), IBM Plex Mono (seeds, hashes, durations, VRAM), Archivo (screen titles, empty states) |
| Scale | display 40/44 · title 20/28 · heading 15/22 · body 14/20 · small 12/16 · label 11/14 caps · mono 12/16 |
| Spacing | 4 px grid: 4 · 8 · 12 · 16 · 24 · 32 |
| Radius | 2 (images, chips) · 4 (controls) · 8 (dialogs only) |
| Elevation | Borders, not shadows; `shadow-pop` only for dialogs, menus and toasts |
| Images | Transparency checkerboard (`checker-a/b`); near-square corners |
| Accessibility | Text contrast ≥ 4.5:1 in both themes; focus ring 2 px accent; touch targets ≥ 44 px on tablet and phone; status never by colour alone |
