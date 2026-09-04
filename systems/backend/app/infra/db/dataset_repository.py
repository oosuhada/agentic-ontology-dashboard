"""Database adapter for the Dataset repository port."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.dataset.dataset_schema import (
    DatasetCreateRequest,
    DatasetFileCreate,
    DatasetVersionCreateRequest,
    MaterializationCreateRequest,
    OntologyMappingCreateRequest,
    ProjectionStatus,
    StoreKind,
)
from app.infra.db.connection import tenant_connection
from app.infra.db.settings import is_postgresql_url


class DatasetRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql_url(self.database)
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

    def _sql(self, value: str) -> str:
        return value.replace("?", "%s") if self.postgresql else value

    def _json(self, value: Any) -> Any:
        if self.postgresql:
            try:
                from psycopg.types.json import Jsonb
            except ImportError as error:
                raise RuntimeError("PostgreSQL Dataset repository requires api[postgres]") from error
            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _dict(row: Any) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _decode_json(value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)

    def create_dataset(
        self,
        *,
        organization_id: str,
        actor_user_id: str,
        request: DatasetCreateRequest,
    ) -> dict[str, Any]:
        dataset_id = request.id or f"ds-{uuid.uuid4()}"
        now = self._now()
        with self._connect(organization_id, request.project_id) as connection:
            workspace = connection.execute(
                self._sql(
                    "SELECT id FROM workspaces WHERE id=? AND organization_id=? AND project_id=?"
                ),
                (request.workspace_id, organization_id, request.project_id),
            ).fetchone()
            if workspace is None:
                raise ValueError("workspace does not belong to the requested organization/project")
            connection.execute(
                self._sql(
                    """
                    INSERT INTO datasets(
                        id,organization_id,project_id,workspace_id,slug,display_name,
                        description,source_type,status,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    dataset_id,
                    organization_id,
                    request.project_id,
                    request.workspace_id,
                    request.slug,
                    request.display_name,
                    request.description,
                    request.source_type,
                    "active",
                    actor_user_id,
                    now,
                    now,
                ),
            )
        return self.get_dataset(
            organization_id=organization_id,
            project_id=request.project_id,
            dataset_id=dataset_id,
        )

    def list_datasets(
        self,
        *,
        organization_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        return self.list_dataset_page(
            organization_id=organization_id,
            project_id=project_id,
            offset=0,
            limit=10_000,
        )["items"]

    def list_dataset_page(
        self,
        *,
        organization_id: str,
        project_id: str,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        workspace_id: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        safe_offset = max(0, offset)
        safe_limit = min(200, max(1, limit))
        clauses = ["d.organization_id=?", "d.project_id=?"]
        params: list[Any] = [organization_id, project_id]
        if status:
            clauses.append("d.status=?")
            params.append(status)
        else:
            clauses.append("d.status <> 'archived'")
        if workspace_id:
            clauses.append("d.workspace_id=?")
            params.append(workspace_id)
        if source_type:
            clauses.append("d.source_type=?")
            params.append(source_type)
        if search:
            clauses.append(
                "(LOWER(d.display_name) LIKE ? OR LOWER(d.slug) LIKE ? OR LOWER(d.description) LIKE ?)"
            )
            pattern = f"%{search.strip().lower()}%"
            params.extend([pattern, pattern, pattern])
        where = " AND ".join(clauses)
        with self._connect(organization_id, project_id) as connection:
            total_row = connection.execute(
                self._sql(f"SELECT COUNT(*) AS total FROM datasets d WHERE {where}"),
                tuple(params),
            ).fetchone()
            rows = connection.execute(
                self._sql(
                    f"""
                    SELECT d.*,
                           v.id AS latest_version_id,
                           v.version_label AS latest_version_label,
                           v.source_version AS latest_source_version,
                           COALESCE(v.record_count,0) AS record_count
                    FROM datasets d
                    LEFT JOIN dataset_versions v ON v.id = (
                        SELECT v2.id FROM dataset_versions v2
                        WHERE v2.dataset_id=d.id
                        ORDER BY v2.version_number DESC LIMIT 1
                    )
                    WHERE {where}
                    ORDER BY d.updated_at DESC,d.display_name,d.id
                    LIMIT ? OFFSET ?
                    """
                ),
                tuple([*params, safe_limit, safe_offset]),
            ).fetchall()
            datasets = [self._dict(row) for row in rows]
            dataset_ids = [item["id"] for item in datasets]
            projections: list[Any] = []
            if dataset_ids:
                placeholders = ",".join("?" for _ in dataset_ids)
                projections = connection.execute(
                    self._sql(
                        f"""
                        SELECT p.dataset_id,p.store_kind,p.status
                        FROM store_projections p
                        JOIN dataset_versions v ON v.id=p.dataset_version_id
                        WHERE p.organization_id=? AND p.project_id=?
                          AND p.dataset_id IN ({placeholders})
                          AND v.version_number=(
                            SELECT MAX(v2.version_number) FROM dataset_versions v2
                            WHERE v2.dataset_id=p.dataset_id
                          )
                        """
                    ),
                    tuple([organization_id, project_id, *dataset_ids]),
                ).fetchall()
        health_by_dataset: dict[str, dict[str, str]] = {}
        for row in projections:
            item = self._dict(row)
            health_by_dataset.setdefault(item["dataset_id"], {})[item["store_kind"]] = item["status"]
        for item in datasets:
            item["projection_health"] = {
                store: health_by_dataset.get(item["id"], {}).get(store, "missing")
                for store in ("relational", "graph", "vector")
            }
        return {
            "items": datasets,
            "offset": safe_offset,
            "limit": safe_limit,
            "total": int(self._dict(total_row)["total"]),
        }

    def get_dataset(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
    ) -> dict[str, Any]:
        items = self.list_datasets(organization_id=organization_id, project_id=project_id)
        item = next((row for row in items if row["id"] == dataset_id), None)
        if item is None:
            raise KeyError(dataset_id)
        return item

    def create_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        actor_user_id: str,
        request: DatasetVersionCreateRequest,
    ) -> dict[str, Any]:
        version_id = f"dsv-{uuid.uuid4()}"
        now = self._now()
        with self._connect(organization_id, project_id) as connection:
            dataset = connection.execute(
                self._sql(
                    "SELECT workspace_id FROM datasets WHERE id=? AND organization_id=? AND project_id=?"
                ),
                (dataset_id, organization_id, project_id),
            ).fetchone()
            if dataset is None:
                raise KeyError(dataset_id)
            workspace_id = self._dict(dataset)["workspace_id"]
            row = connection.execute(
                self._sql(
                    "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM dataset_versions WHERE dataset_id=?"
                ),
                (dataset_id,),
            ).fetchone()
            version_number = int(self._dict(row)["next_version"])
            version_label = request.version_label or f"v{version_number}"
            connection.execute(
                self._sql(
                    """
                    INSERT INTO dataset_versions(
                        id,organization_id,project_id,workspace_id,dataset_id,version_number,
                        version_label,source_version,manifest_id,checksum_sha256,schema_json,
                        profile_json,record_count,status,created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    version_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_id,
                    version_number,
                    version_label,
                    request.source_version,
                    request.manifest_id,
                    request.checksum_sha256.lower(),
                    self._json(request.schema_),
                    self._json(request.profile),
                    request.record_count,
                    "registered",
                    actor_user_id,
                    now,
                ),
            )
            for file_item in request.files:
                self._insert_file(
                    connection,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                    file_item=file_item,
                    now=now,
                )
            object_namespace = f"{project_id}:{dataset_id}:{version_id}"
            for store_kind in ("relational", "graph", "vector"):
                connection.execute(
                    self._sql(
                        """
                        INSERT INTO store_projections(
                            id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                            store_kind,status,object_namespace,source_version,record_count,
                            attempt_count,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """
                    ),
                    (
                        f"projection-{uuid.uuid4()}",
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_id,
                        version_id,
                        store_kind,
                        "pending",
                        object_namespace,
                        request.source_version,
                        0,
                        0,
                        now,
                    ),
                )
            connection.execute(
                self._sql("UPDATE datasets SET updated_at=? WHERE id=? AND project_id=?"),
                (now, dataset_id, project_id),
            )
        return self.get_version(
            organization_id=organization_id,
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )

    def _insert_file(
        self,
        connection: Any,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        dataset_version_id: str,
        file_item: DatasetFileCreate,
        now: str,
    ) -> None:
        connection.execute(
            self._sql(
                """
                INSERT INTO dataset_files(
                    id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                    uri,media_type,checksum_sha256,size_bytes,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """
            ),
            (
                f"file-{uuid.uuid4()}",
                organization_id,
                project_id,
                workspace_id,
                dataset_id,
                dataset_version_id,
                file_item.uri,
                file_item.media_type,
                file_item.checksum_sha256.lower(),
                file_item.size_bytes,
                now,
            ),
        )

    def list_versions(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT * FROM dataset_versions
                    WHERE organization_id=? AND project_id=? AND dataset_id=?
                    ORDER BY version_number DESC
                    """
                ),
                (organization_id, project_id, dataset_id),
            ).fetchall()
        return [self._version_row(row) for row in rows]

    def get_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        with self._connect(organization_id, project_id) as connection:
            row = connection.execute(
                self._sql(
                    """
                    SELECT * FROM dataset_versions
                    WHERE id=? AND organization_id=? AND project_id=? AND dataset_id=?
                    """
                ),
                (version_id, organization_id, project_id, dataset_id),
            ).fetchone()
        if row is None:
            raise KeyError(version_id)
        return self._version_row(row)

    def _version_row(self, row: Any) -> dict[str, Any]:
        item = self._dict(row)
        item["schema"] = self._decode_json(item.pop("schema_json"))
        item["profile"] = self._decode_json(item.pop("profile_json"))
        return item

    def list_files(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [organization_id, project_id, dataset_id]
        where = "organization_id=? AND project_id=? AND dataset_id=?"
        if version_id:
            where += " AND dataset_version_id=?"
            params.append(version_id)
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    f"SELECT * FROM dataset_files WHERE {where} ORDER BY created_at DESC,id"
                ),
                tuple(params),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def list_ingestion_runs(
        self,
        *,
        organization_id: str,
        project_id: str,
        manifest_ids: list[str],
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not manifest_ids:
            return []
        placeholders = ",".join("?" for _ in manifest_ids)
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    f"""
                    SELECT * FROM adapter_ingestion_runs
                    WHERE organization_id=? AND project_id=?
                      AND manifest_id IN ({placeholders})
                    ORDER BY started_at DESC,id
                    LIMIT ?
                    """
                ),
                tuple([organization_id, project_id, *manifest_ids, min(200, max(1, limit))]),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def list_quarantine_records(
        self,
        *,
        organization_id: str,
        project_id: str,
        ingestion_run_ids: list[str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not ingestion_run_ids:
            return []
        placeholders = ",".join("?" for _ in ingestion_run_ids)
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    f"""
                    SELECT * FROM adapter_quarantine_records
                    WHERE organization_id=? AND project_id=?
                      AND ingestion_run_id IN ({placeholders})
                    ORDER BY created_at DESC,id
                    LIMIT ?
                    """
                ),
                tuple([organization_id, project_id, *ingestion_run_ids, min(500, max(1, limit))]),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = self._dict(row)
            item["record"] = self._decode_json(item.pop("record_json"))
            result.append(item)
        return result

    def latest_materialization(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        params: list[Any] = [organization_id, project_id, dataset_id]
        where = "organization_id=? AND project_id=? AND dataset_id=? AND status='ready'"
        if version_id:
            where += " AND dataset_version_id=?"
            params.append(version_id)
        with self._connect(organization_id, project_id) as connection:
            row = connection.execute(
                self._sql(
                    f"SELECT * FROM materializations WHERE {where} ORDER BY created_at DESC,id DESC LIMIT 1"
                ),
                tuple(params),
            ).fetchone()
        if row is None:
            raise KeyError(f"materialization:{dataset_id}")
        return self._materialization_row(row)

    def save_mapping(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str,
        actor_user_id: str,
        request: OntologyMappingCreateRequest,
    ) -> dict[str, Any]:
        mapping_id = f"mapping-{uuid.uuid4()}"
        now = self._now()
        payload = request.model_dump(mode="json")
        with self._connect(organization_id, project_id) as connection:
            version = connection.execute(
                self._sql(
                    "SELECT workspace_id FROM dataset_versions WHERE id=? AND dataset_id=? AND organization_id=? AND project_id=?"
                ),
                (version_id, dataset_id, organization_id, project_id),
            ).fetchone()
            if version is None:
                raise KeyError(version_id)
            workspace_id = self._dict(version)["workspace_id"]
            existing = connection.execute(
                self._sql(
                    "SELECT id FROM ontology_mappings WHERE dataset_version_id=? AND object_type=?"
                ),
                (version_id, request.object_type),
            ).fetchone()
            if existing is not None:
                mapping_id = self._dict(existing)["id"]
                connection.execute(
                    self._sql(
                        """
                        UPDATE ontology_mappings
                        SET identity_field=?,mapping_json=?,status='approved',updated_at=?
                        WHERE id=? AND organization_id=? AND project_id=?
                        """
                    ),
                    (
                        request.identity_field,
                        self._json(payload),
                        now,
                        mapping_id,
                        organization_id,
                        project_id,
                    ),
                )
            else:
                connection.execute(
                    self._sql(
                        """
                        INSERT INTO ontology_mappings(
                            id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                            object_type,identity_field,mapping_json,status,created_by,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """
                    ),
                    (
                        mapping_id,
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_id,
                        version_id,
                        request.object_type,
                        request.identity_field,
                        self._json(payload),
                        "approved",
                        actor_user_id,
                        now,
                        now,
                    ),
                )
        return self.get_mapping(
            organization_id=organization_id,
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            object_type=request.object_type,
        )

    def get_mapping(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str,
        object_type: str | None = None,
    ) -> dict[str, Any]:
        params: list[Any] = [version_id, dataset_id, organization_id, project_id]
        where = "dataset_version_id=? AND dataset_id=? AND organization_id=? AND project_id=?"
        if object_type:
            where += " AND object_type=?"
            params.append(object_type)
        with self._connect(organization_id, project_id) as connection:
            row = connection.execute(
                self._sql(f"SELECT * FROM ontology_mappings WHERE {where} ORDER BY created_at LIMIT 1"),
                tuple(params),
            ).fetchone()
        if row is None:
            raise KeyError(f"mapping:{version_id}")
        return self._mapping_row(row)

    def list_mappings(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    "SELECT * FROM ontology_mappings WHERE organization_id=? AND project_id=? AND dataset_id=? ORDER BY created_at DESC"
                ),
                (organization_id, project_id, dataset_id),
            ).fetchall()
        return [self._mapping_row(row) for row in rows]

    def _mapping_row(self, row: Any) -> dict[str, Any]:
        item = self._dict(row)
        payload = self._decode_json(item.pop("mapping_json"))
        item["property_mapping"] = payload.get("property_mapping", {})
        item["relationship_mapping"] = payload.get("relationship_mapping", [])
        item["content_fields"] = payload.get("content_fields", [])
        item["allowed_roles"] = payload.get("allowed_roles", [])
        return item

    def list_projections(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [organization_id, project_id, dataset_id]
        where = "organization_id=? AND project_id=? AND dataset_id=?"
        if version_id:
            where += " AND dataset_version_id=?"
            params.append(version_id)
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(f"SELECT * FROM store_projections WHERE {where} ORDER BY updated_at,store_kind"),
                tuple(params),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def list_project_projections(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [organization_id, project_id]
        where = "p.organization_id=? AND p.project_id=?"
        if workspace_id is not None:
            where += " AND p.workspace_id=?"
            params.append(workspace_id)
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    f"""
                    SELECT p.*,d.display_name AS dataset_name,v.version_label,v.version_number,
                           v.checksum_sha256,v.status AS dataset_version_status
                    FROM store_projections p
                    JOIN datasets d ON d.id=p.dataset_id
                    JOIN dataset_versions v ON v.id=p.dataset_version_id
                    WHERE {where}
                    ORDER BY p.updated_at DESC,p.dataset_id,p.store_kind
                    """
                ),
                tuple(params),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def get_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        projection_id: str,
    ) -> dict[str, Any]:
        with self._connect(organization_id, project_id) as connection:
            row = connection.execute(
                self._sql(
                    "SELECT * FROM store_projections WHERE id=? AND organization_id=? AND project_id=?"
                ),
                (projection_id, organization_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError(projection_id)
        return self._dict(row)

    def claim_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        projection_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect(organization_id, project_id) as connection:
            cursor = connection.execute(
                self._sql(
                    """
                    UPDATE store_projections
                    SET status='indexing',attempt_count=attempt_count+1,started_at=?,
                        completed_at=NULL,last_error=NULL,updated_at=?
                    WHERE id=? AND organization_id=? AND project_id=? AND status IN ('pending','failed')
                    """
                ),
                (now, now, projection_id, organization_id, project_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("projection is not claimable")
            row = connection.execute(
                self._sql("SELECT * FROM store_projections WHERE id=?"),
                (projection_id,),
            ).fetchone()
        return self._dict(row)

    def complete_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        projection_id: str,
        record_count: int,
    ) -> None:
        now = self._now()
        with self._connect(organization_id, project_id) as connection:
            cursor = connection.execute(
                self._sql(
                    """
                    UPDATE store_projections
                    SET status='ready',record_count=?,completed_at=?,last_error=NULL,updated_at=?
                    WHERE id=? AND organization_id=? AND project_id=? AND status='indexing'
                    """
                ),
                (record_count, now, now, projection_id, organization_id, project_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("projection completion lost scope or lease")
            self._refresh_version_status(connection, projection_id)

    def fail_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        projection_id: str,
        error_message: str,
    ) -> None:
        now = self._now()
        with self._connect(organization_id, project_id) as connection:
            connection.execute(
                self._sql(
                    """
                    UPDATE store_projections
                    SET status='failed',last_error=?,completed_at=?,updated_at=?
                    WHERE id=? AND organization_id=? AND project_id=?
                    """
                ),
                (error_message[:4000], now, now, projection_id, organization_id, project_id),
            )
            self._refresh_version_status(connection, projection_id)

    def retry_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        projection_id: str,
    ) -> None:
        with self._connect(organization_id, project_id) as connection:
            cursor = connection.execute(
                self._sql(
                    """
                    UPDATE store_projections
                    SET status='pending',last_error=NULL,started_at=NULL,completed_at=NULL,updated_at=?
                    WHERE id=? AND organization_id=? AND project_id=? AND status='failed'
                    """
                ),
                (self._now(), projection_id, organization_id, project_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("only failed projections can be retried")

    def _refresh_version_status(self, connection: Any, projection_id: str) -> None:
        projection = connection.execute(
            self._sql("SELECT dataset_version_id FROM store_projections WHERE id=?"),
            (projection_id,),
        ).fetchone()
        if projection is None:
            return
        version_id = self._dict(projection)["dataset_version_id"]
        rows = connection.execute(
            self._sql("SELECT status FROM store_projections WHERE dataset_version_id=?"),
            (version_id,),
        ).fetchall()
        statuses = {self._dict(row)["status"] for row in rows}
        status = "ready" if statuses == {"ready"} else "failed" if "failed" in statuses else "projecting"
        connection.execute(
            self._sql("UPDATE dataset_versions SET status=? WHERE id=?"),
            (status, version_id),
        )

    def create_materialization(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
        version_id: str,
        actor_user_id: str,
        request: MaterializationCreateRequest,
    ) -> dict[str, Any]:
        materialization_id = f"mat-{uuid.uuid4()}"
        with self._connect(organization_id, project_id) as connection:
            version = connection.execute(
                self._sql(
                    "SELECT workspace_id FROM dataset_versions WHERE id=? AND dataset_id=? AND organization_id=? AND project_id=?"
                ),
                (version_id, dataset_id, organization_id, project_id),
            ).fetchone()
            if version is None:
                raise KeyError(version_id)
            workspace_id = self._dict(version)["workspace_id"]
            connection.execute(
                self._sql(
                    """
                    INSERT INTO materializations(
                        id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                        source_kind,source_reference,format,artifact_uri,checksum_sha256,
                        record_count,status,metadata_json,created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                ),
                (
                    materialization_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    dataset_id,
                    version_id,
                    request.source_kind,
                    request.source_reference,
                    request.format,
                    request.artifact_uri,
                    request.checksum_sha256.lower(),
                    request.record_count,
                    "ready",
                    self._json(request.metadata),
                    actor_user_id,
                    self._now(),
                ),
            )
            row = connection.execute(
                self._sql("SELECT * FROM materializations WHERE id=?"),
                (materialization_id,),
            ).fetchone()
        return self._materialization_row(row)

    def list_materializations(
        self,
        *,
        organization_id: str,
        project_id: str,
        dataset_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect(organization_id, project_id) as connection:
            rows = connection.execute(
                self._sql(
                    "SELECT * FROM materializations WHERE organization_id=? AND project_id=? AND dataset_id=? ORDER BY created_at DESC"
                ),
                (organization_id, project_id, dataset_id),
            ).fetchall()
        return [self._materialization_row(row) for row in rows]

    def _materialization_row(self, row: Any) -> dict[str, Any]:
        item = self._dict(row)
        item["metadata"] = self._decode_json(item.pop("metadata_json"))
        return item
