"""PostgreSQL implementation of the Project-scoped Ontology instance repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable

from app.ontology.ontology_domain import LinkRecord, ObjectRecord
from app.infra.db.connection import tenant_connection


class PostgreSQLOntologyInstanceRepository:
    def __init__(
        self,
        database_url: str,
        *,
        organization_id: str,
        project_id: str,
    ) -> None:
        if not project_id:
            raise ValueError("PostgreSQL ontology runtime requires an explicit project_id")
        self.database_url = database_url
        self.organization_id = organization_id
        self.project_id = project_id

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _connection(self):
        return tenant_connection(
            self.database_url,
            self.organization_id,
            project_id=self.project_id,
        )

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
        with self._connection() as connection:
            # Board queries can arrive concurrently and each query asks the
            # adapter to refresh this snapshot. Serialize replacements for the
            # same Project/workspace/source so delete+insert remains atomic.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{self.project_id}:{workspace_id}:{source_system}",),
            )
            workspace = connection.execute(
                """
                SELECT 1 FROM workspaces
                WHERE organization_id=%s AND project_id=%s AND id=%s
                """,
                (self.organization_id, self.project_id, workspace_id),
            ).fetchone()
            if workspace is None:
                raise ValueError("workspace is not assigned to the active PostgreSQL Project")
            connection.execute(
                """
                DELETE FROM ontology_links
                WHERE organization_id=%s AND project_id=%s
                  AND workspace_id=%s AND source_system=%s
                """,
                (self.organization_id, self.project_id, workspace_id, source_system),
            )
            connection.execute(
                """
                DELETE FROM ontology_objects
                WHERE organization_id=%s AND project_id=%s
                  AND workspace_id=%s AND source_system=%s
                """,
                (self.organization_id, self.project_id, workspace_id, source_system),
            )
            for item in object_items:
                connection.execute(
                    """
                    INSERT INTO ontology_objects (
                        organization_id,project_id,workspace_id,object_id,object_type,
                        payload_json,source_system,source_revision,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    """,
                    (
                        self.organization_id,
                        self.project_id,
                        item.workspace_id,
                        item.id,
                        item.object_type,
                        item.model_dump_json(),
                        source_system,
                        source_revision,
                        now,
                    ),
                )
            for item in link_items:
                connection.execute(
                    """
                    INSERT INTO ontology_links (
                        organization_id,project_id,workspace_id,link_id,link_type,
                        source_object_id,target_object_id,payload_json,source_system,
                        source_revision,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    """,
                    (
                        self.organization_id,
                        self.project_id,
                        item.workspace_id,
                        item.id,
                        item.link_type,
                        item.source_object_id,
                        item.target_object_id,
                        item.model_dump_json(),
                        source_system,
                        source_revision,
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO ontology_ingestion_runs (
                    id,organization_id,project_id,workspace_id,source_system,source_revision,
                    object_count,link_count,completed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    uuid.uuid4(),
                    self.organization_id,
                    self.project_id,
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
        clauses = ["organization_id=%s", "project_id=%s", "workspace_id=%s"]
        parameters: list[object] = [self.organization_id, self.project_id, workspace_id]
        if object_type is not None:
            clauses.append("object_type=%s")
            parameters.append(object_type)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM ontology_objects WHERE "
                + " AND ".join(clauses)
                + " ORDER BY object_type,object_id",
                parameters,
            ).fetchall()
        return [ObjectRecord.model_validate(row["payload_json"]) for row in rows]

    def get_object(self, *, workspace_id: str, object_id: str) -> ObjectRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM ontology_objects
                WHERE organization_id=%s AND project_id=%s
                  AND workspace_id=%s AND object_id=%s
                """,
                (self.organization_id, self.project_id, workspace_id, object_id),
            ).fetchone()
        return None if row is None else ObjectRecord.model_validate(row["payload_json"])

    def list_links(
        self,
        *,
        workspace_id: str,
        link_type: str | None = None,
    ) -> list[LinkRecord]:
        clauses = ["organization_id=%s", "project_id=%s", "workspace_id=%s"]
        parameters: list[object] = [self.organization_id, self.project_id, workspace_id]
        if link_type is not None:
            clauses.append("link_type=%s")
            parameters.append(link_type)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM ontology_links WHERE "
                + " AND ".join(clauses)
                + " ORDER BY link_id",
                parameters,
            ).fetchall()
        return [LinkRecord.model_validate(row["payload_json"]) for row in rows]

    def latest_ingestion(self, *, workspace_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id,organization_id,project_id,workspace_id,source_system,
                       source_revision,object_count,link_count,completed_at
                FROM ontology_ingestion_runs
                WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                ORDER BY completed_at DESC LIMIT 1
                """,
                (self.organization_id, self.project_id, workspace_id),
            ).fetchone()
        return None if row is None else dict(row)
