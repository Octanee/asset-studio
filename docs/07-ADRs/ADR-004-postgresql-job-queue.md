---
title: ADR-004 PostgreSQL for data and the job queue
type: adr
status: proposed
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-004: PostgreSQL for data and the job queue

**Status:** proposed — decided at gate G-6.

## Context
Jobs must persist and survive restarts (brief §5.3, NFR-003). There is one GPU lane and few concurrent jobs.

## Decision
PostgreSQL 17. The queue is a `job` table using `SELECT … FOR UPDATE SKIP LOCKED`, leases with `locked_until`, and `LISTEN/NOTIFY` to wake workers. A worker heartbeat lets the system detect interrupted jobs on start.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Redis + Celery/RQ | mature | another service; job state outside the DB complicates recovery and audit |
| SQLite | zero setup | weaker concurrency between processes; the brief prefers PostgreSQL |

## Consequences
One source of truth, transactional with domain changes. Throughput is limited but far above our needs.
