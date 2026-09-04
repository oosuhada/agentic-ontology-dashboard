"""Comprehensive test suite for Generator Training Domain API, Model Artifact Publishing, and Contracts."""

from __future__ import annotations

import inspect
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from systems.generator.app.main import create_app
from systems.generator.app.training.training_router import post_train, post_train_single
from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.model.publisher import (
    ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_TYPE,
    REQUIRED_ARTIFACT_ROLES,
    ModelArtifactPublisher,
)


def _create_versioned_obs_and_fail_datasets(
    data_root: Path,
    dataset_id: str,
    dataset_version: str,
    failure_id: str,
    failure_version: str,
    n_rows: int = 100,
    include_failure_events: bool = True,
) -> tuple[Path, Path]:
    """Helper creating valid versioned Observation and Failure datasets with manifests."""
    np.random.seed(42)

    # 1. Observation dataset
    obs_dir = data_root / "observations" / dataset_id / dataset_version
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs_file = obs_dir / "observations.csv"

    base_time = pd.Timestamp("2026-08-20T00:00:00Z")
    timestamps = [base_time + pd.Timedelta(hours=i) for i in range(n_rows)]
    assets = [f"asset-{(i % 2) + 1}" for i in range(n_rows)]

    obs_df = pd.DataFrame({
        "timestamp": [ts.isoformat() for ts in timestamps],
        "asset_id": assets,
        "Air temperature [K]": np.random.normal(300, 2, n_rows),
        "Process temperature [K]": np.random.normal(310, 2, n_rows),
        "Rotational speed [rpm]": np.random.normal(1500, 50, n_rows),
        "Torque [Nm]": np.random.normal(40, 5, n_rows),
        "Tool wear [min]": np.linspace(0, 200, n_rows),
    })
    obs_df.to_csv(obs_file, index=False)

    # Also create unversioned CSV for preprocessing plan discovery
    prep_file = data_root / f"{dataset_id}.csv"
    obs_df.to_csv(prep_file, index=False)

    obs_sha = compute_file_sha256(obs_file)
    obs_size = obs_file.stat().st_size

    obs_manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "schema_version": "ai4i-physics-v3.1",
        "created_at": "2026-08-24T00:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "observations.csv",
                "media_type": "text/csv",
                "sha256": obs_sha,
                "size_bytes": obs_size,
            }
        ],
    }
    with open(obs_dir / "dataset_manifest.json", "w", encoding="utf-8") as f:
        json.dump(obs_manifest, f, indent=2)

    # 2. Failure dataset
    fail_dir = data_root / "failures" / failure_id / failure_version
    fail_dir.mkdir(parents=True, exist_ok=True)
    fail_file = fail_dir / "failures.csv"

    if include_failure_events:
        fail_df = pd.DataFrame({
            "asset_id": ["asset-1", "asset-2"],
            "failure_point": [
                (base_time + pd.Timedelta(hours=40)).isoformat(),
                (base_time + pd.Timedelta(hours=85)).isoformat(),
            ],
            "period_end": [
                (base_time + pd.Timedelta(hours=44)).isoformat(),
                (base_time + pd.Timedelta(hours=89)).isoformat(),
            ],
            "failure_indicator": [1, 1],
        })
    else:
        fail_df = pd.DataFrame(columns=["asset_id", "failure_point", "period_end", "failure_indicator"])

    fail_df.to_csv(fail_file, index=False)
    fail_sha = compute_file_sha256(fail_file)
    fail_size = fail_file.stat().st_size

    fail_manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "failure",
        "dataset_id": failure_id,
        "dataset_version": failure_version,
        "schema_version": "ai4i-failures-v1",
        "created_at": "2026-08-24T00:00:00Z",
        "files": [
            {
                "role": "failures",
                "path": "failures.csv",
                "media_type": "text/csv",
                "sha256": fail_sha,
                "size_bytes": fail_size,
            }
        ],
    }
    with open(fail_dir / "dataset_manifest.json", "w", encoding="utf-8") as f:
        json.dump(fail_manifest, f, indent=2)

    return obs_dir, fail_dir


@pytest.fixture
def test_setup():
    """Create versioned observation/failure datasets, plan, and feature bundle."""
    uid = uuid.uuid4().hex[:8]
    dataset_id = f"ai4i_train_{uid}"
    dataset_ver = "v1.0"
    fail_id = f"fail_{uid}"
    fail_ver = "v1.0"

    data_dir = getattr(PATHS, "data_dir", Path("data"))
    _create_versioned_obs_and_fail_datasets(
        data_dir, dataset_id, dataset_ver, fail_id, fail_ver, n_rows=100
    )

    app = create_app()
    client = TestClient(app)

    # 1. Preprocessing
    prep_resp = client.post("/preprocessing", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "force_reanalyze": True,
    })
    assert prep_resp.status_code == 200, prep_resp.text
    prep_data = prep_resp.json()
    plan_id = prep_data["preprocessing_plan_id"]
    plan_ver = prep_data["preprocessing_plan_version"]

    # 2. Feature
    feat_resp = client.post("/feature", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "failure_source_mode": "external_dataset",
        "failure_dataset_id": fail_id,
        "failure_dataset_version": fail_ver,
        "preprocessing_plan_id": plan_id,
        "preprocessing_plan_version": plan_ver,
        "feature_schema_version": "ai4i-feature-v1",
        "label_schema_version": "ai4i-label-24h-v1",
        "prediction_horizon_hours": 24,
    })
    assert feat_resp.status_code == 200, feat_resp.text
    feat_data = feat_resp.json()
    feat_ver = feat_data.get("outputs", {}).get("feature_dataset_version") or feat_data.get("feature_dataset_version")

    yield {
        "client": client,
        "app": app,
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "fail_id": fail_id,
        "fail_ver": fail_ver,
    }

    # Cleanup
    (data_dir / f"{dataset_id}.csv").unlink(missing_ok=True)
    shutil.rmtree(data_dir / "observations" / dataset_id, ignore_errors=True)
    shutil.rmtree(data_dir / "failures" / fail_id, ignore_errors=True)
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    shutil.rmtree(models_store / "cache" / "preprocessing_plans" / dataset_id, ignore_errors=True)
    shutil.rmtree(models_store / "cache" / "features" / dataset_id, ignore_errors=True)
    for base_model in ["lightgbm", "xgboost", "random_forest"]:
        shutil.rmtree(models_store / "artifacts" / f"pdm-{base_model}", ignore_errors=True)


