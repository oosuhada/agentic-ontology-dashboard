from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.artifacts import LocalArtifactStore
from ontology_dashboard.modeling.experiments import run_experiment
from ontology_dashboard.modeling.models import (
    CandidateResult,
    ExperimentRun,
    FeatureDatasetVersion,
    FeatureRecipeSet,
    LabelPolicy,
    MappingSet,
    ModelActivateRequest,
    ModelReleaseDecisionRequest,
    ModelReleaseRequestCreate,
    ModelRollbackRequest,
    ModelScoreRequest,
    ModelVersionCreateRequest,
    SplitPolicy,
    canonical_checksum,
)
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.modeling.service import ModelingService


def feature_frame() -> pd.DataFrame:
    rows: list[dict] = []
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    for equipment_offset, equipment_id in enumerate(("M-1", "M-2", "M-3")):
        for index in range(80):
            signal = index + equipment_offset
            rows.append(
                {
                    "equipment_id": equipment_id,
                    "observed_at": start + timedelta(minutes=10 * index),
                    "feature__signal": float(signal),
                    "feature__load": float((index % 10) * (equipment_offset + 1)),
                    "feature__temperature": float(300 + index * 0.1),
                    "label": int(index in {30, 50, 68, 76}),
                }
            )
    return pd.DataFrame(rows)


def split_policy() -> SplitPolicy:
    return SplitPolicy(
        mode="group_chronological",
        group_field="equipment_id",
        time_field="observed_at",
        train_fraction=0.6,
        validation_fraction=0.2,
        test_fraction=0.2,
        embargo_hours=0,
    )


def seed_governed_lineage(
    repository: ModelingRepository,
    store: LocalArtifactStore,
) -> FeatureDatasetVersion:
    mapping = MappingSet(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        mapping_set_id="mapping-v1",
        dataset_version_id="dataset-v1",
        version=1,
        checksum_sha256="a" * 64,
        status="approved",
        candidates=[],
        approved_by="user-fde",
        idempotency_key="mapping-v1",
    )
    recipe = FeatureRecipeSet(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        recipe_set_id="recipe-v1",
        dataset_version_id="dataset-v1",
        mapping_set_id="mapping-v1",
        version=1,
        checksum_sha256="b" * 64,
        status="approved",
        recipes=[],
        label_policy=LabelPolicy(
            label_policy_id="label-v1",
            version=1,
            horizon_hours=1,
            lookback_hours=0,
            embargo_hours=0,
            event_time_field="observed_at",
            observation_time_field="observed_at",
            target_source="machine_failure",
            overlapping_window_policy="nearest_event",
        ),
        validation_report={"valid": True},
        idempotency_key="recipe-v1",
    )
    frame = feature_frame()
    payload = frame.to_json(orient="records", lines=True, date_format="iso").encode("utf-8")
    artifact = store.put_bytes("feature-datasets/feature-v1.jsonl", payload, "application/x-ndjson")
    schema_metadata = {
        "feature_engine_version": "ontology-feature-engine-v1",
        "columns": [
            {"name": column, "dtype": str(frame[column].dtype)} for column in frame.columns
        ],
        "group_by": "equipment_id",
        "order_by": "observed_at",
        "label_column": "label",
    }
    feature_version = FeatureDatasetVersion(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        feature_dataset_version_id="feature-v1",
        dataset_version_id="dataset-v1",
        mapping_set_id="mapping-v1",
        recipe_set_id="recipe-v1",
        label_policy_id="label-v1",
        materialization_checksum_sha256=canonical_checksum({"artifact": artifact.checksum_sha256}),
        status="succeeded",
        row_count=len(frame),
        feature_count=3,
        equipment_count=3,
        time_start=frame.observed_at.min(),
        time_end=frame.observed_at.max(),
        artifact=artifact,
        schema_metadata=schema_metadata,
        idempotency_key="feature-v1",
    )
    repository.put("mapping_set", mapping.model_dump(mode="json"), idempotency_key="mapping-v1")
    repository.put("recipe_set", recipe.model_dump(mode="json"), idempotency_key="recipe-v1")
    repository.put(
        "feature_dataset",
        feature_version.model_dump(mode="json"),
        idempotency_key="feature-v1",
    )
    return feature_version


