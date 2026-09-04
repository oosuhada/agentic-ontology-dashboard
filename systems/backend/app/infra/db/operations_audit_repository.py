"""SQLite persistence adapter for the manufacturing Operations audit trail port."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    question TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    event_id TEXT,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    model_version TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_review_summaries (
                    summary_id TEXT PRIMARY KEY,
                    summary_key TEXT NOT NULL UNIQUE,
                    workflow_run_id TEXT,
                    organization_id TEXT NOT NULL DEFAULT 'org-ontology-demo',
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'manufacturing-demo',
                    asset_id TEXT NOT NULL,
                    event_id TEXT,
                    dataset_version_id TEXT,
                    history_window TEXT NOT NULL,
                    packet_schema_version TEXT NOT NULL,
                    summary_schema_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('ready','fallback','failed','stale')),
                    fallback_reason TEXT,
                    snapshot_basis_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_review_summaries_lookup
                    ON agent_review_summaries (
                        organization_id, project_id, workspace_id, asset_id, event_id, dataset_version_id, updated_at
                    );
                CREATE TABLE IF NOT EXISTS agent_review_workflow_runs (
                    workflow_run_id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    status TEXT NOT NULL,
                    organization_id TEXT NOT NULL DEFAULT 'org-ontology-demo',
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'manufacturing-demo',
                    asset_id TEXT NOT NULL,
                    event_id TEXT,
                    dataset_version_id TEXT,
                    history_window TEXT NOT NULL,
                    summary_key TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    context_sha256 TEXT NOT NULL,
                    packet_schema_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    trace_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_review_workflow_runs_lookup
                    ON agent_review_workflow_runs (
                        organization_id, project_id, workspace_id, asset_id, event_id, dataset_version_id, updated_at
                    );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_review_workflow_runs_running_summary
                    ON agent_review_workflow_runs (
                        organization_id, project_id, workspace_id, summary_key
                    )
                    WHERE status = 'running';
            """
            )
            self._ensure_column(
                connection,
                "agent_review_summaries",
                "workflow_run_id",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "agent_review_summaries",
                "organization_id",
                "TEXT NOT NULL DEFAULT 'org-ontology-demo'",
            )
            self._ensure_column(
                connection,
                "agent_review_summaries",
                "workspace_id",
                "TEXT NOT NULL DEFAULT 'manufacturing-demo'",
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_decision(self, event_id: str, actor: str, decision: str, note: str) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "actor": actor,
            "decision": decision,
            "note": note,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO decisions (id,event_id,actor,decision,note,created_at) VALUES (?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def add_note(self, event_id: str, actor: str, body: str) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "actor": actor,
            "body": body,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO notes (id,event_id,actor,body,created_at) VALUES (?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def add_conversation(
        self,
        thread_id: str,
        event_id: str,
        role: str,
        question: str,
        intent: str,
        answer: str,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "event_id": event_id,
            "role": role,
            "question": question,
            "intent": intent,
            "answer": answer,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id,thread_id,event_id,role,question,intent,answer,created_at) VALUES (?,?,?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def record_audit(
        self,
        *,
        event_id: str | None,
        run_id: str,
        action: str,
        model_version: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "run_id": run_id,
            "action": action,
            "model_version": model_version,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log (id,event_id,run_id,action,model_version,payload_json,created_at) VALUES (?,?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return {**record, "payload": payload}

    def get_agent_review_summary(self, summary_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_review_summaries WHERE summary_key=?",
                (summary_key,),
            ).fetchone()
        if row is None:
            return None
        return self._summary_record_from_row(dict(row))

    def create_agent_review_workflow_run(self, **record: Any) -> dict[str, Any]:
        now = self._now()
        payload = {
            "workflow_run_id": str(record.get("workflow_run_id") or uuid.uuid4()),
            "trigger": str(record["trigger"]),
            "engine": str(record.get("engine") or "simple"),
            "status": str(record.get("status") or "running"),
            "organization_id": str(record.get("organization_id") or "org-ontology-demo"),
            "project_id": str(record["project_id"]),
            "workspace_id": str(record.get("workspace_id") or "manufacturing-demo"),
            "asset_id": str(record["asset_id"]),
            "event_id": record.get("event_id"),
            "dataset_version_id": record.get("dataset_version_id"),
            "history_window": str(record["history_window"]),
            "summary_key": str(record["summary_key"]),
            "source_sha256": str(record["source_sha256"]),
            "context_sha256": str(record["context_sha256"]),
            "packet_schema_version": str(record["packet_schema_version"]),
            "prompt_version": str(record["prompt_version"]),
            "model_version": str(record["model_version"]),
            "started_at": str(record.get("started_at") or now),
            "completed_at": record.get("completed_at"),
            "updated_at": now,
            "error_type": record.get("error_type"),
            "error_message": record.get("error_message"),
            "trace_json": json.dumps(record.get("trace") or {}, ensure_ascii=False, sort_keys=True),
        }
        columns = ",".join(payload.keys())
        placeholders = ",".join("?" for _ in payload)
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO agent_review_workflow_runs ({columns})
                VALUES ({placeholders})
                """,
                tuple(payload.values()),
            )
            row = connection.execute(
                "SELECT * FROM agent_review_workflow_runs WHERE workflow_run_id=?",
                (payload["workflow_run_id"],),
            ).fetchone()
        if row is None:
            raise RuntimeError("agent_review_workflow_run_create_failed")
        return self._workflow_run_record_from_row(dict(row))

    def expire_stale_agent_review_workflow_run(self, **filters: Any) -> dict[str, Any] | None:
        now = self._now()
        trace = {
            "stage": "expired",
            "reason": "stale_running_lease",
            "expired_before": str(filters["started_before"]),
        }
        values = (
            "failed",
            now,
            now,
            "stale_running_lease_expired",
            "running materialization lease expired before completion",
            json.dumps(trace, ensure_ascii=False, sort_keys=True),
            str(filters.get("organization_id") or "org-ontology-demo"),
            str(filters["project_id"]),
            str(filters.get("workspace_id") or "manufacturing-demo"),
            str(filters["summary_key"]),
            str(filters["started_before"]),
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_review_workflow_runs
                WHERE organization_id=?
                  AND project_id=?
                  AND workspace_id=?
                  AND summary_key=?
                  AND status='running'
                  AND started_at<=?
                ORDER BY started_at ASC
                LIMIT 1
                """,
                values[6:],
            ).fetchone()
            if row is None:
                return None
            workflow_run_id = str(row["workflow_run_id"])
            connection.execute(
                """
                UPDATE agent_review_workflow_runs
                SET status=?, completed_at=?, updated_at=?, error_type=?, error_message=?, trace_json=?
                WHERE organization_id=?
                  AND project_id=?
                  AND workspace_id=?
                  AND summary_key=?
                  AND status='running'
                  AND started_at<=?
                """,
                values,
            )
            updated = connection.execute(
                "SELECT * FROM agent_review_workflow_runs WHERE workflow_run_id=?",
                (workflow_run_id,),
            ).fetchone()
        if updated is None:
            return None
        return self._workflow_run_record_from_row(dict(updated))

    def finish_agent_review_workflow_run(
        self,
        workflow_run_id: str,
        **updates: Any,
    ) -> dict[str, Any]:
        now = self._now()
        payload = {
            "status": str(updates["status"]),
            "completed_at": updates.get("completed_at") or now,
            "updated_at": now,
            "error_type": updates.get("error_type"),
            "error_message": updates.get("error_message"),
            "trace_json": json.dumps(updates.get("trace") or {}, ensure_ascii=False, sort_keys=True),
            "workflow_run_id": workflow_run_id,
        }
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_review_workflow_runs
                SET status=?, completed_at=?, updated_at=?, error_type=?, error_message=?, trace_json=?
                WHERE workflow_run_id=?
                """,
                tuple(payload.values()),
            )
            row = connection.execute(
                "SELECT * FROM agent_review_workflow_runs WHERE workflow_run_id=?",
                (workflow_run_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("agent_review_workflow_run_update_failed")
        return self._workflow_run_record_from_row(dict(row))

    def get_agent_review_workflow_run(self, workflow_run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_review_workflow_runs WHERE workflow_run_id=?",
                (workflow_run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._workflow_run_record_from_row(dict(row))

    def list_agent_review_workflow_runs(self, **filters: Any) -> list[dict[str, Any]]:
        clauses = [
            "organization_id=?",
            "project_id=?",
            "workspace_id=?",
        ]
        values: list[Any] = [
            str(filters.get("organization_id") or "org-ontology-demo"),
            str(filters["project_id"]),
            str(filters.get("workspace_id") or "manufacturing-demo"),
        ]
        for column in ("asset_id", "event_id", "dataset_version_id", "status"):
            value = filters.get(column)
            if value:
                clauses.append(f"{column}=?")
                values.append(str(value))
        limit = max(1, min(int(filters.get("limit") or 20), 100))
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM agent_review_workflow_runs
                WHERE {" AND ".join(clauses)}
                ORDER BY updated_at DESC, started_at DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [self._workflow_run_record_from_row(dict(row)) for row in rows]

    def save_agent_review_summary(self, **record: Any) -> dict[str, Any]:
        now = self._now()
        payload = {
            "summary_id": str(record.get("summary_id") or uuid.uuid4()),
            "summary_key": str(record["summary_key"]),
            "workflow_run_id": record.get("workflow_run_id"),
            "organization_id": str(record.get("organization_id") or "org-ontology-demo"),
            "project_id": str(record["project_id"]),
            "workspace_id": str(record.get("workspace_id") or "manufacturing-demo"),
            "asset_id": str(record["asset_id"]),
            "event_id": record.get("event_id"),
            "dataset_version_id": record.get("dataset_version_id"),
            "history_window": str(record["history_window"]),
            "packet_schema_version": str(record["packet_schema_version"]),
            "summary_schema_version": str(record["summary_schema_version"]),
            "prompt_version": str(record["prompt_version"]),
            "model_version": str(record["model_version"]),
            "source_sha256": str(record["source_sha256"]),
            "status": str(record["status"]),
            "fallback_reason": record.get("fallback_reason"),
            "snapshot_basis_json": json.dumps(
                record["snapshot_basis"], ensure_ascii=False, sort_keys=True
            ),
            "summary_json": json.dumps(
                record["summary"], ensure_ascii=False, sort_keys=True
            ),
            "trace_json": json.dumps(record["trace"], ensure_ascii=False, sort_keys=True),
            "generated_at": str(record["generated_at"]),
            "created_at": str(record.get("created_at") or now),
            "updated_at": now,
        }
        columns = ",".join(payload.keys())
        placeholders = ",".join("?" for _ in payload)
        updates = ",".join(
            f"{column}=excluded.{column}"
            for column in payload
            if column not in {"summary_id", "summary_key", "created_at"}
        )
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO agent_review_summaries ({columns})
                VALUES ({placeholders})
                ON CONFLICT(summary_key) DO UPDATE SET {updates}
                """,
                tuple(payload.values()),
            )
            row = connection.execute(
                "SELECT * FROM agent_review_summaries WHERE summary_key=?",
                (payload["summary_key"],),
            ).fetchone()
        if row is None:
            raise RuntimeError("agent_review_summary_persist_failed")
        return self._summary_record_from_row(dict(row))

    def event_activity(self, event_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as connection:
            decisions = [dict(row) for row in connection.execute("SELECT * FROM decisions WHERE event_id=? ORDER BY created_at", (event_id,))]
            notes = [dict(row) for row in connection.execute("SELECT * FROM notes WHERE event_id=? ORDER BY created_at", (event_id,))]
            conversations = [dict(row) for row in connection.execute("SELECT * FROM conversations WHERE event_id=? ORDER BY created_at", (event_id,))]
        return {"decisions": decisions, "notes": notes, "conversations": conversations}

    def reset(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                "DELETE FROM decisions; DELETE FROM notes; DELETE FROM conversations; "
                "DELETE FROM audit_log; DELETE FROM agent_review_summaries; "
                "DELETE FROM agent_review_workflow_runs;"
            )
            ontology_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ontology_action_invocations'"
            ).fetchone()
            if ontology_table is not None:
                connection.execute("DELETE FROM ontology_action_invocations")

    @staticmethod
    def _summary_record_from_row(row: dict[str, Any]) -> dict[str, Any]:
        def decode(value: Any) -> Any:
            if isinstance(value, (dict, list)):
                return value
            return json.loads(str(value))

        return {
            **row,
            "snapshot_basis": decode(row["snapshot_basis_json"]),
            "summary": decode(row["summary_json"]),
            "trace": decode(row["trace_json"]),
        }

    @staticmethod
    def _workflow_run_record_from_row(row: dict[str, Any]) -> dict[str, Any]:
        trace = row.get("trace_json")
        return {
            **row,
            "trace": json.loads(str(trace)) if trace else {},
        }

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
