---
title: ADR-010 BiRefNet for background removal
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-010: BiRefNet for background removal

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
D-34 puts background removal in the MVP. R-20 requires a permissive licence.

## Decision
BiRefNet (MIT) as ONNX on CPU in the worker; optional per project workflow. Falls back to a ComfyUI workflow (native BiRefNet support) if CPU speed is not acceptable.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| RMBG-2.0 | high quality | non-commercial licence |
| rembg U²-Net | Apache-2.0, small | lower edge quality |

## Consequences
Works with the engine stopped (RULE-013). CPU time per image is verified in WP-01.
