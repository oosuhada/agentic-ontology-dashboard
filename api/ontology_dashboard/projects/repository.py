from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ProjectCreateRequest, ProjectUpdateRequest

DEMO_ORGANIZATION_ID = "org-ontology-demo"
DEMO_PROJECT_ID = "manufacturing-demo-project"
DEMO_WORKSPACE_ID = "manufacturing-demo"


class ProjectRepository:
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

    def list_projects(
        self,
        *,
        organization_id: str,
        project_ids: list[str] | None = None,
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

    def get_project(self, *, organization_id: str, project_id: str) -> dict[str, Any] | None:
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
        project_id: str,
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
        project = self.get_project(organization_id=organization_id, project_id=project_id)
        if project is None:
            raise RuntimeError("created project could not be loaded")
        return project

    def update_project(
        self,
        *,
        organization_id: str,
        project_id: str,
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
        project_id: str,
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
