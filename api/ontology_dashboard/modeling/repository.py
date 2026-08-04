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
        self.is_postgresql = self.database.startswith(
            ("postgresql://", "postgresql+psycopg://")
        )

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self.is_postgresql:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - production dependency gate
                raise RuntimeError(
                    "PostgreSQL adaptive modeling requires psycopg"
                ) from exc
            database_url = self.database.replace(
                "postgresql+psycopg://", "postgresql://", 1
            )
            connection = psycopg.connect(database_url, row_factory=dict_row)
        else:
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

    def _execute(
        self,
        connection: Any,
        statement: str,
        parameters: tuple[Any, ...] | list[Any] = (),
    ) -> Any:
        sql = statement.replace("?", "%s") if self.is_postgresql else statement
        return connection.execute(sql, parameters)

    def _set_scope(
        self,
        connection: Any,
        organization_id: str,
        project_id: str,
    ) -> None:
        if not self.is_postgresql:
            return
        self._execute(
            connection,
            """
            SELECT
                set_config('app.organization_id', ?, true),
                set_config('app.project_id', ?, true)
            """,
            (organization_id, project_id),
        )

    def _encode_payload(self, payload: dict[str, Any]) -> Any:
        if self.is_postgresql:
            from psycopg.types.json import Jsonb

            return Jsonb(payload)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _decode_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return json.loads(value)

    @staticmethod
    def _is_integrity_error(exc: Exception) -> bool:
        return isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ in {
            "IntegrityError",
            "UniqueViolation",
            "ForeignKeyViolation",
            "CheckViolation",
        }

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
        rendered = self._encode_payload(payload)
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            if idempotency_key:
                existing = self._execute(
                    connection,
                    f"SELECT payload_json FROM {table} WHERE organization_id=? AND project_id=? AND workspace_id=? AND idempotency_key=?",
                    (organization_id, project_id, workspace_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return self._decode_payload(existing["payload_json"])
            try:
                self._execute(
                    connection,
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
            except Exception as exc:
                if not self._is_integrity_error(exc):
                    raise
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
            self._set_scope(connection, organization_id, project_id)
            row = self._execute(
                connection,
                f"SELECT payload_json FROM {table} WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?",
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return self._decode_payload(row["payload_json"])

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
            self._set_scope(connection, organization_id, project_id)
            rows = self._execute(
                connection,
                f"SELECT payload_json FROM {table} WHERE organization_id=? AND project_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (organization_id, project_id, workspace_id, max(1, min(limit, 500))),
            ).fetchall()
        return [self._decode_payload(row["payload_json"]) for row in rows]

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
            self._set_scope(connection, organization_id, project_id)
            row = self._execute(
                connection,
                f"SELECT {status_column},revision,payload_json FROM {table} WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?",
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(identity)
            if int(row["revision"]) != expected_revision:
                raise ValueError("optimistic revision conflict")
            ensure_transition(str(row[status_column]), target_status, transition_kind)
            payload = self._decode_payload(row["payload_json"])
            payload.update(updated_payload or {})
            payload["status"] = target_status
            payload["revision"] = expected_revision + 1
            rendered = self._encode_payload(payload)
            result = self._execute(
                connection,
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

    def activate_model_version(
        self,
        identity: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        expected_revision: int,
        allowed_current_statuses: set[str],
    ) -> dict[str, Any]:
        """Atomically retire the current task model and activate the target.

        PostgreSQL locks all model rows in the project/workspace. SQLite uses an
        IMMEDIATE transaction. This prevents two administrators from leaving
        two active versions for the same prediction task.
        """

        table, identity_column, status_column = TABLES["model_version"]
        with self._connection() as connection:
            if not self.is_postgresql:
                self._execute(connection, "BEGIN IMMEDIATE")
            self._set_scope(connection, organization_id, project_id)
            lock_suffix = " FOR UPDATE" if self.is_postgresql else ""
            target_row = self._execute(
                connection,
                f"""
                SELECT {status_column},revision,payload_json
                FROM {table}
                WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?
                {lock_suffix}
                """,
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
            if target_row is None:
                raise KeyError(identity)
            current_status = str(target_row[status_column])
            if current_status not in allowed_current_statuses:
                raise ValueError(
                    "activation target must be " + " or ".join(sorted(allowed_current_statuses))
                )
            if int(target_row["revision"]) != expected_revision:
                raise ValueError("optimistic revision conflict")
            ensure_transition(current_status, "active", "model")
            target_payload = self._decode_payload(target_row["payload_json"])
            prediction_task = str(target_payload["prediction_task"])

            rows = self._execute(
                connection,
                f"""
                SELECT {identity_column},{status_column},revision,payload_json
                FROM {table}
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                {lock_suffix}
                """,
                (organization_id, project_id, workspace_id),
            ).fetchall()
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                active_identity = str(row[identity_column])
                if active_identity == identity or str(row[status_column]) != "active":
                    continue
                active_payload = self._decode_payload(row["payload_json"])
                if str(active_payload.get("prediction_task")) != prediction_task:
                    continue
                active_revision = int(row["revision"])
                ensure_transition("active", "retired", "model")
                active_payload.update(
                    {
                        "status": "retired",
                        "revision": active_revision + 1,
                        "retired_at": now,
                    }
                )
                retired = self._execute(
                    connection,
                    f"""
                    UPDATE {table}
                    SET {status_column}=?,revision=?,payload_json=?,updated_at=?
                    WHERE {identity_column}=? AND revision=?
                    """,
                    (
                        "retired",
                        active_revision + 1,
                        self._encode_payload(active_payload),
                        now,
                        active_identity,
                        active_revision,
                    ),
                )
                if retired.rowcount != 1:
                    raise ValueError("concurrent active model retirement conflict")

            target_payload.update(
                {
                    "status": "active",
                    "revision": expected_revision + 1,
                    "activated_at": now,
                    "retired_at": None,
                }
            )
            activated = self._execute(
                connection,
                f"""
                UPDATE {table}
                SET {status_column}=?,revision=?,payload_json=?,updated_at=?
                WHERE {identity_column}=? AND revision=?
                """,
                (
                    "active",
                    expected_revision + 1,
                    self._encode_payload(target_payload),
                    now,
                    identity,
                    expected_revision,
                ),
            )
            if activated.rowcount != 1:
                raise ValueError("concurrent model activation conflict")
        return target_payload

    def update(
        self,
        kind: Literal["manifest_draft", "mapping_set", "recipe_set", "experiment"],
        identity: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        expected_revision: int,
        updated_payload: dict[str, Any],
    ) -> dict[str, Any]:
        table, identity_column, status_column = TABLES[kind]
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            row = self._execute(
                connection,
                f"SELECT {status_column},revision,payload_json FROM {table} WHERE {identity_column}=? AND organization_id=? AND project_id=? AND workspace_id=?",
                (identity, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(identity)
            if int(row["revision"]) != expected_revision:
                raise ValueError("optimistic revision conflict")
            payload = self._decode_payload(row["payload_json"])
            if str(row[status_column]) != "draft" and kind in {"manifest_draft", "mapping_set", "recipe_set"}:
                raise ValueError(f"{kind} is immutable after review decision")
            if kind == "experiment" and str(row[status_column]) != "running":
                raise ValueError("Experiment Run payload is mutable only while running")
            payload.update(updated_payload)
            payload["revision"] = expected_revision + 1
            rendered = self._encode_payload(payload)
            result = self._execute(
                connection,
                f"UPDATE {table} SET revision=?,payload_json=?,updated_at=? WHERE {identity_column}=? AND revision=?",
                (
                    expected_revision + 1,
                    rendered,
                    datetime.now(timezone.utc).isoformat(),
                    identity,
                    expected_revision,
                ),
            )
            if result.rowcount != 1:
                raise ValueError("concurrent update conflict")
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
            self._set_scope(connection, organization_id, project_id)
            self._execute(
                connection,
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
                    self._encode_payload(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_audit(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        aggregate_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = [
            "organization_id=?",
            "project_id=?",
            "workspace_id=?",
        ]
        parameters: list[Any] = [organization_id, project_id, workspace_id]
        if aggregate_type:
            clauses.append("aggregate_type=?")
            parameters.append(aggregate_type)
        parameters.append(max(1, min(limit, 1000)))
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            rows = self._execute(
                connection,
                """
                SELECT actor_id,action,aggregate_type,aggregate_id,payload_json,created_at
                FROM modeling_audit_log
                WHERE """
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [
            {
                "actor_id": str(row["actor_id"]),
                "action": str(row["action"]),
                "aggregate_type": str(row["aggregate_type"]),
                "aggregate_id": str(row["aggregate_id"]),
                "payload": self._decode_payload(row["payload_json"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def put_release_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        rendered = self._encode_payload(payload)
        with self._connection() as connection:
            self._set_scope(
                connection,
                str(payload["organization_id"]),
                str(payload["project_id"]),
            )
            existing = self._execute(
                connection,
                """
                SELECT payload_json
                FROM modeling_model_release_requests
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                  AND model_version_id=? AND status='pending'
                """,
                (
                    payload["organization_id"],
                    payload["project_id"],
                    payload["workspace_id"],
                    payload["model_version_id"],
                ),
            ).fetchone()
            if existing is not None:
                return self._decode_payload(existing["payload_json"])
            self._execute(
                connection,
                """
                INSERT INTO modeling_model_release_requests(
                    release_request_id,organization_id,project_id,workspace_id,
                    model_version_id,status,revision,requested_by,request_rationale,
                    decided_by,decision_rationale,payload_json,created_at,decided_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload["release_request_id"],
                    payload["organization_id"],
                    payload["project_id"],
                    payload["workspace_id"],
                    payload["model_version_id"],
                    payload["status"],
                    payload.get("revision", 1),
                    payload["requested_by"],
                    payload["request_rationale"],
                    payload.get("decided_by"),
                    payload.get("decision_rationale"),
                    rendered,
                    payload.get("created_at", now),
                    payload.get("decided_at"),
                ),
            )
        return payload

    def get_release_request(
        self,
        release_request_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            row = self._execute(
                connection,
                """
                SELECT payload_json
                FROM modeling_model_release_requests
                WHERE release_request_id=? AND organization_id=? AND project_id=? AND workspace_id=?
                """,
                (release_request_id, organization_id, project_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(release_request_id)
        return self._decode_payload(row["payload_json"])

    def list_release_requests(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            rows = self._execute(
                connection,
                """
                SELECT payload_json
                FROM modeling_model_release_requests
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (organization_id, project_id, workspace_id, max(1, min(limit, 500))),
            ).fetchall()
        return [self._decode_payload(row["payload_json"]) for row in rows]

    def decide_release_request(
        self,
        release_request_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        expected_revision: int,
        status: Literal["approved", "rejected"],
        decided_by: str,
        decision_rationale: str,
    ) -> dict[str, Any]:
        with self._connection() as connection:
            self._set_scope(connection, organization_id, project_id)
            row = self._execute(
                connection,
                """
                SELECT status,revision,payload_json
                FROM modeling_model_release_requests
                WHERE release_request_id=? AND organization_id=? AND project_id=? AND workspace_id=?
                """,
                (release_request_id, organization_id, project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(release_request_id)
            if row["status"] != "pending":
                raise ValueError("model release request is already decided")
            if int(row["revision"]) != expected_revision:
                raise ValueError("optimistic revision conflict")
            payload = self._decode_payload(row["payload_json"])
            decided_at = datetime.now(timezone.utc).isoformat()
            payload.update(
                {
                    "status": status,
                    "revision": expected_revision + 1,
                    "decided_by": decided_by,
                    "decision_rationale": decision_rationale,
                    "decided_at": decided_at,
                }
            )
            rendered = self._encode_payload(payload)
            result = self._execute(
                connection,
                """
                UPDATE modeling_model_release_requests
                SET status=?,revision=?,decided_by=?,decision_rationale=?,payload_json=?,decided_at=?
                WHERE release_request_id=? AND revision=?
                """,
                (
                    status,
                    expected_revision + 1,
                    decided_by,
                    decision_rationale,
                    rendered,
                    decided_at,
                    release_request_id,
                    expected_revision,
                ),
            )
            if result.rowcount != 1:
                raise ValueError("concurrent release decision conflict")
        return payload
