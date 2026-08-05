# Observability, SLO and Alerting Runbook

## Telemetry contract

- JSON logs are written to stdout with request, trace and span IDs.
- secrets, cookies, authorization headers and credentials are redacted.
- actor and client identifiers are hashed; raw object/job/artifact IDs are not metric labels.
- W3C `traceparent` is accepted and propagated across API responses and durable work payloads.
- `/metrics` uses Prometheus exposition and requires a bearer token in production.
- OTLP export and alert delivery remain `not_configured` until external endpoints are supplied.

## SLOs

| SLO | Objective | Window | Good event |
|---|---:|---:|---|
| API availability | 99.9% | 30d | non-5xx response |
| Interactive latency | 95% | 30d | response ≤ 750 ms |
| Durable job freshness | 99% | 30d | job starts ≤ 60 s |

The error budget is `1 - objective`. Multi-window burn-rate alerts protect against rapid and slow
budget exhaustion. A release is blocked when the availability budget is exhausted unless an
incident commander records an explicit exception.

## API fast burn

1. Confirm the alert uses both 5-minute and 1-hour windows.
2. Split by route template and status class; never add raw IDs as labels.
3. Correlate request IDs with traces and structured logs.
4. Check database, Redis, object storage and worker readiness before rolling back.
5. Mitigate, verify burn rate recovery, and record the incident timeline.

## Connector freshness

Check source checkpoint age, quarantine depth, retry/backoff, source throttling and worker heartbeat.
Do not mark freshness healthy from a successful HTTP response alone; the checkpoint must advance.

## Alert delivery test

Before production launch, configure `ONTOLOGY_DASHBOARD_ALERT_DESTINATION_REF`, route test alerts
to the owning team, verify acknowledgement and escalation, and record screenshots/exported alert
history. Local alert definitions are PASS; external delivery remains BLOCKED until this exercise.