# ==========================================
# 1. API Endpoints & Happy Paths
# ==========================================

def test_train_all_models_success_and_artifact_bundle(test_setup):
    """Test POST /train trains all registered models and publishes 6-file artifacts."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    req_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "training_config_version": "training-config-v1",
        "activation_policy": "activate_on_success",
    }
    resp = client.post("/train", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "succeeded"
    assert len(data["results"]) == 3
    base_models = [r["base_model"] for r in data["results"]]
    assert set(base_models) == {"lightgbm", "xgboost", "random_forest"}

    models_store = getattr(PATHS, "models_store", Path("models_store"))

    # Verify each published artifact package
    for r in data["results"]:
        assert r["status"] == "succeeded"
        assert r["activated"] is True
        assert r["metrics_summary"] is not None
        assert "f1" in r["metrics_summary"]

        model_id = r["model_id"]
        model_version = r["model_version"]
        artifact_dir = models_store / "artifacts" / model_id / model_version

        assert artifact_dir.exists()

        # Check all 6 files
        for fname in ["manifest.json", "model.joblib", "feature_schema.json", "label_schema.json", "history_requirement.json", "metrics.json"]:
            fpath = artifact_dir / fname
            assert fpath.exists(), f"Missing {fname} in {artifact_dir}"
            assert fpath.stat().st_size > 0

        # Check manifest content
        with open(artifact_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["artifact_type"] == ARTIFACT_TYPE
        assert manifest["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert manifest["model_id"] == model_id
        assert manifest["model_version"] == model_version
        assert manifest["dataset_version"] == dataset_ver
        assert manifest["training_config"]["training_config_version"] == "training-config-v1"
        assert manifest["provenance"]["training_config_version"] == "training-config-v1"

        # Check provenance has real SHA-256 and URLs
        prov = manifest.get("provenance", {})
        assert prov.get("feature_dataset_metadata_sha256") is not None
        assert len(prov.get("feature_dataset_metadata_sha256", "")) == 64
        assert prov.get("training_config_sha256") is not None
        assert len(prov.get("training_config_sha256", "")) == 64

        # Check history requirement
        with open(artifact_dir / "history_requirement.json", "r", encoding="utf-8") as f:
            hist_req = json.load(f)
        assert "required_columns" in hist_req
        assert "Air temperature [K]" in hist_req["required_columns"]
        assert hist_req["minimum_history_rows"] >= 1

        # Check latest.json pointer
        pointer_file = models_store / "artifacts" / model_id / "latest.json"
        assert pointer_file.exists()
        with open(pointer_file, "r", encoding="utf-8") as f:
            pointer = json.load(f)
        assert pointer["active_version"] == model_version


def test_train_single_model_success(test_setup):
    """Test POST /train/{base_model} trains individual specified models."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    for base_model in ["lightgbm", "xgboost", "random_forest"]:
        req_payload = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_ver,
            "feature_dataset_version": feat_ver,
            "training_config_version": "training-config-v1",
            "model_version": f"{base_model}-test-v1",
            "activation_policy": "activate_on_success",
        }
        resp = client.post(f"/train/{base_model}", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert len(data["results"]) == 1
        assert data["results"][0]["base_model"] == base_model
        assert data["results"][0]["model_version"] == f"{base_model}-test-v1"


# ==========================================
# 2. Training Config Contract Tests
# ==========================================

def test_train_unknown_config_version_returns_404(test_setup):
    """Test 404 when requested training_config_version does not exist."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    resp = client.post("/train", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "training_config_version": "nonexistent-config-v999",
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRAINING_CONFIG_NOT_FOUND"


def test_train_invalid_config_ratio_fails_422(test_setup, tmp_path):
    """Test 422 when training config split_ratio sum is not 1.0."""
    from systems.generator.app.training.training_config_provider import TrainingConfigProvider

    bad_config = {
        "training_config_version": "bad-ratio-config",
        "split_strategy": "asset_time_split",
        "split_ratio": {"train": 0.8, "validation": 0.3, "test": 0.1},
        "random_seed": 42,
        "hyperparameters": {},
        "metrics": ["f1"],
        "primary_metric": "f1",
    }
    cfg_file = tmp_path / "bad-ratio-config.json"
    cfg_file.write_text(json.dumps(bad_config), encoding="utf-8")

    provider = TrainingConfigProvider(search_dirs=[tmp_path])
    with pytest.raises(Exception) as exc_info:
        provider.load_training_config("bad-ratio-config")
    assert "1.0" in str(exc_info.value)


# ==========================================
# 3. Error Contracts & Validation
# ==========================================

def test_train_unsupported_model_returns_404(test_setup):
    """Test POST /train/{base_model} with invalid model name returns 404."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    resp = client.post("/train/deep_neural_net", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRAINING_MODEL_NOT_FOUND"


def test_train_invalid_method_returns_405(test_setup):
    """Test non-POST HTTP methods on /train return 405 Method Not Allowed."""
    client = test_setup["client"]
    assert client.get("/train").status_code == 405
    assert client.put("/train").status_code == 405
    assert client.delete("/train").status_code == 405


def test_train_invalid_payload_returns_422(test_setup):
    """Test missing required fields or extra forbidden fields return 422."""
    client = test_setup["client"]
    # Missing fields
    resp = client.post("/train", json={})
    assert resp.status_code == 422

    # Path traversal in dataset_id
    resp2 = client.post("/train", json={
        "dataset_id": "../escape",
        "dataset_version": "v1.0",
        "feature_dataset_version": "v1.0",
    })
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "TRAINING_CONTRACT_ERROR"


def test_train_bundle_not_found_returns_404(test_setup):
    """Test 404 when requested Feature Dataset Bundle does not exist."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]

    resp = client.post("/train", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": "nonexistent-bundle-v999",
    })
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRAINING_INPUT_NOT_FOUND"


def test_train_bundle_identity_mismatch_fails_422(test_setup):
    """Test 422 when dataset_id in request does not match metadata in bundle."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    bundle_dir = models_store / "cache" / "features" / dataset_id / dataset_ver / feat_ver

    # Change dataset_id in feature_metadata.json
    with open(bundle_dir / "feature_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["dataset_id"] = "tampered_dataset_id"
    with open(bundle_dir / "feature_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    resp = client.post("/train", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "TRAINING_CONTRACT_ERROR"


def test_train_conflict_existing_model_version_always_returns_409(test_setup):
    """Test 409 MODEL_ARTIFACT_CONFLICT when re-publishing same model_id/model_version."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    req_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": "conflict-immutable-v1",
    }
    resp1 = client.post("/train/lightgbm", json=req_payload)
    assert resp1.status_code == 200

    # Attempt to retrain same model version -> ALWAYS 409
    resp2 = client.post("/train/lightgbm", json=req_payload)
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "MODEL_ARTIFACT_CONFLICT"


def test_train_activation_policy_publish_only(test_setup):
    """Test that deprecated activation_policy='publish_only' still automatically updates latest.json upon publish."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    pointer_file = models_store / "artifacts" / "pdm-random_forest" / "latest.json"
    if pointer_file.exists():
        pointer_file.unlink()

    req_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": "publish-only-v1",
        "activation_policy": "publish_only",
    }
    resp = client.post("/train/random_forest", json=req_payload)
    assert resp.status_code == 200
    res = resp.json()["results"][0]
    assert res["published"] is True
    assert res["latest_updated"] is True
    assert pointer_file.exists()
    assert json.loads(pointer_file.read_text(encoding="utf-8"))["model_version"] == "publish-only-v1"



def test_train_endpoint_is_synchronous():
    """Verify that POST /train and POST /train/{base_model} are synchronous functions."""
    assert inspect.iscoroutinefunction(post_train) is False
    assert inspect.iscoroutinefunction(post_train_single) is False


def test_train_split_fail_closed_missing_asset_id():
    """Test data_splitter asset_time_split raises 422 when asset_id is missing."""
    from systems.generator.app.training.data_splitter import asset_time_split
    from systems.generator.app.training.training_exception import TrainingDatasetError

    features = np.ones((12, 3), dtype=np.float64)
    labels = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1], dtype=np.int64)
    row_metadata = [{"timestamp": "2026-08-20T00:00:00Z"} for _ in range(12)]  # missing asset_id

    with pytest.raises(TrainingDatasetError) as exc_info:
        asset_time_split(features, labels, row_metadata)
    assert "asset_id가 누락" in str(exc_info.value)


