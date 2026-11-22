---
title: ADR-008 MCP server as an API client
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-008: MCP server as an API client

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
Brief §10: MCP must call the backend API and not bypass rules. D-26/D-30: MCP decisions are allowed per project and off by default.

## Decision
Python MCP SDK, Streamable HTTP on loopback, a per-install token mapped to actor `mcp`. The tool list is in [[MCP-Architecture]]. High-impact operations are refused for `mcp`.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| stdio server with DB access | simple to wire | bypasses API rules; violates the brief |

## Consequences
All rules live in one place (the API). Claude Code connects via HTTP MCP config.
