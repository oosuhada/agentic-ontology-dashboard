"""Small DB-API compatibility layer for reusing repository query logic on PostgreSQL.

The canonical repositories deliberately use conservative SQL. This adapter converts
SQLite qmark placeholders and conflict syntax, binds PostgreSQL RLS lazily from
query scope, and normalizes psycopg rows to the string-oriented persistence contract
used by the existing services.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from app.project import ProjectContext, ProjectContextError
from app.infra.db.pool import (
    pooled_identity_connection,
    pooled_system_connection,
    pooled_tenant_connection,
)

_QMARK = re.compile(r"\?")
_INSERT_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.IGNORECASE)
_INSERT_COLUMNS = re.compile(
    r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+[\w.]+\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_value(key: str, value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if key.endswith("_json") and isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _normalize_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    return {key: _normalize_value(key, value) for key, value in data.items()}


class CompatCursor:
    def __init__(self, cursor: Any | None = None, *, rowcount: int = 0) -> None:
        self.cursor = cursor
        self.rowcount = int(getattr(cursor, "rowcount", rowcount))

    def fetchone(self) -> dict[str, Any] | None:
        if self.cursor is None:
            return None
        return _normalize_row(self.cursor.fetchone())

    def fetchall(self) -> list[dict[str, Any]]:
        if self.cursor is None:
            return []
        return [_normalize_row(row) or {} for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PostgreSQLProjectContextResolver:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._workspace_cache: dict[str, ProjectContext] = {}
        self._project_cache: dict[str, tuple[str, str]] = {}

    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection: Any | None = None,
    ) -> ProjectContext:
        context = self._workspace_cache.get(workspace_id)
        if context is None:
            with pooled_system_connection(self.database_url) as system:
                row = system.execute(
                    "SELECT * FROM resolve_workspace_scope(%s)",
                    (workspace_id,),
                ).fetchone()
            if row is None:
                raise ProjectContextError(
                    f"workspace {workspace_id!r} is not assigned to an accessible Project"
                )
            context = ProjectContext(
                organization_id=str(row["organization_id"]),
                project_id=str(row["project_id"]),
                workspace_id=str(row["workspace_id"]),
            )
            self._workspace_cache[workspace_id] = context
        if expected_organization_id and context.organization_id != expected_organization_id:
            raise ProjectContextError("workspace organization scope does not match the request context")
        if expected_project_id and context.project_id != expected_project_id:
            raise ProjectContextError("workspace project scope does not match the request context")
        if connection is not None and hasattr(connection, "bind_scope"):
            connection.bind_scope(context.organization_id, context.project_id)
        return context

    def resolve_project(self, project_id: str) -> tuple[str, str]:
        cached = self._project_cache.get(project_id)
        if cached is not None:
            return cached
        with pooled_system_connection(self.database_url) as system:
            row = system.execute(
                "SELECT * FROM resolve_project_scope(%s)",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ProjectContextError(f"project {project_id!r} does not exist")
        result = (str(row["organization_id"]), str(row["project_id"]))
        self._project_cache[project_id] = result
        return result

    def resolve_share(self, token_hash: str) -> ProjectContext | None:
        with pooled_system_connection(self.database_url) as system:
            row = system.execute(
                "SELECT * FROM resolve_dashboard_share_scope(%s)",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return ProjectContext(
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            workspace_id=str(row["workspace_id"]),
        )


class PostgreSQLCompatConnection(AbstractContextManager):
    def __init__(
        self,
        database_url: str,
        *,
        identity_access: bool = False,
        organization_id: str | None = None,
        project_id: str | None = None,
        resolver: PostgreSQLProjectContextResolver | None = None,
    ) -> None:
        self.database_url = database_url
        self.identity_access = identity_access
        self.organization_id = organization_id
        self.project_id = project_id
        self.resolver = resolver or PostgreSQLProjectContextResolver(database_url)
        self._manager: Any | None = None
        self._connection: Any | None = None

    def __enter__(self) -> "PostgreSQLCompatConnection":
        if self.identity_access:
            self._open_identity()
        elif self.organization_id is not None:
            self._open_tenant()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool | None:
        if self._manager is not None:
            return self._manager.__exit__(exc_type, exc, traceback)
        return None

    def _open_identity(self) -> None:
        if self._connection is not None:
            return
        self._manager = pooled_identity_connection(self.database_url)
        self._connection = self._manager.__enter__()

    def _open_tenant(self) -> None:
        if self._connection is not None:
            return
        if not self.organization_id:
            raise RuntimeError("PostgreSQL repository query did not bind organization scope")
        self._manager = pooled_tenant_connection(
            self.database_url,
            self.organization_id,
            project_id=self.project_id,
        )
        self._connection = self._manager.__enter__()

    def bind_scope(self, organization_id: str, project_id: str | None = None) -> None:
        if self._connection is not None:
            if self.identity_access:
                return
            if self.organization_id != organization_id or self.project_id != project_id:
                raise RuntimeError("repository transaction attempted to change its RLS scope")
            return
        self.organization_id = organization_id
        self.project_id = project_id
        self._open_tenant()

    @staticmethod
    def _convert_sql(sql: str) -> str:
        stripped = sql.strip()
        if stripped.upper() == "BEGIN IMMEDIATE":
            return ""
        converted = _QMARK.sub("%s", sql)
        if _INSERT_OR_IGNORE.search(converted):
            converted = _INSERT_OR_IGNORE.sub("INSERT INTO ", converted)
            converted = converted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return converted

    @staticmethod
    def _placeholder_index(sql: str, match_start: int) -> int:
        return sql[:match_start].count("%s")

    def _infer_scope(self, sql: str, parameters: Sequence[Any]) -> None:
        if self._connection is not None or self.identity_access:
            return
        organization_id: str | None = None
        project_id: str | None = None

        insert = _INSERT_COLUMNS.search(sql)
        if insert:
            columns = [item.strip().strip('"') for item in insert.group(1).split(",")]
            values = [item.strip() for item in insert.group(2).split(",")]
            parameter_position = 0
            mapping: dict[str, Any] = {}
            for column, value in zip(columns, values):
                if "%s" in value:
                    if parameter_position < len(parameters):
                        mapping[column] = parameters[parameter_position]
                    parameter_position += value.count("%s")
            organization_id = mapping.get("organization_id")
            project_id = mapping.get("project_id")

        if organization_id is None:
            match = re.search(r"organization_id\s*=\s*%s", sql, re.IGNORECASE)
            if match:
                index = self._placeholder_index(sql, match.start())
                if index < len(parameters):
                    organization_id = parameters[index]
        if project_id is None:
            match = re.search(r"project_id\s*=\s*%s", sql, re.IGNORECASE)
            if match:
                index = self._placeholder_index(sql, match.start())
                if index < len(parameters):
                    project_id = parameters[index]

        if organization_id is None and project_id:
            organization_id, project_id = self.resolver.resolve_project(str(project_id))
        if organization_id is not None:
            self.bind_scope(str(organization_id), None if project_id is None else str(project_id))

    @staticmethod
    def _map_integrity_error(exc: Exception) -> Exception:
        if getattr(exc, "sqlstate", None) in {"23505", "23503", "23514", "23502"}:
            return sqlite3.IntegrityError(str(exc))
        return exc

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> CompatCursor:
        parameters = tuple(parameters or ())
        converted = self._convert_sql(sql)
        if not converted:
            return CompatCursor(rowcount=0)
        self._infer_scope(converted, parameters)
        if self._connection is None:
            if self.identity_access:
                self._open_identity()
            else:
                raise RuntimeError(f"unable to infer PostgreSQL RLS scope for query: {converted[:120]}")
        try:
            return CompatCursor(self._connection.execute(converted, parameters))
        except Exception as exc:
            mapped = self._map_integrity_error(exc)
            if mapped is not exc:
                raise mapped from exc
            raise

    def executemany(self, sql: str, parameter_sets: Iterable[Sequence[Any]]) -> CompatCursor:
        count = 0
        for parameters in parameter_sets:
            self.execute(sql, parameters)
            count += 1
        return CompatCursor(rowcount=count)

    def executescript(self, script: str) -> None:
        # Canonical PostgreSQL migrations own DDL. Reset scripts contain only
        # DELETE statements and are executed individually when required.
        statements = [statement.strip() for statement in script.split(";") if statement.strip()]
        for statement in statements:
            self.execute(statement)


def postgres_repository_connection(
    database_url: str,
    *,
    identity_access: bool = False,
    organization_id: str | None = None,
    project_id: str | None = None,
    resolver: PostgreSQLProjectContextResolver | None = None,
) -> PostgreSQLCompatConnection:
    return PostgreSQLCompatConnection(
        database_url,
        identity_access=identity_access,
        organization_id=organization_id,
        project_id=project_id,
        resolver=resolver,
    )
