---
title: Phase Gates
type: governance
status: draft
created: 2026-11-21
updated: 2026-11-24
tags:
  - governance
  - gates
---

# Phase Gates and Approvals

Silence is not approval. A general instruction to continue does not approve a specific gated deliverable.

| Gate | Deliverable | Status | Date |
|---|---|---|---|
| G-0 | Move from Phase 0 to discovery | ✅ approved | 2026-11-21 |
| G-1 | Final business scope | ✅ approved (D-41) | 2026-11-21 |
| G-2 | Documentation baseline | ✅ approved (D-43) | 2026-11-22 |
| G-4 | Complete UI/UX design | ✅ approved (D-45) | 2026-11-22 |
| G-6a | Technical architecture | ✅ approved (D-46) | 2026-11-22 |
| G-6b | Implementation roadmap | ✅ approved (D-46) | 2026-11-22 |
| G-9 | Public release | ✅ approved (D-64): v0.1.0, [[Release-Procedure]], `CHANGELOG.md` | 2026-11-24 |

## Standing authorisations (2026-11-21)

- Work proceeds continuously through the phases but **stops at every gate** for approval.
- Git: the user authorised a local repository, `feature/*` branches, commits, pushing **branches**, and opening pull requests for review. The user did not authorise pushing to `main`, force-pushing, or merging pull requests.

## Verified understanding

Assessed at about **96%** after gate G-6 (2026-11-22). Every area now has approved, documented decisions:
- business scope and rules (G-1);
- documentation baseline (G-2);
- UI/UX (G-4);
- architecture and roadmap (G-6).

The remaining uncertainties are known and bounded:
- R-12: consistency across many poses;
- R-19, R-20: upstream licences of DWPose and BiRefNet;
- R-21: bind-mount speed.

They are verified in **WP-01** before the modules that depend on them, and a negative result comes back to the user as a proposed ADR change. The UX gaps UXQ-01–UXQ-04 are designed before their features (D-45).