def test_train_split_fail_closed_missing_timestamp():
    """Test data_splitter asset_time_split raises 422 when timestamp is missing."""
    from systems.generator.app.training.data_splitter import asset_time_split
    from systems.generator.app.training.training_exception import TrainingDatasetError

    features = np.ones((12, 3), dtype=np.float64)
    labels = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1], dtype=np.int64)
    row_metadata = [{"asset_id": "asset-1"} for _ in range(12)]  # missing timestamp

    with pytest.raises(TrainingDatasetError) as exc_info:
        asset_time_split(features, labels, row_metadata)
    assert "timestamp가 누락" in str(exc_info.value)


# ==========================================
# 4. Golden Test Vector Verification
# ==========================================

def test_generator_training_contract_vectors(test_setup):
    """Verify contracts/examples and contracts/test-vectors schema compliance."""
    import jsonschema

    schema_file = Path("contracts/schemas/generator-training-config.schema.json")
    assert schema_file.exists()
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # 1. Verify example configs pass JSON Schema
    ex_cfg = Path("contracts/examples/generator-training/training-config-v1.json")
    assert ex_cfg.exists()
    jsonschema.validate(instance=json.loads(ex_cfg.read_text(encoding="utf-8")), schema=schema)

    # 2. Verify test-vector config passes JSON Schema
    tv_cfg = Path("contracts/test-vectors/generator-training-v1/training-config.json")
    assert tv_cfg.exists()
    jsonschema.validate(instance=json.loads(tv_cfg.read_text(encoding="utf-8")), schema=schema)


