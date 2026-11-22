---
title: Design Decisions
type: ux
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - ux
  - decisions
---

# Design Decisions

| ID | Decision | Reason |
|---|---|---|
| DD-001 | Dark-first neutral theme, plus a light theme | Long sessions with images; neutral chrome keeps colour judgement honest |
| DD-002 | One accent, separate status palette | Status must never be confused with an action |
| DD-003 | Status always as dot + text | Accessibility (not colour alone), PL/EN labels |
| DD-004 | Pose is a first-class input in Generation Studio | Prototype: references without pose copy the reference pose |
| DD-005 | Review is a dedicated screen with keyboard shortcuts | Batches produce dozens of versions; decisions must be fast |
| DD-006 | Publishing shows a file plan before writing | Makes overwrites visible and confirmable (RULE-004) |
| DD-007 | Claude's actions are labelled "Claude (MCP)" everywhere | Traceability (RULE-006) and trust |
| DD-008 | Disabled controls explain why, and queueing stays possible while the engine is down | RULE-013: the app stays useful |
| DD-009 | Training shows a time estimate per model family before start | RULE-016; 8–20 h SDXL on 6 GB |
| DD-010 | Desktop-first; review also on tablet and phone | Professional production tool; review is the task people do away from the desk |
