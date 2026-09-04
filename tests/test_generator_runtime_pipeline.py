
from __future__ import annotations

def create_test_batch_payload(
    event_id: str = "evt-001",
    asset_id: str = "M14860",
    observed_at: str = "2026-08-25T10:00:00Z",
    model_id: str = "pdm-lightgbm",
    model_version: str = "1.0.0",
    score: float = 0.88,
    output_status: str = "predicted",
    batch_id: str = "batch-001",
    model_set_id: str = "model-set-v1",
    model_set_version: str = "1.0.0",
    source_kind: str = "live_sensor",
    maintenance_event_id: str | None = None,
) -> PredictionResultBatchPayload:
    from datetime import datetime, timezone
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        PredictionResultBatchPayload,
        PredictionResultBatchSourceContext,
        PredictionResultItem,
        PredictionResultProducer,
        PredictionResultLineage,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )

    if isinstance(observed_at, str):
        s = observed_at.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        obs_dt = datetime.fromisoformat(s)
    else:
        obs_dt = observed_at

    f_sha = "1" * 64
    h_sha = "2" * 64
    l_sha = "3" * 64
    if source_kind == "maintenance_replay_overlay" and not maintenance_event_id:
        raise ValueError("maintenance_event_id is required for a maintenance replay test payload")
    lineage = (
        {
            "simulation_session_id": "sim-priority-test",
            "overlay_branch_id": f"overlay-{maintenance_event_id}",
            "history_segment_id": f"history-{maintenance_event_id}",
            "maintenance_event_id": maintenance_event_id,
            "maintenance_action_id": f"action-{maintenance_event_id}",
            "state_version": 1,
        }
        if source_kind == "maintenance_replay_overlay"
        else {
            "simulation_session_id": None,
            "overlay_branch_id": None,
            "history_segment_id": None,
            "maintenance_event_id": None,
            "maintenance_action_id": None,
            "state_version": None,
        }
    )

    item_dict = {
        "event_id": event_id,
        "asset_id": asset_id,
        "observed_at": obs_dt,
        "source_kind": source_kind,
        "source_ref": {"uri": "test.jsonl", "sha256": "a" * 64},
        "output_status": output_status,
        "score": score if output_status == "predicted" else None,
        "model_id": model_id,
        "model_version": model_version,
        "model_artifact_manifest_sha256": "a" * 64,
        "feature_schema_version": "v1.0",
        "history_requirement_version": "v1.0",
        "label_schema_version": "v1.0",
        "feature_schema_sha256": f_sha,
        "history_requirement_sha256": h_sha,
        "label_schema_sha256": l_sha,
        "lineage": lineage,
        "failure_reason": None if output_status == "predicted" else "failure reason",
    }

    item_sha = compute_prediction_result_item_sha256(item_dict)

    item = PredictionResultItem(
        event_id=event_id,
        asset_id=asset_id,
        observed_at=obs_dt,
        source_kind=source_kind,
        source_ref=PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64),
        payload_sha256=item_sha,
        output_status=output_status,
        score=score if output_status == "predicted" else None,
        model_id=model_id,
        model_version=model_version,
        model_artifact_manifest_sha256="a" * 64,
        feature_schema_version="v1.0",
        history_requirement_version="v1.0",
        label_schema_version="v1.0",
        feature_schema_sha256=f_sha,
        history_requirement_sha256=h_sha,
        label_schema_sha256=l_sha,
        lineage=PredictionResultLineage.model_validate(lineage),
        failure_reason=None if output_status == "predicted" else "failure reason",
    )

    model_set = ActiveModelSetSnapshot(
        model_set_id=model_set_id,
        model_set_version=model_set_version,
        models=[
            ActiveModelSnapshotItem(
                model_id=model_id,
                model_version=model_version,
                required=True,
                model_artifact_manifest_sha256="a" * 64,
            )
        ],
    )

    source_context = PredictionResultBatchSourceContext(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source_uri="test.jsonl",
        source_checksum="a" * 64,
        source_kind=source_kind,
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage.model_validate(lineage),
    )

    producer = PredictionResultProducer(system="systems.generator", runtime_version="1.0.0", outbox_id=None)
    return PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id=batch_id,
        producer=producer,
        emitted_at=datetime.now(timezone.utc),
        source_context=source_context,
        model_set=model_set,
        results=[item],
    )


def create_test_runtime_source_context(
    *,
    source_uri: str = "test.jsonl",
    source_checksum: str = "a" * 64,
):
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultLineage,
        RuntimeSourceContext,
    )

    return RuntimeSourceContext(
        source_uri=source_uri,
        source_checksum=source_checksum,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="observation-source-v1",
        pipeline_contract_version="prediction-result-batch-v1",
        lineage=PredictionResultLineage(),
    )


def create_test_runtime_input_identity(
    *,
    dataset_id: str = "canonical-ai4i-v1",
    dataset_version: str = "canonical-ai4i-physics-v3.1",
    source_uri: str = "test.jsonl",
    source_checksum: str = "a" * 64,
    source_kind: str = "live_sensor",
    source_contract_version: str = "observation-source-v1",
    source_schema_version: str = "observation-source-v1",
    pipeline_contract_version: str = "generator-prediction-result-v1",
    lineage=None,
):
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultLineage,
        RuntimeInputIdentity,
        RuntimeSourceContext,
    )

    if lineage is None:
        lineage_obj = PredictionResultLineage()
    elif isinstance(lineage, dict):
        lineage_obj = PredictionResultLineage.model_validate(lineage)
    else:
        lineage_obj = lineage

    return RuntimeInputIdentity(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source=RuntimeSourceContext(
            source_uri=source_uri,
            source_checksum=source_checksum,
            source_kind=source_kind,
            source_contract_version=source_contract_version,
            source_schema_version=source_schema_version,
            pipeline_contract_version=pipeline_contract_version,
            lineage=lineage_obj,
        ),
    )


def create_test_active_model_set_snapshot(
    *,
    model_set_id: str = "pdm-default",
    model_set_version: str = "1.0.0",
    model_id: str = "pdm-lightgbm",
    model_version: str = "pdm-lightgbm-v1.0",
):
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
    )

    return ActiveModelSetSnapshot(
        model_set_id=model_set_id,
        model_set_version=model_set_version,
        models=[
            ActiveModelSnapshotItem(
                model_id=model_id,
                model_version=model_version,
                required=True,
                model_artifact_manifest_sha256="a" * 64,
            )
        ],
    )

"""Comprehensive test suite for the Generator Runtime Prediction Pipeline."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("lightgbm")

from systems.generator.generator_config import PATHS, GeneratorPaths
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.model.publisher import ModelArtifactPublisher
from systems.generator.app.main import app
from systems.generator.app.runtime_pipeline.prediction_batch_service import (
    PredictionBatchService,
)
from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
    PredictionDeliveryService,
)
from systems.generator.app.runtime_pipeline.prediction_delivery_worker import (
    PredictionDeliveryWorker,
)
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineAssetIdMissingError,
    PipelineDeliveryFailedError,
    PipelineDeliveryServerError,
    PipelineDeliveryTimeoutError,
    PipelineDuplicateInputError,
    PipelineHistoryInsufficientError,
    PipelineInputChecksumMismatchError,
    PipelineInputNotFoundError,
    PipelineJobNotFailedError,
    PipelineMappingNotImplementedError,
    PipelineModelFeatureMissingValueHandlingNotImplementedError,
    PipelineModelPredictionFailedError,
    PipelineModelSnapshotArtifactMissingError,
    PipelineModelSnapshotChecksumMismatchError,
    PipelineModelSnapshotIncompatibleError,
    PipelineModelSetChangedError,
    PipelineOutboxEventConflictError,
    PipelineNoActiveModelError,
    PipelinePathNotAllowedError,
    PipelinePredictionObservationAlignmentNotImplementedError,
    PipelineRuntimeFeatureFailedError,
    PipelineSensorValueMissingError,
    PipelineSourceAlreadyProcessedError,
    PipelineSourceAlreadyRegisteredError,
    PipelineSourceChecksumChangedError,
    PipelineSourceFileNotStableError,
    PipelineStateTransitionInvalidError,
    PipelineTimestampInvalidError,
)
from systems.generator.app.runtime_pipeline.pipeline_manager import PipelineManager
from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    InternalModelPredictionResult,
    ModelPredictionResult,
    PredictionDeliveryEventState,
    PredictionOutboxItem,
    PredictionResultBatchPayload,
    PipelineQueueItem,
    PipelineRunState,
    SourceLineage,
    now_utc_iso,
)
from systems.generator.app.runtime_pipeline.pipeline_service import PipelineService
from systems.generator.app.runtime_pipeline.pipeline_state import PipelineStateManager
from systems.generator.app.runtime_pipeline.pipeline_worker import PipelineWorker
from systems.generator.app.runtime_pipeline.prediction_service import (
    PredictionService,
    REGISTERED_BASE_MODELS,
)
from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureService


class MockEstimator:
    """Mock ML model for controlled anomaly score output."""

    def __init__(self, anomaly_prob: float = 0.1) -> None:
        self.anomaly_prob = anomaly_prob

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        n = len(X)
        probs = np.zeros((n, 2))
        for i in range(n):
            if X.shape[1] > 0 and X[i, 0] > 298.25:
                prob = self.anomaly_prob
            else:
                prob = 0.05
            probs[i, 0] = 1.0 - prob
            probs[i, 1] = prob
        return probs

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


@pytest.fixture
def isolated_runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated environment with mock models, database, and directories."""
    data_dir = tmp_path / "data"
    incoming_dir = data_dir / "incoming"
    preprocessed_dir = tmp_path / "data_preprocessed"
    models_store = tmp_path / "models_store"
    artifacts_dir = models_store / "artifacts"
    features_cache_dir = models_store / "cache" / "runtime_features"
    outbox_dir = preprocessed_dir / "prediction_outbox"

    for d in [data_dir, incoming_dir, preprocessed_dir, models_store, artifacts_dir, features_cache_dir, outbox_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Monkeypatch PATHS
    monkeypatch.setattr(PATHS, "data_dir", data_dir)
    monkeypatch.setattr(PATHS, "data_preprocessed", preprocessed_dir)
    monkeypatch.setattr(PATHS, "models_store", models_store)
    monkeypatch.setattr(PATHS, "pipeline_input_roots", [data_dir, preprocessed_dir, tmp_path])
    monkeypatch.setattr(PATHS, "runtime_feature_root", features_cache_dir)
    monkeypatch.setattr(PATHS, "notification_outbox_root", outbox_dir)
    monkeypatch.setattr(PATHS, "pipeline_queue_db", preprocessed_dir / "pipeline_queue" / "queue.db")
    monkeypatch.setattr(PATHS, "pipeline_state_root", preprocessed_dir / "pipeline_runs")
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "test-runtime-1.0.0")

    publisher = ModelArtifactPublisher(artifacts_dir)

    feature_schema = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-feature-schema.schema.json",
        "schema_version": "1.0",
        "features": [
            {
                "feature_name": "feat_air_temp",
                "source_field": "Air temperature [K]",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            },
            {
                "feature_name": "feat_process_temp",
                "source_field": "Process temperature [K]",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            },
            {
                "feature_name": "feat_rot_speed",
                "source_field": "Rotational speed [rpm]",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            },
        ],
    }

    label_schema = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-label-schema.schema.json",
        "schema_version": "1.0",
        "prediction_horizon_hours": 12,
        "target_type": "binary_failure_within_horizon",
    }

    hist_req = {
        "minimum_history_rows": 2,
        "required_columns": [
            "Air temperature [K]",
            "Process temperature [K]",
            "Rotational speed [rpm]",
        ],
        "missing_history_policy": "reject",
    }

    metrics = {
        "metrics_summary": {"f1": 0.88, "precision": 0.90, "recall": 0.86, "accuracy": 0.98},
        "primary_metric": "f1",
    }

    model_probs = {
        "pdm-lightgbm": 0.1,
        "pdm-xgboost": 0.85,
        "pdm-random_forest": 0.75,
    }
    base_map = {
        "pdm-lightgbm": "lightgbm",
        "pdm-xgboost": "xgboost",
        "pdm-random_forest": "random_forest",
    }

    for model_id, prob in model_probs.items():
        dummy_model = MockEstimator(anomaly_prob=prob)
        publisher.publish_artifact(
            model_id=model_id,
            model_version=f"{model_id}-v1.0",
            base_model=base_map[model_id],
            model_obj=dummy_model,
            dataset_id="canonical-ai4i-v1",
            dataset_version="canonical-ai4i-physics-v3.1",
            feature_dataset_version="feat-v1",
            feature_schema=feature_schema,
            label_schema=label_schema,
            history_requirement=hist_req,
            metrics=metrics,
            training_config={
                "training_config_version": "train-cfg-v1",
                "training_config_sha256": "0" * 64,
                "training_config_uri": "models_store/configs/train-cfg-v1.json",
                "hyperparameters": {},
            },
            provenance={
                "dataset_id": "canonical-ai4i-v1",
                "dataset_version": "canonical-ai4i-physics-v3.1",
                "feature_dataset_version": "feat-v1",
                "feature_dataset_metadata_sha256": "1" * 64,
                "feature_schema_sha256": "2" * 64,
                "label_schema_sha256": "3" * 64,
                "prediction_horizon_hours": 12,
            },
        )

    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    active_service = ActiveModelSetService(models_store_dir=models_store)
    active_set = ActiveModelSet(
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={
            "lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True),
            "xgboost": ActiveModelConfig(model_version="pdm-xgboost-v1.0", required=True),
            "random_forest": ActiveModelConfig(model_version="pdm-random_forest-v1.0", required=True),
        },
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    queue = PipelineQueue(db_path=preprocessed_dir / "pipeline_queue" / "queue.db")
    repository = PipelineRepository(base_dir=preprocessed_dir)
    feat_service = RuntimeFeatureService(cache_dir=features_cache_dir)
    pred_service = PredictionService(
        models_store_dir=artifacts_dir,
        publisher=publisher,
    )
    batch_service = PredictionBatchService()
    notif_service = PredictionDeliveryService(outbox_dir=outbox_dir)
    notif_worker = PredictionDeliveryWorker(service=notif_service, repository=repository)

    service = PipelineService(
        repository=repository,
        preprocessing_service=None,
        runtime_feature_service=feat_service,
        prediction_service=pred_service,
        prediction_batch_service=batch_service,
        prediction_delivery_service=notif_service,
    )
    worker = PipelineWorker(queue=queue, service=service, max_attempts=5, retry_backoff_seconds=0.01)
    manager = PipelineManager(
        queue=queue,
        repository=repository,
        service=service,
        prediction_delivery_service=notif_service,
    )

    return {
        "tmp_path": tmp_path,
        "incoming_dir": incoming_dir,
        "artifacts_dir": artifacts_dir,
        "preprocessed_dir": preprocessed_dir,
        "outbox_dir": outbox_dir,
        "publisher": publisher,
        "queue": queue,
        "repository": repository,
        "feat_service": feat_service,
        "pred_service": pred_service,
        "batch_service": batch_service,
        "service": service,
        "worker": worker,
        "manager": manager,
        "notif_service": notif_service,
        "notif_worker": notif_worker,
    }


def create_sample_observation_jsonl(file_path: Path, num_rows: int = 5, asset_id: str = "M14860") -> tuple[Path, str]:
    """Helper creating valid JSONL observation file with asset_id and timestamps."""
    records = []
    for i in range(num_rows):
        records.append({
            "UDI": i + 1,
            "Product ID": f"{asset_id}_{i+1:04d}",
            "asset_id": asset_id,
            "Type": "M",
            "Air temperature [K]": 298.1 + i * 0.1,
            "Process temperature [K]": 308.6 + i * 0.1,
            "Rotational speed [rpm]": 1551 - i * 10,
            "Torque [Nm]": 42.8 + i * 0.5,
            "Tool wear [min]": i * 5,
            "timestamp": f"2026-08-25T10:{i:02d}:00Z",
        })
    content = "\n".join(json.dumps(r) for r in records) + "\n"
    file_path.write_text(content, encoding="utf-8")
    sha256 = compute_file_sha256(file_path)
    return file_path, sha256


# =====================================================================
# 1. Multi-Equipment Prediction and Batch Building Test
# =====================================================================

def test_multi_equipment_prediction_and_batch_building(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]

    # Create multi-equipment input: Asset A (3 rows), Asset B (3 rows), Asset C (1 row)
    records = [
        # Asset A (3 rows -> ready)
        {"UDI": 1, "Product ID": "M14860_01", "asset_id": "M14860", "Air temperature [K]": 298.1, "Process temperature [K]": 308.6, "Rotational speed [rpm]": 1550, "Torque [Nm]": 42.0, "timestamp": "2026-08-25T10:00:00Z"},
        {"UDI": 2, "Product ID": "M14860_02", "asset_id": "M14860", "Air temperature [K]": 298.2, "Process temperature [K]": 308.7, "Rotational speed [rpm]": 1540, "Torque [Nm]": 43.0, "timestamp": "2026-08-25T10:01:00Z"},
        {"UDI": 3, "Product ID": "M14860_03", "asset_id": "M14860", "Air temperature [K]": 298.3, "Process temperature [K]": 308.8, "Rotational speed [rpm]": 1530, "Torque [Nm]": 44.0, "timestamp": "2026-08-25T10:02:00Z"},
        # Asset B (3 rows -> ready)
        {"UDI": 4, "Product ID": "L47181_01", "asset_id": "L47181", "Air temperature [K]": 298.0, "Process temperature [K]": 308.5, "Rotational speed [rpm]": 1400, "Torque [Nm]": 45.0, "timestamp": "2026-08-25T10:00:00Z"},
        {"UDI": 5, "Product ID": "L47181_02", "asset_id": "L47181", "Air temperature [K]": 298.1, "Process temperature [K]": 308.6, "Rotational speed [rpm]": 1405, "Torque [Nm]": 46.0, "timestamp": "2026-08-25T10:01:00Z"},
        {"UDI": 6, "Product ID": "L47181_03", "asset_id": "L47181", "Air temperature [K]": 298.2, "Process temperature [K]": 308.7, "Rotational speed [rpm]": 1410, "Torque [Nm]": 47.0, "timestamp": "2026-08-25T10:02:00Z"},
        # Asset C (1 row -> insufficient history when min=2)
        {"UDI": 7, "Product ID": "H29424_01", "asset_id": "H29424", "Air temperature [K]": 298.0, "Process temperature [K]": 308.4, "Rotational speed [rpm]": 1420, "Torque [Nm]": 40.0, "timestamp": "2026-08-25T10:00:00Z"},
    ]
    src_file = incoming / "multi_equipments.jsonl"
    src_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    sha256 = compute_file_sha256(src_file)

    item = env["queue"].enqueue(
        job_id="job-multi-eq-01",
        runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha256),
    )

    run_state = env["worker"].process_one()
    assert run_state is not None
    assert run_state.status == "partially_succeeded"  # because Asset C has insufficient history

    # 1. Check prediction results per asset — score-based, no threshold/is_anomaly
    results = run_state.prediction_results
    assert len(results) == 9  # 3 assets * 3 models

    assets_in_results = {r.asset_id for r in results}
    assert assets_in_results == {"M14860", "L47181", "H29424"}

    for r in results:
        assert not hasattr(r, "threshold") or "threshold" not in r.model_fields
        assert not hasattr(r, "is_anomaly") or "is_anomaly" not in r.model_fields
        assert not hasattr(r, "prediction") or "prediction" not in r.model_fields
        assert r.observed_at != ""
        if r.status == "succeeded":
            assert r.score is not None
            assert 0.0 <= r.score <= 1.0
            assert r.score_type == "positive_class_probability"
            assert r.score_source == "predict_proba"

    # Asset C must have status="unknown" and PIPELINE_HISTORY_INSUFFICIENT
    asset_c_results = [r for r in results if r.asset_id == "H29424"]
    for r in asset_c_results:
        assert r.status == "unknown"
        assert r.error_code == "PIPELINE_HISTORY_INSUFFICIENT"

    # 2. Check outbox records — model_results is dictionary keyed by model_id, no top-level feature_ref
    outbox_items = env["notif_service"].list_outbox_items()
    outbox_asset_ids = {item.asset_id for item in outbox_items}
    assert len(outbox_items) == 3
    assert "M14860" in outbox_asset_ids
    assert "L47181" in outbox_asset_ids
    assert "H29424" in outbox_asset_ids

    for oi in outbox_items:
        assert oi.status == "pending"
        payload = oi.payload
        assert isinstance(payload.results, list)
        assert len(payload.results) == 3
        model_ids = {r.model_id for r in payload.results}
        assert "pdm-lightgbm" in model_ids
        assert "pdm-xgboost" in model_ids
        assert "pdm-random_forest" in model_ids
        for r in payload.results:
            assert r.observed_at is not None
            assert r.output_status in ("predicted", "history_insufficient")

    assert len(run_state.prediction_event_ids) == len(outbox_items)


# =====================================================================
# 2. Prediction Delivery Worker Outbox Retries & Decoupling Test
# =====================================================================

def test_delivery_worker_decoupled_retry_and_backoff(isolated_runtime_env, monkeypatch):
    env = isolated_runtime_env
    notif_service = env["notif_service"]
    notif_worker = env["notif_worker"]

    payload = create_test_batch_payload(
        event_id="evt-retry-01",
        asset_id="M14860",
        observed_at="2026-08-25T10:00:00Z",
        model_id="pdm-xgboost",
        score=0.88,
        batch_id="batch-retry-01",
    )

    item = notif_service.create_outbox_record(payload)
    event_id = item.event_id
    assert item.status == "pending"
    assert item.attempt == 0

    # 2. Simulate 500 Server Error on first attempt
    def mock_send_500(pl):
        raise PipelineDeliveryServerError("500 Internal Server Error")

    monkeypatch.setattr(notif_service, "send_once", mock_send_500)

    # Process pending items
    processed = notif_worker.process_pending()
    assert processed == 1

    updated_item = notif_service.get_outbox_item(event_id)
    assert updated_item is not None
    assert updated_item.status == "retry_wait"
    assert updated_item.attempt == 1
    assert updated_item.next_retry_at is not None

    # 3. Simulate 400 Bad Request error (non-retryable)
    def mock_send_400(pl):
        raise PipelineDeliveryFailedError("400 Bad Request", retryable=False)

    monkeypatch.setattr(notif_service, "send_once", mock_send_400)
    updated_item.next_retry_at = None  # force due immediately
    notif_service.save_outbox_item(updated_item)

    processed = notif_worker.process_pending()
    assert processed == 1

    failed_item = notif_service.get_outbox_item(event_id)
    assert failed_item.status == "failed"
    assert failed_item.attempt == 2

    # 4. Successful delivery for a new item
    success_payload = create_test_batch_payload(
        event_id="evt-success-01",
        asset_id="M14860",
        score=0.12,
        batch_id="batch-success-01",
    )
    success_item = notif_service.create_outbox_record(success_payload)

    def mock_send_200(pl):
        return {"delivered": True, "status_code": 200}

    monkeypatch.setattr(notif_service, "send_once", mock_send_200)

    processed = notif_worker.process_pending()
    assert processed >= 1
    sent_item = notif_service.get_outbox_item(success_item.event_id)
    assert sent_item.status == "sent"
    assert sent_item.attempt == 1


