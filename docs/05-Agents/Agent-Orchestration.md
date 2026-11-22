---
title: Agent Orchestration
type: agents
status: approved
created: 2026-11-21
updated: 2026-11-22
tags:
  - agents
---

# Agent Orchestration

Claude Code in this repository is the **orchestrator**. It plans each work package, delegates to specialised agents, reviews and integrates their results, and keeps this vault as the source of truth. Agents never invent missing information; they read the docs or report the gap.

## Agents and model policy

The agents are mapped to agent types available in the installed Claude Code setup.

| Role (brief §11.2) | Agent type | Default model | Used for |
|---|---|---|---|
| Orchestrator / architecture | main session, `ecc:architect` | Opus | work-package planning, cross-module design, ADRs |
| Requirements / docs | `ecc:doc-updater` | Haiku | traceability updates, doc maintenance |
| Backend implementation | `general-purpose` | Sonnet | Python modules, API, worker, host agent |
| Frontend implementation | `general-purpose` with `frontend-design` / `ui-styling` skills | Sonnet | screens from the approved design |
| Database | `ecc:database-reviewer` | Sonnet | schema, migrations, query review |
| AI integration | `general-purpose` | Sonnet | ComfyUI adapter, workflows, kohya, ONNX |
| Infrastructure | `general-purpose` | Sonnet | compose, setup scripts, CI |
| MCP | `general-purpose` with `ecc:mcp-server-patterns` | Sonnet | MCP server |
| Security review | `ecc:security-reviewer` | Opus | every PR touching API, files, MCP, host agent |
| Code review | `ecc:python-reviewer`, `ecc:typescript-reviewer`, `ecc:react-reviewer` | Sonnet | every PR |
| QA / E2E | `ecc:e2e-runner`, `ecc:tdd-guide` | Sonnet | tests first, Playwright flows |

## Rules

- Small, low-risk tasks (boilerplate, doc edits) go to Haiku. Architecture, security and cross-module review always go to Opus.
- One writer per file set at a time. Parallel agents only work on independent modules.

Related: [[Agent-Responsibilities]] · [[Delegation-Rules]]
