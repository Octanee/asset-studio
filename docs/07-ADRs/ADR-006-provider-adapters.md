---
title: ADR-006 Provider adapters for generation and training
type: adr
status: proposed
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-006: Provider adapters for generation and training

**Status:** proposed — decided at gate G-6.

## Context
Brief §5.1: the domain must not be coupled to ComfyUI, and future providers must be possible.

## Decision
`GenerationProvider` and `TrainingProvider` interfaces. Implementations: ComfyUI, SvgTemplate, Fake (CI); Kohya through the host agent. Workflow versions map domain inputs to engine-specific graphs.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Call ComfyUI directly from domain code | less code | lock-in; impossible to test without a GPU |

## Consequences
CI runs without a GPU (NFR-015). New engines are added as new adapters.
