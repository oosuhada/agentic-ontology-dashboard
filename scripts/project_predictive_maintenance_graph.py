#!/usr/bin/env python3
"""Deliver one materialized predictive-maintenance Dataset Version to Project 3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ontology_dashboard.integrations.project3 import (
    PredictiveMaintenanceProject3ProjectionHandler,
    Project3Client,
)
from ontology_dashboard.outbox import OutboxMessage, OutboxRepository


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("graph projection CLI requires api[postgres]") from exc
    return psycopg, dict_row


def _message(
    *,
    database_url: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str,
) -> OutboxMessage:
    psycopg, dict_row = _require_psycopg()
    normalized = database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(normalized, row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT set_config('app.organization_id',%s,true)",
                (organization_id,),
            )
            connection.execute(
                "SELECT set_config('app.project_id',%s,true)",
                (project_id,),
            )
            row = connection.execute(
                """
                SELECT * FROM transactional_outbox
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                  AND aggregate_id=%s
                  AND event_type='ontology.materialization.completed'
                ORDER BY created_at DESC LIMIT 1
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_version_id,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    "ontology.materialization.completed outbox event was not found"
                )
            connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processing',attempt_count=attempt_count+1,
                    last_error=NULL
                WHERE id=%s
                """,
                (row["id"],),
            )
            attempt_count = int(row["attempt_count"]) + 1
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return OutboxMessage(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        workspace_id=str(row["workspace_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        event_type=str(row["event_type"]),
        payload=dict(payload),
        attempt_count=attempt_count,
    )


def _projection_row(database_url: str, dataset_version_id: str) -> dict:
    psycopg, dict_row = _require_psycopg()
    normalized = database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(normalized, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT status,record_count,attempt_count,last_error,
                   provider_run_id,provider_metadata_json,
                   started_at,completed_at,updated_at
            FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='graph'
            """,
            (dataset_version_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("graph Store Projection was not found")
    return dict(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--project3-url", default="http://127.0.0.1:8001")
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    message = _message(
        database_url=args.database_url,
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        dataset_version_id=args.dataset_version_id,
    )
    repository = OutboxRepository(args.database_url)
    client = Project3Client(base_url=args.project3_url)
    handler = PredictiveMaintenanceProject3ProjectionHandler(
        args.database_url,
        client,
    )
    try:
        response = handler.deliver(message)
        repository.mark_delivered(
            message,
            handler_code=handler.handler_code,
        )
    except Exception as error:
        repository.mark_failed(
            message,
            error=f"{type(error).__name__}: {error}",
            max_attempts=5,
            retry_delay_seconds=30,
            retryable=bool(getattr(error, "retryable", True)),
        )
        raise
    finally:
        client.close()

    payload = {
        "response": response.model_dump(mode="json"),
        "graph_projection": _projection_row(
            args.database_url,
            args.dataset_version_id,
        ),
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
