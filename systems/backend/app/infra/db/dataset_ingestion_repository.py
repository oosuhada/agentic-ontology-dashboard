from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.dataset.ingestion.ingestion_schema import DatasetManifest, QuarantinedRecord


DEFAULT_ORGANIZATION_ID = "org-ontology-demo"
DEFAULT_PROJECT_ID = "manufacturing-demo-project"
DEFAULT_WORKSPACE_ID = "manufacturing-demo"


class DatasetIngestionRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _resolve_scope(
        self,
        connection: Any,
        workspace_id: str,
        *,
        expected_organization_id: str,
        expected_project_id: str,
    ) -> tuple[str, str, str]:
        resolver = getattr(self, "project_context", None)
        if resolver is not None:
            scope = resolver.resolve(
                workspace_id,
                expected_organization_id=expected_organization_id,
                expected_project_id=expected_project_id,
                connection=connection,
            )
            return scope.organization_id, scope.project_id, scope.workspace_id
        row = None
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'"
        ).fetchone()
        if table_exists:
            row = connection.execute(
                "SELECT organization_id,project_id FROM workspaces WHERE id=?",
                (workspace_id,),
            ).fetchone()
        if row is None:
            if workspace_id != DEFAULT_WORKSPACE_ID:
                raise ValueError(f"workspace {workspace_id!r} is not assigned to an accessible Project")
            organization_id = DEFAULT_ORGANIZATION_ID
            project_id = DEFAULT_PROJECT_ID
        else:
            organization_id = str(row["organization_id"] or "").strip()
            project_id = str(row["project_id"] or "").strip()
        if organization_id != expected_organization_id:
            raise ValueError("workspace organization scope does not match the request context")
        if project_id != expected_project_id:
            raise ValueError("workspace project scope does not match the request context")
        return organization_id, project_id, workspace_id

    def save_manifest(self, manifest: DatasetManifest) -> None:
        with self._connect() as connection:
            organization_id, project_id, workspace_id = self._resolve_scope(
                connection,
                manifest.workspace_id,
                expected_organization_id=manifest.organization_id,
                expected_project_id=manifest.project_id,
            )
            now = self._now()
            connection.execute(
                """
                INSERT INTO dataset_manifests(
                    id,organization_id,project_id,workspace_id,adapter_code,dataset_name,
                    dataset_version,source_uri,source_checksum,media_type,manifest_json,
                    status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    dataset_version=excluded.dataset_version,
                    source_uri=excluded.source_uri,
                    source_checksum=excluded.source_checksum,
                    media_type=excluded.media_type,
                    manifest_json=excluded.manifest_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    manifest.manifest_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    manifest.adapter_code,
                    manifest.dataset_name,
                    manifest.dataset_version,
                    manifest.source.uri,
                    manifest.source.checksum_sha256,
                    manifest.source.media_type,
                    manifest.model_dump_json(by_alias=True),
                    "registered",
                    manifest.created_at.isoformat(),
                    now,
                ),
            )

    def start_run(self, manifest: DatasetManifest) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as connection:
            self._resolve_scope(
                connection,
                manifest.workspace_id,
                expected_organization_id=manifest.organization_id,
                expected_project_id=manifest.project_id,
            )
            connection.execute(
                """
                INSERT INTO adapter_ingestion_runs(
                    id,organization_id,project_id,workspace_id,manifest_id,adapter_code,
                    status,started_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    manifest.organization_id,
                    manifest.project_id,
                    manifest.workspace_id,
                    manifest.manifest_id,
                    manifest.adapter_code,
                    "running",
                    self._now(),
                ),
            )
        return run_id

    def complete_run(
        self,
        *,
        run_id: str,
        manifest: DatasetManifest,
        source_count: int,
        accepted_count: int,
        quarantined: list[QuarantinedRecord],
        error_message: str | None = None,
    ) -> None:
        status = (
            "failed"
            if error_message is not None
            else ("completed_with_quarantine" if quarantined else "completed")
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE adapter_ingestion_runs
                SET status=?,source_record_count=?,accepted_record_count=?,
                    quarantined_record_count=?,error_message=?,completed_at=?
                WHERE id=? AND organization_id=? AND project_id=? AND workspace_id=?
                """,
                (
                    status,
                    source_count,
                    accepted_count,
                    len(quarantined),
                    error_message,
                    self._now(),
                    run_id,
                    manifest.organization_id,
                    manifest.project_id,
                    manifest.workspace_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("ingestion run scope changed or no longer exists")
            connection.executemany(
                """
                INSERT INTO adapter_quarantine_records(
                    id,organization_id,project_id,workspace_id,ingestion_run_id,
                    source_row_number,error_code,error_message,record_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        str(uuid.uuid4()),
                        manifest.organization_id,
                        manifest.project_id,
                        manifest.workspace_id,
                        run_id,
                        item.source_row_number,
                        item.error_code,
                        item.error_message,
                        json.dumps(item.record, ensure_ascii=False, sort_keys=True),
                        self._now(),
                    )
                    for item in quarantined
                ],
            )
            connection.execute(
                "UPDATE dataset_manifests SET status=?,updated_at=? WHERE id=? AND project_id=?",
                (status, self._now(), manifest.manifest_id, manifest.project_id),
            )

    def list_manifests(
        self,
        *,
        organization_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id,organization_id,project_id,workspace_id,adapter_code,dataset_name,
                       dataset_version,source_uri,source_checksum,media_type,status,
                       created_at,updated_at
                FROM dataset_manifests
                WHERE organization_id=? AND project_id=?
                ORDER BY updated_at DESC,id
                """,
                (organization_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, *, run_id: str, organization_id: str, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM adapter_ingestion_runs
                WHERE id=? AND organization_id=? AND project_id=?
                """,
                (run_id, organization_id, project_id),
            ).fetchone()
        return None if row is None else dict(row)
