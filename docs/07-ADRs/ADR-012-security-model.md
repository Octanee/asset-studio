---
title: ADR-012 Security model for a local single-user app
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-012: Security model for a local single-user app

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
D-29: one user, no login. Local web apps are exposed to CSRF and DNS rebinding.

## Decision
Loopback binding, Host allow-list, Origin checks, SameSite=Strict session cookie, per-component tokens (MCP, worker, host agent), strict upload and SVG handling, append-only audit.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| No protection (localhost is trusted) | simplest | any web page could drive the API |
| Full user accounts | strong | contradicts D-29 |

## Consequences
Protects the user without a login. Tokens are created by setup and rotatable in Settings.
