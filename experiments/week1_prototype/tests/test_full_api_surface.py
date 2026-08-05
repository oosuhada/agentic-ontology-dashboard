from __future__ import annotations

from ontology_dashboard.main import app as product_app

from framework_comparison.full_surface import (
    build_full_surface_report,
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
    assert summary["json_success_schema_operation_count"] == 168
    assert summary["field_level_json_success_schema_operation_count"] == 167
    assert summary["non_json_success_schema_operation_count"] == 2
    assert summary["no_content_success_operation_count"] == 2
    assert summary["success_contract_operation_count"] == 172
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


def test_weighted_selection_uses_three_symmetric_feature_benchmarks() -> None:
    report = build_full_surface_report()
    evaluation = report["conclusion"]["evaluation"]
    by_id = {item["id"]: item for item in evaluation["criteria"]}

    assert evaluation["totals"] == {"fastapi": 99.55, "flask": 69.6}
    assert by_id["representative_performance"]["flask_score"] == 4.92
    assert by_id["representative_performance"]["fastapi_score"] == 4.91
    assert by_id["development_productivity"]["weight"] == 25
    assert by_id["development_productivity"]["flask_score"] == 3
    representative = report["representative_features"]
    assert representative["feature_count"] == 3
    assert representative["parity"]["all_feature_responses_equal"] is True
    assert representative["validation"]["all_statuses_match"] is True
    assert representative["implementation"]["fastapi_adapter_loc"] == 50
    assert representative["implementation"]["flask_adapter_loc"] == 80
    assert report["conclusion"]["framework_summaries"]["fastapi"]["disadvantages"]
    assert report["conclusion"]["framework_summaries"]["flask"]["advantages"]

