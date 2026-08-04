from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.artifacts import LocalArtifactStore
from ontology_dashboard.modeling.experiments import (
    dependency_capabilities,
    metric_set,
    run_experiment,
    split_feature_frame,
)
from ontology_dashboard.modeling.models import (
    ArtifactReference,
    CandidateResult,
    ExperimentCancelRequest,
    ExperimentCreateRequest,
    ExperimentRecoverRequest,
    ExperimentRetryRequest,
    ExperimentRun,
    FeatureDatasetVersion,
    FeatureRecipeSet,
    LabelPolicy,
    MappingSet,
    SplitPolicy,
    canonical_checksum,
)
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.modeling.service import ModelingService


def experiment_frame() -> pd.DataFrame:
    rows: list[dict] = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for equipment_index, equipment in enumerate(("M-1", "M-2", "M-3")):
        for index in range(90):
            signal = index + equipment_index * 2
            failure = int(index in {35, 58, 75, 86})
            rows.append(
                {
                    "equipment_id": equipment,
                    "observed_at": start + timedelta(minutes=10 * index),
                    "feature__signal": float(signal),
                    "feature__periodic": float(index % 12),
                    "feature__interaction": float(signal * (index % 7)),
                    "label": failure,
                }
            )
    return pd.DataFrame(rows)


def split_policy(embargo_hours: float = 0) -> SplitPolicy:
    return SplitPolicy(
        mode="group_chronological",
        group_field="equipment_id",
        time_field="observed_at",
        train_fraction=0.6,
        validation_fraction=0.2,
        test_fraction=0.2,
        embargo_hours=embargo_hours,
    )


def experiment(algorithms: list[str] | None = None) -> ExperimentRun:
    algorithms = algorithms or ["dummy_prior", "logistic_regression", "random_forest"]
    return ExperimentRun(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        experiment_id="experiment-test",
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
        idempotency_key="experiment-test",
    )


def test_group_chronological_split_orders_each_equipment_and_applies_embargo() -> None:
    frame = experiment_frame().sample(frac=1, random_state=99).reset_index(drop=True)
    without_embargo = split_feature_frame(frame, split_policy())
    with_embargo = split_feature_frame(frame, split_policy(embargo_hours=0.25))
    for equipment in ("M-1", "M-2", "M-3"):
        train = without_embargo.train[without_embargo.train.equipment_id == equipment]
        validation = without_embargo.validation[without_embargo.validation.equipment_id == equipment]
        test = without_embargo.test[without_embargo.test.equipment_id == equipment]
        assert pd.to_datetime(train.observed_at).max() < pd.to_datetime(validation.observed_at).min()
        assert pd.to_datetime(validation.observed_at).max() < pd.to_datetime(test.observed_at).min()
    assert with_embargo.excluded_embargo_rows > 0
    assert len(with_embargo.validation) < len(without_embargo.validation)
    assert len(with_embargo.test) < len(without_embargo.test)


def test_operational_experiment_rejects_random_row_split() -> None:
    policy = split_policy().model_copy(update={"mode": "benchmark_random"})
    with pytest.raises(ValueError, match="not allowed"):
        split_feature_frame(experiment_frame(), policy)


def test_metric_set_is_safe_when_validation_has_zero_positive_rows() -> None:
    metrics = metric_set(pd.Series([0, 0, 0, 0]), pd.Series([0.1, 0.2, 0.3, 0.4]).to_numpy(), 0.5)
    assert metrics.average_precision == 0
    assert metrics.roc_auc is None
    assert metrics.unavailable_reason == "only_one_target_class_present"
    assert metrics.confusion_matrix == [[4, 0], [0, 0]]


