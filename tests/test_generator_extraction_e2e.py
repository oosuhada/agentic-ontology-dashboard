"""End-to-End integration test suite from gen_data to Backend Inbox (Task 7)."""

from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

pytest.importorskip("lightgbm")

# Ensure systems/backend is resolvable for backend imports
_BACKEND_ROOT = str(Path(__file__).resolve().parents[1] / "systems" / "backend")
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from systems.generator.generator_config import PATHS, PROJECT_ROOT, get_generator_runtime_version
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.model.publisher import ModelArtifactPublisher
from systems.generator.app.runtime_pipeline.active_model_set_service import ActiveModelSetService
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ActiveModelConfig,
    ActiveModelSet,
    PredictionResultBatchPayload,
    PredictionResultLineage,
    now_utc_iso,
)
from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
from systems.generator.app.runtime_pipeline.pipeline_worker import PipelineWorker
from systems.generator.app.runtime_pipeline.pipeline_service import PipelineService
from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository
from systems.generator.app.runtime_pipeline.pipeline_manager import PipelineManager
from systems.generator.app.runtime_pipeline.prediction_delivery_service import PredictionDeliveryService
from systems.generator.app.runtime_pipeline.prediction_delivery_worker import PredictionDeliveryWorker
from systems.generator.app.extraction.extraction_manager import ExtractionManager
from systems.generator.app.extraction.extraction_worker import ExtractionWorker
from systems.generator.app.extraction.extraction_handoff_worker import ExtractionHandoffWorker
from systems.generator.app.extraction.extraction_runtime_handoff_service import ExtractionRuntimeHandoffService
from systems.generator.app.extraction.extraction_handoff_repository import ExtractionHandoffRepository
from systems.generator.app.extraction.mapping_validator import compute_mapping_canonical_sha256

from app.diagnosis.runtime_router import internal_router
from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService
from app.dependencies import get_identity_service, get_predictive_maintenance_runtime_service
from app.identity import AuthError, Principal
from app.identity.identity_router import identity_http_status


class MockEstimator:
    """Mock ML model implementing predict_proba for controlled testing."""

    def __init__(self, anomaly_prob: float = 0.15) -> None:
        self.anomaly_prob = anomaly_prob

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        n = len(X)
        probs = np.zeros((n, 2))
        for i in range(n):
            probs[i, 0] = 1.0 - self.anomaly_prob
            probs[i, 1] = self.anomaly_prob
        return probs

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


