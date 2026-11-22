---
title: ADR-007 Local storage with abstraction and immutable versions
type: adr
status: proposed
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-007: Local storage with abstraction and immutable versions

**Status:** proposed — decided at gate G-6.

## Context
Brief §8.4. Binary files must not live in the database. Approved files must never be overwritten.

## Decision
A `Storage` interface with `LocalStorage`; server-generated keys; one directory per version, written once via temp + rename; derived thumbnails can be regenerated.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Content-addressed store | deduplication | harder for users to inspect; little benefit |
| Object storage (MinIO) | S3 API | extra service with no need |

## Consequences
The layout is easy to back up and inspect. A consistency check runs on start.