def completed_experiment(
    *,
    experiment_id: str,
    store: LocalArtifactStore,
    algorithm_order: list[str] | None = None,
) -> ExperimentRun:
    algorithms = algorithm_order or ["dummy_prior", "logistic_regression", "random_forest"]
    running = ExperimentRun(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        experiment_id=experiment_id,
        dataset_version_id="dataset-v1",
        mapping_set_id="mapping-v1",
        recipe_set_id="recipe-v1",
        feature_dataset_version_id="feature-v1",
        label_policy_id="label-v1",
        status="running",
        split_policy=split_policy(),
        random_seed=42,
        recall_target=0.5,
        false_negative_cost=10,
        false_positive_cost=1,
        progress=0.01,
        candidates=[
            CandidateResult(
                candidate_id=f"queued-{algorithm}",
                algorithm=algorithm,
                status="queued",
            )
            for algorithm in algorithms
        ],
        idempotency_key=experiment_id,
    )
    completed, _, _ = run_experiment(
        running,
        feature_frame=feature_frame(),
        algorithms=algorithms,
        artifact_store=store,
        recall_target=0.5,
        false_negative_cost=10,
        false_positive_cost=1,
    )
    return completed


def build_service(tmp_path: Path, *, experiment_count: int = 1):
    database = tmp_path / "registry.db"
    migrate(str(database))
    repository = ModelingRepository(database)
    store = LocalArtifactStore(tmp_path / "artifacts")
    feature_version = seed_governed_lineage(repository, store)
    experiments = []
    for index in range(experiment_count):
        completed = completed_experiment(
            experiment_id=f"experiment-{index + 1}",
            store=store,
        )
        repository.put(
            "experiment",
            completed.model_dump(mode="json"),
            idempotency_key=completed.idempotency_key,
        )
        experiments.append(completed)
    return ModelingService(repository, artifact_store=store), store, feature_version, experiments


def register_model(service: ModelingService, experiment_id: str, key: str):
    return service.create_model_version(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelVersionCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            experiment_id=experiment_id,
            idempotency_key=key,
        ),
        actor_id="user-ml",
    )


def approve_model(service: ModelingService, model_version_id: str):
    release = service.request_model_release(
        model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelReleaseRequestCreate(
            project_id="project-a",
            workspace_id="workspace-a",
            rationale="validation metrics and lineage reviewed",
        ),
        actor_id="user-ml",
    )
    decided, model = service.decide_model_release(
        release.release_request_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelReleaseDecisionRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=1,
            decision="approve",
            rationale="tenant administrator approved release",
        ),
        actor_id="user-admin",
    )
    assert decided.status == "approved"
    return model


def test_model_version_preserves_full_lineage_and_verified_artifact(tmp_path: Path) -> None:
    service, store, feature_version, experiments = build_service(tmp_path)
    model = register_model(service, experiments[0].experiment_id, "model-v1")
    selected = next(item for item in experiments[0].candidates if item.selected)
    assert model.status == "candidate"
    assert model.artifact.checksum_sha256 == selected.artifact.checksum_sha256
    assert store.read_bytes(model.artifact)
    assert model.dataset_version_id == "dataset-v1"
    assert model.mapping_set_id == "mapping-v1"
    assert model.recipe_set_id == "recipe-v1"
    assert model.feature_dataset_version_id == feature_version.feature_dataset_version_id
    assert model.label_policy_id == "label-v1"
    assert model.threshold_policy.validation_only_selection is True
    assert model.input_features == [
        "feature__signal",
        "feature__load",
        "feature__temperature",
    ]
    assert model.confidence_status == "unavailable_uncalibrated"


def test_release_request_separates_ml_validator_and_admin_decision(tmp_path: Path) -> None:
    service, _, _, experiments = build_service(tmp_path)
    model = register_model(service, experiments[0].experiment_id, "model-v1")
    release = service.request_model_release(
        model.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelReleaseRequestCreate(
            project_id="project-a",
            workspace_id="workspace-a",
            rationale="request approval",
        ),
        actor_id="user-ml",
    )
    assert release.status == "pending"
    assert release.requested_by == "user-ml"
    with pytest.raises(ValueError, match="approved Model Version"):
        service.activate_model(
            model.model_version_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=ModelActivateRequest(
                project_id="project-a",
                workspace_id="workspace-a",
                expected_revision=model.revision,
            ),
            actor_id="user-admin",
        )
    decided, approved = service.decide_model_release(
        release.release_request_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelReleaseDecisionRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=1,
            decision="approve",
            rationale="approved by governance",
        ),
        actor_id="user-admin",
    )
    assert decided.decided_by == "user-admin"
    assert approved.status == "approved"
    with pytest.raises(ValueError, match="already decided"):
        service.decide_model_release(
            release.release_request_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=ModelReleaseDecisionRequest(
                project_id="project-a",
                workspace_id="workspace-a",
                expected_revision=2,
                decision="reject",
                rationale="cannot decide twice",
            ),
            actor_id="user-admin",
        )


