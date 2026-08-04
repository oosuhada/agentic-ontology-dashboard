from __future__ import annotations

from pathlib import Path

import pytest

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.intake import DatasetIntakeProfiler
from ontology_dashboard.modeling.mapping import registered_target
from ontology_dashboard.modeling.models import (
    MappingCandidateDecisionRequest,
    MappingSetDecisionRequest,
)
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.modeling.service import ModelingService


class InvalidMappingProvider:
    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        return {
            "source_field": payload["source_field"],
            "target_object_type": "invented_object",
            "target_property": "invented_property",
            "semantic_role": "measure",
            "confidence": 0.99,
            "rationale": "invalid registry value",
        }


def build_service(tmp_path: Path, *, provider=None) -> ModelingService:
    source_root = tmp_path / "sources"
    source_root.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "mapping.db"
    migrate(str(database))
    return ModelingService(
        ModelingRepository(database),
        intake_profiler=DatasetIntakeProfiler([source_root]),
        mapping_provider=provider,
    )


def create_profile_and_mapping(tmp_path: Path, *, provider=None):
    source = tmp_path / "sources" / "telemetry.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "datetime,machineID,volt,rotate,pressure,vibration,failure,model,age,unknown_field\n"
        "2026-01-01T00:00:00,M-001,220.0,1500,2.1,0.2,0,M1,5,alpha\n"
        "2026-01-01T00:10:00,M-001,221.0,1510,2.2,0.3,1,M1,5,beta\n",
        encoding="utf-8",
    )
    modeling = build_service(tmp_path, provider=provider)
    profile = modeling.profile_source(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        source_path=str(source),
        sheet=None,
        use_llm=False,
        idempotency_key="profile-mapping",
        actor_id="user-fde",
    )
    mapping_set = modeling.create_mapping_set(
        profile_id=profile.profile_id,
        dataset_version_id="dataset-version-v1",
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        use_llm=provider is not None,
        idempotency_key="mapping-v1",
        actor_id="user-fde",
    )
    return modeling, profile, mapping_set


def by_field(mapping_set, field: str):
    return next(item for item in mapping_set.candidates if item.source_field == field)


def decide_candidate(modeling: ModelingService, mapping_set, field: str, *, decision="approve", **edits):
    candidate = by_field(mapping_set, field)
    return modeling.decide_mapping_candidate(
        mapping_set.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=MappingCandidateDecisionRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=mapping_set.revision,
            candidate_id=candidate.candidate_id,
            decision=decision,
            rationale=f"reviewed {field}",
            **edits,
        ),
        actor_id="user-fde",
    )


def test_registry_mapping_fixes_prototype_share_errors_and_keeps_unknown_unresolved(tmp_path: Path) -> None:
    _, _, mapping_set = create_profile_and_mapping(tmp_path)
    datetime_candidate = by_field(mapping_set, "datetime")
    machine_candidate = by_field(mapping_set, "machineID")
    model_candidate = by_field(mapping_set, "model")
    age_candidate = by_field(mapping_set, "age")
    unknown = by_field(mapping_set, "unknown_field")

    assert (datetime_candidate.target_object_type, datetime_candidate.target_property) == (
        "telemetry_observation",
        "observed_at",
    )
    assert (machine_candidate.target_object_type, machine_candidate.target_property) == (
        "telemetry_observation",
        "equipment_id",
    )
    assert (model_candidate.target_object_type, model_candidate.target_property) == (
        "telemetry_observation",
        "product_type",
    )
    assert (age_candidate.target_object_type, age_candidate.target_property) == (
        "telemetry_observation",
        "equipment_age_years",
    )
    assert unknown.status == "unresolved"
    assert unknown.target_object_type is None
    assert all(
        registered_target(item.target_object_type, item.target_property)
        for item in mapping_set.candidates
        if item.target_object_type is not None
    )


