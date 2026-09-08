"""Continuously deliver versioned ontology materializations to Project 3."""

from __future__ import annotations

import os
import json

from app.infra.external.project3 import (
    PredictiveMaintenanceProject3ProjectionHandler,
    Project3Client,
)
from app.infra.messaging.outbox import OutboxMessage, ProjectOutboxRepository, ProjectOutboxWorker


def _latest_materialization_message(
    database_url: str,
    *,
    organization_id: str,
    project_id: str,
) -> OutboxMessage | None:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - production extra guard
        raise RuntimeError("graph projection worker requires the postgres extra") from exc
    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.organization_id',%s,true)", (organization_id,))
        connection.execute("SELECT set_config('app.project_id',%s,true)", (project_id,))
        row = connection.execute(
            """
            SELECT * FROM transactional_outbox
            WHERE organization_id=%s AND project_id=%s
              AND event_type='ontology.materialization.completed'
            ORDER BY created_at DESC,id DESC LIMIT 1
            """,
            (organization_id, project_id),
        ).fetchone()
    if row is None:
        return None
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return OutboxMessage(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        workspace_id=None if row["workspace_id"] is None else str(row["workspace_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        event_type=str(row["event_type"]),
        payload=dict(payload),
        attempt_count=int(row["attempt_count"]),
        lease_token="graph-bootstrap-on-start",
    )


def main() -> int:
    database_url = os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("ONTOLOGY_DASHBOARD_DATABASE_URL is required")
    organization_id = os.getenv("ONTOLOGY_DASHBOARD_GRAPH_ORGANIZATION_ID", "org-ontology-demo").strip()
    project_id = os.getenv("ONTOLOGY_DASHBOARD_GRAPH_PROJECT_ID", "manufacturing-demo-project").strip()
    project3_url = os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_URL", "http://project3:8000").strip()
    client = Project3Client(
        base_url=project3_url,
        project_mapping={},
        timeout_seconds=float(os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_TIMEOUT_SECONDS", "4")),
        max_retries=int(os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_MAX_RETRIES", "1")),
    )
    handler = PredictiveMaintenanceProject3ProjectionHandler(database_url, client)
    worker = ProjectOutboxWorker(
        ProjectOutboxRepository(database_url),
        organization_id=organization_id,
        project_id=project_id,
        handlers={handler.event_type: (handler.handler_code, handler.deliver)},
        max_attempts=5,
        retry_delay_seconds=10,
        lease_seconds=120,
    )
    try:
        if os.getenv("ONTOLOGY_DASHBOARD_GRAPH_BOOTSTRAP_ON_START", "1").strip().lower() not in {"0", "false", "no"}:
            message = _latest_materialization_message(
                database_url,
                organization_id=organization_id,
                project_id=project_id,
            )
            if message is not None:
                handler.deliver(message)
        worker.run_forever(
            poll_seconds=float(os.getenv("ONTOLOGY_DASHBOARD_GRAPH_PROJECTION_POLL_SECONDS", "5"))
        )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
