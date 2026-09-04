from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from systems.backend.app.main import app as canonical_app


HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _openapi_route_surface(app: FastAPI) -> list[tuple[str, str]]:
    schema = app.openapi()
    return sorted(
        (path, method.lower())
        for path, operations in schema.get("paths", {}).items()
        for method in operations
        if method.lower() in HTTP_METHODS
    )


def test_canonical_entrypoint_exposes_required_route_surface() -> None:
    canonical_surface = _openapi_route_surface(canonical_app)

    assert canonical_surface
    assert ("/health", "get") in canonical_surface
    assert ("/api/projects", "get") in canonical_surface
    assert ("/api/events", "get") in canonical_surface
    assert (
        "/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/dashboard",
        "get",
    ) in canonical_surface


def test_legacy_backend_package_is_physically_absent() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "systems/backend/ontology_dashboard").exists()
