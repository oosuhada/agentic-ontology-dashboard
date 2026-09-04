"""Tests for Generator FastAPI daemon server: Startup, Concurrency, API contracts, Model Artifact validation, and Documentation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from systems.generator.generator_main import _training_lock, app
from systems.generator.model.model_registry import (
    REQUIRED_ARTIFACT_ROLES,
    has_any_published_model_artifact,
    has_any_trained_model,
    validate_model_artifact_directory,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_valid_artifact(dest: Path, model_id: str = "pdm-cnc-tool-wear-lightgbm", model_version: str = "v1") -> Path:
    """Helper to create a canonical model-artifact-v1.0 package using publish_model_artifact."""
    temp_model = dest / "_staging_temp" / f"{model_id}_{model_version}.joblib"
    temp_model.parent.mkdir(parents=True, exist_ok=True)
    temp_model.write_bytes(b"dummy_model_binary_content")

    from systems.generator.model.model_registry import publish_model_artifact

    return publish_model_artifact(
        artifact_uri=dest,
        model_id=model_id,
        model_version=model_version,
        dataset_version="ds-v1",
        feature_schema_version="pdm-feature-v1",
        model_file=temp_model,
        feature_schema={"schema_version": "pdm-feature-v1", "features": ["vibration", "temperature"], "target": "label"},
        training_config={"algorithm": "lightgbm", "framework": "lightgbm"},
        metrics={"metrics_schema_version": "pdm-metrics-v1", "validation_metrics": {"f1": 0.85}},
        provenance={"publisher": "systems/generator"},
        compatibility={"runtime": "app.diagnosis"},
    )



@pytest.fixture
def client():
    return TestClient(app)


# ==========================================
# 1. API Endpoints
# ==========================================

def test_generator_daemon_health(client):
    """Test GET /health returns 200 with system identifier."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "system": "generator"}


def test_generator_daemon_train_success(client):
    """Test POST /internal/train invokes train_all and returns response payload."""
    dummy_result = {
        "capabilities": {"FailurePrediction": True},
        "mappings": {},
        "registry": {
            "run_version": 1,
            "run_id": "run-v1-test",
            "models": {"lightgbm": {"artifact_uri": "models_store/artifacts/lightgbm/v1"}},
            "published_artifacts": {"lightgbm": "models_store/artifacts/lightgbm/v1"},
        },
    }
    with patch("systems.generator.generator_main.train_all", return_value=dummy_result) as mock_train:
        response = client.post("/internal/train", json={"force_reanalyze": False})
        assert response.status_code == 200
        assert response.json() == dummy_result
        mock_train.assert_called_once()
    assert not _training_lock.locked()


def test_generator_daemon_retrain_success(client):
    """Test POST /internal/retrain invokes train_all with new version."""
    dummy_result = {
        "capabilities": {"FailurePrediction": True},
        "mappings": {},
        "registry": {
            "run_version": 2,
            "run_id": "run-v2-test",
            "models": {"lightgbm": {"artifact_uri": "models_store/artifacts/lightgbm/v2"}},
            "published_artifacts": {"lightgbm": "models_store/artifacts/lightgbm/v2"},
        },
    }
    with patch("systems.generator.generator_main.train_all", return_value=dummy_result) as mock_train:
        response = client.post("/internal/retrain", json={"force_reanalyze": True})
        assert response.status_code == 200
        assert response.json() == dummy_result
        mock_train.assert_called_once()
    assert not _training_lock.locked()


def test_generator_daemon_train_nonexistent_data_dir_returns_400(client):
    """Test POST /internal/train returns 400 when data_dir does not exist."""
    response = client.post("/internal/train", json={"data_dir": "non_existent_directory_12345"})
    assert response.status_code == 400
    assert "지정한 data_dir가 존재하지 않습니다" in response.json()["detail"]
    assert not _training_lock.locked()


