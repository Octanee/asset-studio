---
title: ADR-004 PostgreSQL for data and the job queue
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-004: PostgreSQL for data and the job queue

**Status:** accepted at gate G-6 (2026-11-22, D-46).

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

## Implementation notes (WP-04)

- Claims use `SELECT … FOR UPDATE SKIP LOCKED`, ordered by priority then age. GPU claims also take a transaction-level advisory lock and refuse while a GPU job is running, so only one GPU job runs across all workers (RULE-012).
- A running job holds a lease (`locked_until`, 60 s by default) that the worker renews. Expired leases are marked `interrupted` on the next scheduling round and on worker start; a worker that stops marks its own jobs `interrupted`. Interrupted, failed and cancelled jobs can be retried (NFR-003).
- `pg_notify('asset_studio_jobs', lane)` on enqueue and retry wakes workers; they also poll every 2 s.
- Lane gates report why a lane cannot run (for example `ENGINE_UNAVAILABLE`); queued jobs then carry that `wait_reason` (RULE-013).
