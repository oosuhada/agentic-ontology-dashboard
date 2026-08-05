from __future__ import annotations

from fastapi.routing import APIRoute

from ontology_dashboard.main import app


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
SUCCESS_CODES = ("200", "201", "202")


def _json_success_schemas() -> list[tuple[str, str, dict]]:
    schemas: list[tuple[str, str, dict]] = []
    for path, path_item in app.openapi()["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            for code in SUCCESS_CODES:
                response = operation.get("responses", {}).get(code)
                if not response:
                    continue
                media = (response.get("content") or {}).get("application/json")
                if media is not None:
                    schemas.append((method.upper(), path, media.get("schema")))
                break
    return schemas


def _walk_routes():
    for route in app.router.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            yield route
            continue
        yield from original_router.routes


def test_public_openapi_has_no_empty_json_success_schema() -> None:
    schemas = _json_success_schemas()

    assert schemas
    assert all(schema not in (None, {}) for _, _, schema in schemas)
    assert not [
        (method, path)
        for method, path, schema in schemas
        if schema.get("type") == "string"
    ]


def test_every_json_route_has_runtime_response_validation() -> None:
    excluded = {
        "logout",
        "delete_dashboard_saved_view",
        "create_export",
        "replay_events",
    }
    missing = []
    for route in _walk_routes():
        if not isinstance(route, APIRoute) or route.name in excluded:
            continue
        if route.path.startswith(("/api", "/health")) and route.response_model is None:
            missing.append((route.methods, route.path, route.name))

    assert missing == []


def test_representative_schemas_expose_real_fields() -> None:
    spec = app.openapi()

    me_schema = spec["paths"]["/api/auth/me"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    projects_schema = spec["paths"]["/api/projects"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    modeling_schema = spec["paths"]["/api/modeling/contracts"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]

    assert me_schema["$ref"].endswith("/CurrentUserResponse")
    assert projects_schema["$ref"].endswith("/ProjectListResponse")
    assert modeling_schema["$ref"].endswith("/ModelingContractsResponse")

    components = spec["components"]["schemas"]
    assert {"user", "csrf_token"} <= set(components["CurrentUserResponse"]["properties"])
    assert "items" in components["ProjectListResponse"]["properties"]
    project_item = components["ProjectListResponse"]["properties"]["items"]["items"]
    assert project_item["$ref"].endswith("/Project")
    assert {"id", "display_name", "status", "default_workspace_id"} <= set(
        components["Project"]["properties"]
    )
    assert {
        "contracts",
        "artifact_store",
        "artifact_capability",
        "organization_id",
        "project_id",
        "workspace_id",
    } <= set(components["ModelingContractsResponse"]["properties"])


def test_stream_and_binary_responses_are_not_documented_as_json_strings() -> None:
    spec = app.openapi()
    export_content = spec["paths"]["/api/exports"]["post"]["responses"]["200"][
        "content"
    ]
    stream_content = spec["paths"][
        "/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/replay/sessions/{session_id}/events"
    ]["get"]["responses"]["200"]["content"]

    assert "application/json" not in export_content
    assert export_content["application/octet-stream"]["schema"]["format"] == "binary"
    assert "application/json" not in stream_content
    assert "text/event-stream" in stream_content