def test_generator_daemon_train_file_as_data_dir_returns_400(client, tmp_path):
    """Test POST /internal/train returns 400 when data_dir is a file instead of directory."""
    dummy_file = tmp_path / "not_a_dir.txt"
    dummy_file.write_text("hello", encoding="utf-8")
    response = client.post("/internal/train", json={"data_dir": str(dummy_file)})
    assert response.status_code == 400
    assert "지정한 data_dir가 디렉터리가 아닙니다" in response.json()["detail"]
    assert not _training_lock.locked()


def test_generator_daemon_train_empty_data_dir_returns_400(client, tmp_path):
    """Test POST /internal/train returns 400 when data_dir is empty."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    response = client.post("/internal/train", json={"data_dir": str(empty_dir)})
    assert response.status_code == 400
    assert "지정한 data_dir가 비어 있습니다" in response.json()["detail"]
    assert not _training_lock.locked()


def test_generator_daemon_train_invalid_schema_returns_422(client):
    """Test POST /internal/train returns 422 for invalid request body schema."""
    response = client.post("/internal/train", json={"force_reanalyze": "invalid_boolean_value_123"})
    assert response.status_code == 422
    assert not _training_lock.locked()


def test_generator_daemon_train_internal_error_returns_sanitized_500(client):
    """Test POST /internal/train returns sanitized 500 without leaking stack trace."""
    with patch("systems.generator.generator_main.train_all", side_effect=RuntimeError("Secret internal path /secret/code.py failed")):
        response = client.post("/internal/train", json={})
        assert response.status_code == 500
        assert response.json()["detail"] == "모델 학습에 실패했습니다."
        assert "/secret/code.py" not in response.json()["detail"]
    assert not _training_lock.locked()


# ==========================================
# 2. Concurrency Control (Lock & 409)
# ==========================================

@pytest.mark.anyio
async def test_generator_daemon_concurrent_training_returns_409():
    """Test concurrent training execution triggers HTTP 409 Conflict."""
    from systems.generator.generator_main import _execute_training

    training_started = threading.Event()
    training_release = threading.Event()

    def slow_train_all(*args, **kwargs):
        training_started.set()
        training_release.wait(timeout=5)
        return {"registry": {}}

    with patch("systems.generator.generator_main.train_all", side_effect=slow_train_all):
        task1 = asyncio.create_task(_execute_training(data_dir=None, force_reanalyze=False))
        await asyncio.to_thread(training_started.wait, 2.0)
        assert _training_lock.locked()

        with pytest.raises(Exception) as exc_info:
            await _execute_training(data_dir=None, force_reanalyze=False)

        assert exc_info.value.status_code == 409
        assert "모델 학습이 이미 진행 중입니다" in exc_info.value.detail

        training_release.set()
        result1 = await task1
        assert "registry" in result1

    assert not _training_lock.locked()


@pytest.mark.anyio
async def test_generator_daemon_lock_released_after_failure():
    """Test concurrency lock is safely released after training failure."""
    from systems.generator.generator_main import _execute_training

    with patch("systems.generator.generator_main.train_all", side_effect=RuntimeError("Training boom")):
        with pytest.raises(Exception) as exc_info:
            await _execute_training(data_dir=None, force_reanalyze=False)
        assert exc_info.value.status_code == 500

    assert not _training_lock.locked(), "Lock must be released even after exception"

    with patch("systems.generator.generator_main.train_all", return_value={"success": True}):
        result = await _execute_training(data_dir=None, force_reanalyze=False)
        assert result == {"success": True}

    assert not _training_lock.locked()


# ==========================================
# 3. Startup & Shutdown Lifecycle (Non-blocking & Graceful Wait)
# ==========================================

@pytest.mark.anyio
async def test_generator_daemon_lifespan_skips_when_model_exists():
    """Test lifespan skips background auto-training if model artifact already exists."""
    from systems.generator.generator_main import lifespan

    with patch("systems.generator.generator_main.has_any_published_model_artifact", return_value=True), \
         patch("systems.generator.generator_main.load_config") as mock_load, \
         patch("asyncio.create_task") as mock_create_task:
        async with lifespan(app):
            mock_load.assert_called_once()
            mock_create_task.assert_not_called()
            assert app.state.initial_training_task is None

    assert not _training_lock.locked()


@pytest.mark.anyio
async def test_generator_daemon_lifespan_yields_immediately_without_waiting():
    """Test lifespan yields immediately (starts daemon) without waiting for training completion."""
    from systems.generator.generator_main import lifespan

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_worker(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        finished.set()
        return {"registry": {}}

    with patch("systems.generator.generator_main.has_any_published_model_artifact", return_value=False), \
         patch("systems.generator.generator_main.load_config"), \
         patch("systems.generator.generator_main.train_all", side_effect=slow_worker):
        async with lifespan(app):
            await asyncio.to_thread(started.wait, 2.0)
            assert started.is_set()
            assert not finished.is_set(), "Lifespan must yield immediately while worker is still running"
            assert _training_lock.locked()
            release.set()

    assert finished.is_set()
    assert not _training_lock.locked()


@pytest.mark.anyio
async def test_shutdown_waits_for_real_training_worker_and_keeps_lock():
    """Test shutdown waits for real blocking training worker thread and keeps lock until completion."""
    from systems.generator.generator_main import lifespan

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_train_all(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        finished.set()
        return {"registry": {}}

    with patch("systems.generator.generator_main.has_any_published_model_artifact", return_value=False), \
         patch("systems.generator.generator_main.load_config"), \
         patch("systems.generator.generator_main.train_all", side_effect=blocking_train_all):

        cm = lifespan(app)
        await cm.__aenter__()

        await asyncio.to_thread(started.wait, 2.0)
        assert started.is_set()
        assert _training_lock.locked()
        assert not finished.is_set()

        shutdown_task = asyncio.create_task(cm.__aexit__(None, None, None))
        await asyncio.sleep(0.05)

        assert not shutdown_task.done(), "Shutdown must not finish while worker is running"
        assert not finished.is_set()
        assert _training_lock.locked()

        release.set()
        await shutdown_task

        assert finished.is_set()
        assert not _training_lock.locked()


@pytest.mark.anyio
async def test_generator_daemon_lifespan_handles_background_training_failure():
    """Test lifespan handles initial training background task failure gracefully without crashing."""
    from systems.generator.generator_main import _run_initial_training

    with patch("systems.generator.generator_main.train_all", side_effect=RuntimeError("Initial train failed")):
        await _run_initial_training()

    assert not _training_lock.locked()


# ==========================================
# 4. Model Artifact Validation Contracts (10 Scenarios)
# ==========================================

def test_artifact_validation_raw_joblib_without_manifest_rejected(tmp_path):
    """5.1 Raw model file only without manifest -> False."""
    store_dir = tmp_path / "models_store"
    (store_dir / "lightgbm").mkdir(parents=True)
    (store_dir / "lightgbm" / "model_v1.joblib").write_text("raw", encoding="utf-8")

    assert has_any_trained_model(store_dir), "Legacy check detects raw file"
    assert not has_any_published_model_artifact(store_dir / "artifacts"), "v1.0 check rejects raw file alone"


def test_artifact_validation_missing_manifest_required_fields_rejected(tmp_path):
    """5.2 Manifest missing required fields -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Remove critical required field
    del manifest["dataset_version"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")



def test_artifact_validation_missing_required_roles_rejected(tmp_path):
    """5.3 Missing one of the 5 required roles (e.g. metrics) -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Filter out metrics role
    manifest["artifact_files"] = [f for f in manifest["artifact_files"] if f["role"] != "metrics"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_duplicate_roles_rejected(tmp_path):
    """5.4 Duplicate role declared in manifest -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Duplicate model role
    model_entry = next(f for f in manifest["artifact_files"] if f["role"] == "model")
    manifest["artifact_files"].append(model_entry.copy())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_missing_declared_file_rejected(tmp_path):
    """5.5 Declared file in manifest missing on disk -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    # Delete model.joblib
    (artifact_dir / "model.joblib").unlink()

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_checksum_mismatch_rejected(tmp_path):
    """5.6 Checksum mismatch for declared file -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Corrupt sha256 for feature_schema
    for f in manifest["artifact_files"]:
        if f["role"] == "feature_schema":
            f["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_unsafe_escaping_path_rejected(tmp_path):
    """5.7 Declared path with .. -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Make path escape root
    manifest["artifact_files"][0]["path"] = "../outside_model.joblib"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_absolute_path_rejected(tmp_path):
    """5.7b Declared path as absolute path -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Set absolute path
    manifest["artifact_files"][0]["path"] = "/etc/passwd"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")


def test_artifact_validation_duplicate_paths_rejected(tmp_path):
    """5.7c Declared duplicate paths across entries -> False."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Assign duplicate path
    manifest["artifact_files"][1]["path"] = manifest["artifact_files"][0]["path"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not has_any_published_model_artifact(tmp_path / "artifacts")



def test_artifact_validation_canonical_complete_v1_accepted(tmp_path):
    """5.8 Canonical complete v1.0 artifact -> True."""
    artifact_dir = _create_valid_artifact(tmp_path / "artifacts")
    assert has_any_published_model_artifact(tmp_path / "artifacts")

    # Direct directory validation test
    validated = validate_model_artifact_directory(artifact_dir)
    assert validated["model_id"] == "pdm-cnc-tool-wear-lightgbm"


def test_artifact_validation_corrupted_and_valid_artifacts_coexist(tmp_path):
    """5.9 Corrupted artifact candidate skipped and valid artifact candidate recognized -> True."""
    artifact_root = tmp_path / "artifacts"

    # Candidate 1: Corrupted
    bad_dir = _create_valid_artifact(artifact_root, model_id="pdm-corrupted", model_version="v1")
    (bad_dir / "manifest.json").write_text("invalid json", encoding="utf-8")

    # Candidate 2: Valid
    _create_valid_artifact(artifact_root, model_id="pdm-valid", model_version="v1")

    assert has_any_published_model_artifact(artifact_root)


@pytest.mark.anyio
async def test_generator_daemon_auto_training_decision_based_on_artifact_validity(tmp_path):
    """5.10 Startup auto-training executed when only corrupted artifacts exist, skipped when valid artifact exists."""
    from systems.generator.generator_main import lifespan

    artifact_root = tmp_path / "artifacts"

    # Case A: Corrupted artifact only -> auto-training executed
    bad_dir = _create_valid_artifact(artifact_root, model_id="pdm-corrupted", model_version="v1")
    (bad_dir / "model.joblib").unlink()

    with patch.dict("os.environ", {"MODEL_ARTIFACT_URI": str(artifact_root)}), \
         patch("systems.generator.generator_main.load_config"), \
         patch("systems.generator.generator_main._run_initial_training") as mock_run_train:
        async with lifespan(app):
            mock_run_train.assert_called_once()

    # Case B: Complete valid artifact added -> auto-training skipped
    _create_valid_artifact(artifact_root, model_id="pdm-valid", model_version="v1")

    with patch.dict("os.environ", {"MODEL_ARTIFACT_URI": str(artifact_root)}), \
         patch("systems.generator.generator_main.load_config"), \
         patch("systems.generator.generator_main._run_initial_training") as mock_run_train:
        async with lifespan(app):
            mock_run_train.assert_not_called()


# ==========================================
# 5. Documentation Contracts
# ==========================================

def test_generator_daemon_docs_in_operations_dir_and_no_predict():
    """Test generator internal API specification resides in docs/operations/ and has no active predict endpoints."""
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "operations" / "generator-internal-api-specification.md"
    assert doc_path.exists(), "Doc must be moved to docs/operations/generator-internal-api-specification.md"

    content = doc_path.read_text(encoding="utf-8")
    assert "GET /health" in content
    assert "POST /internal/train" in content
    assert "POST /internal/retrain" in content
    assert "금지 범위" in content
    assert "artifact_uri" in content
    assert "published_artifacts" in content
    assert "run_id" in content
    assert "has_any_published_model_artifact" in content
