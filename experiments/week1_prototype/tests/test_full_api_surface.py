from __future__ import annotations

from ontology_dashboard.main import app as product_app

from framework_comparison.full_surface import (
    build_flask_contract_mirror,
    collect_operations,
    operation_keys,
    probe_fastapi_surface,
    probe_flask_mirror,
    summarize_schema,
)


def test_full_product_surface_is_inventoried() -> None:
    schema = product_app.openapi()
    summary = summarize_schema(schema)

    assert summary["path_count"] == 162
    assert summary["operation_count"] == 172
    assert summary["response_schema_operation_count"] > 0
    assert summary["request_body_operation_count"] > 0


def test_flask_contract_mirror_registers_every_fastapi_operation() -> None:
    schema = product_app.openapi()
    expected = operation_keys(collect_operations(schema))
    flask_app = build_flask_contract_mirror(schema)
    actual = {
        (method, rule.rule)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint != "static"
        for method in rule.methods
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        and method in {item[0] for item in expected}
    }

    # Flask syntax differs for path parameters, so operation count and runtime
    # probe provide the stable parity assertion.
    assert len(actual) >= len(expected)
    mirror = probe_flask_mirror(schema)
    assert mirror["registered_operation_count"] == 172
    assert mirror["failure_count"] == 0


def test_every_fastapi_operation_reaches_auth_or_validation_without_500() -> None:
    report = probe_fastapi_surface(authenticated=False)

    assert report["operation_count"] == 172
    assert report["unhandled_server_error_count"] == 0
    assert sum(report["status_counts"].values()) == 172


def test_every_fastapi_operation_is_probed_with_authenticated_admin() -> None:
    report = probe_fastapi_surface(authenticated=True)

    assert report["operation_count"] == 172
    assert report["unhandled_server_error_count"] == 0
    assert sum(report["status_counts"].values()) == 172
    # PostgreSQL-only predictive-maintenance runtime routes are expected to
    # report explicit unavailability in the isolated SQLite probe.
    assert report["expected_503_count"] == 10