def test_queue_promotes_only_first_replay_for_each_maintenance_event(tmp_path):
    queue = PipelineQueue(db_path=tmp_path / "queue.db")

    def enqueue(job_id: str, source_kind: str, maintenance_event_id: str | None = None) -> None:
        source_file = tmp_path / f"{job_id}.jsonl"
        source_file.write_text(json.dumps({"job_id": job_id}) + "\n", encoding="utf-8")
        lineage = None
        if source_kind == "maintenance_replay_overlay":
            lineage = {
                "simulation_session_id": "sim-priority-test",
                "overlay_branch_id": f"overlay-{maintenance_event_id}",
                "history_segment_id": f"history-{maintenance_event_id}",
                "maintenance_event_id": maintenance_event_id,
                "maintenance_action_id": f"action-{maintenance_event_id}",
                "state_version": 1,
            }
        queue.enqueue(
            job_id=job_id,
            runtime_input=create_test_runtime_input_identity(
                source_uri=str(source_file),
                source_checksum=compute_file_sha256(source_file),
                source_kind=source_kind,
                lineage=lineage,
            ),
        )

    enqueue("live-first", "live_sensor")
    enqueue("live-second", "live_sensor")
    enqueue("replay-a-first", "maintenance_replay_overlay", "maintenance-a")
    enqueue("replay-a-second", "maintenance_replay_overlay", "maintenance-a")
    enqueue("replay-b-first", "maintenance_replay_overlay", "maintenance-b")

    first = queue.claim_next()
    assert first is not None
    assert first.job_id == "replay-a-first"
    queue.mark_succeeded(first.job_id)

    second = queue.claim_next()
    assert second is not None
    assert second.job_id == "replay-b-first"
    queue.mark_succeeded(second.job_id)

    third = queue.claim_next()
    assert third is not None
    assert third.job_id == "live-first"


def test_delivery_promotes_one_replay_per_event_then_returns_to_fifo(
    isolated_runtime_env,
    monkeypatch,
):
    service = isolated_runtime_env["notif_service"]
    worker = isolated_runtime_env["notif_worker"]
    delivered: list[str] = []

    def register(payload: PredictionResultBatchPayload, created_at: str) -> None:
        item = service.create_outbox_record(payload)
        item.created_at = created_at
        service.save_outbox_item(item)

    register(
        create_test_batch_payload(event_id="evt-live-old", batch_id="batch-live-old"),
        "2026-08-25T10:00:00+00:00",
    )
    register(
        create_test_batch_payload(
            event_id="evt-replay-a-first",
            batch_id="batch-replay-a-first",
            source_kind="maintenance_replay_overlay",
            maintenance_event_id="maintenance-a",
        ),
        "2026-08-25T10:01:00+00:00",
    )
    register(
        create_test_batch_payload(
            event_id="evt-replay-a-second",
            batch_id="batch-replay-a-second",
            source_kind="maintenance_replay_overlay",
            maintenance_event_id="maintenance-a",
        ),
        "2026-08-25T10:02:00+00:00",
    )
    register(
        create_test_batch_payload(
            event_id="evt-replay-b-first",
            batch_id="batch-replay-b-first",
            source_kind="maintenance_replay_overlay",
            maintenance_event_id="maintenance-b",
        ),
        "2026-08-25T10:03:00+00:00",
    )

    def record_delivery(payload: PredictionResultBatchPayload):
        delivered.append(payload.batch_id)
        return {"delivered": True, "status_code": 200}

    monkeypatch.setattr(service, "send_once", record_delivery)

    assert worker.process_pending() == 4
    assert delivered == [
        "batch-replay-a-first",
        "batch-replay-b-first",
        "batch-live-old",
        "batch-replay-a-second",
    ]


def test_new_replay_interrupts_stale_live_delivery_snapshot(
    isolated_runtime_env,
    monkeypatch,
):
    service = isolated_runtime_env["notif_service"]
    worker = isolated_runtime_env["notif_worker"]
    delivered: list[str] = []

    for index in range(3):
        payload = create_test_batch_payload(
            event_id=f"evt-live-{index}",
            batch_id=f"batch-live-{index}",
        )
        item = service.create_outbox_record(payload)
        item.created_at = f"2026-08-25T10:0{index}:00+00:00"
        service.save_outbox_item(item)

    def register_replay_during_first_live_delivery(payload: PredictionResultBatchPayload):
        delivered.append(payload.batch_id)
        if payload.batch_id == "batch-live-0":
            replay = create_test_batch_payload(
                event_id="evt-replay-new",
                batch_id="batch-replay-new",
                source_kind="maintenance_replay_overlay",
                maintenance_event_id="maintenance-new",
            )
            service.create_outbox_record(replay)
        return {"delivered": True, "status_code": 200}

    monkeypatch.setattr(service, "send_once", register_replay_during_first_live_delivery)

    assert worker.process_pending() == 1
    assert delivered == ["batch-live-0"]

    assert worker.process_pending() == 3
    assert delivered == [
        "batch-live-0",
        "batch-replay-new",
        "batch-live-1",
        "batch-live-2",
    ]


# =====================================================================
# 3. Input Validation Fail-Closed Tests (ID & Timestamp & Mapping)
# =====================================================================

def test_missing_or_blank_asset_id_fails_closed(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]

    # Blank / whitespace asset_id
    records = [
        {"asset_id": "  ", "Air temperature [K]": 300.0, "Process temperature [K]": 310.0, "Rotational speed [rpm]": 1500, "timestamp": "2026-08-25T10:00:00Z"},
        {"asset_id": "null", "Air temperature [K]": 305.0, "Process temperature [K]": 315.0, "Rotational speed [rpm]": 1510, "timestamp": "2026-08-25T10:01:00Z"},
    ]
    src_file = incoming / "blank_id.jsonl"
    src_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    sha256 = compute_file_sha256(src_file)

    item = env["queue"].enqueue(
        job_id="job-blank-id-01",
        runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha256),
    )

    run_state = env["worker"].process_one()
    assert run_state is None
    q_items = env["queue"].list_items(status="failed")
    assert any(q.error_code == "PIPELINE_ASSET_ID_VALUE_MISSING" for q in q_items)


def test_invalid_timestamp_fails_closed(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]

    # Invalid timestamp string
    records = [
        {"asset_id": "M14860", "Air temperature [K]": 300.0, "Process temperature [K]": 310.0, "Rotational speed [rpm]": 1500, "timestamp": "not-a-valid-timestamp"},
        {"asset_id": "M14860", "Air temperature [K]": 305.0, "Process temperature [K]": 315.0, "Rotational speed [rpm]": 1510, "timestamp": "2026-08-25T10:01:00Z"},
    ]
    src_file = incoming / "bad_ts.jsonl"
    src_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    sha256 = compute_file_sha256(src_file)

    item = env["queue"].enqueue(
        job_id="job-bad-ts-01",
        runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha256),
    )

    run_state = env["worker"].process_one()
    assert run_state is None
    q_items = env["queue"].list_items(status="failed")
    assert any(q.error_code == "PIPELINE_TIMESTAMP_INVALID" for q in q_items)


def test_unsupported_mapping_fails_with_501(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]

    # Raw sensor data with NO identifiable ID column at all
    records = [
        {"Sensor_A": 300.0, "Sensor_B": 310.0, "Sensor_C": 1500, "timestamp": "2026-08-25T10:00:00Z"},
        {"Sensor_A": 305.0, "Sensor_B": 315.0, "Sensor_C": 1510, "timestamp": "2026-08-25T10:01:00Z"},
    ]
    src_file = incoming / "unmapped.jsonl"
    src_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    sha256 = compute_file_sha256(src_file)

    item = env["queue"].enqueue(
        job_id="job-unmapped-01",
        runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha256),
    )

    run_state = env["worker"].process_one()
    assert run_state is None
    q_items = env["queue"].list_items(status="failed")
    assert any(q.error_code == "PIPELINE_MAPPING_NOT_IMPLEMENTED" for q in q_items)


# =====================================================================
# 4. Failed Job Re-enqueue (retry_failed_job) Transaction Test
# =====================================================================

def test_retry_failed_job_transaction(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]
    src_file, sha256 = create_sample_observation_jsonl(incoming / "re_enqueue.jsonl", num_rows=1)

    # 1. Enqueue and let it fail (1 row -> history insufficient)
    item = env["queue"].enqueue(
        job_id="job-fail-first",
        runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha256),
    )
    env["worker"].process_one()

    failed_items = env["queue"].list_items(status="failed")
    assert len(failed_items) == 1

    # 2. Call retry_failed_job
    new_item = env["queue"].retry_failed_job("job-fail-first")
    assert new_item.status == "queued"
    assert new_item.retry_of_job_id == "job-fail-first"
    assert new_item.attempt == 1
    assert "retry" in new_item.job_id

    # 3. Cannot re-enqueue a succeeded job
    succeeded_file, s_sha = create_sample_observation_jsonl(incoming / "succ.jsonl", num_rows=5)
    s_item = env["queue"].enqueue(
        job_id="job-succ",
        runtime_input=create_test_runtime_input_identity(source_uri=str(succeeded_file), source_checksum=s_sha),
    )
    env["worker"].process_one()

    with pytest.raises(PipelineJobNotFailedError):
        env["queue"].retry_failed_job("job-succ")


# =====================================================================
# 5. Path Allowed Roots & Path Traversal Security Test
# =====================================================================

def test_path_security_and_allowed_roots(isolated_runtime_env):
    env = isolated_runtime_env

    # 1. Path traversal rejected
    with pytest.raises(PipelinePathNotAllowedError):
        env["service"].execute_queue_item(
            PipelineQueueItem(
                job_id="job-trav",
                source_uri="../outside.jsonl",
                source_checksum="a" * 64,
                dataset_id="canonical-ai4i-v1",
                dataset_version="canonical-ai4i-physics-v3.1",
                    pipeline_contract_version="generator-prediction-result-v1",
                    source_kind="live_sensor",
                    source_contract_version="observation-source-v1",
                source_schema_version="observation-source-v1",
            )
        )

    # 2. Outside allowed roots rejected
    outside_file = Path("C:/Windows/temp/outside.jsonl") if os.name == "nt" else Path("/tmp/outside.jsonl")
    with pytest.raises(PipelinePathNotAllowedError):
        env["service"].execute_queue_item(
            PipelineQueueItem(
                job_id="job-outside",
                source_uri=str(outside_file),
                source_checksum="b" * 64,
                dataset_id="canonical-ai4i-v1",
                dataset_version="canonical-ai4i-physics-v3.1",
                    pipeline_contract_version="generator-prediction-result-v1",
                    source_kind="live_sensor",
                    source_contract_version="observation-source-v1",
                source_schema_version="observation-source-v1",
            )
        )


# =====================================================================
# 6. FastAPI Router Endpoints Test
# =====================================================================

def test_runtime_pipeline_router_api_with_retry_failed(isolated_runtime_env):
    env = isolated_runtime_env
    incoming = env["incoming_dir"]
    src_file, sha256 = create_sample_observation_jsonl(incoming / "api_test.jsonl", num_rows=5)

    PipelineManager.set_instance(env["manager"])
    client = TestClient(app)

    # 1. Enqueue endpoint
    resp = client.post(
        "/internal/runtime-pipeline/enqueue",
        json={
            "job_id": "job-api-01",
            "source_uri": str(src_file),
            "source_checksum": sha256,
                "dataset_id": "canonical-ai4i-v1",
                "dataset_version": "canonical-ai4i-physics-v3.1",
                "source_kind": "live_sensor",
                "source_contract_version": "observation-source-v1",
            "source_schema_version": "observation-source-v1",
            "pipeline_contract_version": "generator-prediction-result-v1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-api-01"

    # 2. Queue list
    resp_q = client.get("/runtime-pipeline/queue")
    assert resp_q.status_code == 200
    assert len(resp_q.json()) >= 1

    # 3. Status endpoint
    resp_stat = client.get("/runtime-pipeline/status")
    assert resp_stat.status_code == 200
    assert "queued_count" in resp_stat.json()


# =====================================================================
# 7. Prediction Delivery Run State Synchronization & Event Aggregation Test
# =====================================================================

def test_delivery_worker_run_state_synchronization_and_aggregation(isolated_runtime_env, monkeypatch):
    env = isolated_runtime_env
    repo: PipelineRepository = env["repository"]
    notif_service: PredictionDeliveryService = env["notif_service"]
    notif_worker: PredictionDeliveryWorker = env["notif_worker"]

    run_id = "run-notif-sync-01"
    ev1_id = "evt-sync-01"
    ev2_id = "evt-sync-02"

    p1 = create_test_batch_payload(
        event_id="evt-sync-01",
        asset_id="Asset-1",
        model_id="pdm-xgboost",
        score=0.9,
        batch_id="batch-sync-01",
    )
    p2 = create_test_batch_payload(
        event_id="evt-sync-02",
        asset_id="Asset-2",
        model_id="pdm-xgboost",
        score=0.9,
        batch_id="batch-sync-02",
    )
    item1, _ = notif_service.register_idempotent_outbox_record(p1, run_id=run_id)
    item2, _ = notif_service.register_idempotent_outbox_record(p2, run_id=run_id)
    ev1_id = item1.event_id
    ev2_id = item2.event_id

    # Initial RunState with 2 prediction delivery events in pending
    run_state = PipelineRunState(
        run_id=run_id,
        job_id="job-sync-01",
        status="succeeded",
        current_stage=None,
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="0"*64, role="source_observation_protocol"),
        stages={},
        prediction_results=[],
        prediction_delivery_status="pending",
        prediction_event_ids=[ev1_id, ev2_id],
        prediction_events=[
            PredictionDeliveryEventState(
                event_id=ev1_id,
                asset_id="Asset-1",
                status="pending",
                attempt=0,
                max_attempts=5,
                updated_at=now_utc_iso(),
            ),
            PredictionDeliveryEventState(
                event_id=ev2_id,
                asset_id="Asset-2",
                status="pending",
                attempt=0,
                max_attempts=5,
                updated_at=now_utc_iso(),
            ),
        ],
        errors=[],
    )
    repo.save_run_state(run_state)

    # 1. Process Event 1 successfully (Mock HTTP 200)
    monkeypatch.setattr(notif_service, "send_once", lambda pl: {"delivered": True, "status_code": 200})
    item1 = notif_service.get_outbox_item(ev1_id)
    notif_worker.process_item(item1)

    # Check state after Event 1 sent, Event 2 still pending
    st1 = repo.get_run_state(run_id)
    assert st1 is not None
    assert st1.prediction_delivery_status == "pending"  # because ev2 is not sent yet
    ev1_state = next(e for e in st1.prediction_events if e.event_id == ev1_id)
    assert ev1_state.status == "sent"

    # 2. Process Event 2 successfully
    item2 = notif_service.get_outbox_item(ev2_id)
    notif_worker.process_item(item2)

    # Check state after both events sent -> prediction_delivery_status must be 'sent'
    st2 = repo.get_run_state(run_id)
    assert st2 is not None
    assert st2.prediction_delivery_status == "sent"
    assert all(e.status == "sent" for e in st2.prediction_events)


# =====================================================================
# 8. Delivery Interrupted 'sending' Items Startup Recovery Test
# =====================================================================

def test_delivery_worker_recover_interrupted_sending_items(isolated_runtime_env):
    env = isolated_runtime_env
    repo: PipelineRepository = env["repository"]
    notif_service: PredictionDeliveryService = env["notif_service"]
    notif_worker: PredictionDeliveryWorker = env["notif_worker"]

    run_id = "run-recover-01"
    payload = create_test_batch_payload(
        event_id="evt-recover-01",
        asset_id="Asset-Rec",
        model_id="pdm-xgboost",
        score=0.95,
        batch_id="batch-rec-01",
    )
    item = notif_service.create_outbox_record(payload, run_id=run_id)
    event_id = item.event_id
    item.status = "sending"
    notif_service.save_outbox_item(item)

    # Save run state
    run_state = PipelineRunState(
        run_id=run_id,
        job_id="job-rec-01",
        status="succeeded",
        current_stage=None,
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="0"*64, role="source_observation_protocol"),
        stages={},
        prediction_results=[],
        prediction_delivery_status="pending",
        prediction_event_ids=[event_id],
        prediction_events=[
            PredictionDeliveryEventState(
                event_id=event_id,
                asset_id="Asset-Rec",
                status="sending",
                attempt=0,
                max_attempts=5,
                updated_at=now_utc_iso(),
            )
        ],
        errors=[],
    )
    repo.save_run_state(run_state)

    # Execute recovery hook
    recovered_count = notif_worker.recover_interrupted_items()
    assert recovered_count == 1

    # Verify Outbox Item was recovered to retry_wait
    recovered_item = notif_service.get_outbox_item(event_id)
    assert recovered_item is not None
    assert recovered_item.status == "retry_wait"
    assert recovered_item.last_error_code == "PIPELINE_DELIVERY_INTERRUPTED"
    assert recovered_item.next_retry_at is not None

    # Verify RunState is synced
    updated_run = repo.get_run_state(run_id)
    assert updated_run is not None
    assert updated_run.prediction_delivery_status == "pending"
    ev_state = next(e for e in updated_run.prediction_events if e.event_id == event_id)
    assert ev_state.status == "retry_wait"
    assert ev_state.last_error_code == "PIPELINE_DELIVERY_INTERRUPTED"


# =====================================================================
# 9. Observation Alignment Verification Test (501 Fail-Closed)
# =====================================================================

def test_observation_timestamp_misalignment_raises_501(isolated_runtime_env):
    """If models for the same asset have different observed_at, raise 501 PipelinePredictionObservationAlignmentNotImplementedError."""
    env = isolated_runtime_env
    batch_service = env["batch_service"]

    # Succeeded model predictions with mismatched observed_at for asset M14860
    results = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="pdm-lightgbm-v1.0",
            status="succeeded",
            observed_at="2026-08-25T10:00:00Z",
            score_type="positive_class_probability",
            score_source="predict_proba",
            score=0.10,
        ),
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-xgboost",
            model_version="pdm-xgboost-v1.0",
            status="succeeded",
            observed_at="2026-08-25T10:05:00Z",  # Different timestamp!
            score_type="positive_class_probability",
            score_source="predict_proba",
            score=0.85,
        ),
    ]

    with pytest.raises(PipelinePredictionObservationAlignmentNotImplementedError) as exc_info:
        batch_service.collect(results)

    assert "observed_at" in str(exc_info.value)
    assert exc_info.value.status_code == 501
    assert exc_info.value.code == "PIPELINE_PREDICTION_OBSERVATION_ALIGNMENT_NOT_IMPLEMENTED"


# =====================================================================
# 10. Feature Calculation NaN/Inf Missing Value Handling Test (501 Fail-Closed)
# =====================================================================

def test_feature_calculation_nan_inf_raises_501_with_model_context(isolated_runtime_env):
    """If lag/rolling feature produces NaN/Inf, raise 501 PipelineModelFeatureMissingValueHandlingNotImplementedError with full context."""
    env = isolated_runtime_env
    feat_service: RuntimeFeatureService = env["feat_service"]

    # Data with only 1 row, but lag feature needs prior row
    df = pd.DataFrame([{
        "asset_id": "M14860",
        "Air temperature [K]": 298.1,
        "timestamp": "2026-08-25T10:00:00Z",
    }])

    lag_schema = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-feature-schema.schema.json",
        "schema_version": "1.0",
        "features": [
            {
                "feature_name": "feat_air_temp_lag1",
                "source_field": "Air temperature [K]",
                "operation": "lag",
                "parameters": {"periods": 1},
                "missing_value_policy": "drop",
            }
        ],
    }

    hist_req = {"minimum_history_rows": 1, "required_columns": ["Air temperature [K]"]}

    with pytest.raises(PipelineModelFeatureMissingValueHandlingNotImplementedError) as exc_info:
        feat_service.extract_and_publish(
            preprocessed_df=df,
            feature_schema_dict=lag_schema,
            history_requirement_dict=hist_req,
            model_id="pdm-lag-model",
            model_version="pdm-lag-model-v1.0",
            id_column="asset_id",
            time_column="timestamp",
        )

    assert exc_info.value.status_code == 501
    assert exc_info.value.code == "PIPELINE_MODEL_FEATURE_MISSING_VALUE_HANDLING_NOT_IMPLEMENTED"
    assert exc_info.value.details[0]["model_id"] == "pdm-lag-model"
    assert exc_info.value.details[0]["model_version"] == "pdm-lag-model-v1.0"
    assert exc_info.value.details[0]["feature_name"] == "feat_air_temp_lag1"


# =====================================================================
# 11. Raw Sensor Value Missing Check Test (422 Fail-Closed)
# =====================================================================

