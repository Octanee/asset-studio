---
title: Product Vision
type: business
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - business
  - vision
---

# Product Vision

Universal Asset Studio is a **local-first, open-source application** that anyone can run on their own machine. It is used to create, organize, validate, review and export visual assets with **locally hosted AI models** and programmatic generation such as SVG.

The platform serves **many independent projects**. Each project has its own configuration, visual styles and recurring characters. The key value is **one consistent style and the same characters across all assets of a project**, defined through text and/or example images.

The platform is independent of any single domain. Exercise illustrations for the Exerzio app are the first example project and drive the MVP acceptance scenario, but the platform must stay independent of that project.

## Principles

- **Local-first:** images are generated locally. The app stays useful offline, without a GPU, or with the engine stopped ([[Business-Rules]] (RULE-013)).
- **Human in control:** AI proposes and people decide; approved work is never overwritten ([[Business-Rules]] (RULE-003)).
- **Controlled automation:** Claude Code can automate work through MCP, within project-level permissions ([[Business-Rules]] (RULE-005)).
- **Reproducible:** every generation keeps the metadata needed to repeat it ([[Business-Rules]] (RULE-011)).
- **Open:** Apache-2.0 licence. Model licences are tracked per project ([[Business-Rules]] (RULE-007)).

Related: [[Business-Goals]] · [[Target-Users]] · [[Product-Scope]]
