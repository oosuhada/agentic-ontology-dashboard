from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.project.project_domain import ProjectContext, ProjectContextResolverPort


InvocationState = Literal["running", "succeeded", "failed"]
RecoveryState = Literal[
    "none", "retryable", "compensation_required", "reconciled", "dead_letter"
]


class OntologyActionRepository:
    """Persists ontology Action invocation state and idempotent results."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        project_context: ProjectContextResolverPort,
    ) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_context = project_context
        self._initialize()

    def resolve_scope(self, workspace_id: str) -> ProjectContext:
        return self.project_context.resolve(workspace_id)

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
                CREATE TABLE IF NOT EXISTS ontology_action_invocations (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    actor_display_name TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    audit_id TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    recovery_state TEXT NOT NULL DEFAULT 'none',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error_at TEXT,
                    outbox_event_id TEXT,
                    UNIQUE (workspace_id, actor_user_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_ontology_invocation_object
                    ON ontology_action_invocations(workspace_id, object_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_ontology_invocation_created
                    ON ontology_action_invocations(created_at);
                """
            )
            self.project_context.ensure_scope_columns(
                connection,
                table="ontology_action_invocations",
            )

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        record = dict(row)
        record["request"] = json.loads(record.pop("request_json"))
        result_json = record.pop("result_json")
        error_json = record.pop("error_json")
        record["result"] = json.loads(result_json) if result_json else None
        record["error"] = json.loads(error_json) if error_json else None
        return record

    def find_by_idempotency_key(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            row = connection.execute(
                """
                SELECT * FROM ontology_action_invocations
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                  AND actor_user_id=? AND idempotency_key=?
                """,
                (
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    actor_user_id,
                    idempotency_key,
                ),
            ).fetchone()
        return self._decode(row)

    def reserve(
        self,
        *,
        idempotency_key: str,
        workspace_id: str,
        action_type: str,
        object_id: str,
        actor_user_id: str,
        actor_display_name: str,
        request_hash: str,
        request: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        invocation_id = str(uuid.uuid4())
        created_at = self._now()
        try:
            with self._connect() as connection:
                scope = self.project_context.resolve(workspace_id, connection=connection)
                connection.execute(
                    """
                    INSERT INTO ontology_action_invocations (
                        id,organization_id,project_id,idempotency_key,workspace_id,
                        action_type,object_id,actor_user_id,actor_display_name,
                        request_hash,request_json,state,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        invocation_id,
                        scope.organization_id,
                        scope.project_id,
                        idempotency_key,
                        workspace_id,
                        action_type,
                        object_id,
                        actor_user_id,
                        actor_display_name,
                        request_hash,
                        json.dumps(request, ensure_ascii=False, sort_keys=True),
                        "running",
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.find_by_idempotency_key(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            return existing, False

        reserved = self.find_by_idempotency_key(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
        )
        if reserved is None:
            raise RuntimeError("reserved ontology Action invocation could not be loaded")
        return reserved, True

    def succeed(
        self,
        invocation_id: str,
        *,
        project_id: str,
        result: dict[str, Any],
        audit_id: str,
    ) -> dict[str, Any]:
        completed_at = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ontology_action_invocations
                SET state='succeeded', result_json=?, error_json=NULL, audit_id=?, completed_at=?,
                    recovery_state='reconciled'
                WHERE id=? AND project_id=?
                """,
                (
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    audit_id,
                    completed_at,
                    invocation_id,
                    project_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ontology_action_invocations WHERE id=? AND project_id=?",
                (invocation_id, project_id),
            ).fetchone()
        record = self._decode(row)
        if record is None:
            raise RuntimeError("completed ontology Action invocation could not be loaded")
        return record

    def fail(
        self,
        invocation_id: str,
        *,
        project_id: str,
        code: str,
        message: str,
        recovery_state: RecoveryState = "retryable",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ontology_action_invocations
                SET state='failed', error_json=?, completed_at=?, recovery_state=?,
                    attempt_count=attempt_count+1, last_error_at=?
                WHERE id=? AND project_id=?
                """,
                (
                    json.dumps({"code": code, "message": message}, ensure_ascii=False, sort_keys=True),
                    self._now(),
                    recovery_state,
                    self._now(),
                    invocation_id,
                    project_id,
                ),
            )

    def mark_recovery_state(
        self,
        invocation_id: str,
        *,
        project_id: str,
        recovery_state: RecoveryState,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ontology_action_invocations
                SET recovery_state=?
                WHERE id=? AND project_id=?
                """,
                (recovery_state, invocation_id, project_id),
            )
            row = connection.execute(
                "SELECT * FROM ontology_action_invocations WHERE id=? AND project_id=?",
                (invocation_id, project_id),
            ).fetchone()
        record = self._decode(row)
        if record is None:
            raise RuntimeError("ontology Action recovery state could not be loaded")
        return record

    def list_for_object(self, *, workspace_id: str, object_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            rows = connection.execute(
                """
                SELECT * FROM ontology_action_invocations
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND object_id=?
                ORDER BY created_at DESC
                """,
                (scope.organization_id, scope.project_id, workspace_id, object_id),
            ).fetchall()
        return [record for row in rows if (record := self._decode(row)) is not None]
