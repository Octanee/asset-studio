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
BiRefNet (MIT), run as a **ComfyUI workflow on the GPU** (native BiRefNet support) in the GPU lane; an optional step in the project's processing workflow.

> **Amended 2026-11-22 (D-48):** the original decision (ONNX on CPU) was measured in WP-01 at 22–141 s per image and ~19 GB RAM ([[WP-01-Spike-Report]]). With the engine stopped, background-removal steps wait in the queue with a clear status; all other processing continues.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| RMBG-2.0 | high quality | non-commercial licence |
| rembg U²-Net | Apache-2.0, small | lower edge quality |

## Consequences
Fast, and does not compete for system RAM. Background removal becomes GPU-dependent, like diffusion and training (RULE-013 applies to it accordingly).
