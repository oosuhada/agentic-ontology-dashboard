# Production Deployment Runbook

## Topology

`migration job → API replicas + static Web ingress → analysis/modeling/outbox workers`

PostgreSQL, Redis and optional Neo4j/Object Storage remain private network dependencies. The
Cloudflare development tunnel is not production ingress evidence.

## Release

1. Build API and Web images from the multi-stage Dockerfiles and scan them.
2. Inject configuration and secret references; never bake credentials into the image.
3. Run the one-shot migration Job with a release lock.
4. Verify `/health/startup`, then roll API replicas with zero unavailable.
5. Verify `/health/ready`, worker heartbeats and all four direct routes.
6. Roll Web replicas and verify immutable asset caching, gzip and SPA refresh.

Applied migrations are forward-fixed, never edited. Rollback is allowed only while the previous
application version is compatible with the forward schema; otherwise roll forward with a fix.

## Versioned route smoke

- `/app/projects/manufacturing-demo-project`
- `/app/projects/manufacturing-demo-project/blueprint`
- `/app/projects/manufacturing-demo-project/blueprint-v2`
- `/app/projects/manufacturing-demo-project/blueprint-v4`

The first three remain comparison baselines and are never redirected to V4.
