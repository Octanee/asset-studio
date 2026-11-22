---
title: Documentation Rules
type: governance
status: draft
created: 2026-11-21
updated: 2026-11-22
tags:
  - governance
  - documentation
---

# Documentation Rules

1. **Source of truth.** This vault records approved requirements and decisions. If code and docs disagree, report the conflict, explain the impact, and ask for approval when a business decision is needed. Approved rules are never changed silently.
2. **Language.** Documentation is in English.
3. **Format.** Obsidian Markdown with YAML frontmatter (`title`, `type`, `status`, `created`, `updated`, `tags`), wikilinks, Mermaid diagrams and tables.
4. **Status values.** `draft` → `in-review` → `approved` → `superseded`. Changing an `approved` page materially needs user approval, and the change is noted in [[Decision-Log]].
5. **Identifiers.** IDs are stable and never reused; deleted items are marked `withdrawn`. Prefixes are listed in [[Requirements-Index]]. Numbers are zero-padded to three digits and grouped by module, with gaps left for additions.
6. **Traceability.** Every FR maps to at least one BR. Every implemented FR maps to acceptance criteria and tests before it counts as done.
7. **Definition of Done.** A pull request updates the relevant docs together with the code (brief §13.3).
8. **No private data.** No machine-specific details, usernames, local paths, secrets or personal data. Local reports stay outside the repository (in a git-ignored folder).
9. **ADRs.** Architecture decisions use `07-ADRs/ADR-xxx-<slug>.md`, with Context, Decision, Alternatives, Consequences and Status.
10. **Readability.** Pages must be understandable to a business stakeholder without reading the code.