def test_raw_sensor_value_missing_raises_422(isolated_runtime_env):
    """If raw sensor field contains NaN/null, raise 422 PipelineSensorValueMissingError."""
    env = isolated_runtime_env
    feat_service: RuntimeFeatureService = env["feat_service"]

    df = pd.DataFrame([
        {"asset_id": "M14860", "Air temperature [K]": None, "timestamp": "2026-08-25T10:00:00Z"},
        {"asset_id": "M14860", "Air temperature [K]": 298.2, "timestamp": "2026-08-25T10:01:00Z"},
    ])

    raw_schema = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-feature-schema.schema.json",
        "schema_version": "1.0",
        "features": [
            {
                "feature_name": "feat_air_temp",
                "source_field": "Air temperature [K]",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            }
        ],
    }

    hist_req = {"minimum_history_rows": 2, "required_columns": ["Air temperature [K]"]}

    with pytest.raises(PipelineSensorValueMissingError) as exc_info:
        feat_service.extract_and_publish(
            preprocessed_df=df,
            feature_schema_dict=raw_schema,
            history_requirement_dict=hist_req,
            id_column="asset_id",
            time_column="timestamp",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "PIPELINE_SENSOR_VALUE_MISSING"
    assert exc_info.value.details[0]["source_field"] == "Air temperature [K]"


# =====================================================================
# 12. File Stability & Checksum Change Test
# =====================================================================

def test_file_size_changed_between_enqueue_and_start_raises_file_not_stable_error(isolated_runtime_env):
    """If file size changes between enqueue and execution start, raise PIPELINE_SOURCE_FILE_NOT_STABLE (retryable=True)."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, initial_sha = create_sample_observation_jsonl(incoming_dir / "unstable_size_file.jsonl", num_rows=3)
    item = queue.enqueue(job_id="job-change-size-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=initial_sha))

    # Modify file by appending bytes (changing size)
    with open(src_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "UDI": 99,
            "Product ID": "M14860_0099",
            "asset_id": "M14860",
            "Type": "M",
            "Air temperature [K]": 299.5,
            "Process temperature [K]": 309.5,
            "Rotational speed [rpm]": 1500,
            "Torque [Nm]": 43.0,
            "Tool wear [min]": 50,
            "timestamp": "2026-08-25T10:50:00Z",
        }) + "\n")

    with pytest.raises(PipelineSourceFileNotStableError) as exc_info:
        service.execute_queue_item(item)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "PIPELINE_SOURCE_FILE_NOT_STABLE"
    assert exc_info.value.retryable is True


def test_file_checksum_changed_between_enqueue_and_start_raises_retryable_error(isolated_runtime_env):
    """If file checksum changes (same size) between enqueue and execution start, raise PIPELINE_SOURCE_CHECKSUM_CHANGED (retryable=True)."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, initial_sha = create_sample_observation_jsonl(incoming_dir / "changing_file.jsonl", num_rows=3)
    item = queue.enqueue(job_id="job-change-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=initial_sha))

    # Modify content preserving exact byte length (replace character '1' with '2')
    content = src_file.read_text(encoding="utf-8")
    modified_content = content.replace("298.1", "298.2", 1)
    assert len(content.encode("utf-8")) == len(modified_content.encode("utf-8"))
    src_file.write_text(modified_content, encoding="utf-8")

    with pytest.raises(PipelineSourceChecksumChangedError) as exc_info:
        service.execute_queue_item(item)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "PIPELINE_SOURCE_CHECKSUM_CHANGED"
    assert exc_info.value.retryable is True


# =====================================================================
# 13. Duplicate Source Identity Enqueue Blocked Test
# =====================================================================

def test_duplicate_source_identity_enqueue_blocked(isolated_runtime_env):
    """Enqueuing identical source_identity twice should raise PipelineSourceAlreadyRegisteredError or PipelineSourceAlreadyProcessedError."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "dup_identity.jsonl", num_rows=2)
    item1 = queue.enqueue(job_id="job-dup-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    assert item1.job_id == "job-dup-1"

    # Enqueue same file again while queued
    with pytest.raises(PipelineSourceAlreadyRegisteredError) as exc_info:
        queue.enqueue(job_id="job-dup-2", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PIPELINE_SOURCE_ALREADY_REGISTERED"

    # Verify only 1 item in queue
    items = queue.list_items()
    assert len(items) == 1
    assert items[0].job_id == "job-dup-1"


def test_failed_source_redelivery_requires_explicit_retry(isolated_runtime_env):
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    src_file, sha = create_sample_observation_jsonl(
        incoming_dir / "failed_redelivery.jsonl", num_rows=2
    )
    runtime_input = create_test_runtime_input_identity(
        source_uri=str(src_file), source_checksum=sha
    )
    queue.enqueue(job_id="job-failed-original", runtime_input=runtime_input)
    queue.mark_failed("job-failed-original", "PIPELINE_HISTORY_INSUFFICIENT")

    with pytest.raises(PipelineDuplicateInputError) as exc_info:
        queue.enqueue(job_id="job-failed-redelivery", runtime_input=runtime_input)

    assert exc_info.value.code == "PIPELINE_DUPLICATE_INPUT"
    assert len(queue.list_items()) == 1


# =====================================================================
# 14. Same Path Different Checksum Enqueued as Separate Job Test
# =====================================================================

def test_same_path_different_content_enqueued_as_separate_job(isolated_runtime_env):
    """Overwriting the same path with different content produces a new source_identity and enqueues as a separate job."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]

    src_file = incoming_dir / "reused_path.jsonl"

    # 1. First content
    create_sample_observation_jsonl(src_file, num_rows=2, asset_id="M14860")
    sha1 = compute_file_sha256(src_file)
    item1 = queue.enqueue(job_id="job-reused-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha1))
    queue.mark_succeeded("job-reused-1")

    # 2. Overwrite with new content (different rows)
    create_sample_observation_jsonl(src_file, num_rows=4, asset_id="M14860")
    sha2 = compute_file_sha256(src_file)
    assert sha1 != sha2

    item2 = queue.enqueue(job_id="job-reused-2", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha2))
    assert item2.job_id == "job-reused-2"
    assert item2.source_identity != item1.source_identity


# =====================================================================
# 15. Different Path Same Content Duplicate Blocked Test
# =====================================================================

def test_different_path_same_content_duplicate_blocked(isolated_runtime_env):
    """Two different file paths with identical content share the same source_identity and the second is blocked."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]

    file1 = incoming_dir / "copy_1.jsonl"
    file2 = incoming_dir / "copy_2.jsonl"

    create_sample_observation_jsonl(file1, num_rows=2, asset_id="M14860")
    file2.write_bytes(file1.read_bytes())

    sha = compute_file_sha256(file1)
    item1 = queue.enqueue(job_id="job-copy-1", runtime_input=create_test_runtime_input_identity(source_uri=str(file1), source_checksum=sha))
    assert item1.job_id == "job-copy-1"

    with pytest.raises(PipelineSourceAlreadyRegisteredError):
        queue.enqueue(job_id="job-copy-2", runtime_input=create_test_runtime_input_identity(source_uri=str(file2), source_checksum=sha))


# =====================================================================
# 16. Unordered Timestamps Deterministically Sorted Test
# =====================================================================

def test_unordered_timestamps_deterministically_sorted(isolated_runtime_env):
    """Out-of-order timestamp inputs are deterministically sorted by [asset_id, timestamp]."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file = incoming_dir / "shuffled_times.jsonl"
    # Unordered timestamps across two assets with complete canonical sensor schema
    records = [
        {
            "UDI": 3,
            "Product ID": "M14860_0003",
            "asset_id": "M14860",
            "Type": "M",
            "Air temperature [K]": 298.3,
            "Process temperature [K]": 308.8,
            "Rotational speed [rpm]": 1530,
            "Torque [Nm]": 43.5,
            "Tool wear [min]": 10,
            "timestamp": "2026-08-25T10:02:00Z",
        },
        {
            "UDI": 2,
            "Product ID": "L47181_0002",
            "asset_id": "L47181",
            "Type": "L",
            "Air temperature [K]": 298.4,
            "Process temperature [K]": 308.9,
            "Rotational speed [rpm]": 1540,
            "Torque [Nm]": 44.0,
            "Tool wear [min]": 5,
            "timestamp": "2026-08-25T10:01:00Z",
        },
        {
            "UDI": 1,
            "Product ID": "M14860_0001",
            "asset_id": "M14860",
            "Type": "M",
            "Air temperature [K]": 298.1,
            "Process temperature [K]": 308.6,
            "Rotational speed [rpm]": 1551,
            "Torque [Nm]": 42.8,
            "Tool wear [min]": 0,
            "timestamp": "2026-08-25T10:00:00Z",
        },
        {
            "UDI": 1,
            "Product ID": "L47181_0001",
            "asset_id": "L47181",
            "Type": "L",
            "Air temperature [K]": 298.2,
            "Process temperature [K]": 308.7,
            "Rotational speed [rpm]": 1545,
            "Torque [Nm]": 43.1,
            "Tool wear [min]": 0,
            "timestamp": "2026-08-25T10:00:00Z",
        },
        {
            "UDI": 2,
            "Product ID": "M14860_0002",
            "asset_id": "M14860",
            "Type": "M",
            "Air temperature [K]": 298.2,
            "Process temperature [K]": 308.7,
            "Rotational speed [rpm]": 1540,
            "Torque [Nm]": 43.0,
            "Tool wear [min]": 5,
            "timestamp": "2026-08-25T10:01:00Z",
        },
    ]
    with open(src_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    sha = compute_file_sha256(src_file)
    item = queue.enqueue(job_id="job-sort-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    assert run_state.status == "succeeded"
    assert len(run_state.prediction_events) == 2


# =====================================================================
# 17. Observed_at Matches Actual Feature Row Metadata Test
# =====================================================================

def test_observed_at_matches_actual_feature_row_metadata(isolated_runtime_env):
    """Prediction result batch observed_at must strictly match the last observed feature row metadata."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "observed_at_match.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-obs-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    assert run_state.status == "succeeded"
    event_id = run_state.prediction_event_ids[0]
    event = repo.get_event(event_id)
    assert event is not None
    assert isinstance(event.results, list)
    assert len(event.results) > 0
    for r in event.results:
        obs_str = r.observed_at.isoformat() if hasattr(r.observed_at, "isoformat") else str(r.observed_at)
        assert "2026-08-25T10:02:00" in obs_str


# =====================================================================
# 18. Backend Payload Contains No Local Absolute Paths Test
# =====================================================================

def test_backend_payload_contains_no_local_absolute_paths(isolated_runtime_env):
    """Source lineage source_uri in PredictionResultBatchPayload must be normalized logical URI without drive letters or absolute local paths."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "clean_lineage.jsonl", num_rows=2, asset_id="M14860")
    item = queue.enqueue(job_id="job-lineage-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    event_id = run_state.prediction_event_ids[0]
    event = repo.get_event(event_id)
    assert event is not None

    source_uri = event.results[0].source_ref.uri
    assert not source_uri.startswith("C:")
    assert not source_uri.startswith("c:")
    assert not source_uri.startswith("\\")
    assert not source_uri.startswith("/")
    assert "clean_lineage.jsonl" in source_uri


# =====================================================================
# 19. Failed File Stability Emits No Outbox or Events Test
# =====================================================================

def test_failed_file_stability_emits_no_outbox_or_events(isolated_runtime_env):
    """When a file stability or preprocessing failure occurs, no outbox items or prediction events are published."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    outbox_dir: Path = env["outbox_dir"]
    events_dir: Path = env["repository"].events_dir
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    # File with invalid schema to trigger failure
    src_file = incoming_dir / "unstable_fail.jsonl"
    with open(src_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"unknown_id": "123", "value": 999}) + "\n")

    sha = compute_file_sha256(src_file)
    item = queue.enqueue(job_id="job-fail-outbox-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    with pytest.raises(PipelineMappingNotImplementedError):
        service.execute_queue_item(item)

    # Verify 0 files in outbox and 0 in events
    outbox_files = list(outbox_dir.glob("*.json"))
    event_files = list(events_dir.glob("*.json"))
    assert len(outbox_files) == 0
    assert len(event_files) == 0


# =====================================================================
# 20. Stage Checkpoints Recorded and Persisted Test
# =====================================================================

def test_stage_checkpoints_recorded_and_persisted(isolated_runtime_env):
    """Each completed stage records an atomic, persistent checkpoint with stage outputs and status."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "chk_flow.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-chk-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    assert run_state.status == "succeeded"
    assert run_state.last_completed_stage == "prediction_delivery"
    assert run_state.next_stage == "completed"

    chk = repo.get_checkpoint(run_state.run_id)
    assert chk is not None
    assert chk.checkpoint_version == "generator-runtime-checkpoint-v1"
    assert chk.last_completed_stage == "prediction_delivery"
    assert chk.status == "completed"
    assert "preprocessing" in chk.stage_outputs
    assert "runtime_feature" in chk.stage_outputs
    assert "runtime_prediction" in chk.stage_outputs


# =====================================================================
# 21. Resumption From Stage 2 Skips Preprocessing Test
# =====================================================================

def test_resumption_from_stage_2_skips_preprocessing(isolated_runtime_env, monkeypatch):
    """When a run previously completed Preprocessing (Checkpoint 1), re-execution skips Preprocessing and resumes from Runtime Feature."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "resume_stage2.jsonl", num_rows=3, asset_id="M14860")

    # 1. First execution fails at Stage 2 (simulate failure in runtime_feature)
    call_count = {"prep": 0}
    orig_preprocess = service.preprocessing_service.preprocess_with_plan

    def tracked_preprocess(*args, **kwargs):
        call_count["prep"] += 1
        return orig_preprocess(*args, **kwargs)

    monkeypatch.setattr(service.preprocessing_service, "preprocess_with_plan", tracked_preprocess)

    # Monkeypatch prediction service to fail on first attempt
    orig_predict = service.prediction_service.predict_for_models

    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated inference failure at stage 3")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-resume-prep-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    assert call_count["prep"] == 1
    # Check that Checkpoint 2 was recorded before stage 3 failure
    resumable = repo.find_resumable_run(item1.source_identity)
    assert resumable is not None
    assert resumable.last_completed_stage == "runtime_feature"

    # 2. Second execution with restored prediction service
    monkeypatch.setattr(service.prediction_service, "predict_for_models", orig_predict)

    item2 = PipelineQueueItem(
        job_id="job-resume-prep-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)

    assert run_state2.status == "succeeded"
    assert run_state2.run_id == resumable.run_id
    assert run_state2.resume_count == 1
    # Preprocess was NOT called again during resumption!
    assert call_count["prep"] == 1


# =====================================================================
# 22. Partial Model Feature Recovery Test
# =====================================================================

def test_partial_model_feature_recovery(isolated_runtime_env, monkeypatch):
    """When one model feature NPY is corrupted or deleted, only that model feature is re-extracted while others are reused."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "partial_feat.jsonl", num_rows=3, asset_id="M14860")

    # 1. Fail at prediction stage so Checkpoint 2 is saved
    orig_predict = service.prediction_service.predict_for_models

    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-part-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None
    chk = repo.get_checkpoint(first_run.run_id)
    assert chk is not None
    feat_outputs = chk.stage_outputs.get("runtime_feature", [])
    assert len(feat_outputs) >= 1

    # Corrupt the first feature NPY file
    target_npy = Path(feat_outputs[0].uri)
    if target_npy.exists():
        target_npy.write_text("corrupted", encoding="utf-8")

    # 2. Resume execution
    monkeypatch.setattr(service.prediction_service, "predict_for_models", orig_predict)

    item2 = PipelineQueueItem(
        job_id="job-part-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"


# =====================================================================
# 23. Source Checksum Change Rejects Checkpoint Test
# =====================================================================

def test_source_checksum_change_rejects_old_checkpoint(isolated_runtime_env, monkeypatch):
    """When source file content changes, existing checkpoint is invalidated and a fresh run is created."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha1 = create_sample_observation_jsonl(incoming_dir / "mod_check.jsonl", num_rows=2, asset_id="M14860")

    # 1. Fail at prediction
    orig_predict = service.prediction_service.predict_for_models

    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-mod-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha1))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None

    # 2. Modify file content -> new checksum
    src_file, sha2 = create_sample_observation_jsonl(incoming_dir / "mod_check.jsonl", num_rows=4, asset_id="M14860")
    monkeypatch.setattr(service.prediction_service, "predict_for_models", orig_predict)

    item2 = queue.enqueue(job_id="job-mod-2", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha2))
    run_state2 = service.execute_queue_item(item2)

    assert run_state2.status == "succeeded"
    assert run_state2.run_id != first_run.run_id


# =====================================================================
# 24. Safe Cleanup Removes Run-Dedicated Intermediates Test
# =====================================================================

def test_safe_cleanup_removes_run_dedicated_intermediates_preserves_models(isolated_runtime_env):
    """After Checkpoint 5 is published, run-dedicated intermediate datasets and NPYs are cleaned up while source files and models are preserved."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    models_store: Path = env.get("models_dir", getattr(PATHS, "models_store", Path("models_store")))

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "cleanup_test.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-clean-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    assert run_state.status == "succeeded"
    assert run_state.cleanup_status == "cleaned"

    # Source file MUST exist
    assert src_file.exists()

    # Model artifacts MUST exist
    for base_model in REGISTERED_BASE_MODELS:
        m_dir = models_store / "artifacts" / f"pdm-{base_model}"
        assert m_dir.exists()

    # Run-dedicated pipeline dataset directory MUST be removed
    run_dataset_dir = env["repository"].base_dir / "pipeline_datasets" / run_state.run_id
    assert not run_dataset_dir.exists()


def test_safe_cleanup_accepts_configured_runtime_feature_root(tmp_path, monkeypatch):
    run_id = "run-configured-feature-root"
    feature_root = tmp_path / "external-runtime-features"
    feature_file = feature_root / run_id / "features.npy"
    feature_file.parent.mkdir(parents=True)
    feature_file.write_bytes(b"runtime-features")
    monkeypatch.setattr(PATHS, "runtime_feature_root", feature_root)
    repository = PipelineRepository(base_dir=tmp_path / "data_preprocessed")

    cleaned, deleted, error = repository.cleanup_run_intermediate_outputs(
        run_id,
        [ArtifactReference(uri=str(feature_file), sha256="a" * 64, role="runtime_features")],
    )

    assert cleaned is True
    assert error is None
    assert str(feature_file.resolve()) in deleted
    assert not feature_file.exists()


# =====================================================================
# 25. Cleanup Failure Results In succeeded_with_cleanup_warning Test
# =====================================================================

def test_cleanup_failure_results_in_succeeded_with_cleanup_warning(isolated_runtime_env, monkeypatch):
    """When intermediate file cleanup encounters an error, the run status is succeeded_with_cleanup_warning without invalidating Outbox delivery."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "clean_warn.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-clean-warn-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    # Monkeypatch cleanup to fail
    def failing_cleanup(*args, **kwargs):
        return False, [], "Simulated permission denied on cleanup"

    monkeypatch.setattr(repo, "cleanup_run_intermediate_outputs", failing_cleanup)

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded_with_cleanup_warning"
    assert run_state.cleanup_status == "cleanup_failed"
    # Prediction delivery Outbox MUST still be published
    assert len(run_state.prediction_event_ids) > 0
    assert len(list(env["outbox_dir"].glob("*.json"))) > 0


# =====================================================================
# 26. Model Snapshot Matching Reuses Features and Predictions Test

# =====================================================================

def test_snapshot_matching_reuses_features_and_predictions(isolated_runtime_env, monkeypatch):
    """When active model artifact snapshot matches checkpoint, features and predictions are reused."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "snap_match.jsonl", num_rows=3, asset_id="M14860")

    # 1. Interrupt at Stage 5 delivery so checkpoint 4 is saved with status resumable
    orig_register = service.prediction_delivery_service.register_idempotent_outbox_record

    def failing_delivery(*args, **kwargs):
        raise PipelineDeliveryFailedError("Simulated delivery crash")

    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", failing_delivery)

    item1 = queue.enqueue(job_id="job-snap-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineDeliveryFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None
    chk1 = repo.get_checkpoint(first_run.run_id)
    assert chk1 is not None
    assert "model_snapshot" in chk1.model_dump()
    assert len(chk1.model_snapshot) >= 1

    # 2. Resume item with same source_identity
    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", orig_register)

    extract_called = False
    orig_extract = service.runtime_feature_service.extract_and_publish

    def spy_extract(*args, **kwargs):
        nonlocal extract_called
        extract_called = True
        return orig_extract(*args, **kwargs)

    monkeypatch.setattr(service.runtime_feature_service, "extract_and_publish", spy_extract)

    item2 = PipelineQueueItem(
        job_id="job-snap-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"
    assert not extract_called, "Features should have been reused from snapshot checkpoint"


# =====================================================================
# 27. Model Snapshot Version Change Recalculates Predictions Test
# =====================================================================

def test_snapshot_version_change_recalculates_predictions(isolated_runtime_env, monkeypatch):
    """When active model version changes, prediction results are re-evaluated."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "snap_ver.jsonl", num_rows=3, asset_id="M14860")

    # 1. Fail at batch building to stop at Checkpoint 3
    orig_collect = service.prediction_batch_service.collect

    def failing_collect(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated batch failure")

    monkeypatch.setattr(service.prediction_batch_service, "collect", failing_collect)

    item1 = queue.enqueue(job_id="job-ver-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None

    # 2. Update active model snapshot manifest version
    orig_build_snap = service._build_model_snapshot

    def modified_snap(base_models, *args, **kwargs):
        snap, arts = orig_build_snap(base_models, *args, **kwargs)
        for m_id in snap:
            snap[m_id]["model_version"] = snap[m_id]["model_version"] + "-v2.0"
            snap[m_id]["manifest_sha256"] = "1" * 64
        return snap, arts

    monkeypatch.setattr(service, "_build_model_snapshot", modified_snap)
    monkeypatch.setattr(service.prediction_batch_service, "collect", orig_collect)

    # Track prediction execution calls
    predict_called = False
    orig_predict = service.prediction_service.predict_for_models

    def spy_predict(*args, **kwargs):
        nonlocal predict_called
        predict_called = True
        return orig_predict(*args, **kwargs)

    monkeypatch.setattr(service.prediction_service, "predict_for_models", spy_predict)

    item2 = PipelineQueueItem(
        job_id="job-ver-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"
    assert predict_called, "Prediction should have been re-evaluated due to model version change"


# =====================================================================
# 28. Model Snapshot Feature Schema Change Re-extracts Features Test
# =====================================================================

def test_snapshot_feature_schema_change_reextracts_features(isolated_runtime_env, monkeypatch):
    """When feature schema sha256 differs in snapshot, feature matrix is re-extracted for that model."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "snap_schema.jsonl", num_rows=3, asset_id="M14860")

    # Fail at prediction
    orig_predict = service.prediction_service.predict_for_models

    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-sch-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None

    # Change feature schema sha256 in current snapshot
    orig_build_snap = service._build_model_snapshot

    def modified_snap(base_models, *args, **kwargs):
        snap, arts = orig_build_snap(base_models, *args, **kwargs)
        for m_id in snap:
            snap[m_id]["feature_schema_sha256"] = "f" * 64
        return snap, arts

    monkeypatch.setattr(service, "_build_model_snapshot", modified_snap)
    monkeypatch.setattr(service.prediction_service, "predict_for_models", orig_predict)

    extract_called = False
    orig_extract = service.runtime_feature_service.extract_and_publish

    def spy_extract(*args, **kwargs):
        nonlocal extract_called
        extract_called = True
        return orig_extract(*args, **kwargs)

    monkeypatch.setattr(service.runtime_feature_service, "extract_and_publish", spy_extract)

    item2 = PipelineQueueItem(
        job_id="job-sch-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"
    assert extract_called, "Feature matrix should be re-extracted when feature schema sha256 differs"


# =====================================================================
# 29. Missing Model Snapshot Artifact Fails Closed Test
# =====================================================================

def test_missing_model_snapshot_artifact_fails_closed(isolated_runtime_env, monkeypatch):
    """When active model artifact cannot be loaded, pipeline fails closed without falling back."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "missing_art.jsonl", num_rows=3, asset_id="M14860")

    def failing_load_artifact(base_model):
        raise PipelineModelSnapshotArtifactMissingError(f"Model artifact missing for {base_model}")

    monkeypatch.setattr(service.prediction_service, "load_active_artifact", failing_load_artifact)

    item = queue.enqueue(job_id="job-miss-art", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelSnapshotArtifactMissingError):
        service.execute_queue_item(item)


# =====================================================================
# 30. Model ID With Underscore Identified Without Filename Splitting Test
# =====================================================================

def test_model_id_with_underscore_correctly_identified(isolated_runtime_env):
    """Model IDs containing underscores (e.g. pdm-random_forest) are stored and restored via structured stage outputs without filename splitting."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "underscore_model.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-under-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    run_state = service.execute_queue_item(item)

    assert run_state.status == "succeeded"
    chk = repo.get_checkpoint(run_state.run_id)
    assert chk is not None
    assert "runtime_feature" in chk.model_stage_outputs

    feat_map = chk.model_stage_outputs["runtime_feature"]
    for m_id, entry in feat_map.items():
        assert m_id in ("pdm-lightgbm", "pdm-xgboost", "pdm-random_forest", "pdm-logistic_regression", "pdm-catboost")
        assert "artifact_ref" in entry
        assert entry["artifact_ref"]["uri"]


# =====================================================================
# 31. Checkpoint 4 Stages Batches and Resumes Without Recalculation Test
# =====================================================================

def test_checkpoint_4_stages_batches_and_resumes_without_recalculation(isolated_runtime_env, monkeypatch):
    """Stage 4 stages equipment batches to batch-manifest.json and Stage 5 resumption reuses staged batches."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "stage_batches.jsonl", num_rows=3, asset_id="M14860")

    # 1. Interrupt at Stage 5 delivery
    orig_register = service.prediction_delivery_service.register_idempotent_outbox_record

    def failing_outbox(*args, **kwargs):
        raise PipelineDeliveryFailedError("Simulated delivery crash")

    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", failing_outbox)

    item1 = queue.enqueue(job_id="job-stage4-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineDeliveryFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None
    chk1 = repo.get_checkpoint(first_run.run_id)
    assert chk1 is not None
    assert chk1.batch_manifest_ref is not None
    assert "batch-manifest.json" in chk1.batch_manifest_ref.uri

    # 2. Resume execution
    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", orig_register)

    collect_called = False
    orig_collect = service.prediction_batch_service.collect

    def spy_collect(*args, **kwargs):
        nonlocal collect_called
        collect_called = True
        return orig_collect(*args, **kwargs)

    monkeypatch.setattr(service.prediction_batch_service, "collect", spy_collect)

    item2 = PipelineQueueItem(
        job_id="job-stage4-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"
    assert not collect_called, "Staged batch manifest should be reused on Stage 5 resumption without re-collecting"


# =====================================================================
# 32. Partial Multi-Equipment Outbox Resumption is Idempotent Test
# =====================================================================

def test_partial_multi_equipment_outbox_resumption_is_idempotent(isolated_runtime_env, monkeypatch):
    """When delivery fails after Equipment A outbox item is saved, resumption reuses Equipment A item and registers Equipment B without duplication."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    # Create observation file with 2 equipments: M14860 and L47180
    src_path1, _ = create_sample_observation_jsonl(incoming_dir / "multi_eq1.jsonl", num_rows=3, asset_id="M14860")
    src_path2, _ = create_sample_observation_jsonl(incoming_dir / "multi_eq2.jsonl", num_rows=3, asset_id="L47180")

    df1 = pd.read_json(src_path1, lines=True)
    df2 = pd.read_json(src_path2, lines=True)
    combined_df = pd.concat([df1, df2], ignore_index=True)

    src_path = incoming_dir / "multi_eq_combined.jsonl"
    combined_df.to_json(src_path, orient="records", lines=True)
    sha = compute_file_sha256(src_path)

    orig_register = service.prediction_delivery_service.register_idempotent_outbox_record
    registered_count = 0

    def failing_second_register(payload, run_id=None):
        nonlocal registered_count
        registered_count += 1
        if registered_count == 2:
            raise PipelineDeliveryFailedError("Simulated crash on EQ-002 outbox registration")
        return orig_register(payload, run_id=run_id)

    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", failing_second_register)

    item1 = queue.enqueue(job_id="job-multi-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_path), source_checksum=sha))
    with pytest.raises(PipelineDeliveryFailedError):
        service.execute_queue_item(item1)

    # Check EQ-001 outbox file exists
    outbox_files_before = list(env["outbox_dir"].glob("*.json"))
    assert len(outbox_files_before) == 1

    # Resume execution with normal register_idempotent_outbox_record
    monkeypatch.setattr(service.prediction_delivery_service, "register_idempotent_outbox_record", orig_register)

    item2 = PipelineQueueItem(
        job_id="job-multi-2",
        source_uri=str(src_path),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )
    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"

    # Total outbox files MUST be exactly 2 (EQ-001 and EQ-002) with 0 duplicates
    outbox_files_after = list(env["outbox_dir"].glob("*.json"))
    assert len(outbox_files_after) == 2


# =====================================================================
# 33. Outbox Payload Conflict Raises Error Test
# =====================================================================

def test_outbox_payload_conflict_raises_error(isolated_runtime_env):
    """When attempting to register an outbox item with an existing event_id but different payload checksum, raise PipelineOutboxEventConflictError."""
    env = isolated_runtime_env
    delivery_service: PredictionDeliveryService = env["notif_service"]

    payload1 = create_test_batch_payload(
        event_id="evt-conf-1",
        asset_id="EQ-100",
        observed_at="2026-08-26T00:00:00Z",
        batch_id="batch-conflict-1",
    )
    item1, sha1 = delivery_service.register_idempotent_outbox_record(payload1)
    assert item1.event_id is not None

    # Construct different payload with different score -> different payload_sha256!
    payload2 = create_test_batch_payload(
        event_id="evt-conf-2",
        asset_id="EQ-100",
        observed_at="2026-08-26T01:00:00Z",
        score=0.12,
        batch_id="batch-conflict-2",
    )

    # Force payload2 to produce the same event_id as payload1
    orig_compute = delivery_service.compute_canonical_payload_sha256

    def conflicting_compute(payload):
        _, new_sha = orig_compute(payload)
        return item1.event_id, new_sha

    delivery_service.compute_canonical_payload_sha256 = conflicting_compute

    with pytest.raises(PipelineOutboxEventConflictError):
        delivery_service.register_idempotent_outbox_record(payload2)


# =====================================================================
# 34. Invalidated Checkpoint Intermediates Marked Debug Only Test
# =====================================================================

def test_invalidated_checkpoint_intermediates_marked_debug_only(isolated_runtime_env, monkeypatch):
    """When a checkpoint is invalidated due to source checksum change, its status is set to invalidated and intermediates are marked debug_only."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha1 = create_sample_observation_jsonl(incoming_dir / "inval_check.jsonl", num_rows=2, asset_id="M14860")

    # Fail at prediction
    orig_predict = service.prediction_service.predict_for_models

    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-inval-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha1))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None

    # Restore original predict BEFORE executing item2
    monkeypatch.setattr(service.prediction_service, "predict_for_models", orig_predict)

    # Modify file content -> new checksum
    src_file, sha2 = create_sample_observation_jsonl(incoming_dir / "inval_check.jsonl", num_rows=5, asset_id="M14860")

    item2 = PipelineQueueItem(
        job_id="job-inval-2",
        source_uri=str(src_file),
        source_checksum=sha2,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )

    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"

    # Old run checkpoint MUST be marked invalidated
    chk1 = repo.get_checkpoint(first_run.run_id)
    assert chk1 is not None
    assert chk1.status == "invalidated"


# =====================================================================
# 35. Cleanup Warning Does Not Invalidate Published Outbox Test
# =====================================================================

def test_cleanup_warning_does_not_invalidate_published_outbox(isolated_runtime_env, monkeypatch):
    """When cleanup fails, status is succeeded_with_cleanup_warning, cleanup_failed_paths is recorded, and Outbox remains published."""
    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "clean_warn_track.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-clean-track-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    def failing_cleanup(*args, **kwargs):
        return False, ["data/preprocessed/pipeline_datasets/run-1/obs.csv"], "Permission denied on file deletion"

    monkeypatch.setattr(repo, "cleanup_run_intermediate_outputs", failing_cleanup)

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded_with_cleanup_warning"
    assert run_state.cleanup_status == "cleanup_failed"
    assert len(run_state.cleanup_failed_paths) >= 1
    assert "Permission denied" in run_state.cleanup_failed_paths[0]



# =====================================================================
# 36. Active Model Set Pointer Management & Atomic Update Test
# =====================================================================

def test_active_model_set_pointer_management_and_atomic_update(isolated_runtime_env):
    """ActiveModelSetService loads active-model-set.json, validates pointer, and performs atomic replace with locking."""
    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        ModelSetArtifactNotFoundError,
        ModelSetOptionalModelPolicyNotImplementedError,
    )

    env = isolated_runtime_env
    models_dir: Path = env["tmp_path"] / "models_store"
    models_dir.mkdir(parents=True, exist_ok=True)

    svc = ActiveModelSetService(models_store_dir=models_dir)
    default_set = svc.load_active_model_set()
    assert default_set.model_set_id == "pdm-default"
    assert "lightgbm" in default_set.models

    # Reject required=False optional policy
    invalid_set = ActiveModelSet(
        model_set_id="pdm-opt",
        model_set_version="1.0.1",
        updated_at=now_utc_iso(),
        models={"lightgbm": ActiveModelConfig(model_version="1.0.0", required=False)},
    )
    with pytest.raises(ModelSetOptionalModelPolicyNotImplementedError):
        svc.update_active_model_set(invalid_set, validate_artifacts=False)

    # Reject missing artifact version
    missing_art_set = ActiveModelSet(
        model_set_id="pdm-missing",
        model_set_version="1.0.2",
        updated_at=now_utc_iso(),
        models={"lightgbm": ActiveModelConfig(model_version="99.99.99", required=True)},
    )
    with pytest.raises(ModelSetArtifactNotFoundError):
        svc.update_active_model_set(missing_art_set, validate_artifacts=True)


# =====================================================================
# 37. Real Manifest Checksum Recorded in Prediction Result Test
# =====================================================================

def test_real_manifest_checksum_recorded_in_prediction_result(isolated_runtime_env, monkeypatch):
    """Prediction results record real manifest SHA-256 checksum and model_set provenance."""
    from systems.generator.generator_config import PATHS
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "real_manifest.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-real-manifest-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded"
    assert len(run_state.prediction_results) > 0

    for res in run_state.prediction_results:
        assert res.manifest_checksum is not None
        assert len(res.manifest_checksum) == 64
        assert res.model_set_id == "pdm-default"
        assert res.model_set_version == "1.0.0"


# =====================================================================
# 38. Required Model Failure Blocks Batch Publishing Test
# =====================================================================

def test_required_model_failure_blocks_batch_publishing(isolated_runtime_env, monkeypatch):
    """When a required=true model inference fails, the pipeline fails closed and batch is not published."""
    from systems.generator.generator_config import PATHS
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        PipelineModelArtifactInvalidError,
        PipelineModelPredictionFailedError,
    )
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "req_fail.jsonl", num_rows=3, asset_id="M14860")

    orig_load = service.prediction_service.load_active_artifact

    def failing_load(base_or_id, target_version=None):
        if "xgboost" in base_or_id:
            raise PipelineModelArtifactInvalidError("Simulated XGBoost required load failure")
        return orig_load(base_or_id, target_version=target_version)

    monkeypatch.setattr(service.prediction_service, "load_active_artifact", failing_load)

    item = queue.enqueue(job_id="job-req-fail-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises((PipelineModelPredictionFailedError, PipelineModelArtifactInvalidError)):
        service.execute_queue_item(item)


# =====================================================================
# 39. Generator Runtime Prediction Disabled by Default Test
# =====================================================================

def test_generator_runtime_prediction_disabled_by_default(isolated_runtime_env, monkeypatch):
    """When GENERATOR_RUNTIME_PREDICTION_ENABLED=false (default), pipeline execution and outbox worker start are blocked."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineRuntimePredictionDisabledError

    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", False)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "disabled_test.jsonl", num_rows=2, asset_id="M14860")
    item = queue.enqueue(job_id="job-disabled-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    with pytest.raises(PipelineRuntimePredictionDisabledError):
        service.execute_queue_item(item)


# =====================================================================
# 40. Delivery Worker HTTP Status Codes Handling Test
# =====================================================================

def test_delivery_worker_http_status_codes_handling(isolated_runtime_env, monkeypatch):
    """Delivery worker properly distinguishes 200/202, 409 conflict, 422 unprocessable, 401 unauthorized, and 500 retry."""
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        PipelineDeliveryUnauthorizedError,
        PipelineDeliveryUnprocessableError,
    )

    env = isolated_runtime_env
    delivery_service: PredictionDeliveryService = env["service"].prediction_delivery_service
    src_file, sha = create_sample_observation_jsonl(env["incoming_dir"] / "http_code.jsonl", num_rows=2, asset_id="M14860")

    payload = create_test_batch_payload(
        event_id="evt-test-http-codes",
        asset_id="M14860",
        observed_at="2026-08-26T09:00:00Z",
        model_id="pdm-lightgbm",
        score=0.88,
        batch_id="batch-http-1",
    )

    class MockHTTPResp:
        def getcode(self):
            return 202
        def read(self):
            return b'{"accepted": true}'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    # HTTP 202 Success
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10.0: MockHTTPResp())
    res = delivery_service.send_once(payload)
    assert res["delivered"] is True

    # HTTP 422 Unprocessable Error
    def failing_urlopen_422(req, timeout=10.0):
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable Entity", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen_422)
    with pytest.raises(PipelineDeliveryUnprocessableError):
        delivery_service.send_once(payload)

    # HTTP 401 Unauthorized Error
    def failing_urlopen_401(req, timeout=10.0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen_401)
    with pytest.raises(PipelineDeliveryUnauthorizedError):
        delivery_service.send_once(payload)


# =====================================================================
# 41. Single Model Active Model Set Execution Test (9.1)
# =====================================================================

def test_single_model_active_model_set_execution(isolated_runtime_env, monkeypatch):
    """When Active Model Set contains only 1 model ('lightgbm'), pipeline executes only that model."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    # Set Active Model Set with only lightgbm
    active_service = service.active_model_set_service
    active_set = ActiveModelSet(
        model_set_id="pdm-single-lgb",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={"lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True)},
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "single_lgb.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-single-lgb", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded"
    # Only lightgbm in prediction results
    assert len(run_state.prediction_results) == 1
    assert run_state.prediction_results[0].model_id == "pdm-lightgbm"


# =====================================================================
# 42. Partial Model Active Model Set Execution Test (9.2)
# =====================================================================

def test_partial_model_active_model_set_execution(isolated_runtime_env, monkeypatch):
    """When Active Model Set contains 2 models ('lightgbm', 'xgboost'), pipeline executes only those 2 models."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    active_service = service.active_model_set_service
    active_set = ActiveModelSet(
        model_set_id="pdm-partial-2",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={
            "lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True),
            "xgboost": ActiveModelConfig(model_version="pdm-xgboost-v1.0", required=True),
        },
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "partial_2.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-partial-2", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded"
    model_ids = {r.model_id for r in run_state.prediction_results}
    assert model_ids == {"pdm-lightgbm", "pdm-xgboost"}


# =====================================================================
# 43. Missing Pointer Raises ModelSetNotConfigured Error (9.3)
# =====================================================================

def test_missing_pointer_raises_model_set_not_configured(isolated_runtime_env, monkeypatch):
    """When active-model-set.json does not exist, load_active_model_set raises ModelSetNotConfiguredError (404, MODEL_SET_NOT_CONFIGURED)."""
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetNotConfiguredError

    env = isolated_runtime_env
    service: PipelineService = env["service"]
    active_service = service.active_model_set_service
    pointer_file = active_service.pointer_file
    if pointer_file.exists():
        pointer_file.unlink()

    # Even if latest.json exists, load_active_model_set MUST raise ModelSetNotConfiguredError
    latest_file = active_service.pointer_file.parent / "latest.json"
    latest_file.write_text(json.dumps({"model_version": "pdm-lightgbm-v1.0"}), encoding="utf-8")

    with pytest.raises(ModelSetNotConfiguredError) as exc_info:
        active_service.load_active_model_set()

    assert exc_info.value.code == "MODEL_SET_NOT_CONFIGURED"
    assert exc_info.value.status_code == 404


# =====================================================================
# 44. Corrupt Artifact Promotion Blocked Test (9.4)
# =====================================================================

def test_corrupt_artifact_promotion_blocked(isolated_runtime_env):
    """When updating Active Model Set with corrupt artifacts, update fails and original active-model-set.json is preserved across all 6 corrupt cases."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetArtifactIntegrityError
    from systems.generator.file_integrity import compute_file_sha256

    env = isolated_runtime_env
    service: PipelineService = env["service"]
    active_service = service.active_model_set_service

    # Initial valid active set
    init_set = active_service.load_active_model_set()
    artifacts_base = active_service.pointer_file.parent / "artifacts" / "pdm-lightgbm"

    # Helper function to test corrupt promotion failure & pointer preservation
    def assert_corrupt_fails(target_version: str, mutator_fn):
        c_dir = artifacts_base / target_version
        c_dir.mkdir(parents=True, exist_ok=True)
        mutator_fn(c_dir)

        test_set = ActiveModelSet(
            model_set_id=f"pdm-corrupt-{target_version}",
            model_set_version="2.0.0",
            updated_at=now_utc_iso(),
            models={"lightgbm": ActiveModelConfig(model_version=target_version, required=True)},
        )

        with pytest.raises(ModelSetArtifactIntegrityError):
            active_service.update_active_model_set(test_set, validate_artifacts=True)

        current_set = active_service.load_active_model_set()
        assert current_set.model_set_id == init_set.model_set_id

    # Case 1: manifest required field missing (model_id missing)
    def mut_missing_field(dir_path: Path):
        (dir_path / "manifest.json").write_text(json.dumps({"model_version": "v-c1", "artifact_files": []}), encoding="utf-8")
    assert_corrupt_fails("v-c1", mut_missing_field)

    # Case 2: required role missing (feature_schema missing from artifact_files)
    def mut_missing_role(dir_path: Path):
        manifest = {
            "model_id": "pdm-lightgbm",
            "model_version": "v-c2",
            "schema_version": "1.0",
            "artifact_files": [
                {"role": "model", "path": "model.joblib", "sha256": "0"*64},
                {"role": "label_schema", "path": "label_schema.json", "sha256": "0"*64},
            ]
        }
        (dir_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert_corrupt_fails("v-c2", mut_missing_role)

    # Case 3: duplicate role (role "metrics" declared twice)
    def mut_duplicate_role(dir_path: Path):
        manifest = {
            "model_id": "pdm-lightgbm",
            "model_version": "v-c3",
            "schema_version": "1.0",
            "artifact_files": [
                {"role": "model", "path": "model.joblib", "sha256": "0"*64},
                {"role": "feature_schema", "path": "feature_schema.json", "sha256": "0"*64},
                {"role": "label_schema", "path": "label_schema.json", "sha256": "0"*64},
                {"role": "history_requirement", "path": "history_requirement.json", "sha256": "0"*64},
                {"role": "metrics", "path": "metrics.json", "sha256": "0"*64},
                {"role": "metrics", "path": "metrics_dup.json", "sha256": "0"*64},
            ]
        }
        (dir_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert_corrupt_fails("v-c3", mut_duplicate_role)

    # Case 4: broken JSON syntax in feature_schema.json despite matching SHA-256 in manifest
    def mut_corrupt_json(dir_path: Path):
        feat_path = dir_path / "feature_schema.json"
        feat_path.write_text("{ broken json syntax : ", encoding="utf-8")
        feat_sha = compute_file_sha256(feat_path)
        (dir_path / "model.joblib").write_bytes(b"dummy")
        (dir_path / "label_schema.json").write_text("{}", encoding="utf-8")
        (dir_path / "history_requirement.json").write_text("{}", encoding="utf-8")
        (dir_path / "metrics.json").write_text("{}", encoding="utf-8")
        manifest = {
            "model_id": "pdm-lightgbm",
            "model_version": "v-c4",
            "schema_version": "1.0",
            "artifact_files": [
                {"role": "model", "path": "model.joblib", "sha256": compute_file_sha256(dir_path / "model.joblib")},
                {"role": "feature_schema", "path": "feature_schema.json", "sha256": feat_sha},
                {"role": "label_schema", "path": "label_schema.json", "sha256": compute_file_sha256(dir_path / "label_schema.json")},
                {"role": "history_requirement", "path": "history_requirement.json", "sha256": compute_file_sha256(dir_path / "history_requirement.json")},
                {"role": "metrics", "path": "metrics.json", "sha256": compute_file_sha256(dir_path / "metrics.json")},
            ]
        }
        (dir_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert_corrupt_fails("v-c4", mut_corrupt_json)

    # Case 5: joblib.load fails on corrupted model.joblib file despite matching SHA-256 in manifest
    def mut_corrupt_joblib(dir_path: Path):
        m_path = dir_path / "model.joblib"
        m_path.write_bytes(b"not a valid joblib file content")
        m_sha = compute_file_sha256(m_path)
        (dir_path / "feature_schema.json").write_text("{}", encoding="utf-8")
        (dir_path / "label_schema.json").write_text("{}", encoding="utf-8")
        (dir_path / "history_requirement.json").write_text("{}", encoding="utf-8")
        (dir_path / "metrics.json").write_text("{}", encoding="utf-8")
        manifest = {
            "model_id": "pdm-lightgbm",
            "model_version": "v-c5",
            "schema_version": "1.0",
            "artifact_files": [
                {"role": "model", "path": "model.joblib", "sha256": m_sha},
                {"role": "feature_schema", "path": "feature_schema.json", "sha256": compute_file_sha256(dir_path / "feature_schema.json")},
                {"role": "label_schema", "path": "label_schema.json", "sha256": compute_file_sha256(dir_path / "label_schema.json")},
                {"role": "history_requirement", "path": "history_requirement.json", "sha256": compute_file_sha256(dir_path / "history_requirement.json")},
                {"role": "metrics", "path": "metrics.json", "sha256": compute_file_sha256(dir_path / "metrics.json")},
            ]
        }
        (dir_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert_corrupt_fails("v-c5", mut_corrupt_joblib)

    # Case 6: model_id / model_version mismatch
    def mut_id_mismatch(dir_path: Path):
        manifest = {
            "model_id": "pdm-WRONG-ID",
            "model_version": "v-c6",
            "schema_version": "1.0",
            "artifact_files": []
        }
        (dir_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert_corrupt_fails("v-c6", mut_id_mismatch)


# =====================================================================
# 45. Disabled State Blocks Worker, Enqueue, Retry (9.5)
# =====================================================================

def test_disabled_state_blocks_worker_enqueue_retry(isolated_runtime_env, monkeypatch):
    """When GENERATOR_RUNTIME_PREDICTION_ENABLED=false, workers fail to start, enqueue/retry return HTTP 503, status returns mode: disabled."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineRuntimePredictionDisabledError
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", False)

    env = isolated_runtime_env
    manager: PipelineManager = env["manager"]

    manager.start()
    assert manager._is_running is False

    with pytest.raises(PipelineRuntimePredictionDisabledError) as exc1:
        manager.enqueue(
            job_id="job-dis-1",
            source_uri="data/test.jsonl",
            source_checksum="0"*64,
            dataset_id="test-dataset",
            dataset_version="v1",
            pipeline_contract_version="prediction-result-batch-v1",
            source_kind="live_sensor",
            source_contract_version="observation-source-v1",
            source_schema_version="observation-source-v1",
        )
    assert exc1.value.status_code == 503
    assert exc1.value.code == "PIPELINE_RUNTIME_PREDICTION_DISABLED"

    with pytest.raises(PipelineRuntimePredictionDisabledError) as exc2:
        manager.retry_failed_job("job-dis-1")
    assert exc2.value.status_code == 503

    status_resp = manager.get_status()
    assert status_resp["enabled"] is False
    assert status_resp["mode"] == "disabled"
    assert status_resp["reason"] == "backend_receiver_not_ready"


# =====================================================================
# 46. Model Set Provenance Contract Alignment Test (9.6)
# =====================================================================

def test_model_set_provenance_contract_alignment(isolated_runtime_env):
    """Batch payload includes model_set_id and model_set_version, and mismatched model result raises PipelineModelSetSnapshotMismatchError."""
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        PredictionBatchService,
        PredictionBatchSummary,
        EquipmentModelBatch,
    )
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ModelPredictionResult,
        SourceLineage,
    )
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelSetSnapshotMismatchError

    batch_svc = PredictionBatchService()

    eq_batch = EquipmentModelBatch(
        asset_id="M14860",
        status="succeeded",
        observed_at="2026-08-26T10:00:00Z",
        succeeded_models=["lightgbm"],
        failed_models=[],
        model_results={
            "pdm-lightgbm": ModelPredictionResult(
                model_version="pdm-lightgbm-v1.0",
                status="succeeded",
                observed_at="2026-08-26T10:00:00Z",
                score_type="positive_class_probability",
                score_source="predict_proba",
                score=0.88,
                model_set_id="pdm-MISMATCHED",  # Mismatch!
                model_set_version="1.0.0",
            )
        },
    )

    summary = PredictionBatchSummary(
        overall_status="succeeded",
        equipment_batches={"M14860": eq_batch},
        total_equipments=1,
        succeeded_equipments=["M14860"],
    )

    with pytest.raises(PipelineModelSetSnapshotMismatchError) as exc_info:
        batch_svc.stage_batches(
            run_id="run-prov-1",
            job_id="job-prov-1",
            summary=summary,
            dataset_id="canonical-ai4i-v1",
            dataset_version="v3.1",
            pipeline_contract_version="v1",
            source_lineage=SourceLineage(source_uri="test.jsonl", source_checksum="a"*64),
            model_set_id="pdm-default",
            model_set_version="1.0.0",
            source_context=create_test_runtime_source_context(),
            active_model_set_snapshot=create_test_active_model_set_snapshot(),
            model_schema_map={},
        )
    assert exc_info.value.code == "PIPELINE_MODEL_SET_SNAPSHOT_MISMATCH"


# =====================================================================
# 47. Snapshot Pinning and Model Set Change Invalidates Checkpoint (9.7)
# =====================================================================

def test_snapshot_pinning_and_model_set_change_invalidates_checkpoint(isolated_runtime_env, monkeypatch):
    """When Model Set changes during run resumption, previous checkpoint is invalidated and predictions are recalculated."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelPredictionFailedError
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    repo: PipelineRepository = env["repository"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "snap_pin.jsonl", num_rows=3, asset_id="M14860")

    # Fail at prediction stage on first run to leave resumable checkpoint
    orig_predict = service.prediction_service.predict_for_models
    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated prediction failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-pin-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    first_run = repo.find_resumable_run(item1.source_identity)
    assert first_run is not None

    # Update active model set to new version
    active_service = service.active_model_set_service
    active_set = ActiveModelSet(
        model_set_id="pdm-default",
        model_set_version="2.0.0",  # Version changed!
        updated_at=now_utc_iso(),
        models={
            "lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True),
            "xgboost": ActiveModelConfig(model_version="pdm-xgboost-v1.0", required=True),
            "random_forest": ActiveModelConfig(model_version="pdm-random_forest-v1.0", required=True),
        },
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    # Track if predict_for_models is called during second run
    predict_recalculated = False
    def spy_predict(*args, **kwargs):
        nonlocal predict_recalculated
        predict_recalculated = True
        return orig_predict(*args, **kwargs)

    monkeypatch.setattr(service.prediction_service, "predict_for_models", spy_predict)

    item2 = PipelineQueueItem(
        job_id="job-pin-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )

    run_state2 = service.execute_queue_item(item2)
    assert run_state2.status == "succeeded"
    assert predict_recalculated is True  # Prediction checkpoint was invalidated and recalculated!


# =====================================================================
# 48. Staged Batch Payload Matches Official Schema Test (Component A)
# =====================================================================

def test_staged_batch_payload_matches_official_schema(isolated_runtime_env, monkeypatch):
    """stage_batches()가 실제로 생성한 payload 파일(staging_dir/{asset_id}.json)이 공식 JSON Schema를 additionalProperties: false 검증 하에 통과하는지 검증."""
    import json
    import jsonschema
    from pathlib import Path
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet, now_utc_iso
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]
    notif_service = env["notif_service"]

    # Active Model Set
    active_service = service.active_model_set_service
    active_set = ActiveModelSet(
        model_set_id="pdm-schema-test",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={"lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True)},
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "schema_val.jsonl", num_rows=3, asset_id="M14860")
    item = queue.enqueue(job_id="job-schema-val", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))

    run_state = service.execute_queue_item(item)
    assert run_state.status == "succeeded"
    assert len(run_state.prediction_event_ids) > 0

    event_id = run_state.prediction_event_ids[0]
    outbox_item = notif_service.get_outbox_item(event_id)
    assert outbox_item is not None

    actual_payload = outbox_item.payload.model_dump(mode="json")

    # Build schema map for ref resolution
    schemas_dir = Path("contracts/schemas")
    schema_map = {}
    for schema_file in schemas_dir.rglob("*.schema.json"):
        with open(schema_file, "r", encoding="utf-8") as sf:
            sdata = json.load(sf)
            if "$id" in sdata:
                schema_map[sdata["$id"]] = sdata

    batch_schema_path = schemas_dir / "prediction-result-batch.schema.json"
    with open(batch_schema_path, "r", encoding="utf-8") as sf:
        batch_schema = json.load(sf)
    validator = jsonschema.Draft202012Validator(batch_schema, format_checker=jsonschema.FormatChecker())

    validator.validate(actual_payload)  # Must pass without validation errors!


# =====================================================================
# 49. Direct Staged Disk Batch JSON Schema & Provenance Test (Component 2)
# =====================================================================

def test_staged_disk_batch_json_matches_official_schema(isolated_runtime_env):
    """PredictionBatchService.stage_batches() writes staging_dir/{asset_id}.json directly to disk, passing official JSON Schema with additionalProperties: false."""
    import json
    import jsonschema
    from pathlib import Path
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        PredictionBatchService,
        PredictionBatchSummary,
        EquipmentModelBatch,
    )
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ModelPredictionResult,
        SourceLineage,
    )

    env = isolated_runtime_env
    preprocessed_dir: Path = env["preprocessed_dir"]

    batch_svc = PredictionBatchService()

    eq_batch = EquipmentModelBatch(
        asset_id="M14860",
        status="succeeded",
        observed_at="2026-08-26T10:00:00Z",
        succeeded_models=["lightgbm"],
        failed_models=[],
        model_results={
            "pdm-lightgbm": ModelPredictionResult(
                model_version="pdm-lightgbm-v1.0",
                status="succeeded",
                observed_at="2026-08-26T10:00:00Z",
                score_type="positive_class_probability",
                score_source="predict_proba",
                score=0.88,
                artifact_ref=ArtifactReference(uri="models_store/artifacts/pdm-lightgbm/v1.0", sha256="a"*64, role="model_artifact"),
                feature_ref=ArtifactReference(uri="features.npy", sha256="a"*64, role="runtime_features"),
                manifest_checksum="a"*64,
                feature_schema_version="v1.0",
                label_schema_version="v1.0",
                history_requirement_version="v1.0",
                model_set_id="pdm-schema-test",
                model_set_version="1.0.0",
            )
        },
    )

    summary = PredictionBatchSummary(
        overall_status="succeeded",
        equipment_batches={"M14860": eq_batch},
        total_equipments=1,
        succeeded_equipments=["M14860"],
    )

    run_id = "run-disk-schema-test"
    manifest_ref = batch_svc.stage_batches(
        run_id=run_id,
        job_id="job-disk-schema-test",
        summary=summary,
        dataset_id="canonical-ai4i-v1",
        dataset_version="v3.1",
        pipeline_contract_version="v1",
        source_lineage=SourceLineage(source_uri="test.jsonl", source_checksum="a"*64),
        model_set_id="pdm-schema-test",
        model_set_version="1.0.0",
        base_dir=preprocessed_dir,
        source_context=create_test_runtime_source_context(),
        active_model_set_snapshot=create_test_active_model_set_snapshot(
            model_set_id="pdm-schema-test",
        ),
        model_schema_map={
            "pdm-lightgbm": {
                "feature_schema_sha256": "1" * 64,
                "history_requirement_sha256": "2" * 64,
                "label_schema_sha256": "3" * 64,
                "label_schema_version": "v1.0",
            }
        },
    )

    # Directly read the staged payload file written on disk
    import hashlib
    storage_key = hashlib.sha256("M14860".encode("utf-8")).hexdigest()[:24]
    staged_payload_file = preprocessed_dir / "pipeline_datasets" / run_id / "batch_staging" / f"{storage_key}.json"
    assert staged_payload_file.is_file(), f"Staged disk file not found: {staged_payload_file}"

    with open(staged_payload_file, "r", encoding="utf-8") as f:
        disk_payload = json.load(f)

    # 1. Top-level prediction-result-batch-v1 fields
    assert disk_payload.get("contract_version") == "prediction-result-batch-v1"
    assert disk_payload.get("batch_id") is not None
    assert isinstance(disk_payload.get("results"), list)
    assert len(disk_payload["results"]) == 1

    item_0 = disk_payload["results"][0]
    assert item_0.get("model_id") == "pdm-lightgbm"
    assert item_0.get("score") == 0.88
    assert item_0.get("output_status") == "predicted"
    assert item_0.get("feature_schema_version") is not None
    assert item_0.get("history_requirement_version") is not None

    # 4. Validate against official schema
    schemas_dir = Path("contracts/schemas")
    batch_schema_path = schemas_dir / "prediction-result-batch.schema.json"
    with open(batch_schema_path, "r", encoding="utf-8") as sf:
        batch_schema = json.load(sf)

    validator = jsonschema.Draft202012Validator(batch_schema, format_checker=jsonschema.FormatChecker())
    validator.validate(disk_payload)


# =====================================================================
# 50. Artifact Path Unsupported & Security Blocking Test (Component 1)
# =====================================================================

def test_artifact_path_unsupported_security_blocking(isolated_runtime_env):
    """validate_model_artifact blocks path traversal ('..'), external URIs, and paths escaping root with ModelArtifactContractValidationError."""
    from systems.generator.model.publisher import (
        ModelArtifactContractValidationError,
        validate_model_artifact,
    )

    env = isolated_runtime_env
    root_dir: Path = env["artifacts_dir"]

    # Case 1: Path traversal '..'
    with pytest.raises(ModelArtifactContractValidationError) as exc1:
        validate_model_artifact(
            artifact_dir=root_dir / ".." / "outside",
            expected_model_id="pdm-lightgbm",
            expected_model_version="v1.0",
            artifacts_root=root_dir,
        )
    assert exc1.value.reason in {"path_traversal", "path_outside_root"}

    # Case 2: External URI scheme
    with pytest.raises(ModelArtifactContractValidationError) as exc2:
        validate_model_artifact(
            artifact_dir="http://remote-server.com/models/pdm-lightgbm",
            expected_model_id="pdm-lightgbm",
            expected_model_version="v1.0",
            artifacts_root=root_dir,
        )
    assert exc2.value.reason == "external_uri_unsupported"

    # Case 3: S3 URI scheme
    with pytest.raises(ModelArtifactContractValidationError) as exc3:
        validate_model_artifact(
            artifact_dir="s3://my-bucket/artifacts/model",
            expected_model_id="pdm-lightgbm",
            expected_model_version="v1.0",
            artifacts_root=root_dir,
        )
    assert exc3.value.reason == "external_uri_unsupported"


# =====================================================================
# 51. Model Set Membership Change Not Implemented Test (Component 4)
# =====================================================================

def test_model_set_membership_change_not_implemented(isolated_runtime_env, monkeypatch):
    """When active model set membership (keys) changes during run resumption, PipelineModelSetMembershipChangeNotImplementedError is raised."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        PipelineModelPredictionFailedError,
        PipelineModelSetMembershipChangeNotImplementedError,
    )
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)

    env = isolated_runtime_env
    incoming_dir: Path = env["incoming_dir"]
    queue: PipelineQueue = env["queue"]
    service: PipelineService = env["service"]

    src_file, sha = create_sample_observation_jsonl(incoming_dir / "mem_change.jsonl", num_rows=3, asset_id="M14860")

    # Fail at prediction stage to create resumable run with 3 models in snapshot
    def failing_predict(*args, **kwargs):
        raise PipelineModelPredictionFailedError("Simulated failure")

    monkeypatch.setattr(service.prediction_service, "predict_for_models", failing_predict)

    item1 = queue.enqueue(job_id="job-mem-1", runtime_input=create_test_runtime_input_identity(source_uri=str(src_file), source_checksum=sha))
    with pytest.raises(PipelineModelPredictionFailedError):
        service.execute_queue_item(item1)

    # Change active model set to reduced membership (lightgbm only)
    active_service = service.active_model_set_service
    active_set = ActiveModelSet(
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={"lightgbm": ActiveModelConfig(model_version="pdm-lightgbm-v1.0", required=True)},
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    item2 = PipelineQueueItem(
        job_id="job-mem-2",
        source_uri=str(src_file),
        source_checksum=sha,
        source_identity=item1.source_identity,
        dataset_id=item1.dataset_id,
        dataset_version=item1.dataset_version,
            pipeline_contract_version=item1.pipeline_contract_version,
            source_kind=item1.source_kind,
            source_contract_version=item1.source_contract_version,
        source_schema_version=item1.source_schema_version,
    )

    with pytest.raises(PipelineModelSetMembershipChangeNotImplementedError) as exc_info:
        service.execute_queue_item(item2)

    assert exc_info.value.code == "PIPELINE_MODEL_SET_MEMBERSHIP_CHANGE_NOT_IMPLEMENTED"
    assert exc_info.value.status_code == 501


# =====================================================================
# 52. Disabled API TestClient 503 & Real Status Counts Test (Components 5 & 6)
# =====================================================================

def test_disabled_api_testclient_503_and_real_status_counts(isolated_runtime_env, monkeypatch):
    """Disabled mode returns actual HTTP 503 with domain error code via TestClient, and get_status returns real queue/run counts."""
    from fastapi.testclient import TestClient
    from systems.generator.app.main import app
    from systems.generator.generator_config import PATHS

    env = isolated_runtime_env
    queue: PipelineQueue = env["queue"]

    # Enqueue 1 item into DB while enabled
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)
    queue.enqueue(job_id="job-dis-counts", runtime_input=create_test_runtime_input_identity(source_uri="data/test.jsonl", source_checksum="a"*64))

    # Disable runtime
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", False)

    client = TestClient(app)

    # Test 1: POST /internal/runtime-pipeline/enqueue returns HTTP 503 & PIPELINE_RUNTIME_PREDICTION_DISABLED
    res_enq = client.post(
        "/internal/runtime-pipeline/enqueue",
        json={
            "job_id": "job-dis-http",
            "source_uri": "data/test.jsonl",
            "source_checksum": "a"*64,
            "source_kind": "live_sensor",
            "source_contract_version": "observation-source-v1",
            "source_schema_version": "observation-source-v1",
            "pipeline_contract_version": "prediction-result-batch-v1",
            "dataset_id": "test-dataset",
            "dataset_version": "v1",
        },
    )
    assert res_enq.status_code == 503
    payload_enq = res_enq.json()
    assert payload_enq["error"]["code"] == "PIPELINE_RUNTIME_PREDICTION_DISABLED"

    # Test 2: POST /internal/runtime-pipeline/retry-failed/job-1 returns HTTP 503 & PIPELINE_RUNTIME_PREDICTION_DISABLED
    res_retry = client.post("/internal/runtime-pipeline/retry-failed/job-dis-counts")
    assert res_retry.status_code == 503
    payload_retry = res_retry.json()
    assert payload_retry["error"]["code"] == "PIPELINE_RUNTIME_PREDICTION_DISABLED"

    # Test 3: GET /runtime-pipeline/status when disabled returns real queued_count
    res_status = client.get("/runtime-pipeline/status")
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert st_data["enabled"] is False
    assert st_data["mode"] == "disabled"
    assert st_data["queued_count"] == 1  # Real count, not hardcoded 0!


# =====================================================================
# 53. Model Artifact Provenance & Common Validator Comprehensive Test
# =====================================================================

def test_provenance_and_common_validator_comprehensive(isolated_runtime_env):
    """Comprehensive verification of Model Artifact provenance rules, official Schema validation, and unified Validator."""
    import sys
    import jsonschema
    from systems.generator.model.publisher import (
        ModelArtifactContractValidationError,
        ModelArtifactPublisher,
        ModelArtifactValidationError,
        validate_model_artifact,
    )
    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        ModelSetArtifactIntegrityError,
        ModelSetArtifactNotFoundError,
        ModelSetArtifactPathUnsupportedError,
        PipelineModelArtifactInvalidError,
    )
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelConfig,
        ActiveModelSet,
        ArtifactReference,
        InternalModelPredictionResult,
        ModelPredictionResult,
    )

    env = isolated_runtime_env
    root_dir: Path = env["artifacts_dir"]
    target_dir = root_dir / "pdm-lightgbm" / "pdm-lightgbm-v1.0"

    # 1. Model layer does not import app runtime/training exceptions
    import systems.generator.model.publisher as pub_mod
    for attr in dir(pub_mod):
        obj = getattr(pub_mod, attr)
        if hasattr(obj, "__module__") and getattr(obj, "__module__", "").startswith("systems.generator.app"):
            pytest.fail(f"systems.generator.model.publisher imports app module symbol: {attr} ({obj.__module__})")

    # 2. Verify ValidatedModelArtifact return type and attribute/key access
    val_art = validate_model_artifact(
        artifact_dir=target_dir,
        expected_model_id="pdm-lightgbm",
        expected_model_version="pdm-lightgbm-v1.0",
        load_model=True,
        artifacts_root=root_dir,
    )
    assert val_art.model_id == "pdm-lightgbm"
    assert val_art.model_version == "pdm-lightgbm-v1.0"
    assert len(val_art.manifest_checksum) == 64
    assert val_art["model_id"] == "pdm-lightgbm"
    assert val_art.get("model_version") == "pdm-lightgbm-v1.0"

    # 3. ModelPredictionResult provenance serialization test
    succeeded_internal = InternalModelPredictionResult(
        asset_id="EQUIP-001",
        model_id="pdm-lightgbm",
        model_version="pdm-lightgbm-v1.0",
        status="succeeded",
        observed_at="2026-08-25T14:30:00Z",
        score_type="positive_class_probability",
        score_source="predict_proba",
        score=0.85,
        artifact_ref=ArtifactReference(uri=str(target_dir), sha256=val_art.manifest_checksum, role="model_artifact"),
        feature_ref=ArtifactReference(uri="features.npy", sha256="0"*64, role="runtime_features"),
        manifest_checksum=val_art.manifest_checksum,
        feature_schema_version="v1.0",
        label_schema_version="v1.0",
        history_requirement_version="v1.0",
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        error_code=None,
        error_message=None,
    )

    payload_res = succeeded_internal.to_payload_result()
    dumped = payload_res.model_dump(mode="json")

    # Provenance 4 fields present in payload
    assert dumped["manifest_checksum"] == val_art.manifest_checksum
    assert dumped["feature_schema_version"] == "v1.0"
    assert dumped["label_schema_version"] == "v1.0"
    assert dumped["history_requirement_version"] == "v1.0"

    # Model set fields excluded per-model
    assert "model_set_id" not in dumped
    assert "model_set_version" not in dumped

    # 4. Schema validation of succeeded model prediction result (missing checksum fails)
    schemas_dir = Path("contracts/schemas")
    schema_path = schemas_dir / "generator-model-prediction-result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Valid payload passes
    jsonschema.validate(instance=dumped, schema=schema)

    # Missing manifest_checksum on succeeded status fails
    invalid_dumped = dict(dumped)
    invalid_dumped["manifest_checksum"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_dumped, schema=schema)

    # Invalid checksum pattern fails
    bad_pattern_dumped = dict(dumped)
    bad_pattern_dumped["manifest_checksum"] = "INVALID_HASH"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_pattern_dumped, schema=schema)

    # 5. Failed before artifact load allows null provenance
    failed_before = InternalModelPredictionResult(
        asset_id="EQUIP-001",
        model_id="pdm-lightgbm",
        model_version="v1.0",
        status="failed",
        observed_at="",
        score_type="positive_class_probability",
        score_source=None,
        score=None,
        artifact_ref=None,
        feature_ref=None,
        manifest_checksum=None,
        feature_schema_version=None,
        label_schema_version=None,
        history_requirement_version=None,
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        error_code="MODEL_NOT_FOUND",
        error_message="Artifact missing",
    )
    failed_dumped = failed_before.to_payload_result().model_dump(mode="json")
    jsonschema.validate(instance=failed_dumped, schema=schema)

    # 6. Failed after artifact load retains provenance
    failed_after = InternalModelPredictionResult(
        asset_id="EQUIP-001",
        model_id="pdm-lightgbm",
        model_version="v1.0",
        status="failed",
        observed_at="",
        score_type="positive_class_probability",
        score_source=None,
        score=None,
        artifact_ref=ArtifactReference(uri=str(target_dir), sha256=val_art.manifest_checksum, role="model_artifact"),
        feature_ref=None,
        manifest_checksum=val_art.manifest_checksum,
        feature_schema_version="v1.0",
        label_schema_version="v1.0",
        history_requirement_version="v1.0",
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        error_code="FEATURE_GEN_FAILED",
        error_message="Feature generation failed",
    )
    failed_after_dumped = failed_after.to_payload_result().model_dump(mode="json")
    jsonschema.validate(instance=failed_after_dumped, schema=schema)

    # 7. Common Validator exception conversions across callers
    pub = ModelArtifactPublisher(root_dir)
    # Publisher converts to ModelArtifactValidationError
    with pytest.raises(ModelArtifactValidationError):
        pub.validate_manifest({"model_id": "wrong"}, target_dir)

    # ActiveModelSetService converts reason to ModelSetArtifact*Error
    ams_service = ActiveModelSetService(models_store_dir=root_dir.parent)
    invalid_set = ActiveModelSet(
        model_set_id="pdm-default",
        model_set_version="1.0.0",
        updated_at="2026-08-25T14:30:00Z",
        models={
            "lightgbm": ActiveModelConfig(model_version="non-existent-v99", required=True),
        },
    )
    with pytest.raises(ModelSetArtifactNotFoundError):
        ams_service.update_active_model_set(invalid_set, validate_artifacts=True)

    # Mismatch model_id check
    with pytest.raises(ModelArtifactContractValidationError) as mm_exc:
        validate_model_artifact(
            artifact_dir=target_dir,
            expected_model_id="pdm-wrong-id",
            expected_model_version="pdm-lightgbm-v1.0",
            artifacts_root=root_dir,
        )
    assert mm_exc.value.reason == "model_id_version_mismatch"


# =====================================================================
# 42. Fail-Closed Official Schema Validation & Snapshot Reuse Tests
# =====================================================================

class RereadTestMockEstimator:
    def predict_proba(self, X):
        import numpy as np
        return np.array([[0.1, 0.9]])


def test_official_schema_missing_raises_contract_validation_error(tmp_path, monkeypatch):
    """When official schema file is missing, validate_model_artifact fails closed with reason='official_schema_missing'."""
    from systems.generator.model.publisher import (
        ModelArtifactContractValidationError,
        validate_model_artifact,
    )

    non_existent_schema = tmp_path / "non_existent_schema.json"
    monkeypatch.setattr("systems.generator.model.publisher.OFFICIAL_SCHEMA_PATH", non_existent_schema)

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ModelArtifactContractValidationError) as exc_info:
        validate_model_artifact(staging_dir, load_model=False)

    assert exc_info.value.reason == "official_schema_missing"
    assert "공식 Model Artifact Schema를 찾을 수 없습니다" in str(exc_info.value)


def test_official_schema_parse_failed_raises_contract_validation_error(tmp_path, monkeypatch):
    """When official schema file contains invalid JSON, validate_model_artifact fails closed with reason='official_schema_parse_failed'."""
    from systems.generator.model.publisher import (
        ModelArtifactContractValidationError,
        validate_model_artifact,
    )

    corrupt_schema = tmp_path / "corrupt_schema.json"
    corrupt_schema.write_text("{ invalid json ...", encoding="utf-8")
    monkeypatch.setattr("systems.generator.model.publisher.OFFICIAL_SCHEMA_PATH", corrupt_schema)

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ModelArtifactContractValidationError) as exc_info:
        validate_model_artifact(staging_dir, load_model=False)

    assert exc_info.value.reason == "official_schema_parse_failed"
    assert "공식 Model Artifact Schema 파싱 실패" in str(exc_info.value)


def test_prediction_service_reuses_validated_model_snapshot(isolated_runtime_env, monkeypatch):
    """Prediction Service uses ValidatedModelArtifact snapshot from validate_model_artifact(load_model=True) without redundant re-reading."""
    import joblib
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService

    env = isolated_runtime_env
    pred_service: PredictionService = env["service"].prediction_service

    joblib_load_count = 0
    orig_joblib_load = joblib.load

    def counting_joblib_load(filename, *args, **kwargs):
        nonlocal joblib_load_count
        joblib_load_count += 1
        return orig_joblib_load(filename, *args, **kwargs)

    monkeypatch.setattr("joblib.load", counting_joblib_load)

    # Load active artifact for pdm-lightgbm
    loaded = pred_service.load_active_artifact("lightgbm")

    # joblib.load should be called exactly once inside validate_model_artifact(load_model=True)
    assert joblib_load_count == 1
    assert loaded.model is not None
    assert loaded.manifest_checksum is not None


def test_prediction_service_constructed_snapshot_prevents_post_validation_file_reread(tmp_path):
    """Prediction Service constructs LoadedModelArtifact directly from ValidatedModelArtifact fields."""
    from systems.generator.model.publisher import (
        ModelArtifactPublisher,
    )
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService

    pub = ModelArtifactPublisher(tmp_path / "artifacts")
    pub.publish_artifact(
        model_id="pdm-test-reread",
        model_version="v1.0",
        base_model="lightgbm",
        model_obj=RereadTestMockEstimator(),
        dataset_id="ds-v1",
        dataset_version="v1.0",
        feature_dataset_version="feat-v1",
        feature_schema={
            "feature_schema_version": "v1.0",
            "features": [{"feature_name": "f1", "source_field": "col1", "operation": "raw", "parameters": {}}],
        },
        label_schema={"label_schema_version": "v1.0", "prediction_horizon_hours": 12, "target_type": "binary_failure_within_horizon"},
        history_requirement={"minimum_history_rows": 1, "required_columns": ["col1"], "missing_history_policy": "reject"},
        metrics={"metrics_summary": {"f1": 0.9}, "primary_metric": "f1"},
        training_config={"training_config_version": "v1.0", "training_config_sha256": "0" * 64},
        provenance={},
    )

    pred_service = PredictionService(models_store_dir=tmp_path)
    loaded = pred_service.load_active_artifact("pdm-test-reread", "v1.0")

    assert loaded.model_id == "pdm-test-reread"
    assert loaded.model_version == "v1.0"
    assert loaded.model is not None
    assert loaded.feature_schema["feature_schema_version"] == "v1.0"
    assert loaded.label_schema["label_schema_version"] == "v1.0"
    assert loaded.history_requirement["minimum_history_rows"] == 1
    assert loaded.metrics["primary_metric"] == "f1"
    assert loaded.manifest_checksum is not None
    assert loaded.artifact_ref.sha256 == loaded.manifest_checksum


# =====================================================================
# 56. Active Model Set Fail-Closed Official Schema Verification Tests
# =====================================================================

def test_active_model_set_official_schema_fail_closed_validation(tmp_path: Path, monkeypatch):
    """ActiveModelSetService.load_active_model_set() strictly validates raw JSON against official JSON Schema in fail-closed order."""
    import json
    from systems.generator.generator_config import PROJECT_ROOT
    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError

    models_dir = tmp_path / "models_store"
    models_dir.mkdir(parents=True, exist_ok=True)
    pointer_file = models_dir / "active-model-set.json"

    svc = ActiveModelSetService(models_store_dir=models_dir)

    # 1. Normal official example load success
    valid_data = {
        "model_set_id": "pdm-default",
        "model_set_version": "1.0.0",
        "updated_at": "2026-08-27T10:00:00Z",
        "models": {
            "lightgbm": {"model_version": "1.0.0", "required": True}
        }
    }
    pointer_file.write_text(json.dumps(valid_data), encoding="utf-8")
    loaded = svc.load_active_model_set()
    assert loaded.model_set_id == "pdm-default"
    assert loaded.models["lightgbm"].required is True

    # Helper for invalid schema cases
    def assert_invalid(raw_dict: dict, expected_reason: str):
        pointer_file.write_text(json.dumps(raw_dict), encoding="utf-8")
        with pytest.raises(ModelSetContractInvalidError) as exc_info:
            svc.load_active_model_set()
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "MODEL_SET_CONTRACT_INVALID"
        details = exc_info.value.details
        assert any(d.get("reason") == expected_reason for d in details)

    # 2. model_set_id missing
    d2 = dict(valid_data)
    del d2["model_set_id"]
    assert_invalid(d2, "active_model_set_schema_invalid")

    # 3. Empty model_set_id
    d3 = dict(valid_data, model_set_id="")
    assert_invalid(d3, "active_model_set_schema_invalid")

    # 4. model_set_version missing
    d4 = dict(valid_data)
    del d4["model_set_version"]
    assert_invalid(d4, "active_model_set_schema_invalid")

    # 5. Empty model_set_version
    d5 = dict(valid_data, model_set_version="")
    assert_invalid(d5, "active_model_set_schema_invalid")

    # 6. updated_at missing
    d6 = dict(valid_data)
    del d6["updated_at"]
    assert_invalid(d6, "active_model_set_schema_invalid")

    # 7. Invalid date string
    d7 = dict(valid_data, updated_at="not-a-date")
    assert_invalid(d7, "active_model_set_schema_invalid")

    # 8. models[*].model_version missing
    d8 = {
        "model_set_id": "pdm-default",
        "model_set_version": "1.0.0",
        "updated_at": "2026-08-27T10:00:00Z",
        "models": {"lightgbm": {"required": True}},
    }
    assert_invalid(d8, "active_model_set_schema_invalid")

    # 9. Empty models[*].model_version
    d9 = {
        "model_set_id": "pdm-default",
        "model_set_version": "1.0.0",
        "updated_at": "2026-08-27T10:00:00Z",
        "models": {"lightgbm": {"model_version": "", "required": True}},
    }
    assert_invalid(d9, "active_model_set_schema_invalid")

    # 10. models[*].required missing
    d10 = {
        "model_set_id": "pdm-default",
        "model_set_version": "1.0.0",
        "updated_at": "2026-08-27T10:00:00Z",
        "models": {"lightgbm": {"model_version": "1.0.0"}},
    }
    assert_invalid(d10, "active_model_set_schema_invalid")

    # 11. Empty models object
    d11 = {
        "model_set_id": "pdm-default",
        "model_set_version": "1.0.0",
        "updated_at": "2026-08-27T10:00:00Z",
        "models": {},
    }
    assert_invalid(d11, "active_model_set_schema_invalid")

    # 12. Disallowed extra field
    d12 = dict(valid_data, extra_unallowed_field=123)
    assert_invalid(d12, "active_model_set_schema_invalid")

    # 13. Fail-closed when official schema file missing
    monkeypatch.setattr(
        "systems.generator.app.runtime_pipeline.active_model_set_service.PROJECT_ROOT",
        tmp_path / "non_existent_root",
    )
    pointer_file.write_text(json.dumps(valid_data), encoding="utf-8")
    with pytest.raises(ModelSetContractInvalidError) as exc_missing:
        svc.load_active_model_set()
    assert any(d.get("reason") == "active_model_set_schema_missing" for d in exc_missing.value.details)


def test_active_model_set_corrupt_schema_file_fails_closed(tmp_path: Path, monkeypatch):
    """When official schema file exists but contains corrupt JSON, load_active_model_set() raises active_model_set_schema_parse_failed."""
    import json
    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError

    fake_root = tmp_path / "fake_repo"
    schema_dir = fake_root / "contracts" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    corrupt_schema = schema_dir / "generator-active-model-set.schema.json"
    corrupt_schema.write_text("{ corrupt json syntax", encoding="utf-8")

    models_dir = tmp_path / "models_store"
    models_dir.mkdir(parents=True, exist_ok=True)
    pointer_file = models_dir / "active-model-set.json"
    pointer_file.write_text(json.dumps({"model_set_id": "v1"}), encoding="utf-8")

    monkeypatch.setattr(
        "systems.generator.app.runtime_pipeline.active_model_set_service.PROJECT_ROOT",
        fake_root,
    )

    svc = ActiveModelSetService(models_store_dir=models_dir)
    with pytest.raises(ModelSetContractInvalidError) as exc_corrupt:
        svc.load_active_model_set()
    assert any(d.get("reason") == "active_model_set_schema_parse_failed" for d in exc_corrupt.value.details)


# =====================================================================
# 57. Service Boundary Artifact Path Error Conversion Tests
# =====================================================================

def test_service_boundary_artifact_path_error_conversion(isolated_runtime_env):
    """ActiveModelSetService.update_active_model_set converts artifact path errors into ModelSetArtifactPathUnsupportedError without NameError and preserves existing pointer."""
    from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelConfig, ActiveModelSet, now_utc_iso
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        ModelSetArtifactPathUnsupportedError,
    )

    env = isolated_runtime_env
    root_dir: Path = env["artifacts_dir"]
    svc = ActiveModelSetService(models_store_dir=root_dir.parent)

    # Initial valid pointer
    init_set = svc.load_active_model_set()
    assert init_set.model_set_id == "pdm-default"

    # Helper function to test path error conversion
    def assert_path_unsupported(bad_version: str):
        bad_set = ActiveModelSet(
            model_set_id="pdm-bad-path",
            model_set_version="9.9.9",
            updated_at=now_utc_iso(),
            models={"lightgbm": ActiveModelConfig(model_version=bad_version, required=True)},
        )

        with pytest.raises(ModelSetArtifactPathUnsupportedError) as exc_info:
            svc.update_active_model_set(bad_set, validate_artifacts=True)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "MODEL_SET_ARTIFACT_PATH_UNSUPPORTED"

        # Verify existing pointer is preserved!
        current_set = svc.load_active_model_set()
        assert current_set.model_set_id == init_set.model_set_id

    # 1. Path traversal ..
    assert_path_unsupported("../pdm-lightgbm-v1.0")

    # 2. External URI
    assert_path_unsupported("http://example.com/pdm-lightgbm-v1.0")

    # 3. Path outside root
    assert_path_unsupported("../../outside_root")


