"""Canonical organization/project/workspace context resolution.

Operational repositories still accept ``workspace_id`` at their public boundary for
backward compatibility, but every persisted record is resolved to the full tenant
scope before it is written or queried.  This keeps the compatibility API safe while
Project-aware routes and contracts are rolled out incrementally.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ORGANIZATION_ID = "org-ontology-demo"
DEFAULT_PROJECT_ID = "manufacturing-demo-project"
DEFAULT_WORKSPACE_ID = "manufacturing-demo"


class ProjectContextError(ValueError):
    """Raised when a workspace cannot be resolved to a valid Project context."""


@dataclass(frozen=True, slots=True)
class ProjectContext:
    organization_id: str
    project_id: str
    workspace_id: str


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
        expected_project_id: str | None = None,
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
    connection: sqlite3.Connection,
    *,
    table: str,
    workspace_column: str = "workspace_id",
) -> None:
    """Add/backfill organization and Project columns for a workspace-scoped table.

    SQLite cannot add multiple columns conditionally in plain migration SQL, so
    repositories and the migration runner share this compatibility helper.
    """

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
