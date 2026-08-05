from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ontology_dashboard.artifact_storage import (
    ArtifactIntegrityError,
    ArtifactPermissionError,
    LocalObjectStorageBackend,
    artifact_storage_readiness,
    build_artifact_service,
    deterministic_object_key,
)
from ontology_dashboard.migrations import migrate
from ontology_dashboard.projects import ProjectRepository


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"
WORKSPACE = "manufacturing-demo"
ACTOR = "user-manager"


def service(tmp_path: Path):
    database = tmp_path / "phase24.db"
    migrate(str(database))
    ProjectRepository(database)
    return build_artifact_service(database, local_root=tmp_path / "objects")


def put_report(storage, *, resource_id: str = "report-1", content: bytes = b"governed report", **kwargs):
    return storage.put_bytes(
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        resource_type="report",
        resource_id=resource_id,
        resource_version="v1",
        content=content,
        media_type="application/pdf",
        created_by=ACTOR,
        provenance={
            "dataset_schema_version": "canonical-v3.1",
            "pipeline_version": "pipeline-24",
            "software_bom_digest": "sha256:fixture",
        },
        **kwargs,
    )


def test_deterministic_key_is_tenant_scoped_and_traversal_safe() -> None:
    checksum = hashlib.sha256(b"payload").hexdigest()
    first = deterministic_object_key(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        resource_type="model",
        resource_id="../unsafe model",
        resource_version="1.0.0",
        checksum_sha256=checksum,
        media_type="application/octet-stream",
    )
    second = deterministic_object_key(
        organization_id="org-b",
        project_id="project-a",
        workspace_id="workspace-a",
        resource_type="model",
        resource_id="../unsafe model",
        resource_version="1.0.0",
        checksum_sha256=checksum,
        media_type="application/octet-stream",
    )
    assert first != second
    assert ".." not in first.split("/")
    assert first.endswith(f"{checksum}.bin")
    backend = LocalObjectStorageBackend("/tmp/phase24-key-test")
    with pytest.raises(ValueError):
        backend.put("../escape", b"x", media_type="text/plain", metadata={})


def test_put_is_content_addressed_idempotent_and_cataloged(tmp_path: Path) -> None:
    storage = service(tmp_path)
    first = put_report(storage)
    replay = put_report(storage)
    assert replay.id == first.id
    assert replay.object_key == first.object_key
    assert replay.checksum_sha256 == hashlib.sha256(b"governed report").hexdigest()
    assert replay.metadata["object_metadata"]["size_bytes"] == len(b"governed report")
    assert replay.provenance["dataset_schema_version"] == "canonical-v3.1"
    assert storage.read_verified(first, actor_user_id=ACTOR, purpose="phase24 test") == b"governed report"
    with sqlite3.connect(storage.repository.database) as connection:
        assert connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM artifact_access_audit").fetchone()[0] >= 2


def test_checksum_corruption_is_quarantined_from_download(tmp_path: Path) -> None:
    storage = service(tmp_path)
    artifact = put_report(storage)
    path = storage.backend._path(artifact.object_key)  # local emulator corruption injection
    path.write_bytes(b"tampered")
    verified = storage.verify(artifact, actor_user_id=ACTOR)
    assert verified.state == "checksum_mismatch"
    with pytest.raises(ArtifactIntegrityError):
        storage.read_verified(artifact, actor_user_id=ACTOR, purpose="should fail")


def test_signed_download_is_user_bound_expiring_and_tamper_evident(tmp_path: Path) -> None:
    storage = service(tmp_path)
    artifact = put_report(storage)
    signed = storage.sign_download(
        artifact,
        actor_user_id=ACTOR,
        purpose="regulated review",
        expires_seconds=60,
    )
    token = signed.url.split("token=", 1)[1]
    storage.validate_download_token(artifact, token=token, actor_user_id=ACTOR)
    with pytest.raises(ArtifactPermissionError):
        storage.validate_download_token(artifact, token=token, actor_user_id="user-other")
    with pytest.raises(ArtifactPermissionError):
        storage.validate_download_token(
            artifact,
            token=token,
            actor_user_id=ACTOR,
            now=signed.expires_at + timedelta(seconds=1),
        )
    with pytest.raises(ArtifactPermissionError):
        storage.validate_download_token(artifact, token=f"{token}0", actor_user_id=ACTOR)


def test_retention_dry_run_respects_legal_hold_and_apply_is_idempotent(tmp_path: Path) -> None:
    storage = service(tmp_path)
    expired = put_report(
        storage,
        resource_id="expired",
        content=b"expired",
        retention_class="ephemeral",
        retain_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    held = put_report(
        storage,
        resource_id="held",
        content=b"held",
        retention_class="legal_hold",
        retain_until=datetime.now(timezone.utc) - timedelta(days=30),
        legal_hold=True,
    )
    preview = {item.artifact_id: item for item in storage.retention_preview(
        organization_id=ORG,
        project_id=PROJECT,
    )}
    assert preview[expired.id].action == "delete"
    assert preview[held.id].action == "skip_legal_hold"
    assert storage.apply_retention(
        organization_id=ORG,
        project_id=PROJECT,
        actor_user_id=ACTOR,
    ) == (expired.id,)
    assert storage.apply_retention(
        organization_id=ORG,
        project_id=PROJECT,
        actor_user_id=ACTOR,
    ) == ()
    assert storage.backend.head(held.object_key) is not None


def test_reconciliation_detects_missing_mismatch_and_orphan_then_restore(tmp_path: Path) -> None:
    storage = service(tmp_path)
    missing = put_report(storage, resource_id="missing", content=b"missing-backup")
    mismatch = put_report(storage, resource_id="mismatch", content=b"expected")
    storage.backend.delete(missing.object_key)
    storage.backend._path(mismatch.object_key).write_bytes(b"wrong")
    orphan_key = (
        f"organizations/{ORG}/projects/{PROJECT}/workspaces/{WORKSPACE}/"
        "artifacts/other/orphan/versions/v1/00/orphan.bin"
    )
    storage.backend.put(orphan_key, b"orphan", media_type="application/octet-stream", metadata={})
    report = storage.reconcile(
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        actor_user_id=ACTOR,
        apply=True,
    )
    assert missing.id in report.missing
    assert mismatch.id in report.checksum_mismatch
    assert orphan_key in report.orphan_keys
    restored = storage.restore(
        missing,
        backup_content=b"missing-backup",
        actor_user_id=ACTOR,
    )
    assert restored.state == "available"
    assert restored.id == missing.id
    with pytest.raises(ArtifactIntegrityError):
        storage.restore(mismatch, backup_content=b"not-the-original", actor_user_id=ACTOR)


def test_production_readiness_never_reports_local_storage_as_ready(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_CREDENTIAL_REF", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ARTIFACT_SIGNING_SECRET_REF", raising=False)
    readiness = artifact_storage_readiness()
    assert readiness.state == "blocked"
    assert readiness.backend == "local"
    assert any("node-local" in blocker for blocker in readiness.blockers)