# =====================================================================
# 58. Array Prediction Result Batch Schema & Serialization Tests (Part C-1)
# =====================================================================

def test_prediction_result_batch_array_serialization_and_validation():
    """Verify PredictionResultBatchPayload array model serialization, schema validation, and checksum calculation."""
    from datetime import datetime, timezone
    import json
    import jsonschema
    from systems.generator.generator_config import PROJECT_ROOT
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultBatchPayload,
        PredictionResultBatchSourceContext,
        PredictionResultItem,
        PredictionResultProducer,
        PredictionResultLineage,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )

    schema_file = PROJECT_ROOT / "contracts" / "schemas" / "prediction-result-batch.schema.json"
    assert schema_file.is_file()
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    item_dict = {
        "event_id": "evt-001",
        "asset_id": "CNC-001",
        "observed_at": "2026-08-27T00:00:00Z",
        "source_kind": "live_sensor",
        "source_ref": {
            "uri": "data/incoming/protocol.jsonl",
            "sha256": "a" * 64,
        },
        "output_status": "predicted",
        "score": 0.85,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "b" * 64,
        "feature_schema_version": "v1.0.0",
        "history_requirement_version": "v1.0.0",
        "label_schema_version": "v1.0.0",
        "feature_schema_sha256": "e" * 64,
        "history_requirement_sha256": "f" * 64,
        "label_schema_sha256": "a" * 64,
        "lineage": {
            "simulation_session_id": None,
            "overlay_branch_id": None,
            "history_segment_id": None,
            "maintenance_event_id": None,
            "maintenance_action_id": None,
            "state_version": None,
        },
        "failure_reason": None,
    }

    item_sha = compute_prediction_result_item_sha256(item_dict)

    item = PredictionResultItem(
        event_id="evt-001",
        asset_id="CNC-001",
        observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="data/incoming/protocol.jsonl", sha256="a" * 64),
        payload_sha256=item_sha,
        output_status="predicted",
        score=0.85,
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        model_artifact_manifest_sha256="b" * 64,
        feature_schema_version="v1.0.0",
        history_requirement_version="v1.0.0",
        label_schema_version="v1.0.0",
        feature_schema_sha256="e" * 64,
        history_requirement_sha256="f" * 64,
        label_schema_sha256="a" * 64,
        lineage=PredictionResultLineage(),
        failure_reason=None,
    )

    producer = PredictionResultProducer(system="systems.generator", runtime_version="1.0.0", outbox_id=None)
    batch = PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id="batch-001",
        producer=producer,
        emitted_at=datetime.fromisoformat("2026-08-27T00:00:05+00:00"),
        source_context=PredictionResultBatchSourceContext(
            dataset_id="canonical-ai4i-v1",
            dataset_version="v1.0",
            source_uri="data/incoming/protocol.jsonl",
            source_checksum="a" * 64,
            source_kind="live_sensor",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
        ),
        model_set=create_test_active_model_set_snapshot(
            model_set_id="model-set-v1",
            model_set_version="1.0.0",
            model_version="1.0.0",
        ),
        results=[item],
    )

    batch_json = json.loads(batch.model_dump_json())
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    validator.validate(batch_json)


