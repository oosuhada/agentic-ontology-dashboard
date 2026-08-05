"""Generated Object Views, permission-filtered search and safe metadata runtime."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)
    allowed_types: tuple[str, ...] = ()
    eligible_markings: tuple[str, ...] = ()


class ApplicationRuntimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    object_views: tuple[dict[str, Any], ...]
    search_index: tuple[dict[str, Any], ...]
    application: dict[str, Any]
    component_catalog: tuple[dict[str, Any], ...]
    renderer_registry: dict[str, str]
    safety: dict[str, str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApplicationRuntimeRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def _connection(self, organization_id: str, project_id: str):
        if self.postgresql:
            return postgres_repository_connection(self.database, organization_id=organization_id, project_id=project_id)
        repository = self
        class Context:
            def __enter__(self):
                self.connection = sqlite3.connect(repository.database)
                self.connection.row_factory = sqlite3.Row
                return self.connection
            def __exit__(self, exc_type, exc, tb):
                if exc_type is None: self.connection.commit()
                else: self.connection.rollback()
                self.connection.close()
        return Context()

    def ensure_samples(self, organization_id: str, project_id: str) -> None:
        now = _now()
        views = (
            ("view-equipment-standard", "equipment", "asset", "full", {
                "title_property": "name", "status_property": "status",
                "sections": ["summary", "properties", "links", "actions", "activity", "lineage"],
                "property_order": ["id", "name", "status", "failure_probability"],
            }),
            ("view-compressor-panel", "compressor", "asset", "panel", {
                "title_property": "name", "status_property": "status",
                "sections": ["summary", "properties", "actions"],
                "property_order": ["id", "name", "risk_score"],
            }),
        )
        app = {
            "id": "commercial-v4-operations", "version": 1,
            "pages": [{"id": "objects", "layout": "two-column", "components": [
                {"type": "object-set-table", "version": 1, "input": "assetSet"},
                {"type": "object-view", "version": 1, "input": "selectedAsset"},
            ]}],
            "variables": {
                "assetSet": {"kind": "interface_query", "interface": "asset"},
                "selectedAsset": {"kind": "selection", "source": "assetSet"},
            },
            "events": [{"source": "assetSet.selection", "target": "selectedAsset", "action": "set"}],
        }
        with self._connection(organization_id, project_id) as connection:
            for view_id, object_type, interface, form_factor, definition in views:
                connection.execute(
                    """INSERT INTO object_view_definitions(
                    id,organization_id,project_id,object_type_id,interface_id,form_factor,status,
                    branch_id,definition_json,created_at) VALUES (?,?,?,?,?,?,'published','branch-main',?,?)
                    ON CONFLICT(organization_id,project_id,object_type_id,form_factor,branch_id) DO NOTHING""",
                    (view_id, organization_id, project_id, object_type, interface, form_factor, json.dumps(definition), now),
                )
            connection.execute(
                """INSERT INTO application_runtime_definitions(
                id,version,organization_id,project_id,status,branch_id,definition_json,created_at
                ) VALUES ('commercial-v4-operations',1,?,?,'published','branch-main',?,?)
                ON CONFLICT(organization_id,project_id,id,version,branch_id) DO NOTHING""",
                (organization_id, project_id, json.dumps(app), now),
            )

    def snapshot(self, organization_id: str, project_id: str) -> ApplicationRuntimeSnapshot:
        with self._connection(organization_id, project_id) as connection:
            views = connection.execute(
                "SELECT * FROM object_view_definitions WHERE organization_id=? AND project_id=? ORDER BY object_type_id,form_factor",
                (organization_id, project_id),
            ).fetchall()
            app = connection.execute(
                "SELECT definition_json FROM application_runtime_definitions WHERE organization_id=? AND project_id=? AND id='commercial-v4-operations' ORDER BY version DESC LIMIT 1",
                (organization_id, project_id),
            ).fetchone()
        normalized_views = tuple({
            "id": row["id"], "object_type_id": row["object_type_id"], "interface_id": row["interface_id"],
            "form_factor": row["form_factor"], "status": row["status"],
            "definition": row["definition_json"] if isinstance(row["definition_json"], dict) else json.loads(row["definition_json"]),
        } for row in views)
        search_index = (
            {"type": "object", "id": "equipment:M-001", "title": "CNC Machine M-001", "subtitle": "High risk equipment", "markings": ["confidential"]},
            {"type": "object", "id": "compressor:C-01", "title": "Compressor C-01", "subtitle": "Fleet asset", "markings": []},
            {"type": "dataset", "id": "canonical-v3.1", "title": "Canonical V3.1", "subtitle": "Predictive maintenance Dataset", "markings": ["confidential", "export_restricted"]},
            {"type": "function", "id": "asset-risk-metric", "title": "Asset risk metric", "subtitle": "Governed function", "markings": []},
            {"type": "action", "id": "request-asset-inspection", "title": "Request asset inspection", "subtitle": "Approval-required Action", "markings": []},
            {"type": "application", "id": "commercial-v4", "title": "Ontology Platform · Commercial V4", "subtitle": "Metadata-driven application", "markings": []},
        )
        application = app["definition_json"] if isinstance(app["definition_json"], dict) else json.loads(app["definition_json"])
        return ApplicationRuntimeSnapshot(
            object_views=normalized_views,
            search_index=search_index,
            application=application,
            component_catalog=(
                {"type": "object-set-table", "version": 1, "a11y": "grid keyboard navigation"},
                {"type": "object-view", "version": 1, "a11y": "landmarked sections"},
                {"type": "metric", "version": 1, "a11y": "text alternative required"},
                {"type": "lineage", "version": 1, "a11y": "list fallback required"},
                {"type": "action-form", "version": 1, "a11y": "label and error association"},
            ),
            renderer_registry={
                "string": "text", "number": "localized-number", "unit": "value-with-unit",
                "date": "iso-date", "enum": "status-pill", "boolean": "yes-no",
                "time_series": "chart-with-table", "geospatial": "map-with-list",
                "artifact": "governed-link", "object_reference": "object-link",
                "marked": "masked-value", "unknown": "safe-json-fallback",
            },
            safety={
                "components": "catalog whitelist only", "expressions": "typed variables; no JavaScript",
                "fallback": "standard Object View when configured view is absent",
                "search": "permission and marking pre-filter before result delivery",
            },
        )

    def search(self, organization_id: str, project_id: str, request: SearchRequest) -> tuple[dict[str, Any], ...]:
        snapshot = self.snapshot(organization_id, project_id)
        query = request.query.casefold()
        allowed = set(request.allowed_types)
        eligible = set(request.eligible_markings)
        results = []
        for item in snapshot.search_index:
            if allowed and item["type"] not in allowed:
                continue
            if set(item["markings"]) - eligible:
                continue
            haystack = f"{item['title']} {item['subtitle']} {item['id']}".casefold()
            if query not in haystack:
                continue
            score = 100 if item["title"].casefold() == query else 80 if item["title"].casefold().startswith(query) else 50
            results.append({**item, "score": score, "explanation": "exact/prefix/full-text deterministic ranking"})
        return tuple(sorted(results, key=lambda item: (-item["score"], item["title"])))


__all__ = ["ApplicationRuntimeRepository", "ApplicationRuntimeSnapshot", "SearchRequest"]
