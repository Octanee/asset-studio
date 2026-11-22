---
title: Style Configuration
type: business-process
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - workflow
  - styles
---

# Style and Character Configuration

1. Create a style. Describe it with text attributes (palette, rendering, lighting, background, negative constraints, project-specific fields) and/or attach style references.
2. Create characters. Each has a name, a description and character references.
3. Optionally train a LoRA from approved assets and/or uploads (RULE-017) and attach it to the style or character (FR-016). Only same-family models can use it (RULE-015).
4. Generations combine **style + character(s) + pose + prompt**.

The prototype showed that **reference conditioning must be combined with pose control**; without a pose, the reference pose "leaks" into the result. The UI must therefore make the pose an explicit input.

Requirements: FR-010–FR-016, FR-070–FR-075
