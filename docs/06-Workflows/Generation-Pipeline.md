---
title: Generation Pipeline
type: business-process
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - workflow
  - generation
---

# Generation Pipeline (business view)

```mermaid
flowchart LR
  R[Request<br/>style + character + pose + prompt + model] --> V{Checks}
  V -- family/LoRA/workflow OK --> L{Licence conflict?}
  L -- yes --> W[Warning + audited confirmation]
  L -- no --> Q[Queue job]
  W --> Q
  Q --> E[Engine run<br/>one GPU job at a time]
  E --> G[Version: generated]
  G --> P[Post-processing<br/>resize, convert, background removal]
  P --> T[Technical validation]
  T --> A[awaiting_review]
```

- The engine is unavailable or there is no GPU → the job waits with a clear status (RULE-013).
- Metadata is stored for reproducibility (RULE-011).
- Technical design: [[AI-Generation-Architecture]] (Phase 5).
