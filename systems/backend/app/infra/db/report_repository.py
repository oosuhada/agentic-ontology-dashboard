from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.infra.db.migrations import ensure_scope_columns
from app.report.report_exception import ReportConflictError


class ProjectScope(Protocol):
    organization_id: str
    project_id: str
    workspace_id: str


class ProjectContextResolverPort(Protocol):
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ProjectScope: ...


class _SQLiteScope:
    def __init__(self, organization_id: str, project_id: str, workspace_id: str) -> None:
        self.organization_id = organization_id
        self.project_id = project_id
        self.workspace_id = workspace_id


class _SQLiteWorkspaceScopeLookup:
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> _SQLiteScope:
        if connection is None:
            raise RuntimeError("report scope lookup requires an active repository connection")
        row = connection.execute(
            "SELECT organization_id,project_id FROM workspaces WHERE id=?",
            (workspace_id,),
        ).fetchone()
        if row is None:
            raise KeyError(workspace_id)
        organization_id = str(row[0])
        project_id = str(row[1])
        if expected_organization_id is not None and organization_id != expected_organization_id:
            raise PermissionError("workspace organization scope mismatch")
        if expected_project_id is not None and project_id != expected_project_id:
            raise PermissionError("workspace project scope mismatch")
        return _SQLiteScope(organization_id, project_id, workspace_id)


class ReportRepository:
    def __init__(
        self,
        database_path: str | Path,
        *,
        project_context: ProjectContextResolverPort | None = None,
    ) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_context = project_context or _SQLiteWorkspaceScopeLookup()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def resolve_scope(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
    ) -> ProjectScope:
        with self._connect() as connection:
            return self.project_context.resolve(
                workspace_id,
                expected_organization_id=expected_organization_id,
                expected_project_id=expected_project_id,
                connection=connection,
            )

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
                CREATE TABLE IF NOT EXISTS report_drafts (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    headline TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    sections_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (organization_id, project_id, workspace_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS localized_report_drafts (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    headline TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    sections_json TEXT NOT NULL,
                    content_origin TEXT NOT NULL,
                    source_locale TEXT,
                    source_revision INTEGER,
                    updated_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (organization_id, project_id, workspace_id, event_id, role, locale)
                );
                CREATE INDEX IF NOT EXISTS idx_localized_report_drafts_scope
                    ON localized_report_drafts(
                        organization_id, project_id, workspace_id, event_id, role, locale
                    );
                CREATE INDEX IF NOT EXISTS idx_report_drafts_scope
                    ON report_drafts(organization_id, project_id, workspace_id, event_id);
                """
            )
            ensure_scope_columns(connection, table="export_checkpoints")
            ensure_scope_columns(connection, table="report_drafts")
            ensure_scope_columns(connection, table="localized_report_drafts")
            legacy_rows = connection.execute("SELECT * FROM report_drafts").fetchall()
            for row in legacy_rows:
                text = f"{row['headline']} {row['summary']}"
                locale = "ko-KR" if any("가" <= char <= "힣" for char in text) else "en-US"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO localized_report_drafts (
                        id,organization_id,project_id,workspace_id,event_id,role,locale,revision,
                        headline,summary,sections_json,content_origin,source_locale,source_revision,
                        updated_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"localized:{row['id']}",
                        row["organization_id"],
                        row["project_id"],
                        row["workspace_id"],
                        row["event_id"],
                        "engineer",
                        locale,
                        row["revision"],
                        row["headline"],
                        row["summary"],
                        row["sections_json"],
                        "edited",
                        None,
                        None,
                        row["updated_by"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

    def get_draft(
        self,
        *,
        workspace_id: str,
        event_id: str,
        role: str,
        locale: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            row = connection.execute(
                """
                SELECT * FROM localized_report_drafts
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND event_id=?
                  AND role=? AND locale=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, event_id, role, locale),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "organization_id": row["organization_id"],
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "event_id": row["event_id"],
            "role": row["role"],
            "locale": row["locale"],
            "revision": int(row["revision"]),
            "headline": row["headline"],
            "summary": row["summary"],
            "sections": json.loads(row["sections_json"]),
            "content_origin": row["content_origin"],
            "source_locale": row["source_locale"],
            "source_revision": int(row["source_revision"]) if row["source_revision"] is not None else None,
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def save_draft(
        self,
        *,
        workspace_id: str,
        event_id: str,
        role: str,
        locale: str,
        base_revision: int,
        headline: str,
        summary: str,
        sections: list[dict[str, Any]],
        content_origin: str,
        source_locale: str | None,
        source_revision: int | None,
        updated_by: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            current = connection.execute(
                """
                SELECT id,revision,created_at FROM localized_report_drafts
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND event_id=?
                  AND role=? AND locale=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, event_id, role, locale),
            ).fetchone()
            current_revision = int(current["revision"]) if current is not None else 0
            if current_revision != base_revision:
                raise ReportConflictError("report draft revision changed")
            record_id = str(current["id"]) if current is not None else f"report-draft:{uuid.uuid4()}"
            created_at = str(current["created_at"]) if current is not None else now
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO localized_report_drafts (
                    id,organization_id,project_id,workspace_id,event_id,role,locale,revision,
                    headline,summary,sections_json,content_origin,source_locale,source_revision,
                    updated_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(organization_id,project_id,workspace_id,event_id,role,locale) DO UPDATE SET
                    revision=excluded.revision,
                    headline=excluded.headline,
                    summary=excluded.summary,
                    sections_json=excluded.sections_json,
                    content_origin=excluded.content_origin,
                    source_locale=excluded.source_locale,
                    source_revision=excluded.source_revision,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """,
                (
                    record_id,
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    event_id,
                    role,
                    locale,
                    revision,
                    headline,
                    summary,
                    json.dumps(sections, ensure_ascii=False),
                    content_origin,
                    source_locale,
                    source_revision,
                    updated_by,
                    created_at,
                    now,
                ),
            )
        saved = self.get_draft(
            workspace_id=workspace_id,
            event_id=event_id,
            role=role,
            locale=locale,
        )
        if saved is None:
            raise RuntimeError("saved report draft could not be loaded")
        return saved

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


# Compatibility name for PostgreSQL subclass and older composition code.
ExportRepository = ReportRepository
