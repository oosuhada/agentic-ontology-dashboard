"""Object-storage drivers and deterministic key generation.

This module contains only storage technology concerns. Artifact governance,
retention policy, ownership and catalog semantics remain outside Infra.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict

ArtifactBackend = Literal["local", "s3", "gcs", "azure"]
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

    def put(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> ObjectMetadata: ...

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
            media_type=str(
                sidecar.get("media_type")
                or mimetypes.guess_type(path.name)[0]
                or "application/octet-stream"
            ),
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
            raise ArtifactNotConfigured(
                "S3 adapter requires the production storage dependency"
            ) from error
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> ObjectMetadata:
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
            response_code = getattr(error, "response", {}).get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if response_code == 404:
                return None
            raise ArtifactStorageError(
                f"object head failed: {type(error).__name__}"
            ) from error
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


__all__ = [
    "ArtifactBackend",
    "ArtifactNotConfigured",
    "ArtifactStorageError",
    "LocalObjectStorageBackend",
    "ObjectMetadata",
    "ObjectStorageBackend",
    "ResourceType",
    "S3ObjectStorageBackend",
    "deterministic_object_key",
    "safe_segment",
]
