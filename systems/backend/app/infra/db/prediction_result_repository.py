from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.diagnosis.diagnosis_schema import PredictionResult


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


class PredictionResultRepository:
    def __init__(
        self,
        database_path: str | Path,
        *,
        project_context: ProjectContextResolverPort,
    ) -> None:
        self.path = Path(database_path)
        self.project_context = project_context

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, result: PredictionResult) -> dict[str, Any]:
        with self._connect() as connection:
            scope = self.project_context.resolve(
                result.workspace_id,
                expected_organization_id=result.organization_id,
                expected_project_id=result.project_id,
                connection=connection,
            )
            connection.execute(
                """
                INSERT INTO prediction_results(
                    prediction_id,organization_id,project_id,workspace_id,
                    subject_object_type,subject_object_id,prediction_status,
                    model_version,dataset_version,payload_json,created_at,received_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(prediction_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    prediction_status=excluded.prediction_status,
                    model_version=excluded.model_version,
                    dataset_version=excluded.dataset_version,
                    received_at=excluded.received_at
                WHERE prediction_results.organization_id=excluded.organization_id
                  AND prediction_results.project_id=excluded.project_id
                  AND prediction_results.workspace_id=excluded.workspace_id
                """,
                (
                    result.prediction_id,
                    scope.organization_id,
                    scope.project_id,
                    scope.workspace_id,
                    result.subject.object_type,
                    result.subject.object_id,
                    result.prediction.status,
                    result.model.model_version,
                    result.model.dataset_version,
                    result.model_dump_json(),
                    result.created_at.isoformat(),
                    self._now(),
                ),
            )
            row = connection.execute(
                """
                SELECT prediction_id,organization_id,project_id,workspace_id,
                       subject_object_type,subject_object_id,prediction_status,
                       model_version,dataset_version,created_at,received_at
                FROM prediction_results
                WHERE prediction_id=? AND organization_id=? AND project_id=?
                """,
                (result.prediction_id, scope.organization_id, scope.project_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("prediction result scope conflict")
        return dict(row)

    def list(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["organization_id=?", "project_id=?"]
        parameters: list[Any] = [organization_id, project_id]
        if workspace_id is not None:
            with self._connect() as connection:
                self.project_context.resolve(
                    workspace_id,
                    expected_organization_id=organization_id,
                    expected_project_id=project_id,
                    connection=connection,
                )
            clauses.append("workspace_id=?")
            parameters.append(workspace_id)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT prediction_id,organization_id,project_id,workspace_id,
                       subject_object_type,subject_object_id,prediction_status,
                       model_version,dataset_version,created_at,received_at
                FROM prediction_results
                WHERE """ + " AND ".join(clauses) + " ORDER BY created_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_payload(
        self,
        *,
        organization_id: str,
        project_id: str,
        prediction_id: str,
    ) -> PredictionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM prediction_results
                WHERE organization_id=? AND project_id=? AND prediction_id=?
                """,
                (organization_id, project_id, prediction_id),
            ).fetchone()
        return None if row is None else PredictionResult.model_validate_json(row["payload_json"])
