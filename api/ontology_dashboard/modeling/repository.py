from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from .models import ensure_transition

RecordKind = Literal[
    "intake_profile",
    "manifest_draft",
    "mapping_set",
    "recipe_set",
    "feature_dataset",
    "experiment",
    "model_version",
    "explanation",
]

TABLES: dict[RecordKind, tuple[str, str, str]] = {
    "intake_profile": ("modeling_intake_profiles", "profile_id", "status"),
    "manifest_draft": ("modeling_manifest_drafts", "draft_id", "status"),
    "mapping_set": ("modeling_mapping_sets", "mapping_set_id", "status"),
    "recipe_set": ("modeling_feature_recipe_sets", "recipe_set_id", "status"),
    "feature_dataset": (
        "modeling_feature_dataset_versions",
        "feature_dataset_version_id",
        "status",
    ),
    "experiment": ("modeling_experiment_runs", "experiment_id", "status"),
    "model_version": ("modeling_model_versions", "model_version_id", "status"),
    "explanation": ("modeling_explanation_artifacts", "explanation_id", "status"),
}


class ModelingRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _scope(payload: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(payload["organization_id"]),
            str(payload["project_id"]),
            str(payload["workspace_id"]),
        )

    def put(
        self,
        kind: RecordKind,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        table, identity_column, status_column = TABLES[kind]
        identity = str(payload[identity_column])
        organization_id, project_id, workspace_id = self._scope(payload)
        revision = int(payload.get("revision", 1))
        status = str(payload.get("status", "available"))
        dataset_version_id = payload.get("dataset_version_id")
        parent_keys = {
            "intake_profile": None,
            "manifest_draft": "profile_id",
            "mapping_set": "dataset_version_id",
            "recipe_set": "mapping_set_id",
            "feature_dataset": "recipe_set_id",
            "experiment": "feature_dataset_version_id",
            "model_version": "experiment_id",
            "explanation": "model_version_id",
        }
        parent_key = parent_keys[kind]
        parent_id = payload.get(parent_key) if parent_key else None
        checksum_keys = {
            "intake_profile": "source_checksum_sha256",
            "manifest_draft": "source_checksum_sha256",
            "mapping_set": "checksum_sha256",
            "recipe_set": "checksum_sha256",
            "feature_dataset": "materialization_checksum_sha256",
            "experiment": None,
            "model_version": None,
            "explanation": "checksum_sha256",
        }
        checksum_key = checksum_keys[kind]
        checksum_sha256 = payload.get(checksum_key) if checksum_key else None
        artifact = payload.get("artifact") or {}
        if kind == "model_version":
            checksum_sha256 = artifact.get("checksum_sha256")
        artifact_uri = artifact.get("uri") if isinstance(artifact, dict) else None
        now = datetime.now(timezone.utc).isoformat()
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        with self._connection() as connection:
            if idempotency_key:
                existing = connection.execute(
                    f"SELECT payload_json FROM {table} WHERE organization_id=? AND project_id=? AND workspace_id=? AND idempotency_key=?",
                    (organization_id, project_id, workspace_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return json.loads(existing["payload_json"])
            try:
                connection.execute(
                    f"""
                    INSERT INTO {table}(
                        {identity_column},organization_id,project_id,workspace_id,
                        dataset_version_id,parent_id,checksum_sha256,artifact_uri,
                        {status_column},revision,idempotency_key,payload_json,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        identity,
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_version_id,
                        parent_id,
                        checksum_sha256,
                        artifact_uri,
                        status,
                        revision,
                        idempotency_key,
                        rendered,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"duplicate or invalid {kind} identity: {identity}") from exc
        return payload

    def get(
        self,
        kind: RecordKind,
        identity: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        table, identity_column, _ = TABLES[kind]
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?",
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row["payload_json"])

    def list(
        self,
        kind: RecordKind,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        table, _, _ = TABLES[kind]
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM {table} WHERE organization_id=? AND project_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (organization_id, project_id, workspace_id, max(1, min(limit, 500))),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def transition(
        self,
        kind: Literal[
            "manifest_draft",
            "mapping_set",
            "recipe_set",
            "feature_dataset",
            "experiment",
            "model_version",
        ],
        identity: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        target_status: str,
        expected_revision: int,
        transition_kind: Literal["review", "run", "model"],
        updated_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        table, identity_column, status_column = TABLES[kind]
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT {status_column},revision,payload_json FROM {table} WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?",
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(identity)
            if int(row["revision"]) != expected_revision:
                raise ValueError("optimistic revision conflict")
            ensure_transition(str(row[status_column]), target_status, transition_kind)
            payload = json.loads(row["payload_json"])
            payload.update(updated_payload or {})
            payload["status"] = target_status
            payload["revision"] = expected_revision + 1
            rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
            result = connection.execute(
                f"UPDATE {table} SET {status_column}=?,revision=?,payload_json=?,updated_at=? WHERE {identity_column}=? AND revision=?",
                (
                    target_status,
                    expected_revision + 1,
                    rendered,
                    datetime.now(timezone.utc).isoformat(),
                    identity,
                    expected_revision,
                ),
            )
            if result.rowcount != 1:
                raise ValueError("concurrent transition conflict")
        return payload

    def record_audit(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        actor_id: str,
        action: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO modeling_audit_log(
                    organization_id,project_id,workspace_id,actor_id,action,
                    aggregate_type,aggregate_id,payload_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    actor_id,
                    action,
                    aggregate_type,
                    aggregate_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
