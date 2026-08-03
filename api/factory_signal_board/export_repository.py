from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_dashboard.project_context import SQLiteProjectContextResolver, ensure_scope_columns


class ExportRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_context = SQLiteProjectContextResolver(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS export_checkpoints (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    format TEXT NOT NULL,
                    event_id TEXT,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content_bytes INTEGER NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_by_name TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_export_checkpoint_owner
                    ON export_checkpoints(requested_by, created_at);
                CREATE INDEX IF NOT EXISTS idx_export_checkpoint_workspace
                    ON export_checkpoints(organization_id,project_id,workspace_id,created_at);
                """
            )
            ensure_scope_columns(connection, table="export_checkpoints")

    def create_checkpoint(
        self,
        *,
        workspace_id: str,
        scope: str,
        export_format: str,
        event_id: str | None,
        filename: str,
        media_type: str,
        content_bytes: int,
        snapshot_hash: str,
        content_hash: str,
        requested_by: str,
        requested_by_name: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        checkpoint_id = str(uuid.uuid4())
        created_at = self._now()
        with self._connect() as connection:
            project_context = self.project_context.resolve(workspace_id, connection=connection)
            connection.execute(
                """
                INSERT INTO export_checkpoints (
                    id,organization_id,project_id,workspace_id,scope,format,event_id,
                    filename,media_type,content_bytes,snapshot_hash,content_hash,
                    requested_by,requested_by_name,snapshot_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    checkpoint_id,
                    project_context.organization_id,
                    project_context.project_id,
                    workspace_id,
                    scope,
                    export_format,
                    event_id,
                    filename,
                    media_type,
                    content_bytes,
                    snapshot_hash,
                    content_hash,
                    requested_by,
                    requested_by_name,
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    created_at,
                ),
            )
        return {
            "id": checkpoint_id,
            "organization_id": project_context.organization_id,
            "project_id": project_context.project_id,
            "workspace_id": workspace_id,
            "scope": scope,
            "format": export_format,
            "event_id": event_id,
            "filename": filename,
            "media_type": media_type,
            "content_bytes": content_bytes,
            "snapshot_hash": snapshot_hash,
            "content_hash": content_hash,
            "requested_by": requested_by,
            "requested_by_name": requested_by_name,
            "created_at": created_at,
        }

    def list_checkpoints(
        self,
        *,
        requested_by: str | None = None,
        workspace_id: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        with self._connect() as connection:
            if workspace_id is not None:
                scope = self.project_context.resolve(workspace_id, connection=connection)
                clauses.extend(["organization_id=?", "project_id=?", "workspace_id=?"])
                params.extend([scope.organization_id, scope.project_id, workspace_id])
            else:
                if organization_id is not None:
                    clauses.append("organization_id=?")
                    params.append(organization_id)
                if project_id is not None:
                    clauses.append("project_id=?")
                    params.append(project_id)
            if requested_by is not None:
                clauses.append("requested_by=?")
                params.append(requested_by)
            query = (
                "SELECT id,organization_id,project_id,workspace_id,scope,format,event_id,"
                "filename,media_type,content_bytes,snapshot_hash,content_hash,requested_by,"
                "requested_by_name,created_at FROM export_checkpoints"
            )
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]
