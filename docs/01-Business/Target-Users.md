---
title: Target Users
type: business
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - business
  - users
---

# Target Users and Actors

## Users

The MVP is **single-user**. One person installs and uses the app on their own computer, without login. It is reachable only from the local machine ([[Business-Rules]] (RULE-018), D-29).

Typical users:

| Profile | Need |
|---|---|
| App developer or indie creator (e.g. Exerzio) | Many illustrations in one consistent style for a product |
| Designer or illustrator | Fast variants, references and consistent characters |
| Open-source user with an NVIDIA GPU | A free, local alternative to cloud image services |

## Actors

| Actor | Can do | Cannot do |
|---|---|---|
| `user` | everything in the UI | — |
| `mcp` (Claude Code) | read data; draft project and style configurations; queue generations; add review comments; approve or publish **only where the project allows it** (off by default) | create a project without confirmation in the UI; bypass validation or approval rules; access arbitrary files; download models |
| `system` | run jobs, processing and technical validation; record audit entries | approve, reject or publish |

Out of MVP: multiple accounts, roles, LAN access.
