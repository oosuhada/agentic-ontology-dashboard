"""Persistence adapter for project-scoped company/operational context records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infra.db.postgresql_compat import PostgreSQLProjectContextResolver, postgres_repository_connection
from app.infra.db.postgresql_repositories import is_postgresql


CONTEXT_RECORD_TYPES = (
    "organization_units",
    "plants",
    "assets",
    "products",
    "materials",
    "vendors",
    "business_metrics",
    "kpi_snapshots",
    "financial_periods",
    "maintenance_records",
    "meeting_minutes",
    "decisions",
    "documents",
    "production_orders",
    "quality_incidents",
    "purchase_orders",
    "capa_records",
    "shift_handoffs",
    "calibration_records",
    "safety_events",
)


class CompanyContextRepository:
    def __init__(self, database_target: str | Path) -> None:
        self.target = str(database_target)
        self._postgres = is_postgresql(self.target)
        self._resolver = PostgreSQLProjectContextResolver(self.target) if self._postgres else None

    def _connect(self, *, project_id: str | None = None, workspace_id: str | None = None):
        if self._postgres:
            organization_id = None
            if project_id and self._resolver:
                organization_id, _ = self._resolver.resolve_project(project_id)
            return postgres_repository_connection(
                self.target,
                organization_id=organization_id,
                project_id=project_id,
                resolver=self._resolver,
            )
        path = Path(self.target)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    def list_records(self, *, project_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect(project_id=project_id, workspace_id=workspace_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope") and self._resolver:
                context = self._resolver.resolve(workspace_id, expected_project_id=project_id, connection=connection)
                organization_id = context.organization_id
            else:
                organization_id = "org-ontology-demo"
            rows = connection.execute(
                """
                SELECT record_id,record_type,record_key,payload_json,source_ref,source_updated_at
                FROM company_context_records
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                ORDER BY record_type,record_key
                """,
                (organization_id, project_id, workspace_id),
            ).fetchall()
        return [
            {
                "record_id": str(row["record_id"]),
                "record_type": str(row["record_type"]),
                "record_key": str(row["record_key"]),
                "payload": json.loads(str(row["payload_json"])),
                "source_ref": str(row["source_ref"]),
                "source_updated_at": str(row["source_updated_at"]),
            }
            for row in rows
        ]

    def seed_records(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        context: dict[str, Any],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with self._connect(project_id=project_id, workspace_id=workspace_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            for record_type in CONTEXT_RECORD_TYPES:
                for item in context.get(record_type) or []:
                    if not isinstance(item, dict):
                        continue
                    record_key = str(item.get("id") or item.get("variant") or item.get("name") or uuid.uuid4())
                    record_id = f"company-context:{project_id}:{workspace_id}:{record_type}:{record_key}"
                    source_ref = str(item.get("source_ref") or record_id)
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO company_context_records(
                            record_id,organization_id,project_id,workspace_id,record_type,record_key,
                            payload_json,source_ref,source_updated_at,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            record_id,
                            organization_id,
                            project_id,
                            workspace_id,
                            record_type,
                            record_key,
                            json.dumps(item, ensure_ascii=False, sort_keys=True),
                            source_ref,
                            now,
                            now,
                            now,
                        ),
                    )
                    inserted += max(0, int(getattr(cursor, "rowcount", 0)))
        return inserted


__all__ = ["CompanyContextRepository", "CONTEXT_RECORD_TYPES"]
