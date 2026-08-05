# Phase 23 — Redis, Durable Workers and Transactional Outbox

- Analysis execution moved from FastAPI `BackgroundTasks` to a tenant-scoped durable job table
- atomic claim, lease, heartbeat, crash recovery, cancellation and deterministic backoff
- explicit transient/permanent/validation/cancelled failure taxonomy
- dead-letter replay with an immutable cursor event
- Project queue quota and idempotent enqueue contract
- Redis fixed-window rate-limit policy shared across API instances
- outbox processing lease, exponential retry and dead-letter replay
- production worker entrypoint with graceful SIGTERM drain and runtime checksum
- V4 Distributed runtime surface and operator actions

Local SQLite queue tests pass, while managed Redis remains `not_configured`. Multi-node Redis
failover and production worker autoscaling remain external-environment verification items.