class FakeBackendInboxRepository:
    """In-memory backend repository for Inbox tests."""

    def __init__(self, *, assets: Optional[set[str]] = None) -> None:
        self.assets = assets or {"CNC-01", "CNC-001"}
        self.batches: dict[str, str] = {}
        self.items: dict[str, str] = {}
        self.saved: list[dict[str, Any]] = []
        self.promotions: list[dict[str, Any]] = []

    def clock_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def assets_exist_in_workspace(self, **kwargs: Any) -> set[str]:
        asset_ids = set(kwargs.get("asset_ids", []))
        return asset_ids & self.assets

    def save_prediction_batch_inbox(self, **kwargs: Any) -> dict[str, Any]:
        batch_id = kwargs["batch_id"]
        payload_sha256 = kwargs["payload_sha256"]
        status = kwargs["validation_status"]
        reason = kwargs["rejection_reason"]

        if batch_id in self.batches:
            if self.batches[batch_id] == payload_sha256:
                status = "duplicate"
                reason = None
            else:
                status = "conflict"
                reason = "batch_payload_conflict"

        persisted = []
        for receipt in kwargs["item_receipts"]:
            event_id = receipt["event_id"]
            item_sha = receipt["payload_sha256"]
            item_status = receipt["validation_status"]
            item_reason = receipt["rejection_reason"]
            if event_id in self.items:
                if self.items[event_id] == item_sha:
                    item_status = "duplicate"
                    item_reason = None
                else:
                    item_status = "conflict"
                    item_reason = "event_payload_conflict"
            else:
                self.items[event_id] = item_sha
            persisted.append({
                "event_id": event_id,
                "payload_sha256": item_sha,
                "validation_status": item_status,
                "rejection_reason": item_reason,
            })

        if any(item["validation_status"] == "conflict" for item in persisted):
            status = "conflict"
            reason = reason or "one or more items conflicted"
        elif any(item["validation_status"] == "rejected" for item in persisted):
            status = "rejected"
            reason = reason or "one or more items were rejected"
        elif persisted and all(item["validation_status"] == "duplicate" for item in persisted):
            status = "duplicate"
            reason = None

        self.batches.setdefault(batch_id, payload_sha256)
        row = {
            "batch_id": batch_id,
            "payload_sha256": payload_sha256,
            "validation_status": status,
            "rejection_reason": reason,
            "raw_payload": kwargs["raw_payload"],
            "item_receipts": persisted,
        }
        self.saved.append(row)
        return row

    def prediction_batch_promotion_context(self, **kwargs: Any) -> dict[str, Any] | None:
        batch_id = kwargs["batch_id"]
        row = next(
            (
                item
                for item in reversed(self.saved)
                if item["batch_id"] == batch_id and item["validation_status"] == "accepted"
            ),
            None,
        )
        if row is None:
            return None
        return {
            "dataset_version_id": "e2e-dataset-version",
            "raw_payload": row["raw_payload"],
            "assets": {
                asset_id: {
                    "asset_id": asset_id,
                    "asset_type": "cnc",
                    "site_id": "S01",
                    "cell_id": "L01",
                    "criticality": "medium",
                }
                for asset_id in self.assets
            },
        }

    def save_prediction_batch_promotions(self, **kwargs: Any) -> dict[str, Any]:
        receipts = []
        for promotion in kwargs["promotions"]:
            existing = next(
                (
                    item
                    for item in self.promotions
                    if item["artifact"]["artifact_id"] == promotion["artifact"]["artifact_id"]
                ),
                None,
            )
            if existing is None:
                self.promotions.append(promotion)
                receipts.append(
                    {
                        "event_id": promotion["event_id"],
                        "promotion_status": "promoted",
                        "product_result_id": promotion["prediction_result_id"],
                        "artifact_id": promotion["artifact"]["artifact_id"],
                        "reason": None,
                    }
                )
            else:
                receipts.append(
                    {
                        "event_id": promotion["event_id"],
                        "promotion_status": "already_promoted",
                        "product_result_id": existing["prediction_result_id"],
                        "artifact_id": existing["artifact"]["artifact_id"],
                        "reason": None,
                    }
                )
        return {"item_receipts": receipts}


