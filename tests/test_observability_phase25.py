from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ontology_dashboard.observability import (
    METRICS,
    JsonLogFormatter,
    MetricsRegistry,
    ObservabilityMiddleware,
    SLOS,
    error_budget_status,
    normalize_route,
    observability_readiness,
    parse_traceparent,
    sanitize_for_log,
)
from ontology_dashboard.routers.system import router as system_router


ROOT = Path(__file__).resolve().parents[1]


def test_log_sanitization_redacts_secrets_and_hashes_high_risk_values() -> None:
    payload = sanitize_for_log(
        {
            "password": "plain-text",
            "nested": {"Authorization": "Bearer secret", "safe": "value"},
            "bytes": b"abc",
        }
    )
    assert payload["password"] == "[redacted]"
    assert payload["nested"]["Authorization"] == "[redacted]"
    assert payload["nested"]["safe"] == "value"
    assert payload["bytes"] == "[bytes:3]"

    record = logging.LogRecord(
        name="phase25",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="structured",
        args=(),
        exc_info=None,
    )
    record.structured = {"api_key": "should-not-leak", "result": "ok"}
    rendered = json.loads(JsonLogFormatter().format(record))
    assert rendered["fields"]["api_key"] == "[redacted]"
    assert "should-not-leak" not in json.dumps(rendered)


def test_traceparent_validation_and_route_cardinality_are_bounded() -> None:
    valid = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert parse_traceparent(valid) == (
        "4bf92f3577b34da6a3ce929d0e0e4736",
        "00f067aa0ba902b7",
    )
    assert parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01") is None
    assert normalize_route("/jobs/job-12345/artifacts/artifact-abcdef") == "/jobs/{id}/artifacts/{id}"


def test_metrics_registry_uses_fixed_labels_and_prometheus_histograms() -> None:
    registry = MetricsRegistry()
    registry.inc(
        "ontology_http_requests_total",
        labels={"method": "GET", "route": "/objects/{id}", "status_class": "2xx"},
    )
    registry.observe(
        "ontology_http_request_duration_seconds",
        0.2,
        labels={"method": "GET", "route": "/objects/{id}"},
    )
    output = registry.render_prometheus()
    assert 'route="/objects/{id}"' in output
    assert "ontology_http_request_duration_seconds_bucket" in output
    assert "actual-object-123" not in output


def test_error_budget_math_distinguishes_healthy_risk_and_exhausted() -> None:
    slo = SLOS[0]
    healthy = error_budget_status(slo, good_events=9999, total_events=10000)
    exhausted = error_budget_status(slo, good_events=9900, total_events=10000)
    assert healthy.state in {"healthy", "at_risk"}
    assert exhausted.state == "exhausted"
    assert exhausted.remaining_fraction == 0


def test_observability_middleware_propagates_trace_and_exposes_metrics(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN", raising=False)
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)
    app.include_router(system_router)
    with TestClient(app) as client:
        response = client.get(
            "/health/live",
            headers={
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                "x-request-id": "request-phase25",
            },
        )
        assert response.status_code == 200
        assert response.headers["x-request-id"] == "request-phase25"
        assert response.headers["traceparent"].startswith(
            "00-4bf92f3577b34da6a3ce929d0e0e4736-"
        )
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "ontology_http_requests_total" in metrics.text


def test_production_metrics_endpoint_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN", "metrics-secret")
    app = FastAPI()
    app.include_router(system_router)
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get(
            "/metrics",
            headers={"Authorization": "Bearer metrics-secret"},
        ).status_code == 200


def test_readiness_and_alert_rules_are_honest_and_parseable(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALERT_DESTINATION_REF", raising=False)
    readiness = observability_readiness()
    assert readiness.state == "degraded"
    assert readiness.tracing["state"] == "not_configured"
    assert readiness.metrics["raw_object_ids_allowed"] is False
    rules = yaml.safe_load(
        (ROOT / "infra/observability/prometheus-rules.yaml").read_text(encoding="utf-8")
    )
    alerts = [
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if "alert" in rule
    ]
    assert len(alerts) >= 4
    assert all(rule["annotations"]["runbook"] for rule in alerts)