def test_train_schema_sha256_mismatch_fails_422(test_setup):
    """Test 422 when feature_schema_sha256 in bundle provenance does not match actual schema on disk."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    bundle_dir = models_store / "cache" / "features" / dataset_id / dataset_ver / feat_ver

    # Tamper with feature_schema_sha256 in feature_metadata.json
    with open(bundle_dir / "feature_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["provenance"]["feature_schema_sha256"] = "0" * 64
    with open(bundle_dir / "feature_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    resp = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": "tampered-feat-sha-v1",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"
    assert "Feature Schema SHA-256 불일치" in resp.json()["error"]["message"]


def test_train_label_schema_sha256_mismatch_fails_422(test_setup):
    """Test 422 when label_schema_sha256 in bundle provenance does not match actual label schema."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    bundle_dir = models_store / "cache" / "features" / dataset_id / dataset_ver / feat_ver

    # Tamper with label_schema_sha256 in feature_metadata.json
    with open(bundle_dir / "feature_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["provenance"]["label_schema_sha256"] = "f" * 64
    with open(bundle_dir / "feature_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    resp = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": "tampered-label-sha-v1",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"
    assert "Label Schema SHA-256 불일치" in resp.json()["error"]["message"]


def test_train_missing_schema_sha256_in_provenance_fails_422(test_setup):
    """Test 422 when schema sha256 fields are missing from bundle provenance."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    bundle_dir = models_store / "cache" / "features" / dataset_id / dataset_ver / feat_ver

    with open(bundle_dir / "feature_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    del meta["provenance"]["feature_schema_sha256"]
    with open(bundle_dir / "feature_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    resp = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": "missing-sha-v1",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"


def test_train_omitted_model_version_deterministic_generation_and_conflict(test_setup):
    """Test omitted model_version generates deterministic unique version and returns 409 on duplicate train."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    req_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "training_config_version": "training-config-v1",
    }
    # 1. First training with omitted model_version -> succeeds
    resp1 = client.post("/train/lightgbm", json=req_payload)
    assert resp1.status_code == 200
    res1 = resp1.json()["results"][0]
    gen_ver1 = res1["model_version"]
    assert gen_ver1.startswith("lightgbm-fp")

    # 2. Second training on EXACT same inputs with omitted model_version -> 409 Conflict because same version is generated!
    resp2 = client.post("/train/lightgbm", json=req_payload)
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "MODEL_ARTIFACT_CONFLICT"


def test_train_hyperparameters_and_seed_propagation(test_setup, tmp_path):
    """Test that training config hyperparameters and random_seed propagate to estimator and manifest."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    # Create custom training config with non-default seed and parameters
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cfg_dir = models_store / "training_configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    custom_cfg_file = cfg_dir / "custom-seed-params-v1.json"

    custom_cfg = {
        "training_config_version": "custom-seed-params-v1",
        "random_seed": 777,
        "split_strategy": "asset_time_split",
        "split_ratio": {"train": 0.70, "validation": 0.15, "test": 0.15},
        "metrics": ["f1", "precision", "recall", "roc_auc", "pr_auc"],
        "primary_metric": "f1",
        "hyperparameters": {
            "lightgbm": {"n_estimators": 50, "learning_rate": 0.05},
            "xgboost": {"n_estimators": 50, "learning_rate": 0.05},
            "random_forest": {"n_estimators": 50, "max_depth": 5},
        },
    }
    with open(custom_cfg_file, "w", encoding="utf-8") as f:
        json.dump(custom_cfg, f, indent=2)

    resp = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "training_config_version": "custom-seed-params-v1",
        "model_version": "custom-params-v1",
    })
    assert resp.status_code == 200
    res = resp.json()["results"][0]
    assert res["status"] == "succeeded"
    assert res["published"] is True
    assert res["activated"] is True

    # Inspect published manifest
    publisher = ModelArtifactPublisher()
    art_dir = publisher.get_artifact_dir(res["model_id"], res["model_version"])
    manifest = json.loads((art_dir / "manifest.json").read_text(encoding="utf-8"))

    tc = manifest["training_config"]
    assert tc["random_seed"] == 777
    assert tc["configured_parameters"]["n_estimators"] == 50
    assert tc["configured_parameters"]["learning_rate"] == 0.05
    assert tc["resolved_parameters"]["random_state"] == 777
    assert tc["resolved_parameters"]["n_estimators"] == 50
    assert tc["resolved_parameters"]["learning_rate"] == 0.05

    # Check joblib model estimator params
    import joblib
    model_obj = joblib.load(art_dir / "model.joblib")
    assert model_obj.n_estimators == 50
    assert model_obj.random_state == 777


def test_train_duplicate_seed_in_hyperparameters_rejected(test_setup):
    """Test that declaring random_state/seed inside model hyperparameters is rejected."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cfg_dir = models_store / "training_configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    bad_cfg_file = cfg_dir / "bad-seed-cfg-v1.json"

    bad_cfg = {
        "training_config_version": "bad-seed-cfg-v1",
        "random_seed": 123,
        "split_strategy": "asset_time_split",
        "split_ratio": {"train": 0.70, "validation": 0.15, "test": 0.15},
        "metrics": ["f1"],
        "primary_metric": "f1",
        "hyperparameters": {
            "lightgbm": {"random_state": 999},
        },
    }
    with open(bad_cfg_file, "w", encoding="utf-8") as f:
        json.dump(bad_cfg, f, indent=2)

    resp = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "training_config_version": "bad-seed-cfg-v1",
        "model_version": "bad-seed-test-v1",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "TRAINING_CONTRACT_ERROR"
    assert "random_state" in resp.json()["error"]["message"]


def test_train_single_class_train_partition_fails_422(test_setup):
    """Test that when train partition has only a single class after split, 422 is raised."""
    from systems.generator.app.training.data_splitter import asset_time_split
    from systems.generator.app.training.training_exception import TrainingDatasetError

    features = np.ones((20, 4))
    # 18 zeros, 2 ones placed at the end so time split puts all ones in test
    labels = np.array([0] * 18 + [1, 1])
    row_metadata = [
        {"asset_id": "asset-1", "timestamp": f"2026-08-20T{i:02d}:00:00Z"}
        for i in range(20)
    ]

    with pytest.raises(TrainingDatasetError) as exc_info:
        asset_time_split(features, labels, row_metadata)
    assert "train partition에 두 클래스가 모두 존재하지 않습니다" in str(exc_info.value)


def test_manifest_duplicate_roles_and_paths_rejected(tmp_path):
    """Test that manifest with duplicate roles or duplicate paths is rejected with ModelArtifactValidationError."""
    from systems.generator.app.training.training_exception import ModelArtifactValidationError

    pub = ModelArtifactPublisher(base_dir=tmp_path)
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy files
    for f in ["model.joblib", "feature_schema.json", "label_schema.json", "history_requirement.json", "metrics.json"]:
        (staging_dir / f).write_text("{}", encoding="utf-8")

    checksum_dict = {f: compute_file_sha256(staging_dir / f) for f in ["model.joblib", "feature_schema.json", "label_schema.json", "history_requirement.json", "metrics.json"]}

    manifest_duplicate_role = {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_id": "pdm-test",
        "model_version": "v1.0",
        "dataset_version": "v1.0",
        "feature_schema_version": "feat-v1",
        "label_schema_version": "label-v1",
        "history_requirement_version": "hist-v1",
        "metrics_schema_version": "pdm-metrics-v1",
        "created_at": "2026-08-24T00:00:00Z",
        "training_config": {"training_config_version": "v1"},
        "metrics": {"f1": 0.9},
        "checksum": {"algorithm": "sha256", "files": checksum_dict},
        "provenance": {},
        "compatibility": {"runtime": "app.diagnosis"},
        "artifact_files": [
            {"role": "model", "path": "model.joblib", "sha256": checksum_dict["model.joblib"]},
            {"role": "model", "path": "model.joblib", "sha256": checksum_dict["model.joblib"]},
            {"role": "feature_schema", "path": "feature_schema.json", "sha256": checksum_dict["feature_schema.json"]},
            {"role": "label_schema", "path": "label_schema.json", "sha256": checksum_dict["label_schema.json"]},
            {"role": "history_requirement", "path": "history_requirement.json", "sha256": checksum_dict["history_requirement.json"]},
            {"role": "metrics", "path": "metrics.json", "sha256": checksum_dict["metrics.json"]},
        ],
    }

    with pytest.raises(ModelArtifactValidationError) as exc_info:
        pub.validate_manifest(manifest_duplicate_role, staging_dir)
    assert "role 중복 발견" in str(exc_info.value)


def test_activation_lock_concurrency_returns_409(test_setup, tmp_path):
    """Test that concurrent lock on the same model_id returns 409 MODEL_LATEST_UPDATE_IN_PROGRESS."""
    from systems.generator.model.publisher import ModelActivationLock
    from systems.generator.app.training.training_exception import ModelActivationInProgressError

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    model_id = "pdm-lightgbm"
    lock_file = models_store / "artifacts" / model_id / ".latest.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    # Hold the lock manually
    with ModelActivationLock(lock_file, model_id=model_id):
        # Now attempting to post /train/lightgbm should fail with 409
        resp = client.post("/train/lightgbm", json={
            "dataset_id": dataset_id,
            "dataset_version": dataset_ver,
            "feature_dataset_version": feat_ver,
            "model_version": "lock-test-v1",
        })
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "MODEL_LATEST_UPDATE_IN_PROGRESS"


def test_auto_latest_pointer_created_on_publish(test_setup):
    """Test that latest.json is automatically created and updated upon artifact publish."""
    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))

    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "auto-latest-v1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["published"] is True
    assert data["results"][0]["latest_updated"] is True

    latest_file = models_store / "artifacts" / "pdm-lightgbm" / "latest.json"
    assert latest_file.is_file()
    pointer_data = json.loads(latest_file.read_text(encoding="utf-8"))
    assert pointer_data["model_version"] == "auto-latest-v1"
    assert pointer_data["model_id"] == "pdm-lightgbm"
    assert "artifact_uri" in pointer_data