def test_high_confidence_critical_fields_are_never_auto_approved(tmp_path: Path) -> None:
    modeling, _, mapping_set = create_profile_and_mapping(tmp_path)
    for field in ("datetime", "machineID", "failure"):
        candidate = by_field(mapping_set, field)
        assert candidate.critical_field is True
        assert candidate.confidence >= 0.9
        assert candidate.status == "proposed"
    with pytest.raises(ValueError, match="critical field requires approval"):
        modeling.decide_mapping_set(
            mapping_set.mapping_set_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=MappingSetDecisionRequest(
                project_id="project-a",
                workspace_id="workspace-a",
                expected_revision=1,
                decision="approve",
                rationale="not reviewed",
            ),
            actor_id="user-fde",
        )


def test_capability_requires_complete_approved_prerequisite_set(tmp_path: Path) -> None:
    modeling, _, mapping_set = create_profile_and_mapping(tmp_path)
    initial = {item.capability: item for item in modeling.mapping_capabilities(
        mapping_set.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    )}
    assert initial["predictive_training"].status == "blocked"
    assert set(initial["predictive_training"].missing_prerequisites) == {
        "group_key",
        "timestamp",
        "measure",
        "label",
    }

    for field in ("machineID", "datetime", "volt", "failure"):
        mapping_set = decide_candidate(modeling, mapping_set, field)

    capabilities = {item.capability: item for item in modeling.mapping_capabilities(
        mapping_set.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    )}
    assert capabilities["predictive_training"].status == "ready"
    assert capabilities["predictive_scoring"].status == "ready"
    assert capabilities["replay_time_series"].status == "ready"
    assert capabilities["explanation"].status == "ready"
    assert capabilities["maintenance_context"].status == "blocked"
    assert capabilities["maintenance_context"].missing_prerequisites == [
        "maintenance_reference"
    ]


def test_invalid_llm_mapping_falls_back_without_registry_escape(tmp_path: Path) -> None:
    _, _, mapping_set = create_profile_and_mapping(tmp_path, provider=InvalidMappingProvider())
    assert by_field(mapping_set, "model").target_property == "product_type"
    assert all(
        registered_target(item.target_object_type, item.target_property)
        for item in mapping_set.candidates
        if item.target_object_type is not None
    )


def test_edit_to_unknown_registry_target_and_datatype_conflict_are_rejected(tmp_path: Path) -> None:
    modeling, _, mapping_set = create_profile_and_mapping(tmp_path)
    with pytest.raises(ValueError, match="registered Object Type/Property"):
        decide_candidate(
            modeling,
            mapping_set,
            "unknown_field",
            decision="edit",
            target_object_type="invented_object",
            target_property="invented_property",
            semantic_role="measure",
        )
    with pytest.raises(ValueError, match="datatype conflicts"):
        decide_candidate(
            modeling,
            mapping_set,
            "volt",
            decision="edit",
            target_object_type="telemetry_observation",
            target_property="voltage_v",
            datatype="string",
            semantic_role="measure",
        )


def test_approved_mapping_is_immutable_and_clone_creates_new_draft_version(tmp_path: Path) -> None:
    modeling, _, mapping_set = create_profile_and_mapping(tmp_path)
    critical_fields = [item.source_field for item in mapping_set.candidates if item.critical_field]
    for field in critical_fields:
        mapping_set = decide_candidate(modeling, mapping_set, field)
    mapping_set = decide_candidate(modeling, mapping_set, "volt")
    approved = modeling.decide_mapping_set(
        mapping_set.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=MappingSetDecisionRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=mapping_set.revision,
            decision="approve",
            rationale="critical fields reviewed",
        ),
        actor_id="user-fde",
    )
    assert approved.status == "approved"
    with pytest.raises(ValueError, match="immutable"):
        decide_candidate(modeling, approved, "pressure")

    cloned = modeling.clone_mapping_set(
        approved.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        idempotency_key="mapping-v2",
        actor_id="user-fde",
    )
    assert cloned.version == approved.version + 1
    assert cloned.status == "draft"
    assert cloned.mapping_set_id != approved.mapping_set_id
    assert modeling.mapping_set(
        approved.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    ).status == "approved"


def test_cross_project_mapping_access_is_rejected(tmp_path: Path) -> None:
    modeling, _, mapping_set = create_profile_and_mapping(tmp_path)
    with pytest.raises(KeyError):
        modeling.mapping_set(
            mapping_set.mapping_set_id,
            organization_id="org-a",
            project_id="project-b",
            workspace_id="workspace-a",
        )
