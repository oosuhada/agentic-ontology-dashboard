from __future__ import annotations

from pathlib import Path

import pytest

from app.infra.db.maintenance_repository import MaintenanceRepository
from app.maintenance import (
    EquipmentIdentity,
    MaterializationStrategy,
    ProducerRecommendation,
    imported_result_detail_view,
    materialize_recommended_action,
    validate_single_dataset_writer,
)


class Scope:
    organization_id = "org-1"
    project_id = "project-1"
    workspace_id = "workspace-1"


class Resolver:
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection=None,
    ):
        del connection
        if workspace_id != Scope.workspace_id:
            raise ValueError("workspace scope mismatch")
        if expected_organization_id not in {None, Scope.organization_id}:
            raise ValueError("organization scope mismatch")
        if expected_project_id not in {None, Scope.project_id}:
            raise ValueError("project scope mismatch")
        return Scope()


def _producer(policy_version: str = "recommendation-policy-v1") -> ProducerRecommendation:
    return ProducerRecommendation(
        source_action_id="recommendation-policy-v1:request_inspection",
        source_product_result_id="RESULT#M-001#2026-08-01T00:00:00+09:00",
        source_evidence_id="EVD#M-001#2026-08-01T00:00:00+09:00",
        source_schema_version="result-artifact-v1.0",
        source_policy_version=policy_version,
        label="점검 요청",
        kind="request_inspection",
        requires_human_approval=True,
        basis=("factor.1.tool_wear_min",),
    )


def _unavailable_producer() -> ProducerRecommendation:
    return ProducerRecommendation(
        source_action_id="recommendation-policy-v1:unavailable",
        source_product_result_id="RESULT#M-001#2026-08-01T00:00:00+09:00",
        source_evidence_id="EVD#M-001#2026-08-01T00:00:00+09:00",
        source_schema_version="result-artifact-v1.0",
        source_policy_version="recommendation-policy-v1",
        label="추천 근거 확인 필요",
        kind="unavailable",
        requires_human_approval=True,
        basis=("policy.unavailable",),
    )


def _identity(workspace_id: str = "workspace-1") -> EquipmentIdentity:
    return EquipmentIdentity(
        organization_id="org-1",
        project_id="project-1",
        workspace_id=workspace_id,
        asset_id="M-001",
        equipment_id="M-001",
        asset_type="cnc",
    )


def test_runtime_generated_recommendation_materializes_without_work_order_side_effects(tmp_path: Path) -> None:
    repository = MaintenanceRepository(tmp_path / "maintenance.db", project_context=Resolver())
    recommendation = materialize_recommended_action(
        _producer(),
        identity=_identity(),
        event_id="EVT-GS-002",
    )

    stored = repository.save_recommendation(recommendation)

    assert stored == recommendation
    assert stored.materialization_key == "RESULT#M-001#2026-08-01T00:00:00+09:00:recommendation-policy-v1:request_inspection"
    assert repository.operational_side_effect_counts() == {
        "recommendations": 1,
        "decisions": 0,
        "work_orders": 0,
        "maintenance_actions": 0,
        "maintenance_events": 0,
    }


def test_producer_recommendation_contract_is_diagnosis_owned() -> None:
    assert ProducerRecommendation.__module__ == "app.diagnosis.recommendation_schema"


def test_materialization_rejects_imported_precomputed_as_operational_source() -> None:
    with pytest.raises(ValueError, match="runtime_generated"):
        materialize_recommended_action(
            _producer(),
            identity=_identity(),
            event_id="EVT-GS-002",
            materialization_strategy=MaterializationStrategy.IMPORTED_PRECOMPUTED,
        )


def test_materialization_rejects_unavailable_kind_as_empty_recommendation() -> None:
    with pytest.raises(ValueError, match="unavailable is not a recommendation kind"):
        materialize_recommended_action(
            _unavailable_producer(),
            identity=_identity(),
            event_id="EVT-GS-002",
        )


def test_materialization_rejects_cross_workspace_source(tmp_path: Path) -> None:
    repository = MaintenanceRepository(tmp_path / "maintenance.db", project_context=Resolver())
    recommendation = materialize_recommended_action(_producer(), identity=_identity("workspace-other"), event_id="EVT")

    with pytest.raises(ValueError, match="workspace scope mismatch"):
        repository.save_recommendation(recommendation)


def test_policy_version_is_provenance_not_operational_dedupe_key(tmp_path: Path) -> None:
    repository = MaintenanceRepository(tmp_path / "maintenance.db", project_context=Resolver())
    first = materialize_recommended_action(_producer(), identity=_identity(), event_id="EVT")
    second = materialize_recommended_action(
        _producer("recommendation-policy-v2"),
        recommendation_id="REC-POLICY-V2",
        identity=_identity(),
        event_id="EVT",
    )

    repository.save_recommendation(first)
    with pytest.raises(ValueError, match="conflicts"):
        repository.save_recommendation(second)


def test_runtime_failure_does_not_fallback_to_imported_precomputed_writer() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        validate_single_dataset_writer(
            "dataset-version-1",
            {
                MaterializationStrategy.RUNTIME_GENERATED.value,
                MaterializationStrategy.IMPORTED_PRECOMPUTED.value,
            },
        )


def test_imported_result_without_evidence_preserves_result_and_marks_detail_unavailable() -> None:
    artifact = {
        "schema_version": "result-artifact-v1.0",
        "provenance": {"materialization_strategy": "imported_precomputed"},
        "evidence_payload": {
            "recommended_actions": [{"action_id": "continue_monitoring", "basis": ["factor.1"]}]
        },
    }

    view = imported_result_detail_view(artifact, evidence_detail=None)

    assert view["result_artifact"] is artifact
    assert view["recommendations"] == artifact["evidence_payload"]["recommended_actions"]
    assert view["evidence_detail"] == {
        "status": "unavailable",
        "reason": "imported_result_artifact_missing_evidence_detail",
    }
