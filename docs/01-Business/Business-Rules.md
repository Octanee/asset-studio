---
title: Business Rules
type: business-rules
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - business
  - rules
---

# Business Rules

> [!note] Identifier change
> In the approved Phase 1 draft these rules were numbered BR-01–BR-17. They are renumbered `RULE-xxx` here because `BR-xxx` is reserved for business requirements (see [[Documentation-Rules]]). The content is unchanged. RULE-018 records decision D-29 explicitly.

| ID | Rule | Source |
|---|---|---|
| RULE-001 | Platform logic is never hardcoded for a specific project. | brief §3.1 |
| RULE-002 | Images are generated only by local engines; no external image-generation APIs. | brief §2.2 |
| RULE-003 | An approved or published version is never overwritten; every new generation creates a new version. | brief §7, D-27 |
| RULE-004 | Overwriting a file in an export target requires explicit user confirmation. | brief §6.11, D-33 |
| RULE-005 | MCP may approve, reject or publish only if the project setting allows it. The setting is **off** by default, and changing it is audited. | D-26, D-30 |
| RULE-006 | Every important state transition is audited: actor (`user` / `mcp` / `system`), time, previous and new state, reason. | brief §7 |
| RULE-007 | Using a model whose licence conflicts with the project's intended use shows a warning and requires explicit, audited confirmation. It is not blocked. | D-18 |
| RULE-008 | No model is downloaded without user approval. | brief §6.10 |
| RULE-009 | Technical validation never claims domain correctness (anatomy, exercise technique, medical accuracy); human review is always available. | brief §6.8 |
| RULE-010 | AI never makes irreversible configuration decisions; creating a project from an MCP draft requires confirmation in the UI. | brief §3.4, D-03 |
| RULE-011 | Generation metadata (model and hash, workflow version, parameters, seed, prompts, references, pose, character, LoRA) is stored for reproducibility, without promising bit-exact results. | brief §5.2 |
| RULE-012 | GPU jobs (generation, training) run one at a time; training requires the generation engine to release VRAM. | prototype finding S-4 |
| RULE-013 | Without a GPU, or with the engine stopped, everything except diffusion generation and training keeps working, and the UI says clearly what is unavailable. | D-39 |
| RULE-014 | A project configuration is versioned and validated against a schema, including on import. | brief §3.3, D-37 |
| RULE-015 | A LoRA can be used only with a base model of the same family (SDXL / SD1.5). | D-24 |
| RULE-016 | Before SDXL training starts on hardware below the recommended spec, the app shows an estimated time and a warning. | D-24 |
| RULE-017 | A training dataset may contain approved project assets and/or files uploaded by the user. | D-38 |
| RULE-018 | The app serves one local user without login and listens only on the loopback interface. | D-29 |
| RULE-019 | A published version must be archived before it can be permanently deleted; permanent deletion keeps the audit entry. | D-31, D-41 |
| RULE-020 | Approval can be withdrawn only from a version that has never been published, and a reason is required. | D-31 |