def test_only_one_active_model_per_task_and_rollback(tmp_path: Path) -> None:
    service, _, _, experiments = build_service(tmp_path, experiment_count=2)
    first = approve_model(service, register_model(service, experiments[0].experiment_id, "model-v1").model_version_id)
    first_active = service.activate_model(
        first.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelActivateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=first.revision,
        ),
        actor_id="user-admin",
    )
    assert first_active.status == "active"

    second = approve_model(service, register_model(service, experiments[1].experiment_id, "model-v2").model_version_id)
    second_active = service.activate_model(
        second.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelActivateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=second.revision,
        ),
        actor_id="user-admin",
    )
    assert second_active.status == "active"
    assert service.model_version(
        first.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    ).status == "retired"
    active_models = [
        item
        for item in service.list_model_versions(
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
        )
        if str(item.status) == "active"
    ]
    assert [item.model_version_id for item in active_models] == [second.model_version_id]

    rolled_back = service.rollback_model(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelRollbackRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            target_model_version_id=first.model_version_id,
        ),
        actor_id="user-admin",
    )
    assert rolled_back.model_version_id == first.model_version_id
    assert rolled_back.status == "active"
    assert service.model_version(
        second.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    ).status == "retired"


def test_scoring_requires_active_model_schema_match_and_returns_noncausal_explanation(tmp_path: Path) -> None:
    service, _, _, experiments = build_service(tmp_path)
    captured_predictions = []

    class CapturingPredictionRepository:
        def save(self, result):
            captured_predictions.append(result)
            return {"prediction_id": result.prediction_id}

    service.prediction_repository = CapturingPredictionRepository()
    candidate = register_model(service, experiments[0].experiment_id, "model-v1")
    score_request = ModelScoreRequest(
        project_id="project-a",
        workspace_id="workspace-a",
        observation_id="obs-1",
        observed_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
        features={
            "feature__signal": 70.0,
            "feature__load": 18.0,
            "feature__temperature": 307.0,
        },
        expected_input_schema_checksum_sha256=candidate.input_schema_checksum_sha256,
    )
    with pytest.raises(ValueError, match="active Model Version"):
        service.score_active_model(
            candidate.model_version_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=score_request,
            actor_id="user-engineer",
        )
    approved = approve_model(service, candidate.model_version_id)
    active = service.activate_model(
        approved.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ModelActivateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=approved.revision,
        ),
        actor_id="user-admin",
    )
    result, explanation = service.score_active_model(
        active.model_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=score_request.model_copy(
            update={
                "expected_input_schema_checksum_sha256": active.input_schema_checksum_sha256
            }
        ),
        actor_id="user-engineer",
    )
    assert 0 <= result.failure_probability <= 1
    assert result.confidence is None
    assert result.confidence_status == "unavailable_uncalibrated"
    assert result.explanation_id == explanation.explanation_id
    assert explanation.model_version_id == active.model_version_id
    assert explanation.observation_id == "obs-1"
    assert explanation.causal_proof is False
    assert all(item.contribution_kind == "local_contribution" for item in explanation.top_factors)
    assert len(captured_predictions) == 1
    boundary = captured_predictions[0]
    assert boundary.prediction_id == result.prediction_result_id
    assert boundary.prediction.label in {"failure_risk", "no_significant_risk"}
    assert boundary.prediction.score == result.failure_probability
    assert boundary.prediction.confidence is None
    assert boundary.subject.object_type == "telemetry_observation"
    assert all(action.requires_approval for action in boundary.recommended_actions)
    assert all(
        action.parameters.get("work_order_created") is False
        for action in boundary.recommended_actions
    )
    assert service.explanation(
        explanation.explanation_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    ).checksum_sha256 == explanation.checksum_sha256

    with pytest.raises(ValueError, match="schema checksum"):
        service.score_active_model(
            active.model_version_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=score_request.model_copy(
                update={"expected_input_schema_checksum_sha256": "f" * 64}
            ),
            actor_id="user-engineer",
        )
    with pytest.raises(ValueError, match="missing=.*temperature"):
        service.score_active_model(
            active.model_version_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=score_request.model_copy(
                update={
                    "features": {
                        "feature__signal": 70.0,
                        "feature__load": 18.0,
                    },
                    "expected_input_schema_checksum_sha256": active.input_schema_checksum_sha256,
                }
            ),
            actor_id="user-engineer",
        )