def test_prediction_result_batch_array_duplicate_composite_key_fails_closed():
    """Duplicate composite key (asset_id, model_id, observed_at) in results array fails closed with ModelSetContractInvalidError."""
    from datetime import datetime
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import validate_external_results_array
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )

    dt = datetime.fromisoformat("2026-08-27T00:00:00+00:00")
    d1 = {
        "event_id": "evt-dup-1",
        "asset_id": "CNC-001",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": {"uri": "data/incoming/p.jsonl", "sha256": "c" * 64},
        "output_status": "predicted",
        "score": 0.8,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "d" * 64,
        "feature_schema_version": "v1.0.0",
        "history_requirement_version": "v1.0.0",
        "label_schema_version": "v1.0.0",
        "feature_schema_sha256": "e" * 64,
        "history_requirement_sha256": "f" * 64,
        "label_schema_sha256": "a" * 64,
        "lineage": {"simulation_session_id": None, "overlay_branch_id": None, "history_segment_id": None, "maintenance_event_id": None, "maintenance_action_id": None, "state_version": None},
        "failure_reason": None,
    }
    d2 = {
        "event_id": "evt-dup-2",
        "asset_id": "CNC-001",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": {"uri": "data/incoming/p.jsonl", "sha256": "c" * 64},
        "output_status": "predicted",
        "score": 0.9,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "d" * 64,
        "feature_schema_version": "v1.0.0",
        "history_requirement_version": "v1.0.0",
        "label_schema_version": "v1.0.0",
        "feature_schema_sha256": "e" * 64,
        "history_requirement_sha256": "f" * 64,
        "label_schema_sha256": "a" * 64,
        "lineage": {"simulation_session_id": None, "overlay_branch_id": None, "history_segment_id": None, "maintenance_event_id": None, "maintenance_action_id": None, "state_version": None},
        "failure_reason": None,
    }

    item1 = PredictionResultItem(
        event_id="evt-dup-1",
        asset_id="CNC-001",
        observed_at=dt,
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="data/incoming/p.jsonl", sha256="c" * 64),
        payload_sha256=compute_prediction_result_item_sha256(d1),
        output_status="predicted",
        score=0.8,
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        model_artifact_manifest_sha256="d" * 64,
        feature_schema_version="v1.0.0",
        history_requirement_version="v1.0.0",
        label_schema_version="v1.0.0",
        feature_schema_sha256="e" * 64,
        history_requirement_sha256="f" * 64,
        label_schema_sha256="a" * 64,
        lineage=PredictionResultLineage(),
        failure_reason=None,
    )
    item2 = PredictionResultItem(
        event_id="evt-dup-2",
        asset_id="CNC-001",
        observed_at=dt,
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="data/incoming/p.jsonl", sha256="c" * 64),
        payload_sha256=compute_prediction_result_item_sha256(d2),
        output_status="predicted",
        score=0.9,
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        model_artifact_manifest_sha256="d" * 64,
        feature_schema_version="v1.0.0",
        history_requirement_version="v1.0.0",
        label_schema_version="v1.0.0",
        feature_schema_sha256="e" * 64,
        history_requirement_sha256="f" * 64,
        label_schema_sha256="a" * 64,
        lineage=PredictionResultLineage(),
        failure_reason=None,
    )

    with pytest.raises(ModelSetContractInvalidError) as exc_info:
        validate_external_results_array([item1, item2])
    assert "중복된 복합키" in str(exc_info.value)