def test_runner_compares_baseline_selects_on_validation_and_tests_only_selected(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    completed, threshold, report = run_experiment(
        experiment(),
        feature_frame=experiment_frame(),
        algorithms=["dummy_prior", "logistic_regression", "random_forest", "lightgbm", "xgboost"],
        artifact_store=store,
        recall_target=0.5,
        false_negative_cost=10,
        false_positive_cost=1,
    )
    assert completed.status == "succeeded"
    assert completed.progress == 1
    assert completed.selected_candidate_id
    selected = next(item for item in completed.candidates if item.selected)
    assert selected.algorithm in {"logistic_regression", "random_forest", "lightgbm", "xgboost"}
    assert selected.held_out_test_metrics is not None
    assert all(
        item.held_out_test_metrics is None
        for item in completed.candidates
        if not item.selected
    )
    dummy = next(item for item in completed.candidates if item.algorithm == "dummy_prior")
    assert dummy.validation_metrics is not None
    capabilities = dependency_capabilities()
    for algorithm in ("lightgbm", "xgboost"):
        candidate = next(item for item in completed.candidates if item.algorithm == algorithm)
        expected = capabilities[algorithm]["status"]
        assert candidate.status == ("succeeded" if expected == "ready" else "blocked_dependency")
    assert report["validation_used_for_selection"] is True
    assert report["test_used_for_selection"] is False
    assert report["selected_candidate_id"] == completed.selected_candidate_id
    assert threshold.validation_only_selection is True
    assert threshold.artifact is not None
    assert completed.artifact is not None
    assert store.read_bytes(completed.artifact).startswith(b"{")
    assert store.read_bytes(threshold.artifact).startswith(b"{")


def test_runner_is_reproducible_for_same_seed_and_input(tmp_path: Path) -> None:
    frame = experiment_frame()
    first, first_threshold, _ = run_experiment(
        experiment(),
        feature_frame=frame,
        algorithms=["dummy_prior", "logistic_regression", "random_forest"],
        artifact_store=LocalArtifactStore(tmp_path / "first"),
        recall_target=0.5,
        false_negative_cost=10,
        false_positive_cost=1,
    )
    second_experiment = experiment().model_copy(update={"experiment_id": "experiment-test-2"})
    second, second_threshold, _ = run_experiment(
        second_experiment,
        feature_frame=frame,
        algorithms=["dummy_prior", "logistic_regression", "random_forest"],
        artifact_store=LocalArtifactStore(tmp_path / "second"),
        recall_target=0.5,
        false_negative_cost=10,
        false_positive_cost=1,
    )
    first_selected = next(item for item in first.candidates if item.selected)
    second_selected = next(item for item in second.candidates if item.selected)
    assert first_selected.algorithm == second_selected.algorithm
    assert first_selected.validation_metrics == second_selected.validation_metrics
    assert first_selected.held_out_test_metrics == second_selected.held_out_test_metrics
    assert first_threshold.selected_operational_threshold == second_threshold.selected_operational_threshold


def minimal_mapping() -> MappingSet:
    return MappingSet(
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


def minimal_recipe_set() -> FeatureRecipeSet:
    return FeatureRecipeSet(
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


def build_worker_service(tmp_path: Path) -> ModelingService:
    database = tmp_path / "worker.db"
    migrate(str(database))
    repository = ModelingRepository(database)
    store = LocalArtifactStore(tmp_path / "artifacts")
    frame = experiment_frame()
    payload = frame.to_json(orient="records", lines=True, date_format="iso").encode("utf-8")
    artifact = store.put_bytes("feature-datasets/feature-v1.jsonl", payload, "application/x-ndjson")
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
        schema_metadata={
            "group_by": "equipment_id",
            "order_by": "observed_at",
            "label_column": "label",
        },
        idempotency_key="feature-v1",
    )
    repository.put("mapping_set", minimal_mapping().model_dump(mode="json"), idempotency_key="mapping-v1")
    repository.put("recipe_set", minimal_recipe_set().model_dump(mode="json"), idempotency_key="recipe-v1")
    repository.put("feature_dataset", feature_version.model_dump(mode="json"), idempotency_key="feature-v1")
    return ModelingService(repository, artifact_store=store)


def test_api_service_only_queues_and_worker_executes_later(tmp_path: Path) -> None:
    service = build_worker_service(tmp_path)
    queued = service.queue_experiment(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            feature_dataset_version_id="feature-v1",
            split_policy=split_policy(),
            algorithms=["dummy_prior", "logistic_regression", "random_forest"],
            random_seed=42,
            recall_target=0.5,
            idempotency_key="queue-v1",
        ),
        actor_id="user-ml",
    )
    assert queued.status == "queued"
    assert queued.progress == 0
    assert queued.artifact is None
    repeated = service.queue_experiment(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            feature_dataset_version_id="feature-v1",
            split_policy=split_policy(),
            algorithms=["dummy_prior", "logistic_regression", "random_forest"],
            random_seed=42,
            recall_target=0.5,
            idempotency_key="queue-v1",
        ),
        actor_id="user-ml",
    )
    assert repeated.experiment_id == queued.experiment_id
    completed = service.execute_experiment(
        queued.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        worker_id="worker-test",
    )
    assert completed.status == "succeeded"
    assert completed.progress == 1
    assert completed.selected_candidate_id
    with pytest.raises(ValueError, match="queued"):
        service.execute_experiment(
            queued.experiment_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            worker_id="worker-test",
        )
    with pytest.raises(ValueError, match="mutable only while running"):
        service.repository.update(
            "experiment",
            completed.experiment_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=completed.revision,
            updated_payload={"selected_candidate_id": "tampered-candidate"},
        )


