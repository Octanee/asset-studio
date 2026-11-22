---
title: Project Creation
type: business-process
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - workflow
  - projects
---

# Project Creation

```mermaid
sequenceDiagram
  actor U as User
  participant C as Claude Code (MCP)
  participant A as Asset Studio
  U->>C: Describe the project in natural language
  C->>A: Submit configuration draft
  A->>A: Validate against schema, mark assumptions and missing fields
  U->>A: Review and edit draft in UI
  U->>A: Confirm
  A->>A: Create project (version 1 of configuration), audit entry
```

- **Manual path:** the user fills in the same form in the UI (UC-001).
- **Clone / import:** start from an existing configuration (UC-003); the result is validated again (RULE-014).
- The project setting "MCP may approve/publish" starts **off** (RULE-005).
- Requirements: FR-001–FR-008 · Rules: RULE-010, RULE-014
