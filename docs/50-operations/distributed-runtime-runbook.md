# Distributed Runtime and Worker Runbook

## Canonical execution model

- API requests validate scope and enqueue a durable PostgreSQL job.
- A worker claims with `FOR UPDATE SKIP LOCKED`, a lease token and heartbeat.
- Delivery is **at least once**. Handlers must use idempotency keys and stable delivery IDs.
- An expired lease returns the same job identity to `retry`; exhausted poison messages enter
  `dead_letter` and require a permission-checked replay.
- Transactional outbox side effects are delivered only after the domain transaction commits.

## Redis

Redis coordinates distributed endpoint rate limits and ephemeral fan-out. PostgreSQL remains the
source of truth for jobs and event cursors. Production requires authenticated `rediss://` unless
the deployment explicitly documents a private-network TLS exception.

Rate-limit outage semantics are policy specific:

- login, session, export, Action and Agent: fail closed
- low-risk planner recommendation: fail open with an observability event

## Operations

1. Check V4 **Distributed runtime** for Redis, queue depth, retries, stale leases and DLQ.
2. Drain workers by sending `SIGTERM`; the worker stops claiming new jobs and exits after the
   current handler boundary.
3. A crashed worker is recovered after `ONTOLOGY_DASHBOARD_JOB_LEASE_SECONDS`.
4. Replay a DLQ item only after reviewing its payload, failure class, runtime checksum and
   idempotency contract.
5. During Redis outage, do not bypass fail-closed security endpoints. Database queue work may
   continue, but multi-instance rate limiting and fan-out remain degraded.
