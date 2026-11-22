---
title: Business Goals
type: business-requirements
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - business
  - requirements
---

# Business Goals and Business Requirements

Business requirements (`BR-xxx`) state *why* the product exists. They are refined by [[Functional-Requirements]] and traced in the [[Traceability-Matrix]].

| ID | Business requirement | Source |
|---|---|---|
| BR-001 | Provide one central environment for visual asset production. | brief §2.1 |
| BR-002 | Support many independent projects, each with its own configuration. | brief §2.1, §3 |
| BR-003 | Keep a consistent visual style within each project, defined by text and/or example images. | brief §2.1, D-04 |
| BR-004 | Keep the same recurring characters consistent across a project's assets. | D-12 |
| BR-005 | Make styles and generation configurations reusable. | brief §2.1 |
| BR-006 | Generate images only with locally hosted engines; stay useful offline and without a GPU. | brief §2.2, D-39 |
| BR-007 | Manage assets through their complete lifecycle, with versions and an audit trail. | brief §2.1, §7 |
| BR-008 | Support quality control and human approval. | brief §2.1, D-36 |
| BR-009 | Make generation workflows reproducible. | brief §2.1 |
| BR-010 | Allow controlled automation by Claude Code through MCP, without an LLM inside the app. | brief §2.1, D-03 |
| BR-011 | Be extensible to new project types without fundamental architectural changes. | brief §2.1 |
| BR-012 | Be open source (Apache-2.0) and runnable by anyone on their own machine. | D-01, D-20 |
| BR-013 | Let users train their own style/character models (LoRA) locally. | D-13, D-22 |
| BR-014 | Make model-licence implications visible per project, leaving the decision to the user. | D-02, D-18 |
| BR-015 | Offer the interface in Polish and English. | D-06 |