def test_cannot_skip_latest_pointer_update_with_publish_only(test_setup):
    """Test that passing activation_policy='publish_only' still auto-updates latest.json (user cannot skip)."""
    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))

    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "auto-latest-v2",
        "activation_policy": "publish_only",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["published"] is True
    assert data["results"][0]["latest_updated"] is True

    latest_file = models_store / "artifacts" / "pdm-lightgbm" / "latest.json"
    assert latest_file.is_file()
    pointer_data = json.loads(latest_file.read_text(encoding="utf-8"))
    assert pointer_data["model_version"] == "auto-latest-v2"


def test_parallel_locks_on_different_models_do_not_block_each_other(test_setup):
    """Test that holding lock on model A (xgboost) does not block training/publishing model B (lightgbm)."""
    from systems.generator.model.publisher import ModelActivationLock

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    xgb_lock_file = models_store / "artifacts" / "pdm-xgboost" / ".latest.lock"
    xgb_lock_file.parent.mkdir(parents=True, exist_ok=True)

    client = test_setup["client"]
    with ModelActivationLock(xgb_lock_file, model_id="pdm-xgboost"):
        # Training lightgbm should succeed without blocking
        resp = client.post("/train/lightgbm", json={
            "dataset_id": test_setup["dataset_id"],
            "dataset_version": test_setup["dataset_version"],
            "feature_dataset_version": test_setup["feature_dataset_version"],
            "model_version": "lgb-parallel-v1",
        })
        assert resp.status_code == 200
        assert resp.json()["results"][0]["published"] is True
        assert resp.json()["results"][0]["latest_updated"] is True


def test_public_version_selection_api_does_not_exist(test_setup):
    """Test that manual version selection or rollback public APIs do not exist in current PR."""
    client = test_setup["client"]
    resp = client.post("/models/pdm-lightgbm/select-version", json={"model_version": "v1"})
    assert resp.status_code in (404, 405)


