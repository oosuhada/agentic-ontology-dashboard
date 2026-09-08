"""Refresh the latest approved ontology materialization for graph delivery."""

from __future__ import annotations

import json
import os

from app.infra.db.predictive_maintenance_ontology_projection import (
    DEFAULT_MAPPING_VERSION,
    PredictiveMaintenanceOntologyMaterializer,
)


def _latest_scope(database_url: str, organization_id: str, project_id: str) -> dict[str, str] | None:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("projection refresh requires the postgres extra") from exc
    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.organization_id',%s,true)", (organization_id,))
        connection.execute("SELECT set_config('app.project_id',%s,true)", (project_id,))
        row = connection.execute(
            """
            SELECT m.dataset_id,m.dataset_version_id,m.workspace_id
            FROM ontology_materialization_mappings m
            JOIN store_projections p
              ON p.dataset_version_id=m.dataset_version_id AND p.store_kind='relational'
            WHERE m.organization_id=%s AND m.project_id=%s AND m.status='approved'
              AND p.status='ready'
            ORDER BY m.approved_at DESC NULLS LAST,m.updated_at DESC,m.dataset_version_id DESC
            LIMIT 1
            """,
            (organization_id, project_id),
        ).fetchone()
    return None if row is None else {key: str(row[key]) for key in row.keys()}


def main() -> int:
    database_url = os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("ONTOLOGY_DASHBOARD_DATABASE_URL is required")
    organization_id = os.getenv("ONTOLOGY_DASHBOARD_GRAPH_ORGANIZATION_ID", "org-ontology-demo").strip()
    project_id = os.getenv("ONTOLOGY_DASHBOARD_GRAPH_PROJECT_ID", "manufacturing-demo-project").strip()
    scope = _latest_scope(database_url, organization_id, project_id)
    if scope is None:
        print(json.dumps({"status": "skipped", "reason": "no approved ontology materialization"}))
        return 0
    materializer = PredictiveMaintenanceOntologyMaterializer(database_url)
    materializer.ensure_default_mapping(
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=scope["workspace_id"],
        dataset_id=scope["dataset_id"],
        dataset_version_id=scope["dataset_version_id"],
        approve=True,
        approved_by="graph-projection-v3.2-deployment",
    )
    result = materializer.materialize(
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=scope["workspace_id"],
        dataset_id=scope["dataset_id"],
        dataset_version_id=scope["dataset_version_id"],
        mapping_version=DEFAULT_MAPPING_VERSION,
    )
    print(json.dumps({
        "status": "completed",
        "dataset_version_id": result.dataset_version_id,
        "object_count": result.object_count,
        "link_count": result.link_count,
        "outbox_event_id": result.outbox_event_id,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
