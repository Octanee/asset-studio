---
title: Testing Strategy
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - architecture
  - testing
---

# Testing Strategy

| Level | Tools | Runs in CI | Covers |
|---|---|---|---|
| Unit | pytest, Vitest | ✅ | lifecycle state machine (table-driven from T-01–T-13), config schema, compatibility checks, naming, presets |
| API / contract | pytest + httpx, OpenAPI diff | ✅ | every endpoint, problem codes, actor permissions, confirmations |
| Database | pytest + Postgres service | ✅ | migrations up from empty and from a fixture, constraints, audit append-only |
| Workflow / provider | pytest with FakeProvider; recorded ComfyUI responses | ✅ | request translation, progress parsing, cancellation, failure mapping |
| File processing | pytest + fixture images | ✅ | validation rules, malicious files (bombs, bad MIME, hostile SVG), export file plans |
| Security | pytest, Bandit, pip-audit, pnpm audit, CodeQL | ✅ | Host/Origin checks, path traversal, MCP refusals |
| UI | Vitest + Testing Library | ✅ | components, i18n keys present in PL and EN |
| End-to-end | Playwright against compose with FakeProvider | ✅ | AC-001 … AC-015 flows |
| GPU integration | pytest marker `gpu`, local only | ❌ (manual / self-hosted later) | real ComfyUI and kohya on the reference machine |
| Recovery | pytest + compose | ✅ (fake) | backend restart during a job, interrupted processing, restore from backup |

## Failure scenarios

Each scenario from the brief has a test, using a FakeProvider mode or a fixture:
- engine unavailable;
- timeout;
- invalid workflow;
- model missing;
- insufficient VRAM (simulated OOM error);
- disk full (temp-dir quota);
- restart during generation;
- interrupted processing;
- invalid upload;
- duplicate asset;
- failed export;
- migration failure;
- invalid configuration.

## Traceability

- Test names carry requirement ids (`test_ac003_overwrite_requires_confirmation`).
- A CI script builds the Tests column of [[Traceability-Matrix]] from those markers and fails if a Must FR in a finished work package has no test.
