"""Automated Contract Test suite for Generator Feature Dataset Input Manifest and Golden Vector parity."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from systems.generator.app.feature.feature_exception import (
    FeatureContractError,
    FeatureDatasetIntegrityError,
    FeatureInputNotFoundError,
    FeatureSchemaMismatchError,
)
from systems.generator.app.feature.feature_input_resolver import FeatureInputResolver
from systems.generator.app.feature.feature_schema import FeatureRequest
from systems.generator.app.feature.feature_service import FeatureService
from systems.generator.app.main import create_app
from systems.generator.app.preprocessing.preprocessing_repository import PreprocessingRepository
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS

SCHEMA_PATH = Path("contracts/schemas/generator-dataset-input-manifest.schema.json")
EXAMPLES_DIR = Path("contracts/examples/generator-feature-input")
TEST_VECTOR_DIR = Path("contracts/test-vectors/generator-feature-input-v1")


@pytest.fixture
def manifest_schema() -> dict[str, Any]:
    assert SCHEMA_PATH.exists()
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ==========================================
# 1. JSON Schema & Examples Validation Tests
# ==========================================

def test_example_observation_manifest_passes_schema(manifest_schema):
    """Verify contracts/examples observation manifest complies with schema."""
    ex_obs = EXAMPLES_DIR / "observation-dataset-manifest.json"
    assert ex_obs.exists()
    data = json.loads(ex_obs.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=manifest_schema)


def test_example_failure_manifest_passes_schema(manifest_schema):
    """Verify contracts/examples failure manifest complies with schema."""
    ex_fail = EXAMPLES_DIR / "failure-dataset-manifest.json"
    assert ex_fail.exists()
    data = json.loads(ex_fail.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=manifest_schema)


def test_example_feature_requests_pass_pydantic():
    """Verify contracts/examples feature request files validate against FeatureRequest model."""
    req_ext_file = EXAMPLES_DIR / "feature-request.external.json"
    req_emb_file = EXAMPLES_DIR / "feature-request.embedded.json"

    assert req_ext_file.exists()
    assert req_emb_file.exists()

    req_ext = FeatureRequest.model_validate_json(req_ext_file.read_text(encoding="utf-8"))
    assert req_ext.failure_source_mode == "external_dataset"
    assert req_ext.failure_dataset_id == "example-failure"

    req_emb = FeatureRequest.model_validate_json(req_emb_file.read_text(encoding="utf-8"))
    assert req_emb.failure_source_mode == "embedded_observation"
    assert req_emb.failure_dataset_id is None


def test_manifest_schema_rejects_unsafe_relative_path(manifest_schema):
    """Verify manifest schema rejects path traversal and absolute paths."""
    bad_manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": "test-ds",
        "dataset_version": "v1.0",
        "schema_version": "canonical-v1",
        "created_at": "2026-08-24T00:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "../secret.csv",
                "media_type": "text/csv",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size_bytes": 10,
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_manifest, schema=manifest_schema)


# ==========================================
# 2. Versioned Resolver & Integrity Tests
# ==========================================

def test_resolver_rejects_unversioned_fallback(tmp_path):
    """Verify resolver does NOT fallback to unversioned data/{id}.csv files."""
    # Create unversioned file
    unversioned_file = tmp_path / "legacy_obs.csv"
    unversioned_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    resolver = FeatureInputResolver()
    with pytest.raises(FeatureInputNotFoundError) as exc_info:
        resolver.resolve_dataset("observation", "legacy_obs", "v1.0")
    assert "dataset_manifest.json 포함" in str(exc_info.value)


def test_resolver_rejects_manifest_id_or_version_mismatch(tmp_path):
    """Verify resolver rejects manifest where declared dataset_id/version conflicts with directory/request."""
    ds_dir = tmp_path / "observations" / "my_ds" / "v1.0"
    ds_dir.mkdir(parents=True)
    payload_file = ds_dir / "observations.csv"
    payload_file.write_text("a,b\n1,2\n", encoding="utf-8")

    manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": "DIFFERENT_DS_ID",
        "dataset_version": "v1.0",
        "schema_version": "canonical-v1",
        "created_at": "2026-08-24T00:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "observations.csv",
                "media_type": "text/csv",
                "sha256": compute_file_sha256(payload_file),
                "size_bytes": payload_file.stat().st_size,
            }
        ],
    }
    (ds_dir / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Point PATHS.data_dir to tmp_path
    original_data_dir = getattr(PATHS, "data_dir", Path("data"))
    PATHS.data_dir = tmp_path
    try:
        resolver = FeatureInputResolver()
        with pytest.raises(FeatureSchemaMismatchError) as exc_info:
            resolver.resolve_dataset("observation", "my_ds", "v1.0")
        assert "요청 ID('my_ds')와 일치하지 않습니다" in str(exc_info.value)
    finally:
        PATHS.data_dir = original_data_dir


def test_resolver_rejects_payload_checksum_or_size_mismatch(tmp_path):
    """Verify resolver rejects manifest with tampered payload file or mismatched sha256."""
    ds_dir = tmp_path / "observations" / "tamper_ds" / "v1.0"
    ds_dir.mkdir(parents=True)
    payload_file = ds_dir / "observations.csv"
    payload_file.write_text("a,b\n1,2\n", encoding="utf-8")

    manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": "tamper_ds",
        "dataset_version": "v1.0",
        "schema_version": "canonical-v1",
        "created_at": "2026-08-24T00:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "observations.csv",
                "media_type": "text/csv",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "size_bytes": payload_file.stat().st_size,
            }
        ],
    }
    (ds_dir / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    original_data_dir = getattr(PATHS, "data_dir", Path("data"))
    PATHS.data_dir = tmp_path
    try:
        resolver = FeatureInputResolver()
        with pytest.raises(FeatureDatasetIntegrityError) as exc_info:
            resolver.resolve_dataset("observation", "tamper_ds", "v1.0")
        assert "체크섬 불일치" in str(exc_info.value)
    finally:
        PATHS.data_dir = original_data_dir


# ==========================================
# 3. Golden Vector Execution & Parity Test
# ==========================================

def test_golden_test_vector_execution_and_parity():
    """Execute Feature pipeline on contracts/test-vectors/generator-feature-input-v1 and verify 100% parity."""
    # 1. Copy golden vector datasets into data/observations and data/failures
    obs_src = TEST_VECTOR_DIR / "observation"
    fail_src = TEST_VECTOR_DIR / "failure"
    exp_src = TEST_VECTOR_DIR / "expected"

    obs_target = PATHS.data_dir / "observations" / "golden-observation-v1" / "v1.0"
    fail_target = PATHS.data_dir / "failures" / "golden-failure-v1" / "v1.0"

    obs_target.mkdir(parents=True, exist_ok=True)
    fail_target.mkdir(parents=True, exist_ok=True)

    shutil.copy(obs_src / "dataset_manifest.json", obs_target / "dataset_manifest.json")
    shutil.copy(obs_src / "observations.csv", obs_target / "observations.csv")
    shutil.copy(fail_src / "dataset_manifest.json", fail_target / "dataset_manifest.json")
    shutil.copy(fail_src / "failures.csv", fail_target / "failures.csv")

    app = create_app()
    client = TestClient(app)

    # 2. Publish matching Preprocessing Plan for golden observation dataset
    prep_repo = PreprocessingRepository()
    obs_df = pd.read_csv(obs_target / "observations.csv")
    from systems.generator.app.preprocessing.preprocessing_repository import compute_source_schema_fingerprint
    schema_fp = compute_source_schema_fingerprint(obs_df)

    obs_payload_sha = compute_file_sha256(obs_target / "observations.csv")
    plan_dict = {
        "preprocessing_plan_id": "pp-golden-v1",
        "preprocessing_plan_version": "temp",
        "dataset_id": "golden-observation-v1",
        "dataset_version": "v1.0",
        "source_dataset_uri": f"data/observations/golden-observation-v1/v1.0/observations.csv",
        "source_dataset_sha256": obs_payload_sha,
        "source_schema_fingerprint": schema_fp,
        "decision_source": "rule_fallback",
        "fallback_reason": "golden test vector deterministic plan",
        "planner_version": "1.0",
        "structure_type": "tabular_column_as_attribute",
        "id_column": "Product ID",
        "time_column": "observed_at",
        "attribute_column": None,
        "value_column": None,
        "selected_columns": [
            "Product ID",
            "observed_at",
            "Air temperature [K]",
            "Process temperature [K]",
            "Rotational speed [rpm]",
            "Torque [Nm]",
            "Tool wear [min]"
        ],
        "duplicate_policy": "error",
        "aggregation": None,
        "created_at": "2026-08-24T00:00:00Z",
    }
    from systems.generator.app.preprocessing.preprocessing_repository import compute_preprocessing_plan_version
    plan_ver = compute_preprocessing_plan_version("golden-observation-v1", "v1.0", plan_dict)
    plan_dict["preprocessing_plan_version"] = plan_ver

    plan_dir = prep_repo.get_dataset_plan_dir("golden-observation-v1", "v1.0")
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "pp-golden-v1.json").write_text(json.dumps(plan_dict, indent=2), encoding="utf-8")

    try:
        # 3. Execute POST /feature with golden vector request
        req_file = TEST_VECTOR_DIR / "request.json"
        req_data = json.loads(req_file.read_text(encoding="utf-8"))
        req_data["preprocessing_plan_version"] = plan_ver

        resp = client.post("/feature", json=req_data)
        assert resp.status_code == 200, resp.text
        resp_json = resp.json()
        assert resp_json["status"] == "succeeded"

        feat_ver = resp_json["outputs"]["feature_dataset_version"]
        bundle_dir = PATHS.models_store / "cache" / "features" / "golden-observation-v1" / "v1.0" / feat_ver

        # 4. Compare with Expected Golden Vector Outputs
        # Feature columns
        exp_cols = json.loads((exp_src / "feature_columns.json").read_text(encoding="utf-8"))
        actual_cols = json.loads((bundle_dir / "feature_columns.json").read_text(encoding="utf-8"))
        assert actual_cols["columns"] == exp_cols["columns"]
        assert actual_cols["count"] == exp_cols["count"]

        # Labels
        exp_labels = json.loads((exp_src / "labels.json").read_text(encoding="utf-8"))
        actual_labels = np.load(bundle_dir / "labels.npy", allow_pickle=False)
        np.testing.assert_array_equal(actual_labels, np.array(exp_labels, dtype=np.int64))

        # Row metadata
        exp_rows = json.loads((exp_src / "row_metadata.json").read_text(encoding="utf-8"))
        actual_rows = json.loads((bundle_dir / "row_metadata.json").read_text(encoding="utf-8"))
        assert actual_rows == exp_rows

        # Summary
        exp_summary = json.loads((exp_src / "summary.json").read_text(encoding="utf-8"))
        assert resp_json["outputs"]["row_count"] == exp_summary["row_count"]
        assert resp_json["outputs"]["feature_count"] == exp_summary["feature_count"]
        assert np.sum(actual_labels == 1) == exp_summary["positive_label_count"]
        assert np.sum(actual_labels == 0) == exp_summary["negative_label_count"]

        # Provenance verification
        meta = json.loads((bundle_dir / "feature_metadata.json").read_text(encoding="utf-8"))
        prov = meta["provenance"]
        assert prov["observation_dataset_id"] == "golden-observation-v1"
        assert prov["observation_dataset_version"] == "v1.0"
        assert prov["observation_payload_sha256"] == obs_payload_sha
        assert prov["failure_dataset_id"] == "golden-failure-v1"
        assert prov["failure_dataset_version"] == "v1.0"
        assert prov["failure_payload_sha256"] == compute_file_sha256(fail_target / "failures.csv")

    finally:
        shutil.rmtree(PATHS.data_dir / "observations" / "golden-observation-v1", ignore_errors=True)
        shutil.rmtree(PATHS.data_dir / "failures" / "golden-failure-v1", ignore_errors=True)
        shutil.rmtree(PATHS.models_store / "cache" / "features" / "golden-observation-v1", ignore_errors=True)
        shutil.rmtree(PATHS.models_store / "cache" / "preprocessing_plans" / "golden-observation-v1", ignore_errors=True)


def test_manifest_schema_is_available_from_generator_runtime_root():
    """Verify that generator-dataset-input-manifest.schema.json is resolvable and valid."""
    schema_path = (
        Path("contracts")
        / "schemas"
        / "generator-dataset-input-manifest.schema.json"
    )
    assert schema_path.is_file()

    resolver = FeatureInputResolver()
    schema = resolver._get_manifest_schema()

    assert schema["title"] == "Generator Dataset Input Manifest v1"
