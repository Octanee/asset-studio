---
title: ADR-003 React + TypeScript + Vite frontend
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-003: React + TypeScript + Vite frontend

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
Brief §8.1 prefers React/TS/Vite. The approved design needs dense image grids, a pose editor, comparison views and PL/EN.

## Decision
React 18, TypeScript strict, Vite; TanStack Query (server state), Zustand (UI state), React Router; Radix UI primitives styled with the Asset Studio design tokens (CSS variables, CSS modules); TanStack Virtual for large grids; react-i18next; client generated from OpenAPI.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Component kit (MUI, Ant) | fast forms | generic admin look, against DD-001 and the approved design |
| Svelte/Vue | smaller bundles | outside the preferred direction; smaller pool of contributors |

## Consequences
Full control over the approved visual design, with accessible primitives from Radix.