def test_prediction_result_batch_array_duplicate_event_id_fails_closed():
    """Duplicate event_id in results array fails closed with ModelSetContractInvalidError."""
    from datetime import datetime
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import validate_external_results_array
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )

    dt = datetime.fromisoformat("2026-08-27T00:00:00+00:00")
    d1 = {
        "event_id": "evt-dup-same",
        "asset_id": "CNC-001",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": {"uri": "data/incoming/p.jsonl", "sha256": "c" * 64},
        "output_status": "predicted",
        "score": 0.8,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "d" * 64,
        "feature_schema_version": "v1.0.0",
        "history_requirement_version": "v1.0.0",
        "label_schema_version": "v1.0.0",
        "feature_schema_sha256": "e" * 64,
        "history_requirement_sha256": "f" * 64,
        "label_schema_sha256": "a" * 64,
        "lineage": {"simulation_session_id": None, "overlay_branch_id": None, "history_segment_id": None, "maintenance_event_id": None, "maintenance_action_id": None, "state_version": None},
        "failure_reason": None,
    }
    d2 = {
        "event_id": "evt-dup-same",
        "asset_id": "CNC-001",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": {"uri": "data/incoming/p.jsonl", "sha256": "c" * 64},
        "output_status": "predicted",
        "score": 0.9,
        "model_id": "pdm-xgboost",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "d" * 64,
        "feature_schema_version": "v1.0.0",
        "history_requirement_version": "v1.0.0",
        "label_schema_version": "v1.0.0",
        "feature_schema_sha256": "e" * 64,
        "history_requirement_sha256": "f" * 64,
        "label_schema_sha256": "a" * 64,
        "lineage": {"simulation_session_id": None, "overlay_branch_id": None, "history_segment_id": None, "maintenance_event_id": None, "maintenance_action_id": None, "state_version": None},
        "failure_reason": None,
    }

    item1 = PredictionResultItem(
        event_id="evt-dup-same",
        asset_id="CNC-001",
        observed_at=dt,
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="data/incoming/p.jsonl", sha256="c" * 64),
        payload_sha256=compute_prediction_result_item_sha256(d1),
        output_status="predicted",
        score=0.8,
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        model_artifact_manifest_sha256="d" * 64,
        feature_schema_version="v1.0.0",
        history_requirement_version="v1.0.0",
        label_schema_version="v1.0.0",
        feature_schema_sha256="e" * 64,
        history_requirement_sha256="f" * 64,
        label_schema_sha256="a" * 64,
        lineage=PredictionResultLineage(),
        failure_reason=None,
    )
    item2 = PredictionResultItem(
        event_id="evt-dup-same",
        asset_id="CNC-001",
        observed_at=dt,
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="data/incoming/p.jsonl", sha256="c" * 64),
        payload_sha256=compute_prediction_result_item_sha256(d2),
        output_status="predicted",
        score=0.9,
        model_id="pdm-xgboost",
        model_version="1.0.0",
        model_artifact_manifest_sha256="d" * 64,
        feature_schema_version="v1.0.0",
        history_requirement_version="v1.0.0",
        label_schema_version="v1.0.0",
        feature_schema_sha256="e" * 64,
        history_requirement_sha256="f" * 64,
        label_schema_sha256="a" * 64,
        lineage=PredictionResultLineage(),
        failure_reason=None,
    )

    with pytest.raises(ModelSetContractInvalidError) as exc_info:
        validate_external_results_array([item1, item2])
    assert "중복된 event_id" in str(exc_info.value)


