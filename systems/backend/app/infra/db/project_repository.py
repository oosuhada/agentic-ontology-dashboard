"""SQLite Project persistence and project-scope resolution adapters."""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.project.project_domain import (
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    DEMO_ORGANIZATION_ID,
    DEMO_PROJECT_ID,
    DEMO_WORKSPACE_ID,
    ProjectContext,
    ProjectId,
)
from app.project.project_exception import ProjectContextError, ProjectError
from app.project.project_schema import ProjectCreateRequest, ProjectUpdateRequest


class ProjectRepository:
    """SQLite Project repository; PostgreSQL supplies a connection-compatible subclass."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _is_unique_conflict(exc: BaseException) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, sqlite3.IntegrityError):
                return True
            if getattr(current, "sqlstate", None) == "23505":
                return True
            current = current.__cause__ or current.__context__
        return False

    def list_projects(
        self,
        *,
        organization_id: str,
        project_ids: list[ProjectId] | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if project_ids is None:
                rows = connection.execute(
                    """
                    SELECT id,organization_id,slug,display_name,description,domain_pack_code,
                           status,default_workspace_id,created_at,updated_at
                    FROM projects
                    WHERE organization_id=?
                    ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                             display_name,id
                    """,
                    (organization_id,),
                ).fetchall()
            elif not project_ids:
                rows = []
            else:
                placeholders = ",".join("?" for _ in project_ids)
                rows = connection.execute(
                    f"""
                    SELECT id,organization_id,slug,display_name,description,domain_pack_code,
                           status,default_workspace_id,created_at,updated_at
                    FROM projects
                    WHERE organization_id=? AND id IN ({placeholders})
                    ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                             display_name,id
                    """,
                    (organization_id, *project_ids),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, *, organization_id: str, project_id: ProjectId) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id,organization_id,slug,display_name,description,domain_pack_code,
                       status,default_workspace_id,created_at,updated_at
                FROM projects
                WHERE organization_id=? AND id=?
                """,
                (organization_id, project_id),
            ).fetchone()
        return None if row is None else dict(row)

    def list_workspaces(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        workspace_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            parameters: list[Any] = [organization_id, project_id]
            scope_clause = ""
            if workspace_ids is not None:
                if not workspace_ids:
                    return []
                placeholders = ",".join("?" for _ in workspace_ids)
                scope_clause = f" AND id IN ({placeholders})"
                parameters.extend(workspace_ids)
            rows = connection.execute(
                f"""
                SELECT id,organization_id,project_id,slug,display_name,domain_pack
                FROM workspaces
                WHERE organization_id=? AND project_id=?{scope_clause}
                ORDER BY display_name,id
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def create_project(
        self,
        *,
        organization_id: str,
        request: ProjectCreateRequest,
    ) -> dict[str, Any]:
        project_id = f"project-{uuid.uuid4()}"
        now = self._now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO projects(
                        id,organization_id,slug,display_name,description,domain_pack_code,
                        status,default_workspace_id,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,NULL,?,?)
                    """,
                    (
                        project_id,
                        organization_id,
                        request.slug,
                        request.display_name,
                        request.description,
                        request.domain_pack_code,
                        request.status,
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            if self._is_unique_conflict(exc):
                raise ProjectError(
                    409,
                    "project_slug_conflict",
                    "같은 slug의 Project가 이미 존재합니다.",
                ) from exc
            raise
        project = self.get_project(organization_id=organization_id, project_id=project_id)
        if project is None:
            raise RuntimeError("created project could not be loaded")
        return project

    def update_project(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        request: ProjectUpdateRequest,
    ) -> dict[str, Any] | None:
        current = self.get_project(organization_id=organization_id, project_id=project_id)
        if current is None:
            return None
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return current
        updates["updated_at"] = self._now()
        assignments = ",".join(f"{name}=?" for name in updates)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE projects SET {assignments} WHERE organization_id=? AND id=?",
                (*updates.values(), organization_id, project_id),
            )
        return self.get_project(organization_id=organization_id, project_id=project_id)

    def workspace_belongs_to_project(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        workspace_id: str,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM workspaces
                WHERE organization_id=? AND project_id=? AND id=?
                """,
                (organization_id, project_id, workspace_id),
            ).fetchone()
        return row is not None

    def list_project_members(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id=? AND organization_id=?",
                (project_id, organization_id),
            ).fetchone()
            if project is None:
                raise ProjectError(404, "project_not_found", "Project를 찾을 수 없습니다.")
            rows = connection.execute(
                """
                SELECT pm.user_id,pm.organization_id,pm.project_id,pm.status,
                       pm.created_at,pm.updated_at,u.email,u.display_name,u.status AS user_status
                FROM project_memberships pm
                JOIN users u ON u.id=pm.user_id
                WHERE pm.organization_id=? AND pm.project_id=?
                ORDER BY u.display_name,u.email
                """,
                (organization_id, project_id),
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                roles = [
                    item["role_code"]
                    for item in connection.execute(
                        """
                        SELECT role_code FROM project_membership_roles
                        WHERE user_id=? AND project_id=?
                        ORDER BY role_code
                        """,
                        (row["user_id"], project_id),
                    )
                ]
                items.append({**dict(row), "roles": roles})
        return items

    def update_project_membership(
        self,
        *,
        actor_user_id: str,
        organization_id: str,
        project_id: ProjectId,
        target_user_id: str,
        status: str,
        roles: list[str],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        before_rows = self.list_project_members(
            organization_id=organization_id,
            project_id=project_id,
        )
        before = next(
            (item for item in before_rows if item["user_id"] == target_user_id),
            None,
        )
        now = self._now()
        with self._connect() as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id=? AND organization_id=? AND status<>'archived'",
                (project_id, organization_id),
            ).fetchone()
            user = connection.execute(
                "SELECT id,email,display_name,status FROM users WHERE id=? AND organization_id=?",
                (target_user_id, organization_id),
            ).fetchone()
            if project is None:
                raise ProjectError(404, "project_not_found", "Project를 찾을 수 없습니다.")
            if user is None:
                raise ProjectError(404, "user_not_found", "사용자를 찾을 수 없습니다.")
            if actor_user_id == target_user_id and (
                status != "active" or "tenant_admin" not in roles
            ):
                actor_roles = {
                    item["role_code"]
                    for item in connection.execute(
                        """
                        SELECT role_code FROM project_membership_roles
                        WHERE user_id=? AND project_id=?
                        """,
                        (actor_user_id, project_id),
                    )
                }
                if "tenant_admin" in actor_roles:
                    raise ProjectError(
                        409,
                        "self_lockout_blocked",
                        "현재 Project 관리자 membership을 스스로 제거할 수 없습니다.",
                    )
            connection.execute(
                """
                INSERT OR IGNORE INTO project_memberships(
                    user_id,organization_id,project_id,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (target_user_id, organization_id, project_id, status, now, now),
            )
            connection.execute(
                """
                UPDATE project_memberships
                SET status=?,updated_at=?
                WHERE user_id=? AND organization_id=? AND project_id=?
                """,
                (status, now, target_user_id, organization_id, project_id),
            )
            connection.execute(
                "DELETE FROM project_membership_roles WHERE user_id=? AND project_id=?",
                (target_user_id, project_id),
            )
            for role_code in sorted(set(roles)):
                connection.execute(
                    """
                    INSERT INTO project_membership_roles(user_id,project_id,role_code)
                    VALUES (?,?,?)
                    """,
                    (target_user_id, project_id, role_code),
                )
            if status == "active":
                connection.execute(
                    "INSERT OR IGNORE INTO user_project_scopes(user_id,project_id) VALUES (?,?)",
                    (target_user_id, project_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_scopes(user_id,workspace_id)
                    SELECT ?,id FROM workspaces
                    WHERE organization_id=? AND project_id=?
                    """,
                    (target_user_id, organization_id, project_id),
                )
            else:
                connection.execute(
                    "DELETE FROM user_project_scopes WHERE user_id=? AND project_id=?",
                    (target_user_id, project_id),
                )
                connection.execute(
                    """
                    DELETE FROM user_scopes
                    WHERE user_id=? AND workspace_id IN (
                        SELECT id FROM workspaces WHERE organization_id=? AND project_id=?
                    )
                    """,
                    (target_user_id, organization_id, project_id),
                )
                connection.execute(
                    """
                    UPDATE sessions SET active_project_id=NULL
                    WHERE user_id=? AND active_project_id=? AND revoked_at IS NULL
                    """,
                    (target_user_id, project_id),
                )
        after = next(
            item
            for item in self.list_project_members(
                organization_id=organization_id,
                project_id=project_id,
            )
            if item["user_id"] == target_user_id
        )
        return before, after


class SQLiteProjectContextResolver:
    """Resolve and validate tenant scope using the canonical ``workspaces`` table."""

    def __init__(self, database_path: str | Path, *, cache_ttl_seconds: float = 5.0) -> None:
        self.path = Path(database_path)
        self.cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self._cache: dict[str, tuple[float, ProjectContext]] = {}

    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: ProjectId | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ProjectContext:
        cached = self._cache.get(workspace_id)
        if cached is not None and time.monotonic() - cached[0] <= self.cache_ttl_seconds:
            context = cached[1]
            if expected_organization_id and context.organization_id != expected_organization_id:
                raise ProjectContextError("workspace organization scope does not match the request context")
            if expected_project_id and context.project_id != expected_project_id:
                raise ProjectContextError("workspace project scope does not match the request context")
            return context

        owns_connection = connection is None
        active = connection or sqlite3.connect(self.path)
        active.row_factory = sqlite3.Row
        try:
            row: sqlite3.Row | None = None
            table_exists = active.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'"
            ).fetchone()
            if table_exists:
                row = active.execute(
                    "SELECT organization_id,project_id FROM workspaces WHERE id=?",
                    (workspace_id,),
                ).fetchone()

            if row is None:
                if workspace_id != DEFAULT_WORKSPACE_ID:
                    raise ProjectContextError(
                        f"workspace {workspace_id!r} is not assigned to an accessible Project"
                    )
                context = ProjectContext(
                    organization_id=DEFAULT_ORGANIZATION_ID,
                    project_id=DEFAULT_PROJECT_ID,
                    workspace_id=workspace_id,
                )
            else:
                organization_id = str(row["organization_id"] or "").strip()
                project_id = str(row["project_id"] or "").strip()
                if not organization_id or not project_id:
                    raise ProjectContextError(
                        f"workspace {workspace_id!r} does not have a complete organization/project assignment"
                    )
                context = ProjectContext(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )

            self._cache[workspace_id] = (time.monotonic(), context)
            if expected_organization_id and context.organization_id != expected_organization_id:
                raise ProjectContextError("workspace organization scope does not match the request context")
            if expected_project_id and context.project_id != expected_project_id:
                raise ProjectContextError("workspace project scope does not match the request context")
            return context
        finally:
            if owns_connection:
                active.close()

    def ensure_scope_columns(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        workspace_column: str = "workspace_id",
    ) -> None:
        ensure_scope_columns(
            connection,
            table=table,
            workspace_column=workspace_column,
        )


def ensure_scope_columns(
    connection: sqlite3.Connection,
    *,
    table: str,
    workspace_column: str = "workspace_id",
) -> None:
    """Add/backfill organization and Project columns for a workspace-scoped table."""

    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return
    columns = {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if "organization_id" not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN organization_id TEXT")
    if "project_id" not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN project_id TEXT")

    workspace_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'"
    ).fetchone()
    if workspace_table:
        connection.execute(
            f"""
            UPDATE {table}
            SET organization_id=COALESCE(
                    organization_id,
                    (SELECT organization_id FROM workspaces w WHERE w.id={table}.{workspace_column})
                ),
                project_id=COALESCE(
                    project_id,
                    (SELECT project_id FROM workspaces w WHERE w.id={table}.{workspace_column})
                )
            WHERE organization_id IS NULL OR project_id IS NULL
            """
        )
    connection.execute(
        f"UPDATE {table} SET organization_id=? "
        f"WHERE organization_id IS NULL AND {workspace_column}=?",
        (DEFAULT_ORGANIZATION_ID, DEFAULT_WORKSPACE_ID),
    )
    connection.execute(
        f"UPDATE {table} SET project_id=? "
        f"WHERE project_id IS NULL AND {workspace_column}=?",
        (DEFAULT_PROJECT_ID, DEFAULT_WORKSPACE_ID),
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_project_scope "
        f"ON {table}(organization_id,project_id,{workspace_column})"
    )


__all__ = [
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "DEMO_ORGANIZATION_ID",
    "DEMO_PROJECT_ID",
    "DEMO_WORKSPACE_ID",
    "ProjectRepository",
    "SQLiteProjectContextResolver",
    "ensure_scope_columns",
]
