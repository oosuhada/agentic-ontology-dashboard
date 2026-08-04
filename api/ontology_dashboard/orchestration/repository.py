"""Checkpoint and trace repository for scoped multi-store agent runs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..postgresql import tenant_connection
from ..postgresql_repositories import is_postgresql
from .models import AgentRunPage, AgentRunSummary, AgentState, AgentTraceRecord


class AgentRunRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)
        if not self.postgresql:
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @contextmanager
    def _connect(self, organization_id: str, project_id: str) -> Iterator[Any]:
        if self.postgresql:
            with tenant_connection(
                self.database,
                organization_id,
                project_id=project_id,
            ) as connection:
                yield connection
            return
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgresql else sql

    def _json(self, value: Any) -> Any:
        if self.postgresql:
            try:
                from psycopg.types.json import Jsonb
            except ImportError as error:
                raise RuntimeError("PostgreSQL agent repository requires api[postgres]") from error
            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _decode(value: Any) -> Any:
        return value if isinstance(value, (dict, list)) else json.loads(value)

    def create(self, state: AgentState) -> AgentState:
        now = self._now()
        with self._connect(state.organization_id, state.project_id) as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT INTO agent_runs(
                        id,organization_id,project_id,workspace_id,user_id,question,route,
                        status,state_json,answer,error_message,created_at,updated_at,completed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    state.run_id,
                    state.organization_id,
                    state.project_id,
                    state.workspace_id,
                    state.user_id,
                    state.question,
                    state.route,
                    state.status,
                    self._json(state.model_dump(mode="json")),
                    state.answer,
                    state.error,
                    now,
                    now,
                    None,
                ),
            )
        return self.checkpoint(state, "start")

    def checkpoint(self, state: AgentState, node_name: str) -> AgentState:
        next_sequence = state.checkpoint_sequence + 1
        checkpointed = state.model_copy(update={"checkpoint_sequence": next_sequence})
        now = self._now()
        with self._connect(state.organization_id, state.project_id) as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT INTO agent_checkpoints(
                        id,run_id,organization_id,project_id,workspace_id,sequence,
                        node_name,state_json,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    f"checkpoint-{uuid.uuid4()}",
                    state.run_id,
                    state.organization_id,
                    state.project_id,
                    state.workspace_id,
                    next_sequence,
                    node_name,
                    self._json(checkpointed.model_dump(mode="json")),
                    now,
                ),
            )
            connection.execute(
                self._sql(
                    "UPDATE agent_runs SET state_json=?,status=?,answer=?,error_message=?,updated_at=? WHERE id=?"
                ),
                (
                    self._json(checkpointed.model_dump(mode="json")),
                    checkpointed.status,
                    checkpointed.answer,
                    checkpointed.error,
                    now,
                    state.run_id,
                ),
            )
        return checkpointed

    def trace(
        self,
        state: AgentState,
        *,
        step_name: str,
        store_kind: str | None,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        latency_ms: int | None,
    ) -> None:
        with self._connect(state.organization_id, state.project_id) as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT INTO agent_traces(
                        id,run_id,organization_id,project_id,workspace_id,step_name,
                        store_kind,status,input_json,output_json,latency_ms,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    f"trace-{uuid.uuid4()}",
                    state.run_id,
                    state.organization_id,
                    state.project_id,
                    state.workspace_id,
                    step_name,
                    store_kind,
                    status,
                    self._json(input_payload),
                    self._json(output_payload),
                    latency_ms,
                    self._now(),
                ),
            )

    def finish(self, state: AgentState) -> AgentState:
        final = state.model_copy(
            update={
                "status": state.status,
            }
        )
        now = self._now()
        with self._connect(state.organization_id, state.project_id) as connection:
            connection.execute(
                self._sql(
                    """
                    UPDATE agent_runs
                    SET status=?,state_json=?,answer=?,error_message=?,updated_at=?,completed_at=?
                    WHERE id=? AND organization_id=? AND project_id=?
                    """
                ),
                (
                    final.status,
                    self._json(final.model_dump(mode="json")),
                    final.answer,
                    final.error,
                    now,
                    now,
                    final.run_id,
                    final.organization_id,
                    final.project_id,
                ),
            )
        return final

    def get(
        self,
        *,
        organization_id: str,
        project_id: str,
        run_id: str,
    ) -> AgentState:
        with self._connect(organization_id, project_id) as connection:
            row = connection.execute(
                self._sql(
                    "SELECT state_json FROM agent_runs WHERE id=? AND organization_id=? AND project_id=?"
                ),
                (run_id, organization_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        value = dict(row)["state_json"]
        return AgentState.model_validate(self._decode(value))

    def list_runs(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentState]:
        page = self.list_run_page(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=limit,
        )
        return [
            self.get(
                organization_id=organization_id,
                project_id=project_id,
                run_id=item.run_id,
            )
            for item in page.items
        ]

    def list_run_page(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        offset: int = 0,
        limit: int = 25,
        status: str | None = None,
        route: str | None = None,
        search: str | None = None,
    ) -> AgentRunPage:
        safe_offset = max(0, offset)
        safe_limit = min(100, max(1, limit))
        clauses = ["organization_id=?", "project_id=?", "workspace_id=?"]
        params: list[Any] = [organization_id, project_id, workspace_id]
        if status:
            clauses.append("status=?")
            params.append(status)
        if route:
            clauses.append("route=?")
            params.append(route)
        if search:
            clauses.append("LOWER(question) LIKE ?")
            params.append(f"%{search.strip().lower()}%")
        where = " AND ".join(clauses)
        with self._connect(organization_id, project_id) as connection:
            total_row = connection.execute(
                self._sql(f"SELECT COUNT(*) AS total FROM agent_runs WHERE {where}"),
                tuple(params),
            ).fetchone()
            rows = connection.execute(
                self._sql(
                    f"""
                    SELECT id,project_id,workspace_id,question,route,status,state_json,created_at,updated_at
                    FROM agent_runs
                    WHERE {where}
                    ORDER BY created_at DESC,id DESC
                    LIMIT ? OFFSET ?
                    """
                ),
                tuple([*params, safe_limit, safe_offset]),
            ).fetchall()
        items: list[AgentRunSummary] = []
        for row in rows:
            record = dict(row)
            state = AgentState.model_validate(self._decode(record.pop("state_json")))
            items.append(
                AgentRunSummary(
                    run_id=record.pop("id"),
                    project_id=record["project_id"],
                    workspace_id=record["workspace_id"],
                    question=record["question"],
                    route=record["route"],
                    status=record["status"],
                    evidence_count=len(state.evidence),
                    claim_count=len(state.claims),
                    checkpoint_sequence=state.checkpoint_sequence,
                    created_at=record["created_at"],
                    updated_at=record["updated_at"],
                )
            )
        return AgentRunPage(
            items=items,
            offset=safe_offset,
            limit=safe_limit,
            total=int(dict(total_row)["total"]),
        )

    def checkpoints(
        self,
        *,
        organization_id: str,
        project_id: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT id,run_id,workspace_id,sequence,node_name,state_json,created_at
                    FROM agent_checkpoints
                    WHERE run_id=? AND organization_id=? AND project_id=?
                    ORDER BY sequence,id
                    """
                ),
                (run_id, organization_id, project_id),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["state"] = self._decode(item.pop("state_json"))
            result.append(item)
        return result

    def traces(
        self,
        *,
        organization_id: str,
        project_id: str,
        run_id: str,
    ) -> list[AgentTraceRecord]:
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT id,run_id,step_name,store_kind,status,input_json,output_json,
                           latency_ms,created_at
                    FROM agent_traces
                    WHERE run_id=? AND organization_id=? AND project_id=?
                    ORDER BY created_at,id
                    """
                ),
                (run_id, organization_id, project_id),
            ).fetchall()
        result: list[AgentTraceRecord] = []
        for row in rows:
            item = dict(row)
            item["input"] = self._decode(item.pop("input_json"))
            item["output"] = self._decode(item.pop("output_json"))
            result.append(AgentTraceRecord.model_validate(item))
        return result
