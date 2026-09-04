"""Structured logging, trace propagation, bounded metrics and SLO evidence."""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")
organization_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("organization_id", default="")
project_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("project_id", default="")
actor_hash_var: contextvars.ContextVar[str] = contextvars.ContextVar("actor_hash", default="")


SENSITIVE_KEY = re.compile(
    r"(authorization|cookie|password|passwd|secret|token|api[_-]?key|credential|private[_-]?key)",
    re.IGNORECASE,
)
HIGH_CARDINALITY_PATH = re.compile(
    r"/(?:[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9]{4,}|job-[^/]+|artifact-[^/]+)(?=/|$)",
    re.IGNORECASE,
)


def hash_identifier(value: str | None) -> str:
    if not value:
        return ""
    salt = os.getenv("ONTOLOGY_DASHBOARD_LOG_HASH_SALT", "ontology-dashboard")
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]


def bind_principal_context(*, organization_id: str, project_id: str | None, user_id: str) -> None:
    organization_id_var.set(organization_id)
    project_id_var.set(project_id or "")
    actor_hash_var.set(hash_identifier(user_id))


def sanitize_for_log(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 6:
        return "[depth-limited]"
    if key and SENSITIVE_KEY.search(key):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_for_log(item_value, key=str(item_key), depth=depth + 1)
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_log(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, bytes):
        return f"[bytes:{len(value)}]"
    if isinstance(value, str) and len(value) > 2000:
        return f"{value[:2000]}…[truncated]"
    return value


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
            "span_id": span_id_var.get(),
            "organization_id": organization_id_var.get(),
            "project_id": project_id_var.get(),
            "actor_hash": actor_hash_var.get(),
        }
        extras = getattr(record, "structured", None)
        if isinstance(extras, Mapping):
            payload["fields"] = sanitize_for_log(extras)
        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": sanitize_for_log(str(record.exc_info[1])),
            }
        return json.dumps(
            {
                key: value
                for key, value in payload.items()
                if value is not None and value != "" and value != {}
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def configure_structured_logging() -> None:
    level = getattr(logging, os.getenv("ONTOLOGY_DASHBOARD_LOG_LEVEL", "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(handler, "_ontology_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._ontology_json = True  # type: ignore[attr-defined]
    root.handlers.clear()
    root.addHandler(handler)


MetricLabels = tuple[tuple[str, str], ...]


def _labels(labels: Mapping[str, str] | None) -> MetricLabels:
    if not labels:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def normalize_route(path: str) -> str:
    normalized = HIGH_CARDINALITY_PATH.sub("/{id}", path)
    return normalized[:180]


@dataclass
class HistogramState:
    buckets: tuple[float, ...]
    counts: list[int]
    total_count: int = 0
    total_sum: float = 0.0


class MetricsRegistry:
    """Small dependency-free Prometheus registry with bounded labels."""

    DEFAULT_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, MetricLabels], float] = defaultdict(float)
        self._gauges: dict[tuple[str, MetricLabels], float] = {}
        self._histograms: dict[tuple[str, MetricLabels], HistogramState] = {}

    def inc(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ValueError("counter increments must be non-negative")
        with self._lock:
            self._counters[(name, _labels(labels))] += value

    def set_gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        with self._lock:
            self._gauges[(name, _labels(labels))] = float(value)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        key = (name, _labels(labels))
        selected = buckets or self.DEFAULT_BUCKETS
        with self._lock:
            state = self._histograms.get(key)
            if state is None:
                state = HistogramState(selected, [0 for _ in selected])
                self._histograms[key] = state
            if state.buckets != selected:
                raise ValueError("histogram buckets cannot change for an existing series")
            for index, boundary in enumerate(selected):
                if value <= boundary:
                    state.counts[index] += 1
            state.total_count += 1
            state.total_sum += value

    @staticmethod
    def _render_labels(labels: MetricLabels, extra: tuple[str, str] | None = None) -> str:
        items = list(labels)
        if extra:
            items.append(extra)
        if not items:
            return ""
        rendered = ",".join(
            f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for key, value in items
        )
        return "{" + rendered + "}"

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {
                key: HistogramState(value.buckets, list(value.counts), value.total_count, value.total_sum)
                for key, value in self._histograms.items()
            }
        for (name, labels), value in sorted(counters.items()):
            lines.append(f"{name}{self._render_labels(labels)} {value:g}")
        for (name, labels), value in sorted(gauges.items()):
            lines.append(f"{name}{self._render_labels(labels)} {value:g}")
        for (name, labels), state in sorted(histograms.items()):
            for boundary, count in zip(state.buckets, state.counts):
                lines.append(
                    f'{name}_bucket{self._render_labels(labels, ("le", str(boundary)))} {count}'
                )
            lines.append(f'{name}_bucket{self._render_labels(labels, ("le", "+Inf"))} {state.total_count}')
            lines.append(f"{name}_sum{self._render_labels(labels)} {state.total_sum:g}")
            lines.append(f"{name}_count{self._render_labels(labels)} {state.total_count}")
        return "\n".join(lines) + "\n"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counter_series": len(self._counters),
                "gauge_series": len(self._gauges),
                "histogram_series": len(self._histograms),
                "http_requests": sum(
                    value for (name, _), value in self._counters.items()
                    if name == "ontology_http_requests_total"
                ),
                "http_errors": sum(
                    value for (name, labels), value in self._counters.items()
                    if name == "ontology_http_requests_total"
                    and dict(labels).get("status_class") in {"4xx", "5xx"}
                ),
            }


METRICS = MetricsRegistry()
LOGGER = logging.getLogger("app.observability")
OPEN_METRICS_ENVIRONMENTS = {"development", "test"}


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None
    trace_id, parent_id, flags = parts[1], parts[2], parts[3]
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or trace_id == "0" * 32:
        return None
    if not re.fullmatch(r"[0-9a-f]{16}", parent_id) or parent_id == "0" * 16:
        return None
    if not re.fullmatch(r"[0-9a-f]{2}", flags):
        return None
    return trace_id, parent_id


def new_trace_context(traceparent: str | None) -> tuple[str, str]:
    parsed = parse_traceparent(traceparent)
    trace_id = parsed[0] if parsed else uuid.uuid4().hex
    return trace_id, uuid.uuid4().hex[:16]


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", request_id):
            request_id = f"req-{uuid.uuid4()}"
        trace_id, span_id = new_trace_context(request.headers.get("traceparent"))
        request_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)
        span_token = span_id_var.set(span_id)
        status_code = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            LOGGER.exception(
                "http_request_failed",
                extra={"structured": {"method": request.method, "path": normalize_route(request.url.path)}},
            )
            raise
        finally:
            duration = max(0.0, time.perf_counter() - started)
            route = getattr(request.scope.get("route"), "path", None) or normalize_route(request.url.path)
            labels = {
                "method": request.method,
                "route": normalize_route(route),
                "status_class": f"{status_code // 100}xx",
            }
            METRICS.inc("ontology_http_requests_total", labels=labels)
            METRICS.observe("ontology_http_request_duration_seconds", duration, labels={
                "method": request.method,
                "route": normalize_route(route),
            })
            LOGGER.info(
                "http_request",
                extra={
                    "structured": {
                        "method": request.method,
                        "route": normalize_route(route),
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 3),
                        "client_ip_hash": hash_identifier(request.client.host if request.client else None),
                    }
                },
            )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["traceparent"] = f"00-{trace_id}-{span_id}-01"
            request_id_var.reset(request_token)
            trace_id_var.reset(trace_token)
            span_id_var.reset(span_token)
            organization_id_var.set("")
            project_id_var.set("")
            actor_hash_var.set("")


class SLODefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    objective: float = Field(gt=0, le=1)
    window_days: int = Field(gt=0)
    sli: str
    good_event: str
    total_event: str
    alert_burn_rates: tuple[float, ...]


class ErrorBudgetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slo_id: str
    objective: float
    observed_success_ratio: float
    budget_fraction: float
    consumed_fraction: float
    remaining_fraction: float
    state: Literal["healthy", "at_risk", "exhausted"]


class AlertRuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    severity: Literal["warning", "critical"]
    expression: str
    duration: str
    runbook: str
    routing_key: str


class ObservabilityReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "degraded", "not_configured", "blocked"]
    structured_logging: str
    log_redaction: str
    tracing: dict[str, Any]
    metrics: dict[str, Any]
    slos: tuple[SLODefinition, ...]
    error_budgets: tuple[ErrorBudgetStatus, ...]
    alerts: tuple[AlertRuleDefinition, ...]
    dashboards: tuple[str, ...]
    blockers: tuple[str, ...]


SLOS = (
    SLODefinition(
        id="api-availability",
        name="API availability",
        objective=0.999,
        window_days=30,
        sli="non-5xx responses / eligible responses",
        good_event="status_class != 5xx",
        total_event="all non-health API requests",
        alert_burn_rates=(14.4, 6.0, 3.0, 1.0),
    ),
    SLODefinition(
        id="api-latency",
        name="Interactive API latency",
        objective=0.95,
        window_days=30,
        sli="responses below 750 ms / eligible responses",
        good_event="duration <= 0.75 seconds",
        total_event="interactive API requests",
        alert_burn_rates=(14.4, 6.0, 3.0, 1.0),
    ),
    SLODefinition(
        id="durable-job-freshness",
        name="Durable job start freshness",
        objective=0.99,
        window_days=30,
        sli="jobs started within 60 seconds / queued jobs",
        good_event="queue latency <= 60 seconds",
        total_event="durable jobs",
        alert_burn_rates=(12.0, 4.0, 2.0),
    ),
)


