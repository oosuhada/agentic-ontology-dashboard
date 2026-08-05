"""Full Ontology Dashboard API surface inventory and framework comparison.

The original Week 1 experiment used one shared ``GET /health`` endpoint.  This
module extends the comparison to the complete FastAPI product surface.  It
does not pretend that 172 business handlers have also been rewritten in
Flask.  Instead it measures three separate things explicitly:

1. the real FastAPI application's full OpenAPI contract,
2. unauthenticated and authenticated runtime probes for every operation, and
3. the routing parity and manual contract burden of a generated bare-Flask
   mirror.

That distinction keeps the comparison reproducible without presenting a
generic Flask route mirror as a second implementation of the product.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from flask import Flask, jsonify, request


HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")
KNOWN_PATH_VALUES = {
    "project_id": "manufacturing-demo-project",
    "workspace_id": "manufacturing-demo",
    "role_code": "process_engineer",
    "event_id": "EVT-001",
    "prediction_id": "contract-probe-prediction",
    "session_id": "contract-probe-session",
}


@dataclass(frozen=True)
class OperationContract:
    method: str
    path: str
    operation_id: str
    tags: tuple[str, ...]
    path_parameter_count: int
    query_parameter_count: int
    has_request_body: bool
    has_response_schema: bool


def collect_operations(schema: dict[str, Any]) -> list[OperationContract]:
    operations: list[OperationContract] = []
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            parameters = operation.get("parameters", [])
            operations.append(
                OperationContract(
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId", f"{method}_{path}"),
                    tags=tuple(operation.get("tags", ())),
                    path_parameter_count=sum(
                        item.get("in") == "path" for item in parameters
                    ),
                    query_parameter_count=sum(
                        item.get("in") == "query" for item in parameters
                    ),
                    has_request_body=bool(operation.get("requestBody")),
                    has_response_schema=_has_response_schema(operation),
                )
            )
    return operations


def summarize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    operations = collect_operations(schema)
    tags = Counter(tag for operation in operations for tag in operation.tags)
    methods = Counter(operation.method for operation in operations)
    return {
        "path_count": len(schema.get("paths", {})),
        "operation_count": len(operations),
        "request_body_operation_count": sum(
            operation.has_request_body for operation in operations
        ),
        "parameterized_operation_count": sum(
            operation.path_parameter_count + operation.query_parameter_count > 0
            for operation in operations
        ),
        "response_schema_operation_count": sum(
            operation.has_response_schema for operation in operations
        ),
        "method_counts": dict(sorted(methods.items())),
        "tag_counts": dict(sorted(tags.items(), key=lambda item: (-item[1], item[0]))),
        "operations": [asdict(operation) for operation in operations],
    }


def build_flask_contract_mirror(schema: dict[str, Any]) -> Flask:
    """Register every OpenAPI operation in bare Flask as a contract mirror.

    The mirror intentionally returns metadata rather than executing Ontology
    Dashboard business logic.  It demonstrates route registration parity and
    makes the remaining manual validation/documentation work visible.
    """

    app = Flask("ontology_dashboard_full_surface_mirror")
    for index, operation in enumerate(collect_operations(schema)):
        flask_path = re.sub(r"\{([^}]+)\}", r"<\1>", operation.path)

        def mirror_handler(
            _operation: OperationContract = operation, **path_values: str
        ):
            return jsonify(
                {
                    "status": "contract-mirror",
                    "framework": "Flask",
                    "method": request.method,
                    "path": _operation.path,
                    "operation_id": _operation.operation_id,
                    "path_values": path_values,
                    "business_logic": "not-ported",
                }
            )

        app.add_url_rule(
            flask_path,
            endpoint=f"contract_operation_{index}",
            view_func=mirror_handler,
            methods=[operation.method],
            strict_slashes=False,
        )
    return app


def probe_flask_mirror(schema: dict[str, Any]) -> dict[str, Any]:
    app = build_flask_contract_mirror(schema)
    client = app.test_client()
    statuses: Counter[int] = Counter()
    failures: list[dict[str, Any]] = []
    for operation in collect_operations(schema):
        response = client.open(
            _render_url(operation.path, schema, operation.method),
            method=operation.method,
            json={"__contract_probe__": True}
            if operation.method not in {"GET", "HEAD"}
            else None,
        )
        statuses[response.status_code] += 1
        if response.status_code >= 400:
            failures.append(
                {
                    "method": operation.method,
                    "path": operation.path,
                    "status": response.status_code,
                }
            )
    return {
        "registered_operation_count": len(collect_operations(schema)),
        "status_counts": {str(key): value for key, value in sorted(statuses.items())},
        "failure_count": len(failures),
        "failures": failures,
        "automatic_openapi_operation_count": 0,
        "automatic_request_validation_operation_count": 0,
        "automatic_response_schema_operation_count": 0,
        "business_handler_operation_count": 0,
    }


def probe_fastapi_surface(*, authenticated: bool) -> dict[str, Any]:
    """Exercise every real FastAPI operation in an isolated SQLite runtime."""

    with tempfile.TemporaryDirectory(prefix="ontology-full-surface-") as temp_dir:
        previous = {
            key: os.environ.get(key)
            for key in ("APP_ENV", "SEED_DEMO_ACCOUNTS", "ONTOLOGY_DASHBOARD_DB")
        }
        os.environ["APP_ENV"] = "test"
        os.environ["SEED_DEMO_ACCOUNTS"] = "1"
        os.environ["ONTOLOGY_DASHBOARD_DB"] = str(Path(temp_dir) / "surface.db")
        try:
            from fastapi.testclient import TestClient

            from ontology_dashboard import dependencies
            from ontology_dashboard.identity import CSRF_COOKIE
            from ontology_dashboard.main import app

            _clear_dependency_caches(dependencies)
            schema = app.openapi()
            operations = collect_operations(schema)
            statuses: Counter[int] = Counter()
            failures: list[dict[str, Any]] = []
            expected_unavailable: list[dict[str, Any]] = []
            with TestClient(app, raise_server_exceptions=False) as client:
                csrf_token: str | None = None
                if authenticated:
                    login = client.post(
                        "/api/auth/login",
                        json={
                            "email": "admin@ontology.local",
                            "password": "OntologyAdmin!2026",
                        },
                    )
                    if login.status_code != 200:
                        raise RuntimeError(
                            f"full-surface login failed: {login.status_code} {login.text}"
                        )
                    csrf_token = client.cookies.get(CSRF_COOKIE)

                # Logout is intentionally last so it cannot invalidate the probe.
                ordered = sorted(
                    operations,
                    key=lambda item: (
                        item.path == "/api/auth/logout",
                        item.method not in {"GET", "HEAD"},
                        item.path,
                    ),
                )
                for operation in ordered:
                    headers = (
                        {"X-CSRF-Token": csrf_token}
                        if authenticated and csrf_token
                        else {}
                    )
                    response = client.request(
                        operation.method,
                        _render_url(operation.path, schema, operation.method),
                        headers=headers,
                        json={"__contract_probe__": True}
                        if operation.method not in {"GET", "HEAD"}
                        else None,
                    )
                    statuses[response.status_code] += 1
                    item = {
                        "method": operation.method,
                        "path": operation.path,
                        "status": response.status_code,
                    }
                    if response.status_code == 503:
                        expected_unavailable.append(item)
                    elif response.status_code >= 500:
                        item["body"] = response.text[:500]
                        failures.append(item)
            return {
                "authenticated": authenticated,
                "operation_count": len(operations),
                "status_counts": {
                    str(key): value for key, value in sorted(statuses.items())
                },
                "unhandled_server_error_count": len(failures),
                "unhandled_server_errors": failures,
                "expected_503_count": len(expected_unavailable),
                "expected_503_operations": expected_unavailable,
            }
        finally:
            try:
                from ontology_dashboard import dependencies

                _clear_dependency_caches(dependencies)
            except ImportError:
                pass
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def build_full_surface_report() -> dict[str, Any]:
    from ontology_dashboard.main import app

    schema = app.openapi()
    summary = summarize_schema(schema)
    flask_probe = probe_flask_mirror(schema)
    unauthenticated_probe = probe_fastapi_surface(authenticated=False)
    authenticated_probe = probe_fastapi_surface(authenticated=True)
    operation_count = summary["operation_count"]
    return {
        "scope": {
            "application": "Ontology Dashboard MVP",
            "path_count": summary["path_count"],
            "operation_count": operation_count,
            "comparison_unit": "every OpenAPI path and HTTP operation",
        },
        "fastapi": {
            "real_business_application": True,
            "automatic_openapi_operation_count": operation_count,
            "automatic_request_validation_operation_count": sum(
                bool(
                    operation["has_request_body"]
                    or operation["path_parameter_count"]
                    or operation["query_parameter_count"]
                )
                for operation in summary["operations"]
            ),
            "automatic_response_schema_operation_count": summary[
                "response_schema_operation_count"
            ],
            "unauthenticated_probe": unauthenticated_probe,
            "authenticated_probe": authenticated_probe,
        },
        "flask": {
            "real_business_application": False,
            "comparison_mode": "generated bare-Flask route mirror",
            **flask_probe,
            "manual_port_required_operation_count": operation_count,
        },
        "schema_summary": summary,
        "conclusion": {
            "selected_framework": "FastAPI",
            "reason": (
                "The selection now covers the full 162-path/172-operation MVP surface. "
                "FastAPI already executes the real handlers and generates the request, "
                "response and OpenAPI contracts. Bare Flask can mirror all routes, but "
                "the 172 business handlers plus validation and documentation contracts "
                "would still require an explicit port."
            ),
            "limitation": (
                "The Flask mirror is a routing and migration-effort comparison, not a "
                "claim that the full Ontology Dashboard business implementation exists "
                "twice."
            ),
        },
    }


def write_full_surface_report(path: Path) -> dict[str, Any]:
    report = build_full_surface_report()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _has_response_schema(operation: dict[str, Any]) -> bool:
    for response in operation.get("responses", {}).values():
        for content in response.get("content", {}).values():
            if content.get("schema"):
                return True
    return False


def _placeholder_value(name: str, schema: dict[str, Any]) -> str:
    if name in KNOWN_PATH_VALUES:
        return KNOWN_PATH_VALUES[name]
    if schema.get("enum"):
        return str(schema["enum"][0])
    if schema.get("format") == "uuid":
        return "00000000-0000-4000-8000-000000000001"
    if schema.get("type") in {"integer", "number"}:
        return "1"
    if schema.get("type") == "boolean":
        return "true"
    return "contract-probe"


def _render_url(path: str, schema: dict[str, Any], method: str) -> str:
    operation = schema["paths"][path][method.lower()]
    path_parameters = {
        parameter["name"]: _placeholder_value(
            parameter["name"], parameter.get("schema", {})
        )
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "path"
    }
    return re.sub(
        r"\{([^}]+)\}",
        lambda match: path_parameters.get(match.group(1), "contract-probe"),
        path,
    )


def operation_keys(operations: Iterable[OperationContract]) -> set[tuple[str, str]]:
    return {(operation.method, operation.path) for operation in operations}


def _clear_dependency_caches(module: Any) -> None:
    for name in dir(module):
        candidate = getattr(module, name)
        cache_clear = getattr(candidate, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

