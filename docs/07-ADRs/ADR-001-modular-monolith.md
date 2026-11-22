---
title: ADR-001 Modular monolith
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-001: Modular monolith

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
One person runs the app locally. Brief §8.5 prefers a modular monolith.

## Decision
One backend codebase with strict module boundaries (import-linter), plus separate processes only where the runtime requires them: worker, MCP server and host agent.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Microservices | independent scaling | operational cost, distributed failures, no benefit for one user |
| Single unstructured app | fastest start | coupling grows; hard to extend to new project types (BR-011) |

## Consequences
Simple deployment and debugging. Module rules must be enforced in CI.