@pytest.fixture
def e2e_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sets up an isolated environment with Model Artifacts, Active Model Set, DBs, and paths."""
    PipelineManager.set_instance(None)
    ExtractionManager.set_instance(None)

    data_dir = tmp_path / "data"
    gen_data_dir = data_dir / "gen_data"
    sensor_dir = gen_data_dir / "sensor" / "facS01" / "lineL01"
    sensor_dir.mkdir(parents=True, exist_ok=True)

    observations_dir = data_dir / "observations"
    observations_dir.mkdir(parents=True, exist_ok=True)

    preprocessed_dir = tmp_path / "data_preprocessed"
    preprocessed_dir.mkdir(parents=True, exist_ok=True)

    e2e_queue_db = preprocessed_dir / "e2e" / "pipeline_queue" / "queue.db"
    e2e_queue_db.parent.mkdir(parents=True, exist_ok=True)

    handoffs_root = preprocessed_dir / "extraction_handoffs"
    handoffs_root.mkdir(parents=True, exist_ok=True)

    models_store = tmp_path / "models_store"
    artifacts_dir = models_store / "artifacts"
    features_cache_dir = models_store / "cache" / "runtime_features"
    outbox_dir = preprocessed_dir / "prediction_outbox"

    for d in [models_store, artifacts_dir, features_cache_dir, outbox_dir]:
        d.mkdir(parents=True, exist_ok=True)

    ontology_dir = tmp_path / "ontology"
    mappings_dir = ontology_dir / "mappings"
    mappings_dir.mkdir(parents=True, exist_ok=True)

    # Environment variables
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    monkeypatch.setenv("GENERATOR_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("GENERATOR_EXTRACTION_RUNTIME_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("GENERATOR_RUNTIME_PREDICTION_ENABLED", "true")
    monkeypatch.setenv("GENERATOR_PREDICTION_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_URL", "http://backend:8000/internal/prediction-results")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_PROJECT_ID", "manufacturing-demo-project")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_WORKSPACE_ID", "manufacturing-demo")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_TOKEN", "e2e-secret-token")
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "e2e-secret-token")
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_ORGANIZATION_ID", "org-ontology-demo")

    # Monkeypatch PATHS
    monkeypatch.setattr(PATHS, "data_dir", data_dir)
    monkeypatch.setattr(PATHS, "data_preprocessed", preprocessed_dir)
    monkeypatch.setattr(PATHS, "models_store", models_store)
    monkeypatch.setattr(PATHS, "ontology", ontology_dir)
    monkeypatch.setattr(PATHS, "gen_data_output_dir", gen_data_dir)
    monkeypatch.setattr(PATHS, "gen_data_sensor_root", gen_data_dir / "sensor")
    monkeypatch.setattr(PATHS, "observations_root", observations_dir)
    monkeypatch.setattr(PATHS, "extraction_runs_root", preprocessed_dir / "extraction_runs")
    monkeypatch.setattr(PATHS, "extraction_state_root", preprocessed_dir / "extraction_state")
    monkeypatch.setattr(PATHS, "mapping_root", mappings_dir)
    monkeypatch.setattr(PATHS, "extraction_handoffs_root", handoffs_root)
    monkeypatch.setattr(PATHS, "pipeline_queue_db", e2e_queue_db)
    monkeypatch.setattr(PATHS, "pipeline_state_root", preprocessed_dir / "pipeline_runs")
    monkeypatch.setattr(PATHS, "runtime_feature_root", features_cache_dir)
    monkeypatch.setattr(PATHS, "notification_outbox_root", outbox_dir)
    monkeypatch.setattr(PATHS, "pipeline_input_roots", [data_dir, preprocessed_dir, tmp_path, PROJECT_ROOT / "contracts"])
    monkeypatch.setattr(PATHS, "extraction_input_roots", [data_dir, preprocessed_dir, tmp_path, PROJECT_ROOT / "contracts"])
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)
    monkeypatch.setattr(PATHS, "extraction_enabled", True)
    monkeypatch.setattr(PATHS, "extraction_runtime_handoff_enabled", True)

    # 1. Publish standard Model Artifact
    publisher = ModelArtifactPublisher(artifacts_dir)
    feature_schema = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-feature-schema.schema.json",
        "schema_version": "1.0",
        "features": [
            {
                "feature_name": "feat_air_temp",
                "source_field": "air_temperature_k",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            },
            {
                "feature_name": "feat_rot_speed",
                "source_field": "rotational_speed_rpm",
                "operation": "raw",
                "parameters": {},
                "missing_value_policy": "drop",
            },
            {
                "feature_name": "feat_torque",
                "source_field": "torque_nm",
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
            "air_temperature_k",
            "rotational_speed_rpm",
            "torque_nm",
        ],
        "missing_history_policy": "reject",
    }
    metrics = {
        "metrics_summary": {"f1": 0.90, "precision": 0.92, "recall": 0.88, "accuracy": 0.99},
        "primary_metric": "f1",
    }

    dummy_model = MockEstimator(anomaly_prob=0.15)
    pub_res = publisher.publish_artifact(
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        base_model="lightgbm",
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
    published_manifest_path = artifacts_dir / "pdm-lightgbm" / "1.0.0" / "manifest.json"
    published_model_sha256 = compute_file_sha256(published_manifest_path)

    # 2. Register Active Model Set
    active_service = ActiveModelSetService(models_store_dir=models_store)
    active_set = ActiveModelSet(
        model_set_id="pdm-e2e-set",
        model_set_version="1.0.0",
        updated_at=now_utc_iso(),
        models={
            "lightgbm": ActiveModelConfig(model_version="1.0.0", required=True),
        },
    )
    active_service.update_active_model_set(active_set, validate_artifacts=False)

    # 3. Create Approved Static Mapping JSON
    mapping_obj = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-static-mapping-table.schema.json",
        "mapping_id": "gen-data-sensor-stream-canonical",
        "mapping_version": "v1",
        "status": "approved",
        "source_format": "gen_data_sensor_stream",
        "protocol_version": "v2",
        "source_schema_version": "sensor-record-v2",
        "source_schema_fingerprint": "0" * 64,
        "fingerprint_algorithm_version": "v1",
        "description": "E2E Static Mapping for gen_data stream",
        "field_mappings": [
            {
                "source_field": "temp_k",
                "target_field": "air_temperature_k",
                "source_type": "float",
                "target_type": "float",
                "required": True,
                "transform": "to_float",
            },
            {
                "source_field": "rpm",
                "target_field": "rotational_speed_rpm",
                "source_type": "float",
                "target_type": "float",
                "required": True,
                "transform": "to_float",
            },
            {
                "source_field": "torque",
                "target_field": "torque_nm",
                "source_type": "float",
                "target_type": "float",
                "required": True,
                "transform": "to_float",
            },
        ],
    }
    mapping_obj["mapping_sha256"] = compute_mapping_canonical_sha256(mapping_obj)
    mapping_file = mappings_dir / "gen-data-sensor-stream-canonical_v1.json"
    mapping_file.write_text(json.dumps(mapping_obj, indent=2), encoding="utf-8")

    monkeypatch.setattr(PATHS, "extraction_mapping_id", "gen-data-sensor-stream-canonical")
    monkeypatch.setattr(PATHS, "extraction_mapping_version", "v1")
    monkeypatch.setattr(PATHS, "extraction_mapping_sha256", mapping_obj["mapping_sha256"])

    # 4. Create Backend Test App and Backend Service
    backend_repo = FakeBackendInboxRepository(assets={"CNC-01"})
    backend_service = PredictiveMaintenanceRuntimeService(backend_repo)

    app = FastAPI()
    app.include_router(internal_router)

    @app.exception_handler(AuthError)
    async def auth_error_handler(_, exc: AuthError):
        return JSONResponse(
            status_code=identity_http_status(exc),
            content={"detail": exc.message},
        )

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: backend_service
    test_client = TestClient(app)

    # 5. Wire urllib.request to TestClient for single-dispatch delivery
    def mock_urlopen(req: urllib.request.Request, timeout: float = 10.0):
        url = req.full_url
        headers = dict(req.headers)
        data = req.data
        parsed_url = urllib.parse.urlsplit(url)
        path = parsed_url.path
        if parsed_url.query:
            path += f"?{parsed_url.query}"

        json_body = json.loads(data.decode("utf-8")) if data else None
        client_res = test_client.post(path, json=json_body, headers=headers)

        class MockHTTPResponse:
            def __init__(self, res):
                self._res = res
                self.status = res.status_code

            def getcode(self) -> int:
                return self._res.status_code

            def read(self) -> bytes:
                return self._res.content

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        if client_res.status_code >= 400:
            fp = io.BytesIO(client_res.content)
            raise urllib.error.HTTPError(
                url=url,
                code=client_res.status_code,
                msg=client_res.text,
                hdrs=client_res.headers,
                fp=fp,
            )
        return MockHTTPResponse(client_res)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    yield {
        "tmp_path": tmp_path,
        "sensor_dir": sensor_dir,
        "data_dir": data_dir,
        "preprocessed_dir": preprocessed_dir,
        "e2e_queue_db": e2e_queue_db,
        "handoffs_root": handoffs_root,
        "models_store": models_store,
        "outbox_dir": outbox_dir,
        "backend_repo": backend_repo,
        "backend_service": backend_service,
        "test_client": test_client,
        "published_model_sha256": published_model_sha256,
    }

    PipelineManager.set_instance(None)
    ExtractionManager.set_instance(None)


def test_e2e_gen_data_to_backend_inbox_full_pipeline(e2e_environment) -> None:
    """Validate complete 7-stage automated pipeline from gen_data to Backend Inbox."""
    env = e2e_environment
    sensor_dir = env["sensor_dir"]
    stream_file = sensor_dir / "sensor_stream.jsonl"

    # Stage 0: Create real gen_data JSONL records (4 rows for CNC-01 in 13:00 window, plus 1 in 14:00 to close window)
    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "temp_k": 300.1, "rpm": 1500.0, "torque": 40.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:01:00Z", "temp_k": 300.2, "rpm": 1505.0, "torque": 40.5},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:02:00Z", "temp_k": 300.3, "rpm": 1510.0, "torque": 41.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "temp_k": 300.4, "rpm": 1515.0, "torque": 41.5},
    ]
    stream_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # Stage 1: Extraction Worker polls and publishes Canonical Observation Dataset
    extraction_manager = ExtractionManager()
    extraction_worker = ExtractionWorker(manager=extraction_manager)
    asyncio.run(extraction_worker.run_single_cycle())

    status = extraction_manager.get_status()
    assert status.discovered_source_count == 1
    assert len(status.sources) == 1
    assert status.sources[0].status == "waiting"

    # Verify published observation dataset manifest and observations
    obs_root = PATHS.observations_root
    dataset_dirs = list(obs_root.rglob("dataset_manifest.json"))
    assert len(dataset_dirs) >= 1
    manifest_path = dataset_dirs[0]
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["manifest_version"] == "generator-dataset-input-v1"
    assert manifest_data["schema_version"] == "canonical-observation-v1"

    obs_file = manifest_path.parent / manifest_data["files"][0]["path"]
    obs_lines = [l for l in obs_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(obs_lines) == 3

    dataset_id = manifest_data["dataset_id"]
    dataset_version = manifest_data["dataset_version"]
    obs_checksum = compute_file_sha256(obs_file)

    # Stage 2: Runtime Handoff Worker automatically delivers to PipelineQueue
    queue = PipelineQueue(db_path=env["e2e_queue_db"])
    q_items = queue.list_items(status="queued")
    assert len(q_items) == 1
    q_item = q_items[0]
    assert q_item.source_kind == "live_sensor"
    assert q_item.source_contract_version == "generator-dataset-input-v1"
    assert q_item.source_schema_version == "canonical-observation-v1"
    assert q_item.pipeline_contract_version == "generator-prediction-result-v1"
    assert q_item.dataset_id == dataset_id
    assert q_item.dataset_version == dataset_version
    assert q_item.source_checksum == obs_checksum
    assert isinstance(q_item.lineage, PredictionResultLineage)

    # Stage 3: Pipeline Worker executes preprocessing, feature extraction, inference, batching, outbox
    pipeline_service = PipelineService(
        repository=PipelineRepository(base_dir=env["preprocessed_dir"]),
    )
    pipeline_worker = PipelineWorker(
        queue=queue,
        service=pipeline_service,
    )
    run_state = pipeline_worker.process_one()

    assert run_state is not None
    assert run_state.status == "succeeded"
    assert len(run_state.prediction_results) == 1
    pred_res = run_state.prediction_results[0]
    assert pred_res.asset_id == "CNC-01"
    assert pred_res.status == "succeeded"
    assert pred_res.score == 0.15
    assert pred_res.score_type == "positive_class_probability"
    assert pred_res.score_source == "predict_proba"

    # Stage 4: Outbox item persisted and pending delivery
    delivery_service = PredictionDeliveryService(outbox_dir=env["outbox_dir"])
    outbox_items = delivery_service.list_outbox_items(status="pending")
    assert len(outbox_items) == 1
    outbox_item = outbox_items[0]
    assert outbox_item.status == "pending"
    assert outbox_item.asset_id == "CNC-01"

    batch_payload = outbox_item.payload
    assert isinstance(batch_payload, PredictionResultBatchPayload)
    assert batch_payload.contract_version == "prediction-result-batch-v1"
    assert batch_payload.source_context.source_kind == "live_sensor"
    assert batch_payload.source_context.source_contract_version == "generator-dataset-input-v1"
    assert batch_payload.source_context.source_schema_version == "canonical-observation-v1"
    assert batch_payload.source_context.pipeline_contract_version == "generator-prediction-result-v1"
    assert batch_payload.source_context.dataset_id == dataset_id
    assert batch_payload.source_context.dataset_version == dataset_version
    assert batch_payload.source_context.source_checksum == obs_checksum

    # Stage 5: Prediction Delivery Worker dispatches batch to Backend Inbox
    delivery_worker = PredictionDeliveryWorker(service=delivery_service)
    d_count = delivery_worker.process_pending()
    assert d_count == 1

    # Verify Outbox item transitioned to 'sent'
    sent_items = delivery_service.list_outbox_items(status="sent")
    assert len(sent_items) == 1
    assert sent_items[0].event_id == outbox_item.event_id

    # Stage 6: Backend Prediction Inbox verification
    backend_repo: FakeBackendInboxRepository = env["backend_repo"]
    assert len(backend_repo.saved) == 1
    saved_batch = backend_repo.saved[0]
    assert saved_batch["batch_id"] == batch_payload.batch_id
    assert saved_batch["validation_status"] == "accepted"
    assert len(saved_batch["item_receipts"]) == 1
    item_receipt = saved_batch["item_receipts"][0]
    assert item_receipt["event_id"] == batch_payload.results[0].event_id
    assert item_receipt["validation_status"] == "accepted"


def test_e2e_backend_inbox_idempotency_duplicate_delivery(e2e_environment) -> None:
    """Validate idempotency when re-delivering identical batch payload or re-running extraction."""
    env = e2e_environment
    sensor_dir = env["sensor_dir"]
    stream_file = sensor_dir / "sensor_stream.jsonl"

    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "temp_k": 300.1, "rpm": 1500.0, "torque": 40.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:01:00Z", "temp_k": 300.2, "rpm": 1505.0, "torque": 40.5},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "temp_k": 300.3, "rpm": 1510.0, "torque": 41.0},
    ]
    stream_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # Run extraction, pipeline, delivery
    mgr = ExtractionManager()
    asyncio.run(ExtractionWorker(manager=mgr).run_single_cycle())

    queue = PipelineQueue(db_path=env["e2e_queue_db"])
    PipelineWorker(
        queue=queue,
        service=PipelineService(
            repository=PipelineRepository(base_dir=env["preprocessed_dir"]),
        ),
    ).process_one()

    delivery_service = PredictionDeliveryService(outbox_dir=env["outbox_dir"])
    delivery_worker = PredictionDeliveryWorker(service=delivery_service)
    delivery_worker.process_pending()

    backend_repo: FakeBackendInboxRepository = env["backend_repo"]
    assert len(backend_repo.saved) == 1
    assert backend_repo.saved[0]["validation_status"] == "accepted"

    # 1. Re-deliver the same batch payload via TestClient directly to Backend
    outbox_item = delivery_service.list_outbox_items(status="sent")[0]
    batch_dict = outbox_item.payload.model_dump(mode="json")
    client: TestClient = env["test_client"]

    response = client.post(
        "/internal/prediction-results?project_id=manufacturing-demo-project&workspace_id=manufacturing-demo",
        json=batch_dict,
        headers={"Authorization": "Bearer e2e-secret-token"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["validation_status"] == "duplicate"
    assert res_data["duplicate_results"] == 1

    # 2. Re-running Extraction on unchanged source produces 0 new datasets/queue items
    q_len_before = len(queue.list_items())
    asyncio.run(ExtractionWorker(manager=mgr).run_single_cycle())
    q_len_after = len(queue.list_items())
    assert q_len_after == q_len_before


def test_e2e_pipeline_identifiers_and_source_context_invariants(e2e_environment) -> None:
    """Verify that all 15 key identifiers and contract fields remain unchanged across all stages."""
    env = e2e_environment
    sensor_dir = env["sensor_dir"]
    stream_file = sensor_dir / "sensor_stream.jsonl"

    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "temp_k": 300.1, "rpm": 1500.0, "torque": 40.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:01:00Z", "temp_k": 300.2, "rpm": 1505.0, "torque": 40.5},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "temp_k": 300.3, "rpm": 1510.0, "torque": 41.0},
    ]
    stream_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # Run stages
    mgr = ExtractionManager()
    asyncio.run(ExtractionWorker(manager=mgr).run_single_cycle())

    queue = PipelineQueue(db_path=env["e2e_queue_db"])
    PipelineWorker(
        queue=queue,
        service=PipelineService(
            repository=PipelineRepository(base_dir=env["preprocessed_dir"]),
        ),
    ).process_one()

    delivery_service = PredictionDeliveryService(outbox_dir=env["outbox_dir"])
    PredictionDeliveryWorker(service=delivery_service).process_pending()

    # Retrieve all artifacts across pipeline
    manifest_path = list(PATHS.observations_root.rglob("dataset_manifest.json"))[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    obs_file = manifest_path.parent / manifest["files"][0]["path"]
    obs_sha = compute_file_sha256(obs_file)

    handoff_record = ExtractionHandoffRepository(env["handoffs_root"]).list_handoffs()[0]
    queue_item = queue.list_items()[0]
    outbox_item = delivery_service.list_outbox_items(status="sent")[0]
    batch = outbox_item.payload
    result_item = batch.results[0]
    backend_batch = env["backend_repo"].saved[0]

    # Invariant 1: dataset_id
    assert manifest["dataset_id"] == handoff_record.dataset.dataset_id == queue_item.dataset_id == batch.source_context.dataset_id

    # Invariant 2: dataset_version
    assert manifest["dataset_version"] == handoff_record.dataset.dataset_version == queue_item.dataset_version == batch.source_context.dataset_version

    # Invariant 3: source_uri
    assert handoff_record.runtime_input.source.source_uri == queue_item.source_uri == batch.source_context.source_uri

    # Invariant 4: source_checksum
    assert obs_sha == handoff_record.runtime_input.source.source_checksum == queue_item.source_checksum == batch.source_context.source_checksum

    # Invariant 5: source_kind
    assert handoff_record.runtime_input.source.source_kind == queue_item.source_kind == batch.source_context.source_kind == "live_sensor"

    # Invariant 6: source_contract_version
    assert manifest["manifest_version"] == handoff_record.runtime_input.source.source_contract_version == queue_item.source_contract_version == batch.source_context.source_contract_version == "generator-dataset-input-v1"

    # Invariant 7: source_schema_version
    assert manifest["schema_version"] == handoff_record.runtime_input.source.source_schema_version == queue_item.source_schema_version == batch.source_context.source_schema_version == "canonical-observation-v1"

    # Invariant 8: pipeline_contract_version
    assert handoff_record.runtime_input.source.pipeline_contract_version == queue_item.pipeline_contract_version == batch.source_context.pipeline_contract_version == "generator-prediction-result-v1"

    # Invariant 9: asset_id
    assert result_item.asset_id == "CNC-01"

    # Invariant 10: observed_at
    assert result_item.observed_at is not None

    # Invariant 11: model_id
    assert result_item.model_id == "pdm-lightgbm"

    # Invariant 12: model_version
    assert result_item.model_version == "1.0.0"

    # Invariant 13: model_artifact_manifest_sha256
    assert result_item.model_artifact_manifest_sha256 == env["published_model_sha256"]

    # Invariant 14: event_id
    assert result_item.event_id == backend_batch["item_receipts"][0]["event_id"]

    # Invariant 15: batch_id
    assert batch.batch_id == backend_batch["batch_id"]


def test_e2e_generator_and_delivery_restart_recovery(e2e_environment) -> None:
    """Validate crash and startup recovery for both PipelineQueue and PredictionDeliveryWorker."""
    env = e2e_environment
    queue = PipelineQueue(db_path=env["e2e_queue_db"])

    # 1. PipelineQueue restart recovery
    from systems.generator.app.runtime_pipeline.pipeline_schema import RuntimeInputIdentity, RuntimeSourceContext
    runtime_input = RuntimeInputIdentity(
        dataset_id="ds-crash-01",
        dataset_version="v1",
        source=RuntimeSourceContext(
            source_uri="data/observations/ds-crash-01/v1/dataset_manifest.json",
            source_checksum="a" * 64,
            source_kind="live_sensor",
            source_contract_version="generator-dataset-input-v1",
            source_schema_version="canonical-observation-v1",
            pipeline_contract_version="generator-prediction-result-v1",
        ),
    )
    item = queue.enqueue(job_id="job-crash-test", runtime_input=runtime_input)
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed.job_id == item.job_id
    assert queue.get_item(item.job_id).status == "running"

    # Simulate process restart
    recovered_count = queue.recover_running_on_startup()
    assert recovered_count == 1
    assert queue.get_item(item.job_id).status == "queued"

    # 2. PredictionDeliveryWorker restart recovery
    delivery_service = PredictionDeliveryService(outbox_dir=env["outbox_dir"])
    delivery_worker = PredictionDeliveryWorker(service=delivery_service)

    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        PredictionOutboxItem,
        PredictionResultBatchSourceContext,
        PredictionResultItem,
        PredictionResultLineage,
        PredictionResultProducer,
        PredictionResultSourceRef,
        compute_prediction_result_item_sha256,
    )
    dt_obs = datetime(2026, 8, 28, 13, 0, 0, tzinfo=timezone.utc)
    raw_item = {
        "event_id": "evt-restart-01",
        "asset_id": "CNC-01",
        "observed_at": dt_obs,
        "source_kind": "live_sensor",
        "output_status": "predicted",
        "score": 0.2,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": "2" * 64,
        "feature_schema_version": "1.0",
        "history_requirement_version": "1.0",
        "label_schema_version": "1.0",
        "feature_schema_sha256": "3" * 64,
        "history_requirement_sha256": "4" * 64,
        "label_schema_sha256": "5" * 64,
        "failure_reason": None,
    }
    item_sha = compute_prediction_result_item_sha256(raw_item)
    pred_item = PredictionResultItem(
        **raw_item,
        payload_sha256=item_sha,
        source_ref=PredictionResultSourceRef(uri="data/observations/obs.jsonl", sha256="1" * 64),
        lineage=PredictionResultLineage(),
    )
    dummy_payload = PredictionResultBatchPayload(
        contract_version="prediction-result-batch-v1",
        batch_id="batch-restart-01",
        emitted_at=now_utc_iso(),
        producer=PredictionResultProducer(system="systems.generator", runtime_version="1.0.0"),
        source_context=PredictionResultBatchSourceContext(
            dataset_id="ds-restart-01",
            dataset_version="v1",
            source_uri="data/observations/obs.jsonl",
            source_checksum="1" * 64,
            source_kind="live_sensor",
            source_contract_version="generator-dataset-input-v1",
            source_schema_version="canonical-observation-v1",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
        ),
        model_set=ActiveModelSetSnapshot(
            model_set_id="pdm-e2e-set",
            model_set_version="1.0.0",
            models=[ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0.0", required=True, model_artifact_manifest_sha256="2" * 64)],
        ),
        results=[pred_item],
    )

    outbox_item, _ = delivery_service.register_idempotent_outbox_record(dummy_payload, run_id="run-restart-01")
    o_item = delivery_service.get_outbox_item(outbox_item.event_id)
    o_item.status = "sending"
    o_item.attempt = 1
    delivery_service.save_outbox_item(o_item)
    assert delivery_service.get_outbox_item(outbox_item.event_id).status == "sending"

    # Simulate worker process startup recovery
    recovered_outbox = delivery_worker.recover_interrupted_items()
    assert recovered_outbox == 1
    assert delivery_service.get_outbox_item(outbox_item.event_id).status == "retry_wait"


def test_e2e_model_artifact_and_history_requirement_validation(e2e_environment) -> None:
    """Validate that model artifacts and history requirements are strictly validated and handled."""
    env = e2e_environment
    sensor_dir = env["sensor_dir"]
    stream_file = sensor_dir / "sensor_stream.jsonl"

    # Write only 1 record for CNC-01 in 13:00 (when minimum_history_rows is 2), plus 14:05 to close window
    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "temp_k": 300.1, "rpm": 1500.0, "torque": 40.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "temp_k": 300.4, "rpm": 1515.0, "torque": 41.5},
    ]
    stream_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # Run extraction, handoff, pipeline
    mgr = ExtractionManager()
    asyncio.run(ExtractionWorker(manager=mgr).run_single_cycle())

    queue = PipelineQueue(db_path=env["e2e_queue_db"])
    run_state = PipelineWorker(
        queue=queue,
        service=PipelineService(
            repository=PipelineRepository(base_dir=env["preprocessed_dir"]),
        ),
    ).process_one()

    # The run finishes with failure due to insufficient history rows
    assert run_state is None
    q_items = queue.list_items()
    assert len(q_items) == 1
    failed_item = q_items[0]
    assert failed_item.status in ("failed", "dead_letter")
    assert failed_item.error_code == "PIPELINE_HISTORY_INSUFFICIENT"