def test_partial_failure_preserves_artifact_and_recovers_on_retry(test_setup):
    """Test that pointer failure preserves published immutable artifact in details and recovers on retry."""
    from systems.generator.model.publisher import ModelActivationLock

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    model_id = "pdm-lightgbm"
    lock_file = models_store / "artifacts" / model_id / ".latest.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]
    m_ver = "partial-fail-recovery-v1"

    # 1. Hold the lock manually to simulate pointer lock contention
    with ModelActivationLock(lock_file, model_id=model_id):
        resp = client.post("/train/lightgbm", json={
            "dataset_id": dataset_id,
            "dataset_version": dataset_ver,
            "feature_dataset_version": feat_ver,
            "model_version": m_ver,
        })
        assert resp.status_code == 409
        err = resp.json()["error"]
        assert err["code"] == "MODEL_LATEST_UPDATE_IN_PROGRESS"
        assert len(err["details"]) > 0
        detail = err["details"][0]
        assert detail["published"] is True
        assert detail["latest_updated"] is False
        assert detail["latest_error_code"] == "MODEL_LATEST_UPDATE_IN_PROGRESS"
        assert "partial-fail-recovery-v1" in detail["model_artifact_uri"]

    # Verify immutable artifact exists on disk
    art_dir = models_store / "artifacts" / model_id / m_ver
    assert art_dir.is_dir()
    assert (art_dir / "manifest.json").is_file()
    assert (art_dir / "model.joblib").is_file()

    # Verify staging residue does not exist
    staging_dirs = list((models_store / "artifacts" / model_id).glob(".tmp_*"))
    assert len(staging_dirs) == 0

    # 2. Lock is now released. Retry identical training request -> should recover pointer and succeed!
    resp_retry = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": m_ver,
    })
    assert resp_retry.status_code == 200
    res = resp_retry.json()["results"][0]
    assert res["published"] is True
    assert res["latest_updated"] is True

    latest_file = models_store / "artifacts" / model_id / "latest.json"
    assert latest_file.is_file()
    assert json.loads(latest_file.read_text(encoding="utf-8"))["model_version"] == m_ver

    # 3. Retrying same version after it is already active -> should return 409 MODEL_ARTIFACT_CONFLICT
    resp_conflict = client.post("/train/lightgbm", json={
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": m_ver,
    })
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["error"]["code"] == "MODEL_ARTIFACT_CONFLICT"


