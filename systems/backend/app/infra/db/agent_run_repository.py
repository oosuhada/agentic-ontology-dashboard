"""Durable persistence for grounded Agent execution activity.

The Reliability Assistant exposes a safe execution summary (retrieval,
validation, evidence counts) rather than private model reasoning.  This
repository persists that public execution contract so the UI can reconstruct
activity after a reload and audit the same run later.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infra.db.postgresql_compat import (
    PostgreSQLProjectContextResolver,
    postgres_repository_connection,
)
from app.infra.db.postgresql_repositories import is_postgresql


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


class AgentRunRepository:
    def __init__(self, database_target: str | Path) -> None:
        self.target = str(database_target)
        self._postgres = is_postgresql(self.target)
        self._resolver = PostgreSQLProjectContextResolver(self.target) if self._postgres else None

    def _connect(self, *, project_id: str):
        if self._postgres:
            organization_id = None
            if self._resolver:
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
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def save_run(self, *, state: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        status = str(state.get("status") or "failed")
        completed_at = now if status in {"succeeded", "failed"} else None
        run_id = str(state["run_id"])
        project_id = str(state["project_id"])
        organization_id = str(state["organization_id"])
        workspace_id = str(state["workspace_id"])
        user_id = str(state["user_id"])
        sequence = int(state.get("checkpoint_sequence") or 1)
        state_payload = _json(state)
        with self._connect(project_id=project_id) as connection:
            connection.execute(
                """
                INSERT INTO agent_runs(
                    id,organization_id,project_id,workspace_id,user_id,question,route,status,
                    state_json,answer,error_message,created_at,updated_at,completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    state_json=excluded.state_json,
                    answer=excluded.answer,
                    error_message=excluded.error_message,
                    updated_at=excluded.updated_at,
                    completed_at=excluded.completed_at
                """,
                (
                    run_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    user_id,
                    str(state.get("question") or ""),
                    str(state.get("route") or "hybrid"),
                    status,
                    state_payload,
                    str(state.get("answer") or ""),
                    state.get("error"),
                    now,
                    now,
                    completed_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO agent_checkpoints(
                    id,run_id,organization_id,project_id,workspace_id,sequence,node_name,state_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id,sequence) DO UPDATE SET
                    node_name=excluded.node_name,
                    state_json=excluded.state_json
                """,
                (
                    f"checkpoint-{run_id}-{sequence}",
                    run_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    sequence,
                    "answer_complete" if status == "succeeded" else "query_failed",
                    state_payload,
                    now,
                ),
            )
            connection.execute("DELETE FROM agent_traces WHERE run_id=?", (run_id,))
            for trace in traces:
                connection.execute(
                    """
                    INSERT INTO agent_traces(
                        id,run_id,organization_id,project_id,workspace_id,step_name,store_kind,status,
                        input_json,output_json,latency_ms,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(trace["id"]),
                        run_id,
                        organization_id,
                        project_id,
                        workspace_id,
                        str(trace.get("step_name") or "unknown"),
                        trace.get("store_kind"),
                        str(trace.get("status") or "failed"),
                        _json(trace.get("input") or {}),
                        _json(trace.get("output") or {}),
                        trace.get("latency_ms"),
                        _iso(trace.get("created_at") or now),
                    ),
                )
        return {"run_id": run_id, "checkpoint_sequence": sequence, "status": status}

    @staticmethod
    def _state(row: Any) -> dict[str, Any]:
        return _load_json(row["state_json"], {})

    @staticmethod
    def _summary(row: Any, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "workspace_id": str(row["workspace_id"]),
            "question": str(row["question"]),
            "route": str(row["route"]),
            "status": str(row["status"]),
            "object_type": state.get("object_type"),
            "object_id": state.get("object_id"),
            "event_id": state.get("event_id"),
            "evidence_count": len(state.get("evidence") or []),
            "claim_count": len(state.get("claims") or []),
            "checkpoint_sequence": int(state.get("checkpoint_sequence") or 0),
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }

    def list_runs(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        offset: int,
        limit: int,
        status: str | None,
        route: str | None,
        search: str | None,
        object_id: str | None,
    ) -> dict[str, Any]:
        clauses = [
            "organization_id=?",
            "project_id=?",
            "workspace_id=?",
            "user_id=?",
        ]
        params: list[Any] = [organization_id, project_id, workspace_id, user_id]
        if status:
            clauses.append("status=?")
            params.append(status)
        if route:
            clauses.append("route=?")
            params.append(route)
        if search:
            clauses.append("LOWER(question) LIKE ?")
            params.append(f"%{search.lower()}%")
        if object_id:
            clauses.append(
                "state_json->>'object_id'=?"
                if self._postgres
                else "json_extract(state_json,'$.object_id')=?"
            )
            params.append(object_id)
        where = " AND ".join(clauses)
        with self._connect(project_id=project_id) as connection:
            count_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM agent_runs WHERE {where}",
                tuple(params),
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT * FROM agent_runs
                WHERE {where}
                ORDER BY created_at DESC,id DESC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, limit, offset]),
            ).fetchall()
        summaries = [self._summary(row, self._state(row)) for row in rows]
        total = int(count_row["count"] if count_row is not None else 0)
        return {
            "items": summaries,
            "offset": offset,
            "limit": limit,
            "total": total,
        }

    def get_run(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        with self._connect(project_id=project_id) as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_runs
                WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=? AND user_id=?
                """,
                (run_id, organization_id, project_id, workspace_id, user_id),
            ).fetchone()
            if row is None:
                return None
            trace_rows = connection.execute(
                """
                SELECT * FROM agent_traces
                WHERE run_id=? AND organization_id=? AND project_id=? AND workspace_id=?
                ORDER BY created_at,id
                """,
                (run_id, organization_id, project_id, workspace_id),
            ).fetchall()
        state = self._state(row)
        traces = [
            {
                "id": str(trace["id"]),
                "run_id": str(trace["run_id"]),
                "step_name": str(trace["step_name"]),
                "store_kind": trace["store_kind"],
                "status": str(trace["status"]),
                "input": _load_json(trace["input_json"], {}),
                "output": _load_json(trace["output_json"], {}),
                "latency_ms": trace["latency_ms"],
                "created_at": _iso(trace["created_at"]),
            }
            for trace in trace_rows
        ]
        return {"state": state, "traces": traces}


__all__ = ["AgentRunRepository"]
