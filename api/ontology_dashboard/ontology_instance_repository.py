"""Persistent ontology object and link instance repository.

SQLite is the active runtime backend. The schema is intentionally portable to
PostgreSQL and is mirrored by the SQL migrations under ``api/migrations``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .ontology import LinkRecord, ObjectRecord
from .project_context import SQLiteProjectContextResolver, ensure_scope_columns


class OntologyInstanceRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_context = SQLiteProjectContextResolver(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ontology_objects (
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_revision TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, object_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ontology_objects_type
                    ON ontology_objects(workspace_id, object_type, object_id);

                CREATE TABLE IF NOT EXISTS ontology_links (
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    link_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    source_object_id TEXT NOT NULL,
                    target_object_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_revision TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, link_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ontology_links_source
                    ON ontology_links(workspace_id, source_object_id, link_type);
                CREATE INDEX IF NOT EXISTS idx_ontology_links_target
                    ON ontology_links(workspace_id, target_object_id, link_type);

                CREATE TABLE IF NOT EXISTS ontology_ingestion_runs (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_revision TEXT,
                    object_count INTEGER NOT NULL,
                    link_count INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
                """
            )
            for table in ("ontology_objects", "ontology_links", "ontology_ingestion_runs"):
                ensure_scope_columns(connection, table=table)

    def replace_source_snapshot(
        self,
        *,
        workspace_id: str,
        source_system: str,
        source_revision: str,
        objects: Iterable[ObjectRecord],
        links: Iterable[LinkRecord],
    ) -> None:
        object_items = [item for item in objects if item.workspace_id == workspace_id]
        link_items = [item for item in links if item.workspace_id == workspace_id]
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = self.project_context.resolve(workspace_id, connection=connection)
            scope_values = (scope.organization_id, scope.project_id, workspace_id)
            connection.execute(
                """
                DELETE FROM ontology_links
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND source_system=?
                """,
                (*scope_values, source_system),
            )
            connection.execute(
                """
                DELETE FROM ontology_objects
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND source_system=?
                """,
                (*scope_values, source_system),
            )
            connection.executemany(
                """
                INSERT INTO ontology_objects (
                    organization_id,project_id,workspace_id,object_id,object_type,
                    payload_json,source_system,source_revision,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        scope.organization_id,
                        scope.project_id,
                        item.workspace_id,
                        item.id,
                        item.object_type,
                        item.model_dump_json(),
                        source_system,
                        source_revision,
                        now,
                    )
                    for item in object_items
                ],
            )
            connection.executemany(
                """
                INSERT INTO ontology_links (
                    organization_id,project_id,workspace_id,link_id,link_type,
                    source_object_id,target_object_id,payload_json,source_system,
                    source_revision,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        scope.organization_id,
                        scope.project_id,
                        item.workspace_id,
                        item.id,
                        item.link_type,
                        item.source_object_id,
                        item.target_object_id,
                        item.model_dump_json(),
                        source_system,
                        source_revision,
                        now,
                    )
                    for item in link_items
                ],
            )
            connection.execute(
                """
                INSERT INTO ontology_ingestion_runs (
                    id,organization_id,project_id,workspace_id,source_system,source_revision,
                    object_count,link_count,completed_at
                ) VALUES (lower(hex(randomblob(16))),?,?,?,?,?,?,?,?)
                """,
                (
                    scope.organization_id,
                    scope.project_id,
                    workspace_id,
                    source_system,
                    source_revision,
                    len(object_items),
                    len(link_items),
                    now,
                ),
            )

    def list_objects(
        self,
        *,
        workspace_id: str,
        object_type: str | None = None,
    ) -> list[ObjectRecord]:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            parameters: list[object] = [scope.organization_id, scope.project_id, workspace_id]
            object_filter = ""
            if object_type is not None:
                object_filter = " AND object_type=?"
                parameters.append(object_type)
            rows = connection.execute(
                """
                SELECT payload_json FROM ontology_objects
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                """ + object_filter + " ORDER BY object_type,object_id",
                parameters,
            ).fetchall()
        return [ObjectRecord.model_validate_json(row["payload_json"]) for row in rows]

    def get_object(self, *, workspace_id: str, object_id: str) -> ObjectRecord | None:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            row = connection.execute(
                """
                SELECT payload_json FROM ontology_objects
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND object_id=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, object_id),
            ).fetchone()
        return None if row is None else ObjectRecord.model_validate_json(row["payload_json"])

    def list_links(
        self,
        *,
        workspace_id: str,
        link_type: str | None = None,
    ) -> list[LinkRecord]:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            parameters: list[object] = [scope.organization_id, scope.project_id, workspace_id]
            link_filter = ""
            if link_type is not None:
                link_filter = " AND link_type=?"
                parameters.append(link_type)
            rows = connection.execute(
                """
                SELECT payload_json FROM ontology_links
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                """ + link_filter + " ORDER BY link_id",
                parameters,
            ).fetchall()
        return [LinkRecord.model_validate_json(row["payload_json"]) for row in rows]

    def latest_ingestion(self, *, workspace_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            scope = self.project_context.resolve(workspace_id, connection=connection)
            row = connection.execute(
                """
                SELECT * FROM ontology_ingestion_runs
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                ORDER BY completed_at DESC LIMIT 1
                """,
                (scope.organization_id, scope.project_id, workspace_id),
            ).fetchone()
        return None if row is None else dict(row)
