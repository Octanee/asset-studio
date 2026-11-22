---
title: ADR-011 kohya sd-scripts for LoRA training
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-011: kohya sd-scripts for LoRA training

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
D-22/D-24: SDXL and SD1.5 LoRA training in the MVP. The prototype measured kohya on 6 GB.

## Decision
kohya sd-scripts at a pinned commit in a Python 3.11 venv, run by the host agent from validated run specs. 6 GB presets from the prototype. The time estimate is shown before start (RULE-016).

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| OneTrainer | GUI-oriented, good presets | harder to drive headless |
| ai-toolkit | modern | focus on FLUX; heavier requirements |

## Consequences
A dependency with its own release cadence; pin it and test it in GPU integration tests.
