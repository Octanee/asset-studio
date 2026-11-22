---
title: Agent Responsibilities
type: agents
status: approved
created: 2026-11-21
updated: 2026-11-22
tags:
  - agents
---

# Agent Responsibilities

| Agent role | Owns | Must not |
|---|---|---|
| Orchestrator | plan, integration, final review, docs consistency, PRs | merge PRs, push to `main`, change approved requirements without approval |
| Backend | `backend/` modules within the assigned work package | change another module's tables or API without the orchestrator |
| Frontend | `frontend/` screens and components | change the approved UI without approval |
| AI integration | `backend/asset_studio/providers`, `host-agent/`, workflow templates | download models without approval |
| Infrastructure | `compose.yaml`, `scripts/`, `.github/` | expose services beyond loopback |
| Security reviewer | findings and required fixes | approve its own fixes |
| QA | tests, test data, traceability markers | weaken a test to make it pass |
| Docs | the `docs/` vault | change the content of approved pages |
