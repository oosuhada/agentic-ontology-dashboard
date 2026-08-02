from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ontology_dashboard.postgresql_pool import pooled_tenant_connection
from ontology_dashboard.postgresql_repositories import is_postgresql

from .analysis_models import AnalysisEdgeSnapshot, AnalysisNodeSnapshot, AnalysisSnapshot


class AnalysisVersionConflict(RuntimeError):
    pass


class AnalysisRepository:
    def __init__(self, database_target: str | Path) -> None:
        self.target = str(database_target)
        self.postgresql = is_postgresql(self.target)
        self.path = None if self.postgresql else self._sqlite_path(self.target)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_sqlite()

    @staticmethod
    def _sqlite_path(target: str) -> Path:
        return Path(target.removeprefix("sqlite:///")) if target.startswith("sqlite:///") else Path(target)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        if self.path is None:
            raise RuntimeError("SQLite connection requested for PostgreSQL repository")
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_sqlite(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    published_version INTEGER,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_boards (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    node_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (analysis_id, version, node_id),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    analysis_version INTEGER NOT NULL,
                    requested_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    node_results_json TEXT NOT NULL,
                    error_json TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_analyses_scope
                    ON analyses(organization_id, project_id, workspace_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_analysis_boards_version
                    ON analysis_boards(analysis_id, version, node_id);
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_latest
                    ON analysis_runs(analysis_id, analysis_version, finished_at DESC);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()
            }
            lifecycle_columns = {
                "progress_percent": "INTEGER NOT NULL DEFAULT 0",
                "current_node_id": "TEXT",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
                "cache_key": "TEXT",
                "cache_hit": "INTEGER NOT NULL DEFAULT 0",
                "rows_scanned": "INTEGER NOT NULL DEFAULT 0",
                "updated_at": "TEXT",
            }
            for name, ddl in lifecycle_columns.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE analysis_runs ADD COLUMN {name} {ddl}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_cache ON analysis_runs(organization_id,project_id,workspace_id,analysis_id,analysis_version,cache_key,status,finished_at DESC)"
            )

    @staticmethod
    def _json_timestamp(value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value

    @classmethod
    def _snapshot_from_rows(cls, analysis: dict[str, Any], board_rows: list[dict[str, Any]]) -> AnalysisSnapshot:
        analysis = {
            **analysis,
            "created_at": cls._json_timestamp(analysis.get("created_at")),
            "updated_at": cls._json_timestamp(analysis.get("updated_at")),
        }
        nodes = [AnalysisNodeSnapshot.model_validate(json.loads(row["node_json"])) for row in board_rows]
        edges_payload = json.loads(board_rows[0]["edges_json"]) if board_rows else []
        edges = [AnalysisEdgeSnapshot.model_validate(item) for item in edges_payload]
        return AnalysisSnapshot.model_validate(
            {
                **analysis,
                "published_version": analysis.get("published_version"),
                "nodes": nodes,
                "edges": edges,
            }
        )

    def create(
        self,
        *,
        analysis_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        display_name: str,
        nodes: list[AnalysisNodeSnapshot],
        edges: list[AnalysisEdgeSnapshot],
        actor_user_id: str,
        publish: bool,
    ) -> AnalysisSnapshot:
        now = self._now()
        status = "published" if publish else "draft"
        published_version = 1 if publish else None
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                connection.execute(
                    """
                    INSERT INTO analyses (
                        id,organization_id,project_id,workspace_id,display_name,status,current_version,
                        published_version,created_by,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s)
                    """,
                    (analysis_id, organization_id, project_id, workspace_id, display_name, status, published_version, actor_user_id, now, now),
                )
                self._insert_boards_postgresql(connection, organization_id, project_id, workspace_id, analysis_id, 1, nodes, edges, now)
        else:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO analyses (
                        id,organization_id,project_id,workspace_id,display_name,status,current_version,
                        published_version,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,1,?,?,?,?)
                    """,
                    (analysis_id, organization_id, project_id, workspace_id, display_name, status, published_version, actor_user_id, now, now),
                )
                self._insert_boards_sqlite(connection, organization_id, project_id, workspace_id, analysis_id, 1, nodes, edges, now)
        snapshot = self.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if snapshot is None:
            raise RuntimeError("analysis create did not persist")
        return snapshot

    def update(
        self,
        *,
        analysis_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        display_name: str,
        nodes: list[AnalysisNodeSnapshot],
        edges: list[AnalysisEdgeSnapshot],
        actor_user_id: str,
        base_version: int,
        publish: bool,
    ) -> AnalysisSnapshot:
        current = self.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if current is None:
            raise KeyError(analysis_id)
        if current.current_version != base_version:
            raise AnalysisVersionConflict("analysis version changed")
        next_version = current.current_version + 1
        now = self._now()
        status = "published" if publish else "draft"
        published_version = next_version if publish else current.published_version
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                result = connection.execute(
                    """
                    UPDATE analyses SET display_name=%s,status=%s,current_version=%s,published_version=%s,updated_at=%s
                    WHERE id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s AND current_version=%s
                    """,
                    (display_name, status, next_version, published_version, now, analysis_id, organization_id, project_id, workspace_id, base_version),
                )
                if result.rowcount != 1:
                    raise AnalysisVersionConflict("analysis version changed")
                self._insert_boards_postgresql(connection, organization_id, project_id, workspace_id, analysis_id, next_version, nodes, edges, now)
        else:
            with self._connect() as connection:
                result = connection.execute(
                    """
                    UPDATE analyses SET display_name=?,status=?,current_version=?,published_version=?,updated_at=?
                    WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=? AND current_version=?
                    """,
                    (display_name, status, next_version, published_version, now, analysis_id, organization_id, project_id, workspace_id, base_version),
                )
                if result.rowcount != 1:
                    raise AnalysisVersionConflict("analysis version changed")
                self._insert_boards_sqlite(connection, organization_id, project_id, workspace_id, analysis_id, next_version, nodes, edges, now)
        snapshot = self.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if snapshot is None:
            raise RuntimeError("analysis update did not persist")
        return snapshot

    def get(
        self,
        *,
        analysis_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        version: int | None = None,
    ) -> AnalysisSnapshot | None:
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                row = connection.execute(
                    """
                    SELECT * FROM analyses
                    WHERE id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s
                    """,
                    (analysis_id, organization_id, project_id, workspace_id),
                ).fetchone()
                if row is None:
                    return None
                selected_version = version or int(row["current_version"])
                boards = connection.execute(
                    """
                    SELECT node_json::text AS node_json,edges_json::text AS edges_json
                    FROM analysis_boards
                    WHERE analysis_id=%s AND version=%s
                    ORDER BY created_at,node_id
                    """,
                    (analysis_id, selected_version),
                ).fetchall()
                return self._snapshot_from_rows(dict(row), [dict(item) for item in boards]).model_copy(update={"current_version": selected_version})
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM analyses
                WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=?
                """,
                (analysis_id, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            selected_version = version or int(row["current_version"])
            boards = connection.execute(
                """
                SELECT node_json,edges_json FROM analysis_boards
                WHERE analysis_id=? AND version=?
                ORDER BY created_at,node_id
                """,
                (analysis_id, selected_version),
            ).fetchall()
        return self._snapshot_from_rows(dict(row), [dict(item) for item in boards]).model_copy(update={"current_version": selected_version})

    def record_run(
        self,
        *,
        run_id: str,
        analysis_id: str,
        analysis_version: int,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        requested_by: str,
        status: str,
        parameters: dict[str, Any],
        node_results: dict[str, dict[str, Any]],
        started_at: str,
        finished_at: str | None,
        error: dict[str, Any] | None = None,
        progress_percent: int | None = None,
        current_node_id: str | None = None,
        cancel_requested: bool = False,
        cache_key: str | None = None,
        cache_hit: bool = False,
        rows_scanned: int = 0,
    ) -> dict[str, Any]:
        updated_at = finished_at or started_at
        resolved_progress = progress_percent if progress_percent is not None else (100 if status in {"succeeded", "failed", "cancelled"} else 0)
        values = (
            run_id,
            organization_id,
            project_id,
            workspace_id,
            analysis_id,
            analysis_version,
            requested_by,
            status,
            json.dumps(parameters, ensure_ascii=False),
            json.dumps(node_results, ensure_ascii=False),
            json.dumps(error, ensure_ascii=False) if error else None,
            started_at,
            finished_at,
            resolved_progress,
            current_node_id,
            cancel_requested,
            cache_key,
            cache_hit,
            max(0, rows_scanned),
            updated_at,
        )
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                connection.execute(
                    """
                    INSERT INTO analysis_runs (
                        id,organization_id,project_id,workspace_id,analysis_id,analysis_version,
                        requested_by,status,parameters_json,node_results_json,error_json,started_at,finished_at,
                        progress_percent,current_node_id,cancel_requested,cache_key,cache_hit,rows_scanned,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    values,
                )
        else:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO analysis_runs (
                        id,organization_id,project_id,workspace_id,analysis_id,analysis_version,
                        requested_by,status,parameters_json,node_results_json,error_json,started_at,finished_at,
                        progress_percent,current_node_id,cancel_requested,cache_key,cache_hit,rows_scanned,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    values,
                )
        return self.get_run(
            run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ) or {}

    def update_run_lifecycle(
        self,
        *,
        run_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        status: str | None = None,
        progress_percent: int | None = None,
        current_node_id: str | None = None,
        node_results: dict[str, dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
        finished_at: str | None = None,
        rows_scanned: int | None = None,
        cache_hit: bool | None = None,
    ) -> dict[str, Any]:
        assignments: list[str] = ["updated_at=?"]
        params: list[Any] = [self._now()]
        if status is not None:
            assignments.append("status=?")
            params.append(status)
        if progress_percent is not None:
            assignments.append("progress_percent=?")
            params.append(min(100, max(0, progress_percent)))
        if current_node_id is not None or status in {"succeeded", "failed", "cancelled"}:
            assignments.append("current_node_id=?")
            params.append(current_node_id)
        if node_results is not None:
            assignments.append("node_results_json=?::jsonb" if self.postgresql else "node_results_json=?")
            params.append(json.dumps(node_results, ensure_ascii=False))
        if error is not None or status in {"succeeded", "cancelled"}:
            assignments.append("error_json=?::jsonb" if self.postgresql else "error_json=?")
            params.append(json.dumps(error, ensure_ascii=False) if error else None)
        if finished_at is not None:
            assignments.append("finished_at=?")
            params.append(finished_at)
        if rows_scanned is not None:
            assignments.append("rows_scanned=?")
            params.append(max(0, rows_scanned))
        if cache_hit is not None:
            assignments.append("cache_hit=?")
            params.append(cache_hit)
        params.extend([run_id, organization_id, project_id, workspace_id])
        sql = f"UPDATE analysis_runs SET {','.join(assignments)} WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=?"
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                cursor = connection.execute(sql.replace("?", "%s"), tuple(params))
                if cursor.rowcount != 1:
                    raise KeyError(run_id)
        else:
            with self._connect() as connection:
                cursor = connection.execute(sql, tuple(params))
                if cursor.rowcount != 1:
                    raise KeyError(run_id)
        return self.get_run(
            run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ) or {}

    def request_cancel(
        self,
        *,
        run_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        sql = """
            UPDATE analysis_runs
            SET cancel_requested=?,updated_at=?
            WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=?
              AND status IN ('queued','running')
        """
        params = (True, self._now(), run_id, organization_id, project_id, workspace_id)
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                connection.execute(sql.replace("?", "%s"), params)
        else:
            with self._connect() as connection:
                connection.execute(sql, params)
        payload = self.get_run(
            run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if payload is None:
            raise KeyError(run_id)
        return payload

    def is_cancel_requested(
        self,
        *,
        run_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> bool:
        payload = self.get_run(
            run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        return bool(payload and payload.get("cancel_requested"))

    def find_cached_run(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        analysis_id: str,
        analysis_version: int,
        cache_key: str,
    ) -> dict[str, Any] | None:
        query = """
            SELECT id FROM analysis_runs
            WHERE organization_id=? AND project_id=? AND workspace_id=?
              AND analysis_id=? AND analysis_version=? AND cache_key=? AND status='succeeded'
            ORDER BY finished_at DESC LIMIT 1
        """
        params = (
            organization_id,
            project_id,
            workspace_id,
            analysis_id,
            analysis_version,
            cache_key,
        )
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                row = connection.execute(query.replace("?", "%s"), params).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(query, params).fetchone()
        if row is None:
            return None
        return self.get_run(
            run_id=row["id"],
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )

    def get_run(
        self,
        *,
        run_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                row = connection.execute(
                    """
                    SELECT *,parameters_json::text AS parameters_text,node_results_json::text AS results_text,error_json::text AS error_text
                    FROM analysis_runs WHERE id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s
                    """,
                    (run_id, organization_id, project_id, workspace_id),
                ).fetchone()
                if row is None:
                    return None
                payload = dict(row)
                payload["started_at"] = self._json_timestamp(payload.get("started_at"))
                payload["finished_at"] = self._json_timestamp(payload.get("finished_at"))
                payload["updated_at"] = self._json_timestamp(payload.get("updated_at"))
                payload["parameters"] = json.loads(payload.pop("parameters_text"))
                payload["node_results"] = json.loads(payload.pop("results_text"))
                error_text = payload.pop("error_text")
                payload["error"] = json.loads(error_text) if error_text else None
                payload.pop("parameters_json", None)
                payload.pop("node_results_json", None)
                payload.pop("error_json", None)
                return payload
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM analysis_runs WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=?
                """,
                (run_id, organization_id, project_id, workspace_id),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["parameters"] = json.loads(payload.pop("parameters_json"))
        payload["node_results"] = json.loads(payload.pop("node_results_json"))
        payload["cancel_requested"] = bool(payload.get("cancel_requested"))
        payload["cache_hit"] = bool(payload.get("cache_hit"))
        error_json = payload.pop("error_json")
        payload["error"] = json.loads(error_json) if error_json else None
        return payload

    def latest_successful_run(
        self,
        *,
        analysis_id: str,
        analysis_version: int,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        if self.postgresql:
            with pooled_tenant_connection(self.target, organization_id, project_id=project_id) as connection:
                row = connection.execute(
                    """
                    SELECT id FROM analysis_runs
                    WHERE analysis_id=%s AND analysis_version=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s AND status='succeeded'
                    ORDER BY finished_at DESC NULLS LAST LIMIT 1
                    """,
                    (analysis_id, analysis_version, organization_id, project_id, workspace_id),
                ).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT id FROM analysis_runs
                    WHERE analysis_id=? AND analysis_version=? AND organization_id=? AND project_id=? AND workspace_id=? AND status='succeeded'
                    ORDER BY finished_at DESC LIMIT 1
                    """,
                    (analysis_id, analysis_version, organization_id, project_id, workspace_id),
                ).fetchone()
        if row is None:
            return None
        return self.get_run(
            run_id=row["id"],
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}:{uuid.uuid4()}"

    @staticmethod
    def _insert_boards_sqlite(connection, organization_id, project_id, workspace_id, analysis_id, version, nodes, edges, now) -> None:
        edges_json = json.dumps([edge.model_dump(mode="json", exclude_none=True) for edge in edges], ensure_ascii=False)
        for node in nodes:
            connection.execute(
                """
                INSERT INTO analysis_boards (
                    id,organization_id,project_id,workspace_id,analysis_id,version,node_id,node_json,edges_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (str(uuid.uuid4()), organization_id, project_id, workspace_id, analysis_id, version, node.id, node.model_dump_json(exclude_none=True), edges_json, now),
            )

    @staticmethod
    def _insert_boards_postgresql(connection, organization_id, project_id, workspace_id, analysis_id, version, nodes, edges, now) -> None:
        edges_json = json.dumps([edge.model_dump(mode="json", exclude_none=True) for edge in edges], ensure_ascii=False)
        for node in nodes:
            connection.execute(
                """
                INSERT INTO analysis_boards (
                    id,organization_id,project_id,workspace_id,analysis_id,version,node_id,node_json,edges_json,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                """,
                (str(uuid.uuid4()), organization_id, project_id, workspace_id, analysis_id, version, node.id, node.model_dump_json(exclude_none=True), edges_json, now),
            )
