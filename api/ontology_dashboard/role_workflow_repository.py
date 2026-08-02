from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_dashboard.project_context import SQLiteProjectContextResolver, ensure_scope_columns


_WORKFLOW_TABLES = {"template_publish_requests", "model_release_requests"}


class RoleWorkflowRepository:
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

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(value: str) -> Any:
        return json.loads(value)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_export_checkpoints (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    export_format TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_by_name TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_export_event
                    ON audit_export_checkpoints(organization_id,project_id,workspace_id,event_id,created_at);

                CREATE TABLE IF NOT EXISTS field_task_actions (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    actor_display_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_field_task_event
                    ON field_task_actions(organization_id,project_id,workspace_id,event_id,created_at);

                CREATE TABLE IF NOT EXISTS template_publish_requests (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    target_role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_by_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_by TEXT,
                    decision_by_name TEXT,
                    decision_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_template_publish_status
                    ON template_publish_requests(organization_id,project_id,workspace_id,status,created_at);

                CREATE TABLE IF NOT EXISTS model_release_requests (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_by_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_by TEXT,
                    decision_by_name TEXT,
                    decision_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_release_status
                    ON model_release_requests(organization_id,project_id,workspace_id,status,created_at);
                """
            )
            for table in (
                "audit_export_checkpoints",
                "field_task_actions",
                "template_publish_requests",
                "model_release_requests",
                "transactional_outbox",
            ):
                ensure_scope_columns(connection, table=table)

    def create_export_checkpoint(
        self,
        *,
        workspace_id: str,
        event_id: str,
        export_format: str,
        reason: str,
        requested_by: str,
        requested_by_name: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = self._now()
        checkpoint_id = str(uuid.uuid4())
        snapshot_json = self._json(snapshot)
        content_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            connection.execute(
                """
                INSERT INTO audit_export_checkpoints (
                    id,organization_id,project_id,workspace_id,event_id,export_format,
                    reason,content_hash,requested_by,requested_by_name,snapshot_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    checkpoint_id,
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    event_id,
                    export_format,
                    reason,
                    content_hash,
                    requested_by,
                    requested_by_name,
                    snapshot_json,
                    created_at,
                ),
            )
        return {
            "id": checkpoint_id,
            "organization_id": scope.organization_id,
            "project_id": scope.project_id,
            "workspace_id": workspace_id,
            "event_id": event_id,
            "export_format": export_format,
            "reason": reason,
            "content_hash": content_hash,
            "requested_by": requested_by,
            "requested_by_name": requested_by_name,
            "created_at": created_at,
        }

    def list_export_checkpoints(self, *, workspace_id: str, event_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            rows = connection.execute(
                """
                SELECT id,organization_id,project_id,workspace_id,event_id,export_format,
                       reason,content_hash,requested_by,requested_by_name,created_at
                FROM audit_export_checkpoints
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND event_id=?
                ORDER BY created_at DESC
                """,
                (scope.organization_id, scope.project_id, workspace_id, event_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_field_action(
        self,
        *,
        workspace_id: str,
        event_id: str,
        action: str,
        actor_user_id: str,
        actor_display_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status_by_action = {
            "complete": "completed",
            "issue_found": "issue_found",
            "blocked": "blocked",
        }
        status = status_by_action[action]
        record_id = str(uuid.uuid4())
        created_at = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = self.project_context.resolve(workspace_id, connection=connection)
            connection.execute(
                """
                INSERT INTO field_task_actions (
                    id,organization_id,project_id,workspace_id,event_id,action,status,
                    actor_user_id,actor_display_name,payload_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record_id,
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    event_id,
                    action,
                    status,
                    actor_user_id,
                    actor_display_name,
                    self._json(payload),
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO transactional_outbox (
                    id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                    event_type,payload_json,status,attempt_count,created_at,available_at
                ) VALUES (?,?,?,?,?,?,?,?,'pending',0,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    "field_task",
                    event_id,
                    f"field_task.{action}",
                    self._json(payload),
                    created_at,
                    created_at,
                ),
            )
        return {
            "id": record_id,
            "organization_id": scope.organization_id,
            "project_id": scope.project_id,
            "workspace_id": workspace_id,
            "event_id": event_id,
            "action": action,
            "status": status,
            "actor_user_id": actor_user_id,
            "actor_display_name": actor_display_name,
            "payload": payload,
            "created_at": created_at,
        }

    def list_field_actions(self, *, workspace_id: str, event_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            query = (
                "SELECT * FROM field_task_actions "
                "WHERE organization_id=? AND project_id=? AND workspace_id=?"
            )
            params: list[Any] = [scope.organization_id, scope.project_id, workspace_id]
            if event_id is not None:
                query += " AND event_id=?"
                params.append(event_id)
            query += " ORDER BY created_at"
            rows = connection.execute(query, params).fetchall()
        return [
            {
                **dict(row),
                "payload": self._decode(row["payload_json"]),
            }
            for row in rows
        ]

    def latest_field_statuses(self, *, workspace_id: str) -> dict[str, dict[str, Any]]:
        records = self.list_field_actions(workspace_id=workspace_id)
        latest: dict[str, dict[str, Any]] = {}
        for record in records:
            latest[record["event_id"]] = record
        return latest

    def _create_workflow_request(
        self,
        *,
        table: str,
        workspace_id: str,
        requested_by: str,
        requested_by_name: str,
        payload: dict[str, Any],
        target_role: str | None = None,
    ) -> dict[str, Any]:
        if table not in _WORKFLOW_TABLES:
            raise ValueError("unsupported workflow table")
        request_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            if table == "template_publish_requests":
                connection.execute(
                    """
                    INSERT INTO template_publish_requests (
                        id,organization_id,project_id,workspace_id,target_role,status,
                        requested_by,requested_by_name,payload_json,decision_by,
                        decision_by_name,decision_note,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)
                    """,
                    (
                        request_id,
                        scope.organization_id,
                        scope.project_id,
                        workspace_id,
                        target_role,
                        "pending_approval",
                        requested_by,
                        requested_by_name,
                        self._json(payload),
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO model_release_requests (
                        id,organization_id,project_id,workspace_id,status,requested_by,
                        requested_by_name,payload_json,decision_by,decision_by_name,
                        decision_note,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)
                    """,
                    (
                        request_id,
                        scope.organization_id,
                        scope.project_id,
                        workspace_id,
                        "pending_approval",
                        requested_by,
                        requested_by_name,
                        self._json(payload),
                        now,
                        now,
                    ),
                )
        return self.get_workflow_request(
            table=table,
            request_id=request_id,
            project_id=scope.project_id,
        )

    def create_template_publish_request(
        self,
        *,
        workspace_id: str,
        target_role: str,
        requested_by: str,
        requested_by_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._create_workflow_request(
            table="template_publish_requests",
            workspace_id=workspace_id,
            target_role=target_role,
            requested_by=requested_by,
            requested_by_name=requested_by_name,
            payload=payload,
        )

    def create_model_release_request(
        self,
        *,
        workspace_id: str,
        requested_by: str,
        requested_by_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._create_workflow_request(
            table="model_release_requests",
            workspace_id=workspace_id,
            requested_by=requested_by,
            requested_by_name=requested_by_name,
            payload=payload,
        )

    def get_workflow_request(
        self,
        *,
        table: str,
        request_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        if table not in _WORKFLOW_TABLES:
            raise ValueError("unsupported workflow table")
        clauses = ["id=?"]
        params: list[Any] = [request_id]
        if project_id is not None:
            clauses.append("project_id=?")
            params.append(project_id)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {' AND '.join(clauses)}",
                params,
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        result = dict(row)
        result["workflow_type"] = (
            "template_publish" if table == "template_publish_requests" else "model_release"
        )
        result["payload"] = self._decode(result.pop("payload_json"))
        return result

    def list_workflow_requests(
        self,
        *,
        table: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
        organization_id: str | None = None,
        requested_by: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if table not in _WORKFLOW_TABLES:
            raise ValueError("unsupported workflow table")
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
            if status is not None:
                clauses.append("status=?")
                params.append(status)
            query = f"SELECT * FROM {table}"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC"
            rows = connection.execute(query, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            result = dict(row)
            result["workflow_type"] = (
                "template_publish" if table == "template_publish_requests" else "model_release"
            )
            result["payload"] = self._decode(result.pop("payload_json"))
            items.append(result)
        return items

    def decide_workflow_request(
        self,
        *,
        table: str,
        request_id: str,
        decision: str,
        decision_by: str,
        decision_by_name: str,
        note: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("unsupported approval decision")
        existing = self.get_workflow_request(
            table=table,
            request_id=request_id,
            project_id=project_id,
        )
        if existing["status"] != "pending_approval":
            raise RuntimeError("workflow request has already been decided")
        status = "approved" if decision == "approve" else "rejected"
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE {table}
                SET status=?,decision_by=?,decision_by_name=?,decision_note=?,updated_at=?
                WHERE id=? AND project_id=?
                """,
                (
                    status,
                    decision_by,
                    decision_by_name,
                    note,
                    now,
                    request_id,
                    existing["project_id"],
                ),
            )
        return self.get_workflow_request(
            table=table,
            request_id=request_id,
            project_id=existing["project_id"],
        )
