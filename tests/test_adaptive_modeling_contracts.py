from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.artifacts import ArtifactStoreBlocked, LocalArtifactStore
from ontology_dashboard.modeling.models import (
    DatasetIntakeProfile,
    ManifestDraft,
    ManifestFieldSuggestion,
    ModelStatus,
    ReviewStatus,
    canonical_checksum,
    ensure_transition,
)
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.modeling.schema import adaptive_modeling_schema
from ontology_dashboard.modeling.service import ModelingService


def profile_payload() -> dict:
    source_checksum = "a" * 64
    return DatasetIntakeProfile(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        profile_id="profile-a",
        source_uri="artifact://sources/telemetry.csv",
        source_checksum_sha256=source_checksum,
        parser_version="csv-profile-v1",
        cache_key=canonical_checksum(
            {"source_checksum_sha256": source_checksum, "parser_version": "csv-profile-v1"}
        ),
        byte_size=120,
        media_type="text/csv",
        status="ready_for_review",
        structure_type="tabular_column_as_attribute",
        field_profiles=[],
        preview_rows=[],
        row_count=3,
        retryable=False,
        idempotency_key="profile:a",
    ).model_dump(mode="json")


def draft_payload() -> dict:
    return ManifestDraft(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        draft_id="draft-a",
        profile_id="profile-a",
        source_checksum_sha256="a" * 64,
        format="csv",
        encoding="utf-8",
        delimiter=",",
        field_suggestions=[
            ManifestFieldSuggestion(
                source_field="machine_id",
                canonical_field="equipment_id",
                required=True,
                essential_key=True,
                rationale="identifier pattern",
                confidence=0.98,
            )
        ],
        idempotency_key="draft:a",
    ).model_dump(mode="json")


def test_draft_2020_12_schema_and_pydantic_examples_match() -> None:
    schema = json.loads(Path("schemas/adaptive-modeling.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema == adaptive_modeling_schema()
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    assert list(validator.iter_errors(profile_payload())) == []
    assert list(validator.iter_errors(draft_payload())) == []


def test_unknown_field_status_and_cache_identity_are_rejected() -> None:
    payload = profile_payload()
    with pytest.raises(ValidationError):
        DatasetIntakeProfile.model_validate({**payload, "unknown": True})
    with pytest.raises(ValidationError):
        DatasetIntakeProfile.model_validate({**payload, "status": "finished"})
    with pytest.raises(ValidationError):
        DatasetIntakeProfile.model_validate({**payload, "cache_key": "b" * 64})


def test_status_transition_guards() -> None:
    ensure_transition(ReviewStatus.DRAFT, ReviewStatus.APPROVED, "review")
    ensure_transition(ModelStatus.APPROVED, ModelStatus.ACTIVE, "model")
    with pytest.raises(ValueError, match="invalid review status transition"):
        ensure_transition(ReviewStatus.APPROVED, ReviewStatus.DRAFT, "review")
    with pytest.raises(ValueError, match="invalid model status transition"):
        ensure_transition(ModelStatus.CANDIDATE, ModelStatus.ACTIVE, "model")


def test_repository_idempotency_scope_and_revision(tmp_path: Path) -> None:
    database = tmp_path / "modeling.db"
    migrate(str(database))
    repository = ModelingRepository(database)
    profile = profile_payload()
    first = repository.put("intake_profile", profile, idempotency_key=profile["idempotency_key"])
    second = repository.put("intake_profile", profile, idempotency_key=profile["idempotency_key"])
    assert first == second
    assert repository.get(
        "intake_profile",
        "profile-a",
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    )["source_checksum_sha256"] == "a" * 64
    with pytest.raises(KeyError):
        repository.get(
            "intake_profile",
            "profile-a",
            organization_id="org-a",
            project_id="project-b",
            workspace_id="workspace-a",
        )

    draft = draft_payload()
    repository.put("manifest_draft", draft, idempotency_key=draft["idempotency_key"])
    approved = repository.transition(
        "manifest_draft",
        "draft-a",
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        target_status="approved",
        expected_revision=1,
        transition_kind="review",
        updated_payload={"approved_by": "user-admin", "decision_rationale": "reviewed"},
    )
    assert approved["revision"] == 2
    with pytest.raises(ValueError, match="revision conflict"):
        repository.transition(
            "manifest_draft",
            "draft-a",
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            target_status="superseded",
            expected_revision=1,
            transition_kind="review",
        )


def test_artifact_uri_checksum_and_root_traversal(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    reference = store.put_bytes("models/model.json", b"model", "application/json")
    assert reference.uri == "artifact://models/model.json"
    assert store.read_bytes(reference) == b"model"
    with pytest.raises(ValueError, match="traversal"):
        store.put_bytes("../escape.bin", b"bad")
    with pytest.raises(ValueError, match="portable"):
        store.put_bytes("models\\windows.joblib", b"bad")
    store.resolve(reference).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        store.read_bytes(reference)


def test_unconfigured_artifact_store_is_explicitly_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT", raising=False)
    with pytest.raises(ArtifactStoreBlocked):
        LocalArtifactStore()
    database = tmp_path / "blocked.db"
    migrate(str(database))
    service = ModelingService.configured(str(database), None)
    assert service.contract_summary().artifact_store == "blocked"
    assert service.artifact_capability()["local_path_is_identity"] is False