def test_failed_run_can_retry_with_same_identity_and_incremented_counter(tmp_path: Path) -> None:
    service = build_worker_service(tmp_path)
    queued = service.queue_experiment(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            feature_dataset_version_id="feature-v1",
            split_policy=split_policy(),
            algorithms=["dummy_prior"],
            idempotency_key="queue-fail",
        ),
        actor_id="user-ml",
    )
    with pytest.raises(ValueError, match="no non-baseline"):
        service.execute_experiment(
            queued.experiment_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            worker_id="worker-test",
        )
    failed = service.experiment(
        queued.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    )
    assert failed.status == "failed"
    retried = service.retry_experiment(
        failed.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentRetryRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=failed.revision,
        ),
        actor_id="user-ml",
    )
    assert retried.experiment_id == failed.experiment_id
    assert retried.status == "queued"
    assert retried.retry_count == 1


def test_queued_run_can_be_cancelled_and_retried(tmp_path: Path) -> None:
    service = build_worker_service(tmp_path)
    queued = service.queue_experiment(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            feature_dataset_version_id="feature-v1",
            split_policy=split_policy(),
            algorithms=["dummy_prior", "logistic_regression"],
            idempotency_key="queue-cancel",
        ),
        actor_id="user-ml",
    )
    cancelled = service.cancel_experiment(
        queued.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCancelRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=queued.revision,
            reason="operator requested cancellation",
        ),
        actor_id="user-ml",
    )
    assert cancelled.status == "cancelled"
    assert all(item.status == "rejected" for item in cancelled.candidates)
    retried = service.retry_experiment(
        cancelled.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentRetryRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=cancelled.revision,
        ),
        actor_id="user-ml",
    )
    assert retried.status == "queued"
    assert all(item.status == "queued" for item in retried.candidates)


def test_stale_running_run_is_requeued_with_same_identity(tmp_path: Path) -> None:
    service = build_worker_service(tmp_path)
    queued = service.queue_experiment(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            feature_dataset_version_id="feature-v1",
            split_policy=split_policy(),
            algorithms=["dummy_prior", "logistic_regression"],
            idempotency_key="queue-stale",
        ),
        actor_id="user-ml",
    )
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    running = ExperimentRun.model_validate(
        service.repository.transition(
            "experiment",
            queued.experiment_id,
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            target_status="running",
            expected_revision=queued.revision,
            transition_kind="run",
            updated_payload={"updated_at": stale_time.isoformat(), "progress": 0.4},
        )
    )
    recovered = service.recover_stale_experiment(
        running.experiment_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=ExperimentRecoverRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=running.revision,
            stale_after_minutes=30,
        ),
        actor_id="user-admin",
    )
    assert recovered.experiment_id == queued.experiment_id
    assert recovered.status == "queued"
    assert recovered.retry_count == 1
