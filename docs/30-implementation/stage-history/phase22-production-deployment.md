# Phase 22 — Production Deployment Foundation

- multi-stage non-root API/Web images
- Nginx static runtime with immutable assets, compression, security headers and SPA deep-link fallback
- separate liveness, startup and readiness probes
- one-shot migration Job and two-replica API/Web production reference topology
- read-only root filesystem and bounded writable `/tmp` mounts
- versioned V1–V4 route contract
- V4 Deployment surface with real local blockers

Image publication, cluster credentials, TLS ingress and staging rollout evidence remain `BLOCKED`
outside the customer deployment environment.
