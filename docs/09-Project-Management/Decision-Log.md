---
title: Decision Log
type: decision-log
status: draft
created: 2026-11-21
updated: 2026-11-22
tags:
  - decisions
---

# Decision Log

User decisions recorded during Phases 0–1 (all dated 2026-11-21).

| ID | Decision |
|---|---|
| D-01 | Open-source project that anyone can run on their own machine |
| D-02 | Commercial use depends on the project; model licences are tracked per project |
| D-03 | Natural-language assistance through Claude Code + MCP; no LLM built into the app |
| D-04 | MVP example: exercise illustrations (Exerzio); one style defined by text or example images |
| D-05 | Technology chosen for quality and performance (decided by ADRs) |
| D-06 | UI in Polish and English |
| D-07 | Repository `Octanee/asset-studio` |
| D-08 | Documentation as an Obsidian vault in `docs/` |
| D-09 | Data locations configured in the app |
| D-10 | MVP platform: Windows + NVIDIA |
| D-12 | Consistent style **and** consistent characters |
| D-13 | LoRA training may be in scope |
| D-14 | Documentation in English |
| D-15 | Local environment reports stay outside the repository |
| D-17 | Distribution: Docker Compose and a native installer |
| D-18 | Licence conflicts → warning; using the model is the user's decision |
| D-19 | Native installer after the MVP |
| D-20 | Licence: Apache-2.0 |
| D-21 | No confidential data may reach the repository |
| D-22 | LoRA training in the MVP |
| D-23 | Poses from a library + editor and from detection |
| D-24 | Training on both SDXL and SD1.5 |
| D-25 | MVP also includes model management, export presets, dashboard, SVG generation |
| D-26 | Whether MCP may approve/publish is configurable per project |
| D-27 | Regeneration creates a new version of the same asset |
| D-28 | "Published" means exported to a target through a preset |
| D-29 | Single local user, no login |
| D-30 | MCP approval is off by default |
| D-31 | Reversible: rejected → review; withdraw approval; restore from archive; permanent deletion with confirmation |
| D-32 | Exerzio technical parameters set later as a project preset |
| D-33 | Re-export to the same target overwrites after explicit confirmation |
| D-34 | Background removal in the MVP |
| D-35 | Character as its own project entity |
| D-36 | Visual review by a human, optionally with Claude comments via MCP |
| D-37 | Project cloning and configuration import/export in the MVP |
| D-38 | Training data: approved assets and uploaded files |
| D-39 | Without a GPU: everything except diffusion and training works |
| D-40 | Manual backup/restore in the MVP |
| D-41 | Business scope approved, including: published-version pointer, backups without models, MoSCoW priorities, WCAG 2.2 AA, 10,000 versions per project, `processing_failed` state, archive before deleting a published version |
| D-42 | Phases run continuously, stopping at each gate; git authorisation as in [[Phase-Gates]] |
| D-43 | Documentation baseline approved (2026-11-22) |
| D-44 | One-time exception: bootstrap `main` with LICENSE and .gitignore pushed directly, because the remote was empty and a pull request needs a base branch (2026-11-22). All further changes go through pull requests |

IDs D-11 (licence delegated → D-20) and D-16 (ambiguous → D-18) were superseded and are kept for history.