def test_tampered_model_artifact_and_cross_project_access_are_rejected(tmp_path: Path) -> None:
    service, store, _, experiments = build_service(tmp_path)
    model = register_model(service, experiments[0].experiment_id, "model-v1")
    path = store.resolve(model.artifact)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        store.read_bytes(model.artifact)
    with pytest.raises(KeyError):
        service.model_version(
            model.model_version_id,
            organization_id="org-a",
            project_id="project-b",
            workspace_id="workspace-a",
        )


def test_workbench_payload_uses_real_experiment_artifacts_and_explicit_blocked_state(tmp_path: Path) -> None:
    service, _, _, experiments = build_service(tmp_path)
    model = register_model(service, experiments[0].experiment_id, "model-workbench")
    payload = service.workbench_payload(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        selected_experiment_id=experiments[0].experiment_id,
    )
    assert payload["schema_version"] == "ml-validator-workbench-v1"
    assert payload["project_id"] == "project-a"
    assert payload["workspace_id"] == "workspace-a"
    assert payload["scope"]["project_id"] == payload["project_id"]
    assert payload["scope"]["workspace_id"] == payload["workspace_id"]
    assert payload["report"]["status"] == "available"
    assert payload["report"]["validation_used_for_selection"] is True
    assert payload["report"]["test_used_for_selection"] is False
    assert any(item["selected"] for item in payload["leaderboard"])
    assert payload["models"][0]["model_version_id"] == model.model_version_id
    assert payload["lineage_detail"]["mapping_set"]["status"] == "approved"
    assert payload["global_feature_importance"]["status"] == "unavailable"
    assert payload["operational_monitoring"]["status"] == "unavailable"
    assert "Gold fixtures" not in str(payload)

    blocked = ModelingService(
        service.repository,
        artifact_store=None,
        artifact_blocked_reason="artifact store deliberately unavailable",
    ).workbench_payload(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        selected_experiment_id=experiments[0].experiment_id,
    )
    assert blocked["report"]["status"] == "blocked"
    assert "deliberately unavailable" in blocked["report"]["reason"]


def test_promotion_gate_rejects_report_identity_and_baseline_regression(tmp_path: Path) -> None:
    service, store, _, experiments = build_service(tmp_path)
    original = experiments[0]
    assert original.artifact is not None
    report = __import__("json").loads(store.read_bytes(original.artifact))

    mismatched_report = {**report, "experiment_id": "wrong-experiment"}
    mismatched_artifact = store.put_bytes(
        "experiments/experiment-mismatch/report.json",
        __import__("json").dumps(mismatched_report).encode("utf-8"),
        "application/json",
    )
    mismatched = original.model_copy(
        update={
            "experiment_id": "experiment-mismatch",
            "artifact": mismatched_artifact,
            "idempotency_key": "experiment-mismatch",
        }
    )
    service.repository.put(
        "experiment",
        mismatched.model_dump(mode="json"),
        idempotency_key=mismatched.idempotency_key,
    )
    with pytest.raises(ValueError, match="report identity"):
        register_model(service, mismatched.experiment_id, "model-mismatch")

    baseline = next(item for item in original.candidates if item.algorithm == "dummy_prior")
    selected = next(item for item in original.candidates if item.selected)
    assert baseline.validation_metrics is not None
    assert selected.validation_metrics is not None
    regressed_candidates = [
        item.model_copy(
            update={
                "validation_metrics": item.validation_metrics.model_copy(
                    update={
                        "average_precision": baseline.validation_metrics.average_precision
                    }
                )
            }
        )
        if item.candidate_id == selected.candidate_id
        else item
        for item in original.candidates
    ]
    regressed_report = {
        **report,
        "experiment_id": "experiment-regressed",
        "candidate_results": [
            item.model_dump(mode="json") for item in regressed_candidates
        ],
    }
    regressed_artifact = store.put_bytes(
        "experiments/experiment-regressed/report.json",
        __import__("json").dumps(regressed_report).encode("utf-8"),
        "application/json",
    )
    regressed = original.model_copy(
        update={
            "experiment_id": "experiment-regressed",
            "candidates": regressed_candidates,
            "artifact": regressed_artifact,
            "idempotency_key": "experiment-regressed",
        }
    )
    service.repository.put(
        "experiment",
        regressed.model_dump(mode="json"),
        idempotency_key=regressed.idempotency_key,
    )
    with pytest.raises(ValueError, match="does not improve"):
        register_model(service, regressed.experiment_id, "model-regressed")