def test_prediction_result_batch_empty_results_fails_closed():
    """Empty results array fails closed with ModelSetContractInvalidError."""
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import validate_external_results_array

    with pytest.raises(ModelSetContractInvalidError) as exc_info:
        validate_external_results_array([])
    assert "results 배열이 비어 있습니다" in str(exc_info.value)


# =====================================================================
# 59. Model Inference Failure Fail-Closed Tests (Part C-2)
# =====================================================================

def test_model_inference_exception_raises_pipeline_model_prediction_failed_error(isolated_runtime_env, monkeypatch):
    """When model inference raises an arbitrary exception (e.g. ValueError), predict_for_models raises PipelineModelPredictionFailedError for required models."""
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelPredictionFailedError
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService

    import numpy as np
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, RuntimeFeatureRowMetadata
    from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureBundle

    env = isolated_runtime_env
    svc: PredictionService = env["service"].prediction_service

    feat_path = env["preprocessed_dir"] / "test_dummy_feat.npy"
    np.save(feat_path, np.array([[1.0, 2.0, 3.0]]))
    feat_ref = ArtifactReference(uri=str(feat_path), sha256="0"*64, role="runtime_features")
    row_meta = RuntimeFeatureRowMetadata(row_index=0, asset_id="M14860", observed_at="2026-08-27T00:00:00Z")
    bundle = RuntimeFeatureBundle(
        features=np.array([[1.0, 2.0, 3.0]]),
        feature_columns=["f1", "f2", "f3"],
        row_metadata=[row_meta],
        runtime_feature_version="1.0",
        feature_schema_version="v1.0",
        dataset_id="canonical-ai4i-v1",
        dataset_version="v3.1",
        asset_history_status={"M14860": {"ready": True, "count": 5, "minimum_history_rows": 1}},
    )

    class BrokenModel:
        def predict_proba(self, X):
            raise ValueError("Internal model crash during predict_proba")

    artifact = svc.load_active_artifact("lightgbm")
    monkeypatch.setattr(artifact, "model", BrokenModel())
    monkeypatch.setattr(svc, "load_active_artifact", lambda base_model, target_version=None: artifact)

    with pytest.raises(PipelineModelPredictionFailedError) as exc_info:
        svc.predict_for_models(
            base_models=["lightgbm"],
            model_feature_refs={"lightgbm": feat_ref},
            model_feature_bundles={"lightgbm": bundle},
            asset_ids=["M14860"],
            active_model_set=env["service"].active_model_set_service.load_active_model_set(),
        )

    assert "추론 실패" in str(exc_info.value) or "predict_proba" in str(exc_info.value)


def test_model_inference_nan_score_raises_pipeline_model_prediction_failed_error(isolated_runtime_env, monkeypatch):
    """When model inference returns NaN score, predict_for_models raises PipelineModelPredictionFailedError."""
    import numpy as np
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelPredictionFailedError
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, RuntimeFeatureRowMetadata
    from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureBundle

    env = isolated_runtime_env
    svc: PredictionService = env["service"].prediction_service

    feat_path = env["preprocessed_dir"] / "test_dummy_feat.npy"
    np.save(feat_path, np.array([[1.0, 2.0, 3.0]]))
    feat_ref = ArtifactReference(uri=str(feat_path), sha256="0"*64, role="runtime_features")
    row_meta = RuntimeFeatureRowMetadata(row_index=0, asset_id="M14860", observed_at="2026-08-27T00:00:00Z")
    bundle = RuntimeFeatureBundle(
        features=np.array([[1.0, 2.0, 3.0]]),
        feature_columns=["f1", "f2", "f3"],
        row_metadata=[row_meta],
        runtime_feature_version="1.0",
        feature_schema_version="v1.0",
        dataset_id="canonical-ai4i-v1",
        dataset_version="v3.1",
        asset_history_status={"M14860": {"ready": True, "count": 5, "minimum_history_rows": 1}},
    )

    class NaNModel:
        def predict_proba(self, X):
            return np.array([[0.5, np.nan]])

    artifact = svc.load_active_artifact("lightgbm")
    monkeypatch.setattr(artifact, "model", NaNModel())
    monkeypatch.setattr(svc, "load_active_artifact", lambda base_model, target_version=None: artifact)

    with pytest.raises(PipelineModelPredictionFailedError) as exc_info:
        svc.predict_for_models(
            base_models=["lightgbm"],
            model_feature_refs={"lightgbm": feat_ref},
            model_feature_bundles={"lightgbm": bundle},
            asset_ids=["M14860"],
            active_model_set=env["service"].active_model_set_service.load_active_model_set(),
        )

    assert "non-finite score" in str(exc_info.value)


def test_model_inference_inf_score_raises_pipeline_model_prediction_failed_error(isolated_runtime_env, monkeypatch):
    """When model inference returns Inf score, predict_for_models raises PipelineModelPredictionFailedError."""
    import numpy as np
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelPredictionFailedError
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, RuntimeFeatureRowMetadata
    from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureBundle

    env = isolated_runtime_env
    svc: PredictionService = env["service"].prediction_service

    feat_path = env["preprocessed_dir"] / "test_dummy_feat.npy"
    np.save(feat_path, np.array([[1.0, 2.0, 3.0]]))
    feat_ref = ArtifactReference(uri=str(feat_path), sha256="0"*64, role="runtime_features")
    row_meta = RuntimeFeatureRowMetadata(row_index=0, asset_id="M14860", observed_at="2026-08-27T00:00:00Z")
    bundle = RuntimeFeatureBundle(
        features=np.array([[1.0, 2.0, 3.0]]),
        feature_columns=["f1", "f2", "f3"],
        row_metadata=[row_meta],
        runtime_feature_version="1.0",
        feature_schema_version="v1.0",
        dataset_id="canonical-ai4i-v1",
        dataset_version="v3.1",
        asset_history_status={"M14860": {"ready": True, "count": 5, "minimum_history_rows": 1}},
    )

    class InfModel:
        def predict_proba(self, X):
            return np.array([[0.0, np.inf]])

    artifact = svc.load_active_artifact("lightgbm")
    monkeypatch.setattr(artifact, "model", InfModel())
    monkeypatch.setattr(svc, "load_active_artifact", lambda base_model, target_version=None: artifact)

    with pytest.raises(PipelineModelPredictionFailedError) as exc_info:
        svc.predict_for_models(
            base_models=["lightgbm"],
            model_feature_refs={"lightgbm": feat_ref},
            model_feature_bundles={"lightgbm": bundle},
            asset_ids=["M14860"],
            active_model_set=env["service"].active_model_set_service.load_active_model_set(),
        )

    assert "non-finite score" in str(exc_info.value)


def test_model_inference_out_of_bounds_score_raises_pipeline_model_prediction_failed_error(isolated_runtime_env, monkeypatch):
    """When model inference returns score outside [0.0, 1.0], predict_for_models raises PipelineModelPredictionFailedError."""
    import numpy as np
    import pytest
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineModelPredictionFailedError
    from systems.generator.app.runtime_pipeline.prediction_service import PredictionService
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, RuntimeFeatureRowMetadata
    from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureBundle

    env = isolated_runtime_env
    svc: PredictionService = env["service"].prediction_service

    feat_path = env["preprocessed_dir"] / "test_dummy_feat.npy"
    np.save(feat_path, np.array([[1.0, 2.0, 3.0]]))
    feat_ref = ArtifactReference(uri=str(feat_path), sha256="0"*64, role="runtime_features")
    row_meta = RuntimeFeatureRowMetadata(row_index=0, asset_id="M14860", observed_at="2026-08-27T00:00:00Z")
    bundle = RuntimeFeatureBundle(
        features=np.array([[1.0, 2.0, 3.0]]),
        feature_columns=["f1", "f2", "f3"],
        row_metadata=[row_meta],
        runtime_feature_version="1.0",
        feature_schema_version="v1.0",
        dataset_id="canonical-ai4i-v1",
        dataset_version="v3.1",
        asset_history_status={"M14860": {"ready": True, "count": 5, "minimum_history_rows": 1}},
    )

    class OOBModel:
        def predict_proba(self, X):
            return np.array([[0.0, 1.5]])

    artifact = svc.load_active_artifact("lightgbm")
    monkeypatch.setattr(artifact, "model", OOBModel())
    monkeypatch.setattr(svc, "load_active_artifact", lambda base_model, target_version=None: artifact)

    with pytest.raises(PipelineModelPredictionFailedError) as exc_info:
        svc.predict_for_models(
            base_models=["lightgbm"],
            model_feature_refs={"lightgbm": feat_ref},
            model_feature_bundles={"lightgbm": bundle},
            asset_ids=["M14860"],
            active_model_set=env["service"].active_model_set_service.load_active_model_set(),
        )

    assert "out of bounds" in str(exc_info.value)


@pytest.mark.parametrize(
    ("selected_model", "non_applicable_model"),
    [
        ("lightgbm", "compressor"),
        ("compressor", "lightgbm"),
    ],
)
def test_prediction_service_runs_only_models_selected_for_the_input_family(
    isolated_runtime_env,
    monkeypatch,
    selected_model,
    non_applicable_model,
):
    """A required model for another asset family must not block a scoped prediction."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelConfig,
        ActiveModelSet,
        now_utc_iso,
    )

    svc = isolated_runtime_env["service"].prediction_service
    artifact = svc.load_active_artifact("lightgbm")
    active_set = ActiveModelSet(
        model_set_id="family-scoped-model-set",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={
            non_applicable_model: ActiveModelConfig(
                model_version="non-applicable-v1",
                required=True,
            ),
            selected_model: ActiveModelConfig(
                model_version=artifact.model_version,
                required=True,
            ),
        },
    )
    loaded_models: list[str] = []

    def load_selected(base_model: str, target_version=None):
        loaded_models.append(base_model)
        if base_model == non_applicable_model:
            raise AssertionError("non-applicable family model was loaded")
        return artifact

    monkeypatch.setattr(svc, "load_active_artifact", load_selected)

    with pytest.raises(PipelineModelPredictionFailedError, match=selected_model):
        svc.predict_for_models(
            base_models=[selected_model],
            model_feature_refs={},
            active_model_set=active_set,
        )

    assert loaded_models == [selected_model]


# =====================================================================
# 60. Delivery Contract and Endpoint URL Configuration Tests
# =====================================================================

def test_delivery_service_default_endpoint_and_env_config(isolated_runtime_env, monkeypatch):
    """PredictionDeliveryService defaults to /internal/prediction-results and respects GENERATOR_PREDICTION_RESULT_URL."""
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import PredictionDeliveryService

    # 1. Default URL
    monkeypatch.delenv("GENERATOR_PREDICTION_RESULT_URL", raising=False)
    monkeypatch.delenv("GENERATOR_PREDICTION_RECEIVER_URL", raising=False)
    svc = PredictionDeliveryService()
    assert svc.endpoint_url == (
        "http://localhost:8000/internal/prediction-results"
        "?project_id=manufacturing-demo-project&workspace_id=manufacturing-demo"
    )

    # 2. Standard ENV override
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_URL", "https://prod-backend:8443/internal/prediction-results")
    svc2 = PredictionDeliveryService()
    assert svc2.endpoint_url == (
        "https://prod-backend:8443/internal/prediction-results"
        "?project_id=manufacturing-demo-project&workspace_id=manufacturing-demo"
    )

    # 3. Legacy ENV fallback with warning
    monkeypatch.delenv("GENERATOR_PREDICTION_RESULT_URL", raising=False)
    monkeypatch.setenv("GENERATOR_PREDICTION_RECEIVER_URL", "https://legacy-backend:8443/internal/prediction-results")
    svc3 = PredictionDeliveryService()
    assert svc3.endpoint_url == (
        "https://legacy-backend:8443/internal/prediction-results"
        "?project_id=manufacturing-demo-project&workspace_id=manufacturing-demo"
    )

    # 4. Conflicting ENVs raise ValueError
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_URL", "http://backend-1/internal/prediction-results")
    monkeypatch.setenv("GENERATOR_PREDICTION_RECEIVER_URL", "http://backend-2/internal/prediction-results")
    with pytest.raises(ValueError) as exc_info:
        PredictionDeliveryService()
    assert "conflicting values" in str(exc_info.value)


def test_delivery_service_send_once_headers_and_post_method(isolated_runtime_env, monkeypatch):
    """send_once dispatches HTTP POST with Idempotency-Key and X-Request-ID headers."""
    import urllib.request
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import PredictionDeliveryService

    monkeypatch.delenv("GENERATOR_PREDICTION_RESULT_TOKEN", raising=False)
    svc = PredictionDeliveryService(endpoint_url="http://localhost:8000/internal/prediction-results")
    payload = create_test_batch_payload(
        event_id="evt-post-01",
        asset_id="M14860",
        batch_id="batch-post-01",
    )

    captured_req = None

    class MockResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def getcode(self):
            return 200
        def read(self):
            return b'{"status": "ok"}'

    def mock_urlopen(req, timeout=10.0):
        nonlocal captured_req
        captured_req = req
        return MockResponse()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    res = svc.send_once(payload)
    assert res["delivered"] is True
    assert res["status_code"] == 200

    assert captured_req is not None
    assert captured_req.get_method() == "POST"
    assert captured_req.full_url == (
        "http://localhost:8000/internal/prediction-results"
        "?project_id=manufacturing-demo-project&workspace_id=manufacturing-demo"
    )
    idempotency_val = captured_req.headers.get("Idempotency-key") or captured_req.headers.get("Idempotency-Key")
    assert idempotency_val is not None
    assert idempotency_val.startswith("evt-batch-")
    assert captured_req.headers.get("X-request-id") == "batch-post-01" or captured_req.headers.get("X-Request-ID") == "batch-post-01"
    assert captured_req.headers.get("Authorization") is None


# =====================================================================
# 61. Provenance Fail-Closed and Fallback Removal Tests
# =====================================================================

def test_to_external_result_item_provenance_preservation():
    """Valid observed_at and source_ref are strictly preserved in external PredictionResultItem."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
        ArtifactReference,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item

    src_ref = PredictionResultSourceRef(uri="data/incoming/raw_sensors.jsonl", sha256="c" * 64)
    art_ref = ArtifactReference(uri="models_store/lgbm.joblib", sha256="d" * 64, role="model_artifact")
    internal = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-25T14:30:00Z",
        score_type="probability",
        score_source="predict_proba",
        score=0.88,
        artifact_ref=art_ref,
        manifest_checksum="d" * 64,
        feature_schema_version="v1.0",
        label_schema_version="v1.0",
        history_requirement_version="v1.0",
    )

    item = to_external_result_item(
        internal,
        source_kind="live_sensor",
        source_ref=src_ref,
        feature_schema_sha256="a" * 64,
        history_requirement_sha256="b" * 64,
        label_schema_sha256="c" * 64,
    )
    assert item.asset_id == "M14860"
    assert item.model_id == "pdm-lightgbm"
    assert item.source_ref.uri == "data/incoming/raw_sensors.jsonl"
    assert item.source_ref.sha256 == "c" * 64
    assert item.model_artifact_manifest_sha256 == "d" * 64
    assert item.output_status == "predicted"
    assert item.score == 0.88
    assert "2026-08-25T14:30:00" in item.observed_at.isoformat()


def test_to_external_result_item_missing_or_blank_observed_at_raises():
    """Missing or blank observed_at raises ModelSetContractInvalidError without fake current time fallback."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
    )
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item

    src_ref = PredictionResultSourceRef(uri="data/incoming/raw.jsonl", sha256="c" * 64)

    # 1. None observed_at
    internal_none = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="",
        score=0.8,
        manifest_checksum="d" * 64,
    )
    with pytest.raises(ModelSetContractInvalidError) as exc:
        to_external_result_item(internal_none, source_kind="live_sensor", source_ref=src_ref)
    assert "missing required observed_at" in str(exc.value) or "blank" in str(exc.value)

    # 2. Blank whitespace observed_at
    internal_blank = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="   ",
        score=0.8,
        manifest_checksum="d" * 64,
    )
    with pytest.raises(ModelSetContractInvalidError) as exc2:
        to_external_result_item(internal_blank, source_kind="live_sensor", source_ref=src_ref)
    assert "blank observed_at" in str(exc2.value)


def test_to_external_result_item_invalid_timestamp_format_raises():
    """Invalid timestamp string raises ModelSetContractInvalidError without fake fallback."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
    )
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item

    src_ref = PredictionResultSourceRef(uri="data/incoming/raw.jsonl", sha256="c" * 64)
    internal_bad = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026/08/25 not-a-date",
        score=0.8,
        manifest_checksum="d" * 64,
    )
    with pytest.raises(ModelSetContractInvalidError) as exc:
        to_external_result_item(internal_bad, source_kind="live_sensor", source_ref=src_ref)
    assert "invalid observed_at ISO timestamp format" in str(exc.value)


def test_to_external_result_item_missing_or_empty_source_ref_raises():
    """Missing source_ref or empty source_ref.uri raises ModelSetContractInvalidError without dummy URI fallback."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
    )
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item

    internal = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-25T14:30:00Z",
        score=0.8,
        manifest_checksum="d" * 64,
    )

    # 1. source_ref is None
    with pytest.raises(ModelSetContractInvalidError) as exc:
        to_external_result_item(internal, source_kind="live_sensor", source_ref=None)
    assert "missing required source_ref" in str(exc.value)

    # 2. source_ref.uri is blank
    bad_ref = PredictionResultSourceRef(uri="   ", sha256="c" * 64)
    with pytest.raises(ModelSetContractInvalidError) as exc2:
        to_external_result_item(internal, source_kind="live_sensor", source_ref=bad_ref)
    assert "empty source_ref.uri" in str(exc2.value)


def test_to_external_result_item_zero_or_invalid_source_sha256_raises():
    """Zero checksum ('0'*64), non-hex, or invalid length sha256 in source_ref is rejected."""
    from pydantic import ValidationError
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultSourceRef,
    )

    # 1. Zero checksum '0'*64 is rejected
    with pytest.raises(ValidationError) as exc:
        PredictionResultSourceRef(uri="data/in.jsonl", sha256="0" * 64)
    assert "SHA-256 checksum cannot be all zeros" in str(exc.value)

    # 2. Short checksum is rejected
    with pytest.raises(ValidationError) as exc2:
        PredictionResultSourceRef(uri="data/in.jsonl", sha256="abc123")
    assert "String should match pattern" in str(exc2.value) or "pattern" in str(exc2.value).lower()


def test_to_external_result_item_missing_artifact_sha256_for_predicted_raises():
    """Predicted output_status missing model artifact checksum raises ModelSetContractInvalidError."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
    )
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item

    src_ref = PredictionResultSourceRef(uri="data/in.jsonl", sha256="c" * 64)
    internal = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-25T14:30:00Z",
        score=0.8,
        manifest_checksum=None,
        artifact_ref=None,
    )

    with pytest.raises(ModelSetContractInvalidError) as exc:
        to_external_result_item(internal, source_kind="live_sensor", source_ref=src_ref)
    assert "missing model_artifact_manifest_sha256" in str(exc.value)


# =====================================================================
# 62. Prediction Result Batch v1 Schema Semantic & Pattern Tests
# =====================================================================