def test_batch_train_isolates_pointer_contention_partial_success(test_setup):
    """Test batch /train isolates pointer lock failure as failed model while allowing other models to succeed."""
    from systems.generator.model.publisher import ModelActivationLock

    models_store = getattr(PATHS, "models_store", Path("models_store"))
    xgb_lock_file = models_store / "artifacts" / "pdm-xgboost" / ".latest.lock"
    xgb_lock_file.parent.mkdir(parents=True, exist_ok=True)

    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]

    with ModelActivationLock(xgb_lock_file, model_id="pdm-xgboost"):
        resp = client.post("/train", json={
            "dataset_id": dataset_id,
            "dataset_version": dataset_ver,
            "feature_dataset_version": feat_ver,
            "model_version": "batch-iso-v1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partially_succeeded"

        results_by_model = {r["base_model"]: r for r in data["results"]}
        # xgboost had lock conflict -> published=True, latest_updated=False, status=failed
        xgb_res = results_by_model["xgboost"]
        assert xgb_res["published"] is True
        assert xgb_res["latest_updated"] is False
        assert xgb_res["status"] == "failed"
        assert xgb_res["latest_error_code"] == "MODEL_LATEST_UPDATE_IN_PROGRESS"

        # lightgbm succeeded normally
        lgb_res = results_by_model["lightgbm"]
        assert lgb_res["published"] is True
        assert lgb_res["latest_updated"] is True
        assert lgb_res["status"] == "succeeded"


def test_prediction_horizon_positive_integer_validation(test_setup, tmp_path):
    """Test strict prediction_horizon_hours validation rejects non-positive-int values with 422."""
    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cache_dir = models_store / "cache" / "features" / test_setup["dataset_id"] / test_setup["dataset_version"] / test_setup["feature_dataset_version"]
    meta_path = cache_dir / "feature_metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    invalid_horizons = [0, -24, 24.5, "24", True, None]

    for inv_h in invalid_horizons:
        meta_corrupt = dict(meta)
        meta_corrupt["provenance"] = dict(meta["provenance"])
        if inv_h is None:
            meta_corrupt["provenance"].pop("prediction_horizon_hours", None)
        else:
            meta_corrupt["provenance"]["prediction_horizon_hours"] = inv_h

        meta_path.write_text(json.dumps(meta_corrupt), encoding="utf-8")

        resp = client.post("/train/lightgbm", json={
            "dataset_id": test_setup["dataset_id"],
            "dataset_version": test_setup["dataset_version"],
            "feature_dataset_version": test_setup["feature_dataset_version"],
            "model_version": f"horizon-inv-{type(inv_h).__name__}",
        })
        assert resp.status_code == 422, f"Failed for horizon value {inv_h!r}"
        assert resp.json()["error"]["code"] == "TRAINING_CONTRACT_ERROR"

    # Restore valid metadata
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def test_prediction_horizon_mismatch_with_label_schema_returns_422(test_setup):
    """Test mismatch between Feature Bundle horizon and Label Schema horizon returns 422 without creating artifact."""
    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cache_dir = models_store / "cache" / "features" / test_setup["dataset_id"] / test_setup["dataset_version"] / test_setup["feature_dataset_version"]
    meta_path = cache_dir / "feature_metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    meta_mismatch = dict(meta)
    meta_mismatch["provenance"] = dict(meta["provenance"])
    meta_mismatch["provenance"]["prediction_horizon_hours"] = 999  # Label schema has 24h
    meta_path.write_text(json.dumps(meta_mismatch), encoding="utf-8")

    m_ver = "mismatch-horizon-v1"
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": m_ver,
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "TRAINING_CONTRACT_ERROR"
    assert "Prediction horizon mismatch" in resp.json()["error"]["message"]

    # Verify no artifact destination or latest.json was created for this version
    art_dir = models_store / "artifacts" / "pdm-lightgbm" / m_ver
    assert not art_dir.exists()

    # Restore valid metadata
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def test_batch_train_duplicate_request_returns_conflict_not_latest_error(test_setup):
    """Test duplicate batch /train returns MODEL_ARTIFACT_CONFLICT with published=False and latest_error_code=None."""
    client = test_setup["client"]
    dataset_id = test_setup["dataset_id"]
    dataset_ver = test_setup["dataset_version"]
    feat_ver = test_setup["feature_dataset_version"]
    m_ver = "batch-dup-v1"

    req_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_ver,
        "feature_dataset_version": feat_ver,
        "model_version": m_ver,
    }

    # 1. First batch train -> succeeds
    resp1 = client.post("/train", json=req_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "succeeded"
    for r in data1["results"]:
        assert r["published"] is True
        assert r["latest_updated"] is True
        assert r["error_code"] is None

    # 2. Second batch train with same version -> already active, fails with MODEL_ARTIFACT_CONFLICT
    resp2 = client.post("/train", json=req_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "failed"
    for r in data2["results"]:
        assert r["published"] is False
        assert r["latest_updated"] is False
        assert r["latest_error_code"] is None
        assert r["model_artifact_uri"] is None
        assert r["error_code"] == "MODEL_ARTIFACT_CONFLICT"


def test_trainer_failure_with_existing_artifact_preserves_trainer_error(test_setup, monkeypatch):
    """Test that a trainer execution failure preserves original error and does NOT convert to MODEL_LATEST_UPDATE_FAILED."""
    from systems.generator.model.registry import LightGBMTrainer
    from systems.generator.app.training.training_exception import TrainingExecutionError

    def failing_train(*args, **kwargs):
        raise TrainingExecutionError("Mock trainer numerical instability failure")

    monkeypatch.setattr(LightGBMTrainer, "train", failing_train)

    client = test_setup["client"]
    resp = client.post("/train", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "trainer-fail-v1",
    })
    assert resp.status_code == 200
    data = resp.json()
    lgb_result = next(r for r in data["results"] if r["base_model"] == "lightgbm")
    assert lgb_result["published"] is False
    assert lgb_result["latest_updated"] is False
    assert lgb_result["latest_error_code"] is None
    assert lgb_result["error_code"] == "TRAINING_EXECUTION_ERROR"


def test_row_metadata_structure_integrity_returns_422(test_setup):
    """Test that non-list row_metadata and non-dict items fail closed with FEATURE_DATASET_INTEGRITY_ERROR (422)."""
    from systems.generator.file_integrity import compute_file_sha256

    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cache_dir = models_store / "cache" / "features" / test_setup["dataset_id"] / test_setup["dataset_version"] / test_setup["feature_dataset_version"]
    row_meta_path = cache_dir / "row_metadata.json"
    feat_meta_path = cache_dir / "feature_metadata.json"
    original_row_data = row_meta_path.read_text(encoding="utf-8")
    original_feat_data = feat_meta_path.read_text(encoding="utf-8")
    feat_meta = json.loads(original_feat_data)

    def write_row_meta(content_str: str):
        row_meta_path.write_text(content_str, encoding="utf-8")
        updated_feat = dict(feat_meta)
        updated_feat["payload_checksums"] = dict(feat_meta.get("payload_checksums", {}))
        updated_feat["payload_checksums"]["row_metadata.json"] = compute_file_sha256(row_meta_path)
        feat_meta_path.write_text(json.dumps(updated_feat), encoding="utf-8")

    try:
        # 1. Non-list row_metadata (dict)
        write_row_meta(json.dumps({"type": "invalid_structure"}))
        resp = client.post("/train/lightgbm", json={
            "dataset_id": test_setup["dataset_id"],
            "dataset_version": test_setup["dataset_version"],
            "feature_dataset_version": test_setup["feature_dataset_version"],
            "model_version": "rowmeta-dict-v1",
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"

        # 2. List containing string items instead of dict
        write_row_meta(json.dumps(["item_str_1", "item_str_2"]))
        resp = client.post("/train/lightgbm", json={
            "dataset_id": test_setup["dataset_id"],
            "dataset_version": test_setup["dataset_version"],
            "feature_dataset_version": test_setup["feature_dataset_version"],
            "model_version": "rowmeta-str-v1",
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"

        # 3. List containing list items instead of dict
        write_row_meta(json.dumps([["sub1"], ["sub2"]]))
        resp = client.post("/train/lightgbm", json={
            "dataset_id": test_setup["dataset_id"],
            "dataset_version": test_setup["dataset_version"],
            "feature_dataset_version": test_setup["feature_dataset_version"],
            "model_version": "rowmeta-list-v1",
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FEATURE_DATASET_INTEGRITY_ERROR"

    finally:
        row_meta_path.write_text(original_row_data, encoding="utf-8")
        feat_meta_path.write_text(original_feat_data, encoding="utf-8")


def test_row_metadata_and_timestamp_validation_returns_422(test_setup):
    """Test that missing asset_id, bool, NaN, and Inf timestamps return 422 TRAINING_DATASET_ERROR."""
    from systems.generator.file_integrity import compute_file_sha256

    client = test_setup["client"]
    models_store = getattr(PATHS, "models_store", Path("models_store"))
    cache_dir = models_store / "cache" / "features" / test_setup["dataset_id"] / test_setup["dataset_version"] / test_setup["feature_dataset_version"]
    row_meta_path = cache_dir / "row_metadata.json"
    feat_meta_path = cache_dir / "feature_metadata.json"
    original_row_data = row_meta_path.read_text(encoding="utf-8")
    original_feat_data = feat_meta_path.read_text(encoding="utf-8")
    original_rows = json.loads(original_row_data)
    feat_meta = json.loads(original_feat_data)

    invalid_cases = [
        # (modified_rows, expected_err_code, desc)
        ([{**r, "asset_id": ""} for r in original_rows], "TRAINING_DATASET_ERROR", "empty asset_id"),
        ([{**r, "asset_id": None} for r in original_rows], "TRAINING_DATASET_ERROR", "null asset_id"),
        ([{**r, "asset_id": True} for r in original_rows], "TRAINING_DATASET_ERROR", "bool asset_id"),
        ([{**r, "timestamp": True} for r in original_rows], "TRAINING_DATASET_ERROR", "bool timestamp"),
        ([{**r, "timestamp": float("nan")} for r in original_rows], "TRAINING_DATASET_ERROR", "NaN timestamp"),
        ([{**r, "timestamp": float("inf")} for r in original_rows], "TRAINING_DATASET_ERROR", "Inf timestamp"),
        ([{**r, "timestamp": float("-inf")} for r in original_rows], "TRAINING_DATASET_ERROR", "-Inf timestamp"),
        ([{**r, "timestamp": "NaN"} for r in original_rows], "TRAINING_DATASET_ERROR", "string NaN timestamp"),
        ([{**r, "timestamp": "Infinity"} for r in original_rows], "TRAINING_DATASET_ERROR", "string Infinity timestamp"),
    ]

    try:
        for idx, (bad_rows, exp_code, desc) in enumerate(invalid_cases):
            row_meta_path.write_text(json.dumps(bad_rows), encoding="utf-8")
            updated_feat = dict(feat_meta)
            updated_feat["payload_checksums"] = dict(feat_meta.get("payload_checksums", {}))
            updated_feat["payload_checksums"]["row_metadata.json"] = compute_file_sha256(row_meta_path)
            feat_meta_path.write_text(json.dumps(updated_feat), encoding="utf-8")

            resp = client.post("/train/lightgbm", json={
                "dataset_id": test_setup["dataset_id"],
                "dataset_version": test_setup["dataset_version"],
                "feature_dataset_version": test_setup["feature_dataset_version"],
                "model_version": f"invalid-row-{idx}",
            })
            assert resp.status_code == 422, f"Failed for {desc}"
            assert resp.json()["error"]["code"] == exp_code, f"Failed code for {desc}"
            art_dir = models_store / "artifacts" / "pdm-lightgbm" / f"invalid-row-{idx}"
            assert not art_dir.exists()
    finally:
        row_meta_path.write_text(original_row_data, encoding="utf-8")
        feat_meta_path.write_text(original_feat_data, encoding="utf-8")


def test_artifact_publish_rename_conflict_returns_409(test_setup, monkeypatch):
    """Test that a FileExistsError during staging rename is translated to 409 MODEL_ARTIFACT_CONFLICT."""
    from pathlib import Path

    def mock_rename(self, target):
        raise FileExistsError("Concurrent destination exists")

    monkeypatch.setattr(Path, "rename", mock_rename)

    client = test_setup["client"]
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "conflict-rename-v1",
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "MODEL_ARTIFACT_CONFLICT"


def test_artifact_publish_io_error_returns_500_with_stage(test_setup, monkeypatch):
    """Test that an OSError during artifact publication is mapped to 500 MODEL_ARTIFACT_PUBLISH_ERROR with stage info."""
    import joblib

    def failing_dump(*args, **kwargs):
        raise OSError("Disk quota exceeded or read-only volume")

    monkeypatch.setattr(joblib, "dump", failing_dump)

    client = test_setup["client"]
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "publish-io-err-v1",
    })
    assert resp.status_code == 500
    err_body = resp.json()["error"]
    assert err_body["code"] == "MODEL_ARTIFACT_PUBLISH_ERROR"
    assert len(err_body["details"]) > 0
    assert err_body["details"][0]["stage"] == "artifact_model_write"
    assert err_body["details"][0]["published"] is False


def test_latest_pointer_lock_open_io_error_returns_500(test_setup, monkeypatch):
    """Test that an I/O error preparing lock file returns 500 MODEL_LATEST_UPDATE_FAILED rather than 409."""
    from systems.generator.model.publisher import ModelActivationLock

    original_enter = ModelActivationLock.__enter__

    def failing_enter(self):
        raise OSError("Read-only filesystem on lock open")

    monkeypatch.setattr(ModelActivationLock, "__enter__", failing_enter)

    client = test_setup["client"]
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "lock-open-io-v1",
    })
    # Since Phase A succeeded and Phase B failed with lock open IO error, it returns 500
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "MODEL_LATEST_UPDATE_FAILED"


def test_latest_pointer_readback_mismatch_returns_500(test_setup, monkeypatch):
    """Test that a read-back mismatch after pointer replacement returns 500 MODEL_LATEST_VERIFY_FAILED."""
    import os
    from systems.generator.model import publisher

    # Let os.replace write an invalid pointer content
    original_replace = os.replace

    def corrupt_replace(src, dst):
        Path(dst).write_text(json.dumps({"model_version": "corrupted-pointer", "model_id": "pdm-lightgbm"}), encoding="utf-8")
        if Path(src).exists():
            Path(src).unlink()

    monkeypatch.setattr(os, "replace", corrupt_replace)

    client = test_setup["client"]
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "readback-mismatch-v1",
    })
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "MODEL_LATEST_VERIFY_FAILED"


def test_pointer_commit_cleanup_failure_preserves_error(test_setup, monkeypatch):
    """Test that cleanup failure of temp pointer does not mask original error and sets cleanup_failed."""
    import os
    from pathlib import Path

    def failing_replace(src, dst):
        raise OSError("Disk write I/O error during pointer replacement")

    original_unlink = Path.unlink

    def failing_unlink(self, missing_ok=False):
        if ".latest." in self.name and ".tmp" in self.name:
            raise OSError("Permission denied on temp unlink")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", failing_replace)
    monkeypatch.setattr(Path, "unlink", failing_unlink)

    client = test_setup["client"]
    resp = client.post("/train/lightgbm", json={
        "dataset_id": test_setup["dataset_id"],
        "dataset_version": test_setup["dataset_version"],
        "feature_dataset_version": test_setup["feature_dataset_version"],
        "model_version": "cleanup-fail-v1",
    })
    assert resp.status_code == 500
    err_body = resp.json()["error"]
    assert err_body["code"] == "MODEL_LATEST_UPDATE_FAILED"
