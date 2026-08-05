# Phase 25 — Observability, SLO and Alerting

- JSON structured logging with request/trace/span/tenant context and secret redaction
- W3C traceparent propagation and response correlation headers
- bounded-cardinality Prometheus counters, gauges and histograms
- production-authenticated `/metrics` endpoint
- API availability, latency and durable-job freshness SLOs with error-budget calculation
- multi-window burn, queue stall, artifact integrity and connector freshness alert definitions
- runbook/routing metadata for every alert
- V4 Operations UI for telemetry readiness, SLOs, budgets, alerts and dashboards

Local logging and metrics are active. OTLP collector export and alert-destination delivery are
`not_configured` and remain external-environment verification items.