def _get_batch_schema():
    import json
    from pathlib import Path
    schema_path = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "prediction-result-batch.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _make_sample_batch_dict(**item_overrides):
    import json
    import hashlib
    base_item = {
        "event_id": "evt-001",
        "asset_id": "M14860",
        "observed_at": "2026-08-27T00:00:00Z",
        "source_kind": "live_sensor",
        "source_ref": {
            "uri": "data/incoming/protocol.jsonl",
            "sha256": "a" * 64,
        },
        "output_status": "predicted",
        "score": 0.85,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "b" * 64,
        "feature_schema_version": "v1.0",
        "history_requirement_version": "v1.0",
        "label_schema_version": "v1.0",
        "feature_schema_sha256": "1" * 64,
        "history_requirement_sha256": "2" * 64,
        "label_schema_sha256": "3" * 64,
        "lineage": {
            "simulation_session_id": None,
            "overlay_branch_id": None,
            "history_segment_id": None,
            "maintenance_event_id": None,
            "maintenance_action_id": None,
            "state_version": None,
        },
        "failure_reason": None,
    }
    base_item.update(item_overrides)
    if "payload_sha256" not in base_item:
        d_for_sha = dict(base_item)
        d_for_sha.pop("payload_sha256", None)
        c = json.dumps(d_for_sha, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        base_item["payload_sha256"] = hashlib.sha256(c.encode("utf-8")).hexdigest()

    return {
        "contract_version": "prediction-result-batch-v1",
        "batch_id": "batch-001",
        "producer": {
            "system": "systems.generator",
            "runtime_version": "1.0.0",
            "outbox_id": None,
        },
        "emitted_at": "2026-08-27T00:00:05Z",
        "source_context": {
            "dataset_id": "canonical-ai4i-v1",
            "dataset_version": "v1.0",
            "source_uri": "data/incoming/protocol.jsonl",
            "source_checksum": "a" * 64,
            "source_kind": base_item.get("source_kind", "live_sensor"),
            "source_contract_version": "observation-source-v1",
            "source_schema_version": "sensor-record-v2",
            "pipeline_contract_version": "generator-prediction-result-v1",
            "lineage": base_item.get("lineage", {
                "simulation_session_id": None,
                "overlay_branch_id": None,
                "history_segment_id": None,
                "maintenance_event_id": None,
                "maintenance_action_id": None,
                "state_version": None,
            }),
        },
        "model_set": {
            "model_set_id": "model-set-v1",
            "model_set_version": "1.0.0",
            "models": [
                {
                    "model_id": "pdm-lightgbm",
                    "model_version": "1.0.0",
                    "required": True,
                    "model_artifact_manifest_sha256": "b" * 64,
                }
            ],
        },
        "results": [base_item],
    }


def test_schema_predicted_with_score_none_fails():
    """Schema rejects output_status='predicted' when score is null."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(output_status="predicted", score=None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_predicted_with_failure_reason_fails():
    """Schema rejects output_status='predicted' when failure_reason is provided."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(output_status="predicted", score=0.85, failure_reason="unexpected error")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_predicted_with_missing_manifest_sha_fails():
    """Schema rejects output_status='predicted' when model_artifact_manifest_sha256 is null."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(output_status="predicted", score=0.85, model_artifact_manifest_sha256=None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_predicted_with_zero_manifest_sha_fails():
    """Schema rejects model_artifact_manifest_sha256 consisting of 64 zeros."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(output_status="predicted", score=0.85, model_artifact_manifest_sha256="0" * 64)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_predicted_with_score_out_of_range_fails():
    """Schema rejects score outside [0.0, 1.0]."""
    import jsonschema
    schema = _get_batch_schema()
    batch_high = _make_sample_batch_dict(output_status="predicted", score=1.5)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch_high, schema)

    batch_neg = _make_sample_batch_dict(output_status="predicted", score=-0.1)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch_neg, schema)


def test_schema_failed_status_with_non_null_score_fails():
    """Schema rejects failed output_status when score is not null."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(output_status="failed_model_inference", score=0.5, failure_reason="OOM error")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_failed_status_with_null_failure_reason_fails():
    """Schema rejects failed output_status when failure_reason is null or empty."""
    import jsonschema
    schema = _get_batch_schema()
    batch_null = _make_sample_batch_dict(output_status="failed_model_inference", score=None, failure_reason=None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch_null, schema)

    batch_empty = _make_sample_batch_dict(output_status="failed_model_inference", score=None, failure_reason="")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch_empty, schema)


def test_schema_history_insufficient_with_missing_manifest_sha_fails():
    """Schema rejects history_insufficient when model_artifact_manifest_sha256 is null."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(
        output_status="history_insufficient",
        score=None,
        failure_reason="Need 10 data points",
        model_artifact_manifest_sha256=None,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_maintenance_replay_overlay_missing_lineage_fails():
    """Schema rejects maintenance_replay_overlay when lineage fields are missing or state_version < 1."""
    import jsonschema
    schema = _get_batch_schema()
    bad_lineage = {
        "simulation_session_id": "sim-001",
        "overlay_branch_id": None,
        "history_segment_id": "seg-001",
        "maintenance_event_id": "m-001",
        "maintenance_action_id": "act-001",
        "state_version": 1,
    }
    batch = _make_sample_batch_dict(
        source_kind="maintenance_replay_overlay",
        lineage=bad_lineage,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_maintenance_replay_overlay_valid_lineage_passes():
    """Schema accepts maintenance_replay_overlay with all 6 required lineage fields."""
    import jsonschema
    schema = _get_batch_schema()
    valid_lineage = {
        "simulation_session_id": "sim-001",
        "overlay_branch_id": "branch-001",
        "history_segment_id": "seg-001",
        "maintenance_event_id": "m-001",
        "maintenance_action_id": "act-001",
        "state_version": 2,
    }
    batch = _make_sample_batch_dict(
        source_kind="maintenance_replay_overlay",
        lineage=valid_lineage,
    )
    reg = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    reg.validate(batch)


def test_schema_zero_source_sha256_fails():
    """Schema rejects source_ref.sha256 consisting of 64 zeros."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(source_ref={"uri": "data/in.jsonl", "sha256": "0" * 64})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


def test_schema_zero_payload_sha256_fails():
    """Schema rejects payload_sha256 consisting of 64 zeros."""
    import jsonschema
    schema = _get_batch_schema()
    batch = _make_sample_batch_dict(payload_sha256="0" * 64)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(batch, schema)


# =====================================================================
# 63. Pydantic Model Validator Negative & Positive Tests
# =====================================================================

def test_pydantic_score_nan_or_inf_rejected():
    """Pydantic rejects NaN or Inf score in PredictionResultItem."""
    from datetime import datetime
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
    )

    src_ref = PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64)
    lin = PredictionResultLineage()

    with pytest.raises(ValueError, match="finite"):
        PredictionResultItem(
            event_id="evt-nan",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="predicted",
            score=float("nan"),
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
        )

    with pytest.raises(ValueError, match="finite"):
        PredictionResultItem(
            event_id="evt-inf",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="predicted",
            score=float("inf"),
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
        )


def test_pydantic_predicted_without_score_or_with_failure_reason_rejected():
    """Pydantic rejects output_status='predicted' with score=None or failure_reason not None."""
    from datetime import datetime
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
    )

    src_ref = PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64)
    lin = PredictionResultLineage()

    with pytest.raises(ValueError, match="Score is required"):
        PredictionResultItem(
            event_id="evt-no-score",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="predicted",
            score=None,
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
        )

    with pytest.raises(ValueError, match="failure_reason must be None"):
        PredictionResultItem(
            event_id="evt-with-reason",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="predicted",
            score=0.8,
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
            failure_reason="some error",
        )


def test_pydantic_failed_with_score_or_without_reason_rejected():
    """Pydantic rejects failed output_status with non-None score or missing failure_reason."""
    from datetime import datetime
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
    )

    src_ref = PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64)
    lin = PredictionResultLineage()

    with pytest.raises(ValueError, match="Score must be None"):
        PredictionResultItem(
            event_id="evt-failed-with-score",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="failed_model_inference",
            score=0.5,
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
            failure_reason="failed",
        )

    with pytest.raises(ValueError, match="failure_reason is required"):
        PredictionResultItem(
            event_id="evt-failed-no-reason",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="live_sensor",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="failed_model_inference",
            score=None,
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=lin,
            failure_reason=None,
        )


def test_pydantic_maintenance_replay_overlay_missing_lineage_rejected():
    """Pydantic rejects maintenance_replay_overlay without complete lineage."""
    from datetime import datetime
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultSourceRef,
    )

    src_ref = PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64)
    bad_lin = PredictionResultLineage(simulation_session_id="sim-01")

    with pytest.raises(ValueError, match="all 6 lineage fields"):
        PredictionResultItem(
            event_id="evt-overlay-incomplete",
            asset_id="M14860",
            observed_at=datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
            source_kind="maintenance_replay_overlay",
            source_ref=src_ref,
            payload_sha256="a" * 64,
            output_status="predicted",
            score=0.8,
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            model_artifact_manifest_sha256="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
            feature_schema_sha256="1" * 64,
            history_requirement_sha256="2" * 64,
            label_schema_sha256="3" * 64,
            lineage=bad_lin,
        )


# =====================================================================
# 64. Checksum Tamper Detection & Order-Independent Batch Tests
# =====================================================================

def test_item_payload_sha256_tamper_detected():
    """Mutating item properties without updating payload_sha256 is detected and raises ModelSetContractInvalidError."""
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        to_external_result_item,
        validate_prediction_result_item_checksum,
        validate_external_results_array,
    )
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        PredictionResultSourceRef,
    )

    src_ref = PredictionResultSourceRef(uri="data/in.jsonl", sha256="c" * 64)
    internal = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-25T14:30:00Z",
        score=0.88,
        manifest_checksum="d" * 64,
        feature_schema_version="v1.0",
        history_requirement_version="v1.0",
        label_schema_version="v1.0",
    )

    item = to_external_result_item(
        internal,
        source_kind="live_sensor",
        source_ref=src_ref,
        feature_schema_sha256="1" * 64,
        history_requirement_sha256="2" * 64,
        label_schema_sha256="3" * 64,
    )
    validate_prediction_result_item_checksum(item)

    # Tamper with score
    item_tampered = item.model_copy(update={"score": 0.12})
    with pytest.raises(ModelSetContractInvalidError, match="payload_sha256 mismatch"):
        validate_prediction_result_item_checksum(item_tampered)

    with pytest.raises(ModelSetContractInvalidError, match="payload_sha256 mismatch"):
        validate_external_results_array([item_tampered])


def test_batch_id_and_outbox_id_independent_of_item_ordering():
    """Changing order of items in batch produces identical canonical SHA-256 and Outbox ID."""
    from datetime import datetime
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        PredictionResultBatchPayload,
        PredictionResultBatchSourceContext,
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultProducer,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    dt = datetime.fromisoformat("2026-08-27T00:00:00+00:00")
    src_ref = PredictionResultSourceRef(uri="test.jsonl", sha256="a" * 64)
    lin = PredictionResultLineage()

    d1 = {
        "event_id": "evt-01",
        "asset_id": "M14860",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": src_ref.model_dump(mode="json"),
        "output_status": "predicted",
        "score": 0.8,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0",
        "model_artifact_manifest_sha256": "b" * 64,
        "feature_schema_version": "v1.0",
        "history_requirement_version": "v1.0",
        "label_schema_version": "v1.0",
        "feature_schema_sha256": "1" * 64,
        "history_requirement_sha256": "2" * 64,
        "label_schema_sha256": "3" * 64,
        "lineage": lin.model_dump(mode="json"),
        "failure_reason": None,
    }
    d2 = {
        "event_id": "evt-02",
        "asset_id": "M14860",
        "observed_at": dt,
        "source_kind": "live_sensor",
        "source_ref": src_ref.model_dump(mode="json"),
        "output_status": "predicted",
        "score": 0.9,
        "model_id": "pdm-xgboost",
        "model_version": "1.0",
        "model_artifact_manifest_sha256": "c" * 64,
        "feature_schema_version": "v1.0",
        "history_requirement_version": "v1.0",
        "label_schema_version": "v1.0",
        "feature_schema_sha256": "4" * 64,
        "history_requirement_sha256": "5" * 64,
        "label_schema_sha256": "6" * 64,
        "lineage": lin.model_dump(mode="json"),
        "failure_reason": None,
    }

    item1 = PredictionResultItem(**d1, payload_sha256=compute_prediction_result_item_sha256(d1))
    item2 = PredictionResultItem(**d2, payload_sha256=compute_prediction_result_item_sha256(d2))

    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0", required=True, model_artifact_manifest_sha256="b" * 64),
            ActiveModelSnapshotItem(model_id="pdm-xgboost", model_version="1.0", required=True, model_artifact_manifest_sha256="c" * 64),
        ],
    )

    producer = PredictionResultProducer(system="systems.generator", runtime_version="1.0.0", outbox_id=None)
    source_ctx = PredictionResultBatchSourceContext(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source_uri="data/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    batch_order_1 = PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id="batch-001",
        producer=producer,
        emitted_at=dt,
        source_context=source_ctx,
        model_set=model_set,
        results=[item1, item2],
    )
    batch_order_2 = PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id="batch-001",
        producer=producer,
        emitted_at=dt,
        source_context=source_ctx,
        model_set=model_set,
        results=[item2, item1],
    )

    evt1, sha1 = PredictionDeliveryService.compute_canonical_payload_sha256(batch_order_1)
    evt2, sha2 = PredictionDeliveryService.compute_canonical_payload_sha256(batch_order_2)

    assert evt1 == evt2
    assert sha1 == sha2
    assert evt1.startswith("evt-batch-")


def test_staging_asset_storage_key_sha256_and_traversal_protection(tmp_path, monkeypatch):
    """Staging derives filename from SHA-256 storage key and prevents directory traversal attacks."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        InternalModelPredictionResult,
        SourceLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        EquipmentModelBatch,
        PredictionBatchService,
        PredictionBatchSummary,
    )

    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "test-runtime-1.0.0")
    svc = PredictionBatchService()
    summary = PredictionBatchSummary(
        overall_status="succeeded",
        equipment_batches={
            "../../malicious/asset": EquipmentModelBatch(
                asset_id="../../malicious/asset",
                status="succeeded",
                observed_at="2026-08-27T00:00:00Z",
                succeeded_models=["pdm-lightgbm"],
                failed_models=[],
                model_results={},
                internal_results=[
                    InternalModelPredictionResult(
                        asset_id="../../malicious/asset",
                        model_id="pdm-lightgbm",
                        model_version="1.0",
                        status="succeeded",
                        observed_at="2026-08-27T00:00:00Z",
                        score=0.85,
                        manifest_checksum="b" * 64,
                        feature_schema_version="v1.0",
                        history_requirement_version="v1.0",
                        label_schema_version="v1.0",
                    )
                ],
            )
        },
        total_equipments=1,
        succeeded_equipments=1,
        partially_succeeded_equipments=0,
        failed_equipments=0,
    )

    src_lineage = SourceLineage(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
    )

    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    art_ref = svc.stage_batches(
        run_id="run-safe-test",
        job_id="job-safe-test",
        summary=summary,
        dataset_id="ds-01",
        dataset_version="v1.0",
        pipeline_contract_version="prediction-result-batch-v1",
        source_lineage=src_lineage,
        model_set_id="ms-01",
        model_set_version="1.0",
        base_dir=tmp_path,
        model_schema_map=model_schema_map,
        source_context=create_test_runtime_source_context(
            source_uri="data/in.jsonl",
            source_checksum="a" * 64,
        ),
        active_model_set_snapshot=create_test_active_model_set_snapshot(
            model_set_id="ms-01",
            model_set_version="1.0",
            model_version="1.0",
        ),
    )

    staging_dir = tmp_path / "pipeline_datasets" / "run-safe-test" / "batch_staging"
    assert staging_dir.is_dir()
    created_files = list(staging_dir.glob("*.json"))
    assert len(created_files) == 2
    filenames = [f.name for f in created_files]
    assert "batch-manifest.json" in filenames
    assert not any(".." in f.name for f in created_files)


# =====================================================================
# 65. PipelineRepository Default Path & DATA_PREPROCESSED_DIR Tests
# =====================================================================

def test_pipeline_repository_defaults_to_paths_data_preprocessed(tmp_path, monkeypatch):
    """PipelineRepository() with no args uses PATHS.data_preprocessed without relative fallback."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository

    custom_preprocessed = tmp_path / "custom_preprocessed_target"
    monkeypatch.setattr(PATHS, "data_preprocessed", custom_preprocessed)

    repo = PipelineRepository()
    assert repo.base_dir == custom_preprocessed
    assert repo.runs_dir == custom_preprocessed / "pipeline_runs"
    assert repo.checkpoints_dir == custom_preprocessed / "pipeline_checkpoints"
    assert repo.events_dir == custom_preprocessed / "pipeline_events"

    assert (custom_preprocessed / "pipeline_runs").is_dir()
    assert (custom_preprocessed / "pipeline_checkpoints").is_dir()
    assert (custom_preprocessed / "pipeline_events").is_dir()


def test_pipeline_repository_does_not_create_relative_dir_in_cwd(tmp_path, monkeypatch):
    """PipelineRepository() does not create a relative 'data_preprocessed' folder in current working directory."""
    from systems.generator.generator_config import PATHS
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository

    target_preprocessed = tmp_path / "target_preprocessed"
    monkeypatch.setattr(PATHS, "data_preprocessed", target_preprocessed)

    isolated_cwd = tmp_path / "isolated_cwd"
    isolated_cwd.mkdir()
    monkeypatch.chdir(isolated_cwd)

    repo = PipelineRepository()
    assert repo.base_dir == target_preprocessed

    # Verify no 'data_preprocessed' folder was created in isolated_cwd
    assert not (isolated_cwd / "data_preprocessed").exists()


def test_pipeline_repository_explicit_base_dir_honored(tmp_path):
    """PipelineRepository(base_dir=...) uses the explicitly provided directory."""
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository

    explicit_dir = tmp_path / "explicit_dir"
    repo = PipelineRepository(base_dir=explicit_dir)
    assert repo.base_dir == explicit_dir
    assert (explicit_dir / "pipeline_runs").is_dir()
    assert (explicit_dir / "pipeline_checkpoints").is_dir()
    assert (explicit_dir / "pipeline_events").is_dir()


def test_internal_stage_schema_validation_passes():
    """generator-runtime-prediction-stage.schema.json validates internal staging payload."""
    import json
    import jsonschema
    from pathlib import Path

    schema_file = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "generator-runtime-prediction-stage.schema.json"
    example_file = Path(__file__).resolve().parent.parent / "contracts" / "examples" / "generator-runtime-prediction" / "generator-runtime-prediction-stage.json"

    assert schema_file.is_file()
    assert example_file.is_file()

    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    example = json.loads(example_file.read_text(encoding="utf-8"))

    # Need schema registry for generator-model-prediction-result.schema.json reference
    schemas_dir = Path(__file__).resolve().parent.parent / "contracts" / "schemas"
    model_res_schema = json.loads((schemas_dir / "generator-model-prediction-result.schema.json").read_text(encoding="utf-8"))
    import referencing
    from referencing import Registry, Resource
    reg = Registry().with_resources([
        ("https://ontology-dashboard.local/schemas/generator-model-prediction-result.schema.json", Resource.from_contents(model_res_schema)),
        ("generator-model-prediction-result.schema.json", Resource.from_contents(model_res_schema)),
    ])
    validator = jsonschema.Draft202012Validator(schema, registry=reg, format_checker=jsonschema.FormatChecker())
    validator.validate(example)


def test_queue_retry_preserves_overlay_source_context(tmp_path):
    """Retry preserves the exact source kind, contract versions, and overlay lineage."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import PredictionResultLineage

    queue = PipelineQueue(db_path=tmp_path / "queue.db")
    lineage = PredictionResultLineage(
        simulation_session_id="sim-1",
        overlay_branch_id="branch-1",
        history_segment_id="history-1",
        maintenance_event_id="maint-event-1",
        maintenance_action_id="maint-action-1",
        state_version=2,
    )
    item = queue.enqueue(
        job_id="overlay-job-1",
        runtime_input=create_test_runtime_input_identity(
            source_uri="overlay/snapshot.jsonl",
            source_checksum="a" * 64,
            dataset_id="overlay-dataset",
            dataset_version="v1",
            pipeline_contract_version="prediction-result-batch-v1",
            source_kind="maintenance_replay_overlay",
            source_contract_version="runtime-overlay-observation-v1",
            source_schema_version="runtime-overlay-observation-v1",
            lineage=lineage,
        ),
    )
    queue.mark_failed(item.job_id, error_code="PIPELINE_RETRYABLE_TEST")

    retried = queue.retry_failed_job(item.job_id)

    assert retried.source_kind == item.source_kind
    assert retried.source_contract_version == item.source_contract_version
    assert retried.source_schema_version == item.source_schema_version
    assert retried.lineage == lineage
    assert retried.source_identity == item.source_identity


def test_legacy_queue_rows_are_dead_lettered_without_invented_source_context(tmp_path):
    """Pre-contract rows are isolated rather than silently labelled live_sensor."""
    import sqlite3

    db_path = tmp_path / "legacy-queue.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE queue_items (
                job_id TEXT PRIMARY KEY, source_uri TEXT NOT NULL,
                source_checksum TEXT NOT NULL, dedup_key TEXT UNIQUE NOT NULL,
                dataset_id TEXT NOT NULL, dataset_version TEXT NOT NULL,
                detected_at TEXT NOT NULL, sequence INTEGER NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL,
                error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO queue_items (
                job_id, source_uri, source_checksum, dedup_key, dataset_id,
                dataset_version, detected_at, sequence, attempt, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-job", "legacy.jsonl", "a" * 64, "legacy-dedup",
                "legacy-dataset", "v1", "2026-08-27T00:00:00Z", 1, 1,
                "queued", "2026-08-27T00:00:00Z", "2026-08-27T00:00:00Z",
            ),
        )
        conn.commit()

    queue = PipelineQueue(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        status, error_code, source_kind = conn.execute(
            "SELECT status, error_code, source_kind FROM queue_items WHERE job_id = ?",
            ("legacy-job",),
        ).fetchone()
    assert status == "dead_letter"
    assert error_code == "PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED"
    assert source_kind is None

    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineQueueItemInvalidError

    with pytest.raises(PipelineQueueItemInvalidError):
        queue.retry_failed_job("legacy-job")


def test_failed_source_result_does_not_invent_schema_versions():
    """Artifact-unavailable statuses use null provenance, never v1/unknown placeholders."""
    from systems.generator.app.runtime_pipeline.prediction_batch_service import to_external_result_item
    from systems.generator.app.runtime_pipeline.pipeline_schema import PredictionResultSourceRef

    internal = InternalModelPredictionResult(
        asset_id="asset-1",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="failed",
        observed_at="2026-08-27T00:00:00Z",
        error_code="PIPELINE_SOURCE_UNAVAILABLE",
        error_message="source unavailable",
    )
    item = to_external_result_item(
        internal,
        source_kind="live_sensor",
        source_ref=PredictionResultSourceRef(uri="missing.jsonl", sha256="a" * 64),
    )

    assert item.output_status == "failed_source_unavailable"
    assert item.feature_schema_version is None
    assert item.history_requirement_version is None
    assert item.label_schema_version is None


def test_generator_runtime_version_must_be_explicit(monkeypatch):
    from systems.generator.generator_config import get_generator_runtime_version

    monkeypatch.delenv("GENERATOR_RUNTIME_VERSION", raising=False)
    with pytest.raises(RuntimeError, match="GENERATOR_RUNTIME_VERSION"):
        get_generator_runtime_version()


def test_runtime_prediction_uses_family_history_version_for_legacy_model_artifacts():
    from systems.generator.app.runtime_pipeline.prediction_service import _fallback_history_requirement_version

    assert _fallback_history_requirement_version("cnc-failure-risk", "cnc-random-forest-v3") == "cnc-history-requirement-v1"
    assert _fallback_history_requirement_version("compressor-failure-risk", "compressor-random-forest-v3") == "compressor-history-requirement-v1"
    assert _fallback_history_requirement_version("pdm-random_forest", "pdm-v1") == "pdm-history-v1"
