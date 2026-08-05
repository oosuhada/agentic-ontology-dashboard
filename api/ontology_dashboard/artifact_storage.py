"""Object-storage abstraction and governed artifact catalog.

PostgreSQL is authoritative for ownership, metadata, retention and audit. Object
storage is authoritative only for immutable bytes. Local storage implements the
same contract for tests and single-node demos without exposing filesystem paths.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Protocol
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict, Field

from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql


ArtifactBackend = Literal["local", "s3", "gcs", "azure"]
ArtifactState = Literal[
    "available",
    "missing",
    "checksum_mismatch",
    "quarantined",
    "retention_pending",
    "deleted",
]
RetentionClass = Literal["ephemeral", "standard", "regulated", "backup", "legal_hold"]
ResourceType = Literal[
    "dataset_file",
    "materialization",
    "model",
    "evaluation",
    "feature_manifest",
    "explanation",
    "report",
    "export",
    "backup",
    "pipeline",
    "other",
]


class ArtifactStorageError(RuntimeError):
    pass


class ArtifactNotConfigured(ArtifactStorageError):
    pass


class ArtifactIntegrityError(ArtifactStorageError):
    pass


class ArtifactPermissionError(ArtifactStorageError):
    pass


class ArtifactObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    organization_id: str
    project_id: str
    workspace_id: str | None = None
    resource_type: ResourceType
    resource_id: str
    resource_version: str
    object_key: str
    uri: str
    backend: ArtifactBackend
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    state: ArtifactState
    retention_class: RetentionClass
    retain_until: datetime | None = None
    legal_hold: bool = False
    created_by: str
    created_at: datetime
    verified_at: datetime | None = None
    deleted_at: datetime | None = None


class SignedArtifactDownload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    url: str
    expires_at: datetime
    media_type: str
    size_bytes: int
    checksum_sha256: str


class ArtifactReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    mode: Literal["dry_run", "apply"]
    catalog_count: int
    object_count: int
    verified: tuple[str, ...]
    missing: tuple[str, ...]
    checksum_mismatch: tuple[str, ...]
    orphan_keys: tuple[str, ...]
    completed_at: datetime


class ArtifactRetentionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    object_key: str
    retention_class: RetentionClass
    retain_until: datetime | None
    legal_hold: bool
    action: Literal["retain", "delete", "skip_legal_hold"]
    reason: str


class ArtifactGovernanceReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "degraded", "not_configured", "blocked"]
    backend: ArtifactBackend
    bucket: str | None
    endpoint_configured: bool
    credential_reference_configured: bool
    encryption: str
    versioning: str
    signed_downloads: str
    deterministic_key_schema: str
    checksum: str
    retention_classes: tuple[RetentionClass, ...]
    reconciliation: str
    blockers: tuple[str, ...]


class ArtifactGovernanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness: ArtifactGovernanceReadiness
    artifacts: tuple[ArtifactObject, ...]
    retention_preview: tuple[ArtifactRetentionCandidate, ...]
    last_reconciliation: ArtifactReconciliationReport | None = None


class ArtifactOperatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=3, max_length=500)


class ObjectMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    checksum_sha256: str
    size_bytes: int
    media_type: str
    custom: dict[str, str]
    modified_at: datetime


class ObjectStorageBackend(Protocol):
    backend: ArtifactBackend

    def put(self, key: str, content: bytes, *, media_type: str, metadata: Mapping[str, str]) -> ObjectMetadata: ...
    def get(self, key: str) -> bytes: ...
    def head(self, key: str) -> ObjectMetadata | None: ...
    def delete(self, key: str) -> None: ...
    def list_keys(self, prefix: str) -> tuple[str, ...]: ...


_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,180}$")


def safe_segment(value: str) -> str:
    rendered = value.strip()
    if not _SEGMENT_PATTERN.fullmatch(rendered) or rendered in {".", ".."}:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
        rendered = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")[:80]
        rendered = f"{rendered or 'value'}-{digest}"
    return rendered


def deterministic_object_key(
    *,
    organization_id: str,
    project_id: str,
    workspace_id: str | None,
    resource_type: ResourceType,
    resource_id: str,
    resource_version: str,
    checksum_sha256: str,
    media_type: str,
) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", checksum_sha256):
        raise ValueError("checksum_sha256 must be a lowercase SHA-256 digest")
    extension = mimetypes.guess_extension(media_type, strict=False) or ".bin"
    workspace = safe_segment(workspace_id or "project")
    return "/".join(
        (
            "organizations",
            safe_segment(organization_id),
            "projects",
            safe_segment(project_id),
            "workspaces",
            workspace,
            "artifacts",
            safe_segment(resource_type),
            safe_segment(resource_id),
            "versions",
            safe_segment(resource_version),
            checksum_sha256[:2],
            f"{checksum_sha256}{extension}",
        )
    )


class LocalObjectStorageBackend:
    backend: ArtifactBackend = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or "\\" in key:
            raise ValueError("object key must be a portable relative path")
        decoded = unquote(key)
        if any(part in {"", ".", ".."} for part in decoded.split("/")):
            raise ValueError("object key contains an invalid segment")
        path = (self.root / decoded).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("object key escapes the configured storage root")
        return path

    def _metadata_path(self, key: str) -> Path:
        path = self._path(key)
        return path.with_name(f"{path.name}.metadata.json")

    def put(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> ObjectMetadata:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256(content).hexdigest()
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        modified = datetime.now(timezone.utc)
        sidecar = {
            "checksum_sha256": checksum,
            "size_bytes": len(content),
            "media_type": media_type,
            "custom": dict(sorted(metadata.items())),
            "modified_at": modified.isoformat(),
        }
        metadata_path = self._metadata_path(key)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
        return ObjectMetadata(key=key, **sidecar)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def head(self, key: str) -> ObjectMetadata | None:
        path = self._path(key)
        if not path.is_file():
            return None
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        metadata_path = self._metadata_path(key)
        sidecar: dict[str, Any] = {}
        if metadata_path.is_file():
            try:
                sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                sidecar = {}
        return ObjectMetadata(
            key=key,
            checksum_sha256=checksum,
            size_bytes=len(content),
            media_type=str(sidecar.get("media_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
            custom={str(k): str(v) for k, v in dict(sidecar.get("custom") or {}).items()},
            modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
        )

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        self._metadata_path(key).unlink(missing_ok=True)

    def list_keys(self, prefix: str) -> tuple[str, ...]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return ()
        keys = []
        for path in base.rglob("*"):
            if not path.is_file() or path.name.endswith(".metadata.json"):
                continue
            keys.append(path.relative_to(self.root).as_posix())
        return tuple(sorted(keys))


class S3ObjectStorageBackend:
    backend: ArtifactBackend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError as error:
            raise ArtifactNotConfigured("S3 adapter requires the production storage dependency") from error
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(self, key: str, content: bytes, *, media_type: str, metadata: Mapping[str, str]) -> ObjectMetadata:
        checksum = hashlib.sha256(content).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=media_type,
            ChecksumSHA256=hashlib.sha256(content).digest(),
            Metadata={**dict(metadata), "checksum-sha256": checksum},
            ServerSideEncryption=os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_SSE", "AES256"),
        )
        return ObjectMetadata(
            key=key,
            checksum_sha256=checksum,
            size_bytes=len(content),
            media_type=media_type,
            custom=dict(metadata),
            modified_at=datetime.now(timezone.utc),
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def head(self, key: str) -> ObjectMetadata | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            response_code = getattr(error, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
            if response_code == 404:
                return None
            raise ArtifactStorageError(f"object head failed: {type(error).__name__}") from error
        checksum = response.get("Metadata", {}).get("checksum-sha256")
        if not checksum:
            checksum = hashlib.sha256(self.get(key)).hexdigest()
        return ObjectMetadata(
            key=key,
            checksum_sha256=checksum,
            size_bytes=int(response["ContentLength"]),
            media_type=response.get("ContentType") or "application/octet-stream",
            custom=dict(response.get("Metadata") or {}),
            modified_at=response["LastModified"],
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def list_keys(self, prefix: str) -> tuple[str, ...]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(str(item["Key"]) for item in page.get("Contents", []))
        return tuple(sorted(keys))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class ArtifactCatalogRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def _connect_sqlite(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _connection(self, organization_id: str, project_id: str):
        if self.postgresql:
            return postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            )
        repository = self

        class SQLiteContext:
            def __enter__(self):
                self.connection = repository._connect_sqlite()
                return self.connection

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
                self.connection.close()

        return SQLiteContext()

    @staticmethod
    def _decode(row: Mapping[str, Any] | None) -> ArtifactObject | None:
        if row is None:
            return None
        metadata = row["metadata_json"]
        provenance = row["provenance_json"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if isinstance(provenance, str):
            provenance = json.loads(provenance)
        return ArtifactObject(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            workspace_id=None if row.get("workspace_id") is None else str(row["workspace_id"]),
            resource_type=str(row["resource_type"]),
            resource_id=str(row["resource_id"]),
            resource_version=str(row["resource_version"]),
            object_key=str(row["object_key"]),
            uri=str(row["uri"]),
            backend=str(row["backend"]),
            checksum_sha256=str(row["checksum_sha256"]),
            media_type=str(row["media_type"]),
            size_bytes=int(row["size_bytes"]),
            metadata=dict(metadata),
            provenance=dict(provenance),
            state=str(row["state"]),
            retention_class=str(row["retention_class"]),
            retain_until=_parse_datetime(row.get("retain_until")),
            legal_hold=bool(row["legal_hold"]),
            created_by=str(row["created_by"]),
            created_at=_parse_datetime(row["created_at"]),
            verified_at=_parse_datetime(row.get("verified_at")),
            deleted_at=_parse_datetime(row.get("deleted_at")),
        )

    def register(
        self,
        *,
        artifact_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str | None,
        resource_type: ResourceType,
        resource_id: str,
        resource_version: str,
        object_key: str,
        uri: str,
        backend: ArtifactBackend,
        checksum_sha256: str,
        media_type: str,
        size_bytes: int,
        metadata: dict[str, Any],
        provenance: dict[str, Any],
        retention_class: RetentionClass,
        retain_until: datetime | None,
        legal_hold: bool,
        created_by: str,
    ) -> tuple[ArtifactObject, bool]:
        now = _utcnow().isoformat()
        values = (
            artifact_id,
            organization_id,
            project_id,
            workspace_id,
            resource_type,
            resource_id,
            resource_version,
            object_key,
            uri,
            backend,
            checksum_sha256,
            media_type,
            size_bytes,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            json.dumps(provenance, ensure_ascii=False, sort_keys=True),
            retention_class,
            None if retain_until is None else retain_until.isoformat(),
            bool(legal_hold),
            created_by,
            now,
            now,
        )
        with self._connection(organization_id, project_id) as connection:
            existing = connection.execute(
                """
                SELECT * FROM artifact_objects
                WHERE organization_id=? AND project_id=? AND workspace_id IS NOT DISTINCT FROM ?
                  AND resource_type=? AND resource_id=? AND resource_version=? AND checksum_sha256=?
                """ if self.postgresql else """
                SELECT * FROM artifact_objects
                WHERE organization_id=? AND project_id=? AND coalesce(workspace_id,'')=coalesce(?,'')
                  AND resource_type=? AND resource_id=? AND resource_version=? AND checksum_sha256=?
                """,
                (
                    organization_id,
                    project_id,
                    workspace_id,
                    resource_type,
                    resource_id,
                    resource_version,
                    checksum_sha256,
                ),
            ).fetchone()
            if existing is not None:
                return self._decode(dict(existing)), False
            connection.execute(
                """
                INSERT INTO artifact_objects(
                    id,organization_id,project_id,workspace_id,resource_type,resource_id,
                    resource_version,object_key,uri,backend,checksum_sha256,media_type,
                    size_bytes,metadata_json,provenance_json,retention_class,retain_until,
                    legal_hold,created_by,created_at,verified_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            row = connection.execute("SELECT * FROM artifact_objects WHERE id=?", (artifact_id,)).fetchone()
        return self._decode(dict(row)), True

    def get(self, *, organization_id: str, project_id: str, artifact_id: str) -> ArtifactObject | None:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                "SELECT * FROM artifact_objects WHERE id=? AND organization_id=? AND project_id=?",
                (artifact_id, organization_id, project_id),
            ).fetchone()
        return self._decode(None if row is None else dict(row))

    def list(
        self,
        *,
        organization_id: str,
        project_id: str,
        include_deleted: bool = False,
        limit: int = 100,
    ) -> tuple[ArtifactObject, ...]:
        deleted = "" if include_deleted else " AND deleted_at IS NULL"
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM artifact_objects
                WHERE organization_id=? AND project_id=?{deleted}
                ORDER BY created_at DESC,id DESC LIMIT ?
                """,
                (organization_id, project_id, max(1, min(500, limit))),
            ).fetchall()
        return tuple(self._decode(dict(row)) for row in rows)

    def set_state(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_id: str,
        state: ArtifactState,
        verified: bool = False,
        deleted: bool = False,
    ) -> ArtifactObject:
        now = _utcnow().isoformat()
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """
                UPDATE artifact_objects SET state=?,verified_at=CASE WHEN ? THEN ? ELSE verified_at END,
                    deleted_at=CASE WHEN ? THEN ? ELSE deleted_at END
                WHERE id=? AND organization_id=? AND project_id=?
                """,
                (state, int(verified), now, int(deleted), now, artifact_id, organization_id, project_id),
            )
            row = connection.execute("SELECT * FROM artifact_objects WHERE id=?", (artifact_id,)).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return self._decode(dict(row))

    def audit(
        self,
        *,
        artifact: ArtifactObject,
        actor_user_id: str,
        action: str,
        decision: str,
        purpose: str | None = None,
        signed_until: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        audit_id = f"artifact-audit-{uuid.uuid4()}"
        with self._connection(artifact.organization_id, artifact.project_id) as connection:
            connection.execute(
                """
                INSERT INTO artifact_access_audit(
                    id,organization_id,project_id,workspace_id,artifact_id,actor_user_id,
                    action,purpose,decision,signed_until,details_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    audit_id,
                    artifact.organization_id,
                    artifact.project_id,
                    artifact.workspace_id,
                    artifact.id,
                    actor_user_id,
                    action,
                    purpose,
                    decision,
                    None if signed_until is None else signed_until.isoformat(),
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                    _utcnow().isoformat(),
                ),
            )
        return audit_id

    def save_reconciliation(
        self,
        *,
        report: ArtifactReconciliationReport,
        organization_id: str,
        project_id: str,
        workspace_id: str | None,
        created_by: str,
    ) -> None:
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """
                INSERT INTO artifact_reconciliation_runs(
                    id,organization_id,project_id,workspace_id,mode,state,catalog_count,
                    object_count,verified_count,missing_count,mismatch_count,orphan_count,
                    details_json,created_by,created_at,completed_at
                ) VALUES (?,?,?,?,?,'succeeded',?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    report.run_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    report.mode,
                    report.catalog_count,
                    report.object_count,
                    len(report.verified),
                    len(report.missing),
                    len(report.checksum_mismatch),
                    len(report.orphan_keys),
                    json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                    created_by,
                    report.completed_at.isoformat(),
                    report.completed_at.isoformat(),
                ),
            )


@dataclass
class ArtifactGovernanceService:
    repository: ArtifactCatalogRepository
    backend: ObjectStorageBackend
    signing_secret: bytes
    download_base_path: str = "/api/platform/artifacts/download"

    def put_bytes(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None,
        resource_type: ResourceType,
        resource_id: str,
        resource_version: str,
        content: bytes,
        media_type: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        retention_class: RetentionClass = "standard",
        retain_until: datetime | None = None,
        legal_hold: bool = False,
    ) -> ArtifactObject:
        checksum = hashlib.sha256(content).hexdigest()
        key = deterministic_object_key(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            checksum_sha256=checksum,
            media_type=media_type,
        )
        object_metadata = self.backend.put(
            key,
            content,
            media_type=media_type,
            metadata={
                "organization-id": organization_id,
                "project-id": project_id,
                "workspace-id": workspace_id or "",
                "resource-type": resource_type,
                "resource-id": resource_id,
                "resource-version": resource_version,
                "checksum-sha256": checksum,
            },
        )
        if object_metadata.checksum_sha256 != checksum:
            raise ArtifactIntegrityError("object backend returned a different checksum")
        artifact, created = self.repository.register(
            artifact_id=f"artifact-{uuid.uuid4()}",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            object_key=key,
            uri=f"{self.backend.backend}://{quote(key, safe='/')}",
            backend=self.backend.backend,
            checksum_sha256=checksum,
            media_type=media_type,
            size_bytes=len(content),
            metadata={**(metadata or {}), "object_metadata": object_metadata.model_dump(mode="json")},
            provenance={
                **(provenance or {}),
                "content_checksum_sha256": checksum,
                "object_key_schema": "artifact-object-key/v1",
            },
            retention_class=retention_class,
            retain_until=retain_until,
            legal_hold=legal_hold or retention_class == "legal_hold",
            created_by=created_by,
        )
        if created:
            self.repository.audit(
                artifact=artifact,
                actor_user_id=created_by,
                action="register",
                decision="completed",
                details={"backend": self.backend.backend},
            )
        return artifact

    def verify(self, artifact: ArtifactObject, *, actor_user_id: str) -> ArtifactObject:
        metadata = self.backend.head(artifact.object_key)
        if metadata is None:
            updated = self.repository.set_state(
                organization_id=artifact.organization_id,
                project_id=artifact.project_id,
                artifact_id=artifact.id,
                state="missing",
            )
            self.repository.audit(
                artifact=artifact,
                actor_user_id=actor_user_id,
                action="verify",
                decision="failed",
                details={"reason": "missing"},
            )
            return updated
        state: ArtifactState = (
            "available"
            if metadata.checksum_sha256 == artifact.checksum_sha256
            and metadata.size_bytes == artifact.size_bytes
            else "checksum_mismatch"
        )
        updated = self.repository.set_state(
            organization_id=artifact.organization_id,
            project_id=artifact.project_id,
            artifact_id=artifact.id,
            state=state,
            verified=state == "available",
        )
        self.repository.audit(
            artifact=artifact,
            actor_user_id=actor_user_id,
            action="verify",
            decision="completed" if state == "available" else "failed",
            details={
                "catalog_checksum": artifact.checksum_sha256,
                "object_checksum": metadata.checksum_sha256,
            },
        )
        return updated

    def read_verified(self, artifact: ArtifactObject, *, actor_user_id: str, purpose: str) -> bytes:
        content = self.backend.get(artifact.object_key)
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != artifact.checksum_sha256:
            self.repository.set_state(
                organization_id=artifact.organization_id,
                project_id=artifact.project_id,
                artifact_id=artifact.id,
                state="checksum_mismatch",
            )
            self.repository.audit(
                artifact=artifact,
                actor_user_id=actor_user_id,
                action="download",
                decision="failed",
                purpose=purpose,
                details={"reason": "checksum_mismatch"},
            )
            raise ArtifactIntegrityError("artifact checksum mismatch")
        self.repository.audit(
            artifact=artifact,
            actor_user_id=actor_user_id,
            action="download",
            decision="completed",
            purpose=purpose,
        )
        return content

    def sign_download(
        self,
        artifact: ArtifactObject,
        *,
        actor_user_id: str,
        purpose: str,
        expires_seconds: int = 300,
    ) -> SignedArtifactDownload:
        if artifact.state not in {"available"} or artifact.deleted_at is not None:
            raise ArtifactPermissionError("only available artifacts can be downloaded")
        expires_at = _utcnow() + timedelta(seconds=max(30, min(900, expires_seconds)))
        expires = int(expires_at.timestamp())
        payload = f"{artifact.organization_id}|{artifact.project_id}|{artifact.id}|{actor_user_id}|{expires}"
        signature = hmac.new(self.signing_secret, payload.encode(), hashlib.sha256).hexdigest()
        token = quote(f"{actor_user_id}.{expires}.{signature}", safe="")
        self.repository.audit(
            artifact=artifact,
            actor_user_id=actor_user_id,
            action="download_sign",
            decision="allowed",
            purpose=purpose,
            signed_until=expires_at,
        )
        return SignedArtifactDownload(
            artifact_id=artifact.id,
            url=f"{self.download_base_path}/{quote(artifact.id, safe='')}?token={token}",
            expires_at=expires_at,
            media_type=artifact.media_type,
            size_bytes=artifact.size_bytes,
            checksum_sha256=artifact.checksum_sha256,
        )

    def validate_download_token(
        self,
        artifact: ArtifactObject,
        *,
        token: str,
        actor_user_id: str,
        now: datetime | None = None,
    ) -> None:
        try:
            token_actor, expires_text, signature = unquote(token).split(".", 2)
            expires = int(expires_text)
        except (ValueError, TypeError) as error:
            raise ArtifactPermissionError("signed download token is malformed") from error
        if token_actor != actor_user_id:
            raise ArtifactPermissionError("signed download token belongs to another user")
        current = int((now or _utcnow()).timestamp())
        if expires < current:
            raise ArtifactPermissionError("signed download token expired")
        payload = f"{artifact.organization_id}|{artifact.project_id}|{artifact.id}|{actor_user_id}|{expires}"
        expected = hmac.new(self.signing_secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ArtifactPermissionError("signed download token is invalid")

    def retention_preview(
        self,
        *,
        organization_id: str,
        project_id: str,
        now: datetime | None = None,
    ) -> tuple[ArtifactRetentionCandidate, ...]:
        current = now or _utcnow()
        candidates = []
        for artifact in self.repository.list(
            organization_id=organization_id,
            project_id=project_id,
            limit=500,
        ):
            if artifact.legal_hold or artifact.retention_class == "legal_hold":
                action: Literal["retain", "delete", "skip_legal_hold"] = "skip_legal_hold"
                reason = "legal hold blocks deletion"
            elif artifact.retain_until is not None and artifact.retain_until <= current:
                action = "delete"
                reason = "retention period expired"
            else:
                action = "retain"
                reason = "retention period remains active"
            candidates.append(ArtifactRetentionCandidate(
                artifact_id=artifact.id,
                object_key=artifact.object_key,
                retention_class=artifact.retention_class,
                retain_until=artifact.retain_until,
                legal_hold=artifact.legal_hold,
                action=action,
                reason=reason,
            ))
        return tuple(candidates)

    def apply_retention(
        self,
        *,
        organization_id: str,
        project_id: str,
        actor_user_id: str,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        deleted = []
        by_id = {
            item.id: item
            for item in self.repository.list(
                organization_id=organization_id,
                project_id=project_id,
                limit=500,
            )
        }
        for candidate in self.retention_preview(
            organization_id=organization_id,
            project_id=project_id,
            now=now,
        ):
            if candidate.action != "delete":
                continue
            artifact = by_id[candidate.artifact_id]
            self.backend.delete(artifact.object_key)
            self.repository.set_state(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact.id,
                state="deleted",
                deleted=True,
            )
            self.repository.audit(
                artifact=artifact,
                actor_user_id=actor_user_id,
                action="retention_apply",
                decision="completed",
                details={"reason": candidate.reason},
            )
            deleted.append(artifact.id)
        return tuple(deleted)

    def reconcile(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None,
        actor_user_id: str,
        apply: bool = False,
    ) -> ArtifactReconciliationReport:
        artifacts = self.repository.list(
            organization_id=organization_id,
            project_id=project_id,
            limit=500,
        )
        prefix = "/".join(("organizations", safe_segment(organization_id), "projects", safe_segment(project_id)))
        object_keys = set(self.backend.list_keys(prefix))
        catalog_keys = {item.object_key for item in artifacts if item.deleted_at is None}
        verified: list[str] = []
        missing: list[str] = []
        mismatch: list[str] = []
        for artifact in artifacts:
            if artifact.deleted_at is not None:
                continue
            metadata = self.backend.head(artifact.object_key)
            if metadata is None:
                missing.append(artifact.id)
                if apply:
                    self.repository.set_state(
                        organization_id=organization_id,
                        project_id=project_id,
                        artifact_id=artifact.id,
                        state="missing",
                    )
            elif metadata.checksum_sha256 != artifact.checksum_sha256 or metadata.size_bytes != artifact.size_bytes:
                mismatch.append(artifact.id)
                if apply:
                    self.repository.set_state(
                        organization_id=organization_id,
                        project_id=project_id,
                        artifact_id=artifact.id,
                        state="checksum_mismatch",
                    )
            else:
                verified.append(artifact.id)
                if apply:
                    self.repository.set_state(
                        organization_id=organization_id,
                        project_id=project_id,
                        artifact_id=artifact.id,
                        state="available",
                        verified=True,
                    )
        report = ArtifactReconciliationReport(
            run_id=f"artifact-reconcile-{uuid.uuid4()}",
            mode="apply" if apply else "dry_run",
            catalog_count=len(catalog_keys),
            object_count=len(object_keys),
            verified=tuple(sorted(verified)),
            missing=tuple(sorted(missing)),
            checksum_mismatch=tuple(sorted(mismatch)),
            orphan_keys=tuple(sorted(object_keys - catalog_keys)),
            completed_at=_utcnow(),
        )
        self.repository.save_reconciliation(
            report=report,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            created_by=actor_user_id,
        )
        return report

    def restore(
        self,
        artifact: ArtifactObject,
        *,
        backup_content: bytes,
        actor_user_id: str,
    ) -> ArtifactObject:
        checksum = hashlib.sha256(backup_content).hexdigest()
        if checksum != artifact.checksum_sha256:
            raise ArtifactIntegrityError("restore payload does not match the catalog checksum")
        self.backend.put(
            artifact.object_key,
            backup_content,
            media_type=artifact.media_type,
            metadata={"restored-artifact-id": artifact.id},
        )
        restored = self.repository.set_state(
            organization_id=artifact.organization_id,
            project_id=artifact.project_id,
            artifact_id=artifact.id,
            state="available",
            verified=True,
        )
        self.repository.audit(
            artifact=artifact,
            actor_user_id=actor_user_id,
            action="restore",
            decision="completed",
        )
        return restored


def artifact_storage_readiness() -> ArtifactGovernanceReadiness:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    backend = os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BACKEND", "local").strip().lower()
    bucket = os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BUCKET", "").strip() or None
    endpoint = os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_ENDPOINT", "").strip()
    credential_ref = os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_CREDENTIAL_REF", "").strip()
    signing_ref = os.getenv("ONTOLOGY_DASHBOARD_ARTIFACT_SIGNING_SECRET_REF", "").strip()
    blockers: list[str] = []
    normalized_backend: ArtifactBackend = backend if backend in {"local", "s3", "gcs", "azure"} else "local"
    if environment == "production":
        if normalized_backend == "local":
            blockers.append("Production artifacts cannot use node-local storage.")
        if not bucket:
            blockers.append("Object-storage bucket/container is not configured.")
        if not credential_ref:
            blockers.append("Object-storage credential reference is not configured.")
        if not signing_ref:
            blockers.append("Artifact signing-secret reference is not configured.")
    state: Literal["ready", "degraded", "not_configured", "blocked"]
    if blockers:
        state = "blocked"
    elif normalized_backend == "local":
        state = "degraded"
    else:
        state = "ready"
    return ArtifactGovernanceReadiness(
        state=state,
        backend=normalized_backend,
        bucket=bucket,
        endpoint_configured=bool(endpoint),
        credential_reference_configured=bool(credential_ref),
        encryption=os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_SSE", "AES256"),
        versioning="required in production; local emulator preserves immutable content keys",
        signed_downloads="permission check + short-lived HMAC/presigned URL + audit",
        deterministic_key_schema=(
            "organizations/{org}/projects/{project}/workspaces/{workspace}/artifacts/"
            "{type}/{resource}/versions/{version}/{checksum-prefix}/{checksum}.{ext}"
        ),
        checksum="SHA-256 on upload, read, reconciliation and restore",
        retention_classes=("ephemeral", "standard", "regulated", "backup", "legal_hold"),
        reconciliation="catalog/object missing, mismatch and orphan detection",
        blockers=tuple(blockers),
    )


def build_artifact_service(
    database: str | Path,
    *,
    local_root: str | Path | None = None,
) -> ArtifactGovernanceService:
    readiness = artifact_storage_readiness()
    if readiness.backend == "s3":
        if not readiness.bucket:
            raise ArtifactNotConfigured("S3 bucket is not configured")
        backend: ObjectStorageBackend = S3ObjectStorageBackend(
            bucket=readiness.bucket,
            endpoint_url=os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_ENDPOINT") or None,
            region=os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_REGION") or None,
        )
    elif readiness.backend in {"gcs", "azure"}:
        raise ArtifactNotConfigured(f"{readiness.backend} adapter contract exists but provider dependency is not configured")
    else:
        configured = local_root or os.getenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_LOCAL_ROOT")
        root = Path(configured or ".runtime/object-storage").expanduser().resolve()
        backend = LocalObjectStorageBackend(root)
    signing_secret = os.getenv("ONTOLOGY_DASHBOARD_ARTIFACT_SIGNING_SECRET", "").encode()
    if not signing_secret:
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise ArtifactNotConfigured("artifact signing secret is not configured")
        signing_secret = hashlib.sha256(f"local-artifact-signing:{Path(str(database)).name}".encode()).digest()
    return ArtifactGovernanceService(
        repository=ArtifactCatalogRepository(database),
        backend=backend,
        signing_secret=signing_secret,
    )


__all__ = [
    "ArtifactCatalogRepository",
    "ArtifactGovernanceReadiness",
    "ArtifactGovernanceService",
    "ArtifactGovernanceSnapshot",
    "ArtifactIntegrityError",
    "ArtifactNotConfigured",
    "ArtifactObject",
    "ArtifactOperatorRequest",
    "ArtifactPermissionError",
    "ArtifactReconciliationReport",
    "ArtifactRetentionCandidate",
    "ArtifactStorageError",
    "LocalObjectStorageBackend",
    "ObjectMetadata",
    "S3ObjectStorageBackend",
    "SignedArtifactDownload",
    "artifact_storage_readiness",
    "build_artifact_service",
    "deterministic_object_key",
    "safe_segment",
]