ALERTS = (
    AlertRuleDefinition(
        id="api-fast-burn",
        severity="critical",
        expression="availability error-budget burn > 14.4x for 5m and > 6x for 1h",
        duration="5m",
        runbook="docs/50-operations/observability-slo-alerting-runbook.md#api-fast-burn",
        routing_key="platform-oncall",
    ),
    AlertRuleDefinition(
        id="worker-queue-stalled",
        severity="critical",
        expression="oldest queued job > 300s or stale worker lease > 0",
        duration="10m",
        runbook="docs/50-operations/distributed-runtime-runbook.md",
        routing_key="data-platform-oncall",
    ),
    AlertRuleDefinition(
        id="artifact-integrity",
        severity="critical",
        expression="artifact checksum mismatch or missing regulated artifact > 0",
        duration="0m",
        runbook="docs/50-operations/object-storage-artifact-governance-runbook.md",
        routing_key="security-data-oncall",
    ),
    AlertRuleDefinition(
        id="connector-freshness",
        severity="warning",
        expression="connector checkpoint age exceeds source freshness policy",
        duration="15m",
        runbook="docs/50-operations/production-deployment-runbook.md",
        routing_key="data-operations",
    ),
)


def error_budget_status(
    slo: SLODefinition,
    *,
    good_events: int,
    total_events: int,
) -> ErrorBudgetStatus:
    observed = 1.0 if total_events <= 0 else max(0.0, min(1.0, good_events / total_events))
    budget = 1.0 - slo.objective
    consumed = max(0.0, (1.0 - observed) / budget) if budget > 0 else 0.0
    remaining = max(0.0, 1.0 - consumed)
    state: Literal["healthy", "at_risk", "exhausted"] = (
        "exhausted" if remaining <= 0 else "at_risk" if remaining < 0.25 else "healthy"
    )
    return ErrorBudgetStatus(
        slo_id=slo.id,
        objective=slo.objective,
        observed_success_ratio=observed,
        budget_fraction=budget,
        consumed_fraction=consumed,
        remaining_fraction=remaining,
        state=state,
    )


def observability_readiness() -> ObservabilityReadiness:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    metrics_token = os.getenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN", "").strip()
    alert_destination = os.getenv("ONTOLOGY_DASHBOARD_ALERT_DESTINATION_REF", "").strip()
    blockers: list[str] = []
    if not endpoint:
        blockers.append("OpenTelemetry collector endpoint is not configured.")
    if environment == "production" and not metrics_token:
        blockers.append("Production metrics scrape token is not configured.")
    if not alert_destination:
        blockers.append("Alert destination reference is not configured.")
    snapshot = METRICS.snapshot()
    total = int(snapshot["http_requests"])
    errors = int(snapshot["http_errors"])
    budgets = tuple(
        error_budget_status(slo, good_events=max(0, total - errors), total_events=total)
        for slo in SLOS
    )
    state: Literal["ready", "degraded", "not_configured", "blocked"]
    if environment == "production" and blockers:
        state = "blocked"
    elif blockers:
        state = "degraded"
    else:
        state = "ready"
    return ObservabilityReadiness(
        state=state,
        structured_logging="JSON stdout with request/trace/span context",
        log_redaction="secrets redacted; actor and client identifiers hashed",
        tracing={
            "state": "ready" if endpoint else "not_configured",
            "protocol": os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
            "endpoint_configured": bool(endpoint),
            "traceparent_propagation": True,
            "sampling": os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1"),
        },
        metrics={
            "endpoint": "/metrics",
            "format": "Prometheus text exposition",
            "bounded_labels": ["method", "route-template", "status-class", "worker-type", "job-type"],
            "raw_object_ids_allowed": False,
            "scrape_auth": "bearer token required in production",
            **snapshot,
        },
        slos=SLOS,
        error_budgets=budgets,
        alerts=ALERTS,
        dashboards=(
            "API availability and latency",
            "Durable queue depth, age, retries and DLQ",
            "Connector freshness and quarantine",
            "Artifact integrity and reconciliation",
            "Model drift and automation execution",
        ),
        blockers=tuple(blockers),
    )


def metrics_authorized(request: Request) -> bool:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    expected = os.getenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN", "").strip()
    if environment in OPEN_METRICS_ENVIRONMENTS and not expected:
        return True
    provided = request.headers.get("authorization", "")
    return bool(expected) and hmac_compare(provided, f"Bearer {expected}")


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode(), right.encode())


__all__ = [
    "ALERTS",
    "METRICS",
    "SLOS",
    "AlertRuleDefinition",
    "ErrorBudgetStatus",
    "JsonLogFormatter",
    "MetricsRegistry",
    "ObservabilityMiddleware",
    "ObservabilityReadiness",
    "SLODefinition",
    "configure_structured_logging",
    "bind_principal_context",
    "error_budget_status",
    "hash_identifier",
    "metrics_authorized",
    "new_trace_context",
    "normalize_route",
    "observability_readiness",
    "parse_traceparent",
    "sanitize_for_log",
]
