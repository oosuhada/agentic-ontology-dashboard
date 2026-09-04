"""Tests for Generator domain FastAPI application and Preprocessing API (/preprocessing)."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import uuid
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.main import app, create_app
from systems.generator.app.preprocessing.preprocessing_schema import (
    PreprocessingRequest,
    PreprocessingResponse,
    PreprocessingPlanResponse,
)
from systems.generator.app.preprocessing.preprocessing_exception import (
    PreprocessingError,
    DatasetNotFoundError,
    DatasetContractError,
    PreprocessingRoleError,
    PreprocessingPlanValidationError,
    PreprocessingPlanPublishError,
    PreprocessingPlanConflictError,
)
from systems.generator.app.preprocessing.preprocessing_repository import (
    PreprocessingRepository,
    compute_preprocessing_plan_version,
    compute_source_schema_fingerprint,
    canonicalize_dtype,
)
from systems.generator.app.preprocessing.preprocessing_planner import (
    PreprocessingPlanner,
    PLANNER_VERSION,
)
from systems.generator.app.preprocessing.preprocessing_service import (
    PreprocessingService,
    preprocess_with_plan,
    load_all_sources,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_wide_csv(tmp_path):
    rel_path = "tmp_telemetry_wide_test.csv"
    csv_path = PATHS.data_dir / rel_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "asset_id": ["M001", "M001", "M002"],
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 01:00:00", "2026-01-01 00:00:00"],
        "temperature": [55.2, 57.8, 62.1],
        "vibration": [0.12, 0.15, 0.18],
    })
    df.to_csv(csv_path, index=False)
    yield rel_path
    if csv_path.exists():
        csv_path.unlink()


@pytest.fixture
def sample_long_csv(tmp_path):
    rel_path = "tmp_telemetry_long_test.csv"
    csv_path = PATHS.data_dir / rel_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "machine_id": ["M1", "M1", "M1", "M1"],
        "ts": ["2026-01-01 00:00:00", "2026-01-01 00:00:00", "2026-01-01 01:00:00", "2026-01-01 01:00:00"],
        "metric_name": ["temp", "vib", "temp", "vib"],
        "metric_value": [50.0, 0.1, 52.0, 0.15],
    })
    df.to_csv(csv_path, index=False)
    yield rel_path
    if csv_path.exists():
        csv_path.unlink()


# ==========================================
# 1. Health & Base Endpoints
# ==========================================

def test_app_health_endpoint(client):
    """GET /health returns 200 and system identifier."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["system"] == "generator"
    assert "X-Request-ID" in res.headers


# ==========================================
# 2. Responsibility Boundaries (Ontology Mapping Removed)
# ==========================================

def test_preprocessing_responsibility_boundaries(client, sample_wide_csv, tmp_path, monkeypatch):
    """POST /preprocessing returns preprocessing_plan_uri and does NOT produce ontology mapping."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload = {
        "dataset_id": "test_boundary",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": True,
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 200
    data = res.json()

    # 1. Response fields
    assert "result" in data
    res_result = data["result"]
    assert "mapping_uri" not in res_result
    assert "mapping_version" not in res_result
    assert "mapping_uri" not in data
    assert "preprocessing_plan_uri" in res_result
    assert "preprocessing_plan_sha256" in res_result

    # 2. Verify no ontology mapping files created in models_store
    mapping_dir = models_store / "cache" / "mappings"
    assert not mapping_dir.exists() or len(list(mapping_dir.glob("*.json"))) == 0

    # 3. Verify published plan JSON contains no ontology or feature fields
    plan_id = data["preprocessing_plan_id"]
    repo = PreprocessingRepository(base_dir=models_store / "cache" / "preprocessing_plans")
    plan_json = repo.load_plan("test_boundary", "v1.0", plan_id)
    assert "mapping_uri" not in plan_json
    assert "mapping_version" not in plan_json
    assert "ontology_node" not in plan_json
    assert "feature_recipe" not in plan_json
    assert "feature_names" not in plan_json


# ==========================================
# 3. Plan Identification, Provenance, & Determinism
# ==========================================

def test_preprocessing_plan_identification_and_provenance(client, sample_wide_csv, tmp_path, monkeypatch):
    """Plan records source_dataset_uri, source_dataset_sha256, source_schema_fingerprint, decision_source, and planner_version."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    csv_path = PATHS.data_dir / sample_wide_csv
    expected_file_sha = compute_file_sha256(csv_path)
    df_raw = pd.read_csv(csv_path)
    expected_schema_fp = compute_source_schema_fingerprint(df_raw)

    payload = {
        "dataset_id": "test_ident",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": True,
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 200
    data = res.json()

    plan_id = data["preprocessing_plan_id"]
    plan_ver = data["preprocessing_plan_version"]

    assert plan_id.startswith("pp-")
    raw_uuid = plan_id[3:]
    assert uuid.UUID(raw_uuid)

    assert plan_ver.startswith("preprocessing-plan-")
    assert len(plan_ver) == len("preprocessing-plan-") + 16

    # Load from disk and verify identity and provenance
    repo = PreprocessingRepository(base_dir=models_store / "cache" / "preprocessing_plans")
    loaded = repo.load_plan("test_ident", "v1.0", plan_id)
    assert loaded["preprocessing_plan_id"] == plan_id
    assert loaded["preprocessing_plan_version"] == plan_ver
    assert loaded["dataset_id"] == "test_ident"
    assert loaded["dataset_version"] == "v1.0"
    assert loaded["source_dataset_sha256"] == expected_file_sha
    assert loaded["source_schema_fingerprint"] == expected_schema_fp
    assert loaded["decision_source"] in ("llm", "rule_fallback")
    assert loaded["planner_version"] == PLANNER_VERSION
    assert not Path(loaded["source_dataset_uri"]).is_absolute()
    assert ".." not in Path(loaded["source_dataset_uri"]).parts


def test_compute_preprocessing_plan_version_detects_changes():
    """Modifying selected_columns, id_column, duplicate_policy, source_dataset_sha256, source_schema_fingerprint, or planner provenance changes version."""
    base = {
        "source_dataset_sha256": "a" * 64,
        "source_schema_fingerprint": "1" * 64,
        "decision_source": "rule_fallback",
        "fallback_reason": "stage1: llm_call_failed; stage2: llm_call_failed",
        "planner_version": "preprocessing-planner-v1",
        "structure_type": "tabular_column_as_attribute",
        "selected_columns": ["asset_id", "timestamp", "voltage"],
        "id_column": "asset_id",
        "time_column": "timestamp",
        "duplicate_policy": "error",
        "aggregation": None,
    }
    v_base = compute_preprocessing_plan_version("ds1", "v1.0", base)

    v_cols = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "selected_columns": ["asset_id", "timestamp"]})
    assert v_cols != v_base

    v_id = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "id_column": "machine_id"})
    assert v_id != v_base

    v_dup = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "duplicate_policy": "aggregate", "aggregation": "mean"})
    assert v_dup != v_base

    v_sha = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "source_dataset_sha256": "b" * 64})
    assert v_sha != v_base

    v_schema_fp = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "source_schema_fingerprint": "2" * 64})
    assert v_schema_fp != v_base

    v_decision = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "decision_source": "llm", "fallback_reason": None})
    assert v_decision != v_base

    v_planner_ver = compute_preprocessing_plan_version("ds1", "v1.0", {**base, "planner_version": "preprocessing-planner-v2"})
    assert v_planner_ver != v_base


# ==========================================
# 4. Storage Structure & latest.json
# ==========================================

def test_preprocessing_storage_structure_and_latest_pointer(client, sample_wide_csv, tmp_path, monkeypatch):
    """Plans stored in {dataset_id}/{dataset_version}/ with latest.json pointing to current plan."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload = {
        "dataset_id": "storage_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": True,
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 200
    data = res.json()

    plan_id = data["preprocessing_plan_id"]
    plan_ver = data["preprocessing_plan_version"]
    plan_uri = data["result"]["preprocessing_plan_uri"]
    plan_sha = data["result"]["preprocessing_plan_sha256"]

    # Check relative logical URI (never absolute)
    assert not plan_uri.startswith("C:")
    assert not plan_uri.startswith("/")
    assert not plan_uri.startswith("..")
    assert plan_uri.endswith(f"{plan_id}.json")

    repo_dir = models_store / "cache" / "preprocessing_plans" / "storage_ds" / "v1.0"
    assert repo_dir.is_dir()

    plan_file = repo_dir / f"{plan_id}.json"
    assert plan_file.is_file()
    assert compute_file_sha256(plan_file) == plan_sha

    latest_file = repo_dir / "latest.json"
    assert latest_file.is_file()
    with open(latest_file, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    assert latest_data["dataset_id"] == "storage_ds"
    assert latest_data["dataset_version"] == "v1.0"
    assert latest_data["preprocessing_plan_id"] == plan_id
    assert latest_data["preprocessing_plan_version"] == plan_ver
    assert latest_data["path"] == f"{plan_id}.json"
    assert latest_data["sha256"] == plan_sha


# ==========================================
# 5. Long Format & Contract Validation
# ==========================================

def test_preprocessing_long_format_success(client, sample_long_csv, monkeypatch):
    """POST /preprocessing on long format data plans roles and pivots successfully."""
    from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner
    def mock_plan_columns(self, filepath, structure_type, df_preview, duplicate_policy="error", aggregation=None):
        return {
            "selected_columns": ["machine_id", "ts", "metric_name", "metric_value"],
            "id_column": "machine_id",
            "time_column": "ts",
            "attribute_column": "metric_name",
            "value_column": "metric_value",
            "duplicate_policy": duplicate_policy,
            "aggregation": aggregation,
        }

    monkeypatch.setattr(PreprocessingPlanner, "classify_structure", lambda self, f, d: "tabular_row_as_attribute")
    monkeypatch.setattr(PreprocessingPlanner, "plan_columns", mock_plan_columns)

    payload = {
        "dataset_id": "test_long",
        "dataset_version": "v1.0",
        "source_uri": sample_long_csv,
        "force_reanalyze": True,
        "duplicate_policy": "error",
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "succeeded"
    assert data["dataset_id"] == "test_long"
    assert data["result"]["id_column"] == "machine_id"
    assert data["result"]["attribute_column"] == "metric_name"
    assert data["result"]["value_column"] == "metric_value"
    assert data["result"]["time_column"] == "ts"


def test_preprocessing_dataset_not_found(client):
    """POST /preprocessing returns 404 when dataset cannot be resolved."""
    payload = {
        "dataset_id": "non_existent_dataset_xyz",
        "dataset_version": "v99.0",
        "source_uri": "non_existent_path.csv",
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "DATASET_NOT_FOUND"


def test_preprocessing_long_format_missing_roles_fails_fast(client, sample_long_csv, monkeypatch):
    """POST /preprocessing raises 422 PREPROCESSING_ROLE_COLUMNS_MISSING when long-format roles are incomplete."""
    from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner
    def mock_plan_columns_incomplete(self, filepath, structure_type, df_preview, duplicate_policy="error", aggregation=None):
        return {
            "selected_columns": ["machine_id", "ts"],
            "id_column": "machine_id",
            "time_column": "ts",
            "attribute_column": None,
            "value_column": None,
        }

    monkeypatch.setattr(PreprocessingPlanner, "classify_structure", lambda self, f, d: "tabular_row_as_attribute")
    monkeypatch.setattr(PreprocessingPlanner, "plan_columns", mock_plan_columns_incomplete)

    payload = {
        "dataset_id": "test_long_missing_roles",
        "dataset_version": "v1.0",
        "source_uri": sample_long_csv,
        "force_reanalyze": True,
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "PREPROCESSING_ROLE_COLUMNS_MISSING"


def test_preprocessing_path_confinement_and_security(client):
    """POST /preprocessing rejects path traversal in source_uri, dataset_id, and dataset_version."""
    # 1. source_uri traversal
    res = client.post("/preprocessing", json={"dataset_id": "ds", "dataset_version": "v1", "source_uri": "../../../etc/passwd"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "DATASET_CONTRACT_ERROR"

    # 2. dataset_id traversal
    res = client.post("/preprocessing", json={"dataset_id": "../../../etc/passwd", "dataset_version": "v1"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "DATASET_CONTRACT_ERROR"

    # 3. dataset_version traversal
    res = client.post("/preprocessing", json={"dataset_id": "ds", "dataset_version": "../../../etc/shadow"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "DATASET_CONTRACT_ERROR"


# ==========================================
# 6. Reanalysis Policy, Reuse & Conflict Detection
# ==========================================

def test_preprocessing_reanalysis_policy(client, sample_wide_csv, tmp_path, monkeypatch):
    """force_reanalyze=False reuses latest; force_reanalyze=True publishes new plan ID."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload_initial = {
        "dataset_id": "reuse_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": False,
    }

    # 1. First run creates plan
    res1 = client.post("/preprocessing", json=payload_initial)
    assert res1.status_code == 200
    d1 = res1.json()
    plan_id1 = d1["preprocessing_plan_id"]
    plan_ver1 = d1["preprocessing_plan_version"]

    # 2. Second run with force_reanalyze=False reuses exact plan
    res2 = client.post("/preprocessing", json=payload_initial)
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["preprocessing_plan_id"] == plan_id1
    assert d2["preprocessing_plan_version"] == plan_ver1

    # 3. Third run with force_reanalyze=True creates new plan ID but keeps content version (same content)
    payload_reanalyze = {**payload_initial, "force_reanalyze": True}
    res3 = client.post("/preprocessing", json=payload_reanalyze)
    assert res3.status_code == 200
    d3 = res3.json()
    plan_id3 = d3["preprocessing_plan_id"]
    plan_ver3 = d3["preprocessing_plan_version"]

    assert plan_id3 != plan_id1  # New unique plan ID
    assert plan_ver3 == plan_ver1  # Content is identical, so content-hash version matches


def test_preprocessing_checksum_mismatch_fails_409(client, sample_wide_csv, tmp_path, monkeypatch):
    """When dataset content changes on disk (values only), reuse returns 409 with content_changed=True, schema_changed=False."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload = {
        "dataset_id": "checksum_conflict_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": False,
    }

    # 1. First run creates valid plan
    res1 = client.post("/preprocessing", json=payload)
    assert res1.status_code == 200

    # 2. Modify CSV file content on disk (values only, same columns & dtypes)
    csv_path = PATHS.data_dir / sample_wide_csv
    df = pd.read_csv(csv_path)
    df["temperature"] = df["temperature"] + 10.0
    df.to_csv(csv_path, index=False)

    # 3. Subsequent run with force_reanalyze=False detects checksum mismatch -> 409
    res2 = client.post("/preprocessing", json=payload)
    assert res2.status_code == 409
    data2 = res2.json()
    assert data2["error"]["code"] == "PREPROCESSING_PLAN_CONFLICT"
    assert "force_reanalyze=True" in data2["error"]["message"]

    details = data2["error"]["details"][0]
    assert details["content_changed"] is True
    assert details["schema_changed"] is False
    assert details["existing_schema_fingerprint"] == details["current_schema_fingerprint"]

    # 4. Run with force_reanalyze=True succeeds and issues new plan
    res3 = client.post("/preprocessing", json={**payload, "force_reanalyze": True})
    assert res3.status_code == 200


def test_preprocessing_schema_fingerprint_change_fails_409(client, sample_wide_csv, tmp_path, monkeypatch):
    """When columns/structure change on disk, reuse returns 409 with schema_changed=True."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload = {
        "dataset_id": "schema_conflict_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": False,
    }

    # 1. First run
    res1 = client.post("/preprocessing", json=payload)
    assert res1.status_code == 200

    # 2. Modify schema on disk (add column)
    csv_path = PATHS.data_dir / sample_wide_csv
    df = pd.read_csv(csv_path)
    df["pressure"] = [101.3, 101.5, 101.2]
    df.to_csv(csv_path, index=False)

    # 3. Subsequent run -> 409 with schema_changed=True
    res2 = client.post("/preprocessing", json=payload)
    assert res2.status_code == 409
    data2 = res2.json()
    assert data2["error"]["code"] == "PREPROCESSING_PLAN_CONFLICT"

    details = data2["error"]["details"][0]
    assert details["content_changed"] is True
    assert details["schema_changed"] is True
    assert details["existing_schema_fingerprint"] != details["current_schema_fingerprint"]


def test_preprocessing_duplicate_policy_mismatch_fails_409(client, sample_wide_csv, tmp_path, monkeypatch):
    """When requested duplicate_policy or aggregation differs from existing plan, reuse returns 409."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload_error = {
        "dataset_id": "dup_policy_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": False,
        "duplicate_policy": "error",
    }
    res1 = client.post("/preprocessing", json=payload_error)
    assert res1.status_code == 200

    # Request aggregate policy on same dataset without force_reanalyze -> 409
    payload_agg = {
        "dataset_id": "dup_policy_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": False,
        "duplicate_policy": "aggregate",
        "aggregation": "mean",
    }
    res2 = client.post("/preprocessing", json=payload_agg)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "PREPROCESSING_PLAN_CONFLICT"


def test_preprocessing_selected_columns_missing_fails_422():
    """preprocess_with_plan fails fast (422) when declared selected_columns are missing in DataFrame."""
    df = pd.DataFrame({"asset_id": ["A1"], "time": ["2026-01-01 00:00:00"], "col1": [1.0]})
    plan = {
        "structure_type": "tabular_column_as_attribute",
        "selected_columns": ["asset_id", "time", "non_existent_col"],
    }
    with pytest.raises(PreprocessingPlanValidationError) as exc_info:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            df.to_csv(f.name, index=False)
            tmp_csv = f.name
        try:
            preprocess_with_plan(tmp_csv, plan)
        finally:
            Path(tmp_csv).unlink(missing_ok=True)

    assert "존재하지 않는 컬럼" in str(exc_info.value)


def test_preprocessing_wide_format_timestamp_and_stable_sort():
    """preprocess_with_plan normalizes timestamp and stably sorts by [id_column, time_column]."""
    df = pd.DataFrame({
        "asset_id": ["M002", "M001", "M001"],
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 02:00:00", "2026-01-01 01:00:00"],
        "temperature": [62.1, 58.0, 55.2],
    })
    plan = {
        "structure_type": "tabular_column_as_attribute",
        "selected_columns": ["asset_id", "timestamp", "temperature"],
        "id_column": "asset_id",
        "time_column": "timestamp",
        "duplicate_policy": "error",
    }

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        df.to_csv(f.name, index=False)
        tmp_csv = f.name
    try:
        processed_df = preprocess_with_plan(tmp_csv, plan)
    finally:
        Path(tmp_csv).unlink(missing_ok=True)

    # Check stable sorting: M001 at 01:00, M001 at 02:00, M002 at 00:00
    assert processed_df["asset_id"].tolist() == ["M001", "M001", "M002"]
    assert pd.api.types.is_datetime64_any_dtype(processed_df["timestamp"])
    assert processed_df["temperature"].tolist() == [55.2, 58.0, 62.1]


def test_preprocessing_idempotency_key_removed_fails_422(client, sample_wide_csv):
    """Sending removed idempotency_key in request payload fails fast (422 extra forbid)."""
    payload = {
        "dataset_id": "test_idem",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "idempotency_key": "any-key-value",
    }
    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


def test_preprocessing_corrupted_latest_fails_fast(client, sample_wide_csv, tmp_path, monkeypatch):
    """Corrupted latest.json or checksum mismatch raises DatasetContractError instead of silent recreation."""
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    payload = {
        "dataset_id": "corrupt_ds",
        "dataset_version": "v1.0",
        "source_uri": sample_wide_csv,
        "force_reanalyze": True,
    }
    res1 = client.post("/preprocessing", json=payload)
    assert res1.status_code == 200

    # Tamper with the plan file
    plan_dir = models_store / "cache" / "preprocessing_plans" / "corrupt_ds" / "v1.0"
    latest_file = plan_dir / "latest.json"
    with open(latest_file, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    plan_file = plan_dir / latest_data["path"]
    with open(plan_file, "w", encoding="utf-8") as f:
        f.write('{"tampered": true}')

    # Now call with force_reanalyze=False -> must detect checksum corruption
    payload_reuse = {**payload, "force_reanalyze": False}
    res_tampered = client.post("/preprocessing", json=payload_reuse)
    assert res_tampered.status_code == 422
    assert res_tampered.json()["error"]["code"] == "DATASET_CONTRACT_ERROR"


# ==========================================
# 7. Planner Provenance & Schema Fingerprint Unit Tests
# ==========================================

def test_source_schema_fingerprint_computation_and_invariance():
    """Schema fingerprint remains unchanged when sensor values change, but changes on column alterations."""
    df1 = pd.DataFrame({
        "id": ["A1", "A2"],
        "ts": ["2026-01-01", "2026-01-02"],
        "val": [10.5, 20.5],
    })
    fp1 = compute_source_schema_fingerprint(df1)
    assert len(fp1) == 64

    # 1. Values change -> same fingerprint
    df2 = pd.DataFrame({
        "id": ["B99", "B100"],
        "ts": ["2026-05-01", "2026-05-02"],
        "val": [999.9, -12.3],
    })
    assert compute_source_schema_fingerprint(df2) == fp1

    # 2. Add column -> different
    df_add = df1.copy()
    df_add["extra"] = [1, 2]
    assert compute_source_schema_fingerprint(df_add) != fp1

    # 3. Drop column -> different
    assert compute_source_schema_fingerprint(df1[["id", "val"]]) != fp1

    # 4. Reorder columns -> different
    assert compute_source_schema_fingerprint(df1[["val", "ts", "id"]]) != fp1

    # 5. Rename column -> different
    df_rename = df1.rename(columns={"val": "value"})
    assert compute_source_schema_fingerprint(df_rename) != fp1


def test_planner_provenance_llm_success_and_fallback_tracking(monkeypatch, sample_wide_csv):
    """Planner records decision_source='llm' when LLM succeeds, and 'rule_fallback' with sanitized reason on failure."""
    from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner
    import systems.generator.generator_llm_client as generator_llm_client

    planner = PreprocessingPlanner()
    filepath = str(PATHS.data_dir / sample_wide_csv)

    # 1. Normal fallback when no API key (rule_fallback)
    plan_fallback = planner.build_plan(filepath)
    assert plan_fallback["decision_source"] == "rule_fallback"
    assert "stage1:" in plan_fallback["fallback_reason"]
    assert "stage2:" in plan_fallback["fallback_reason"]
    assert plan_fallback["planner_version"] == PLANNER_VERSION

    # 2. Mock LLM success
    def mock_call_llm(prompt, system=None):
        if "classifier" in (system or ""):
            return '{"structure_type": "tabular_column_as_attribute", "reason": "ok"}'
        return '{"structure_type": "tabular_column_as_attribute", "selected_columns": ["asset_id", "timestamp", "temperature", "vibration"], "id_column": "asset_id", "time_column": "timestamp"}'

    monkeypatch.setattr(generator_llm_client, "call_llm", mock_call_llm)
    plan_llm = planner.build_plan(filepath)
    assert plan_llm["decision_source"] == "llm"
    assert plan_llm["fallback_reason"] is None
    assert plan_llm["planner_version"] == PLANNER_VERSION


def test_repository_validation_enforces_schema_fingerprint_and_provenance(tmp_path):
    """Repository strictly validates presence and format of source_schema_fingerprint and planner provenance."""
    models_store = tmp_path / "models_store"
    repo = PreprocessingRepository(base_dir=models_store / "cache" / "preprocessing_plans")

    plan_data = {
        "source_dataset_uri": "data/test.csv",
        "source_dataset_sha256": "a" * 64,
        "source_schema_fingerprint": "b" * 64,
        "decision_source": "llm",
        "fallback_reason": None,
        "planner_version": PLANNER_VERSION,
        "structure_type": "tabular_column_as_attribute",
        "selected_columns": ["id", "val"],
        "duplicate_policy": "error",
    }

    # 1. Valid publish
    published = repo.publish_plan("ds_test", "v1.0", plan_data)
    assert published.preprocessing_plan_id.startswith("pp-")

    # 2. Missing source_schema_fingerprint raises PreprocessingPlanPublishError
    bad_plan = {**plan_data, "source_schema_fingerprint": None}
    with pytest.raises(PreprocessingPlanPublishError):
        repo.publish_plan("ds_test", "v1.0", bad_plan)


# ==========================================
# 8. Atomicity & Failure Isolation
# ==========================================

def test_preprocessing_full_execution_failure_prevents_plan_publishing(client, tmp_path, monkeypatch):
    """If full dataset execution fails after preview/validation, plan and latest pointer must NOT be published."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(PATHS, "data_dir", data_dir)
    monkeypatch.setattr(PATHS, "data_preprocessed", data_dir)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    # Create dataset where first 5 rows are valid, but row 6 has duplicate (id, time)
    rows = []
    for i in range(5):
        rows.append({"asset_id": "M1", "timestamp": f"2026-01-01 0{i}:00:00", "voltage": 220.0 + i, "rotation": 1500.0})
    rows.append({"asset_id": "M1", "timestamp": "2026-01-01 04:00:00", "voltage": 999.0, "rotation": 9999.0})
    df_dup = pd.DataFrame(rows)

    dup_file = data_dir / "dup_test.csv"
    df_dup.to_csv(dup_file, index=False)

    payload = {
        "dataset_id": "dup_test",
        "dataset_version": "v1.0",
        "source_uri": "dup_test.csv",
        "force_reanalyze": True,
        "duplicate_policy": "error",
    }

    res = client.post("/preprocessing", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert data["error"]["code"] in ("PREPROCESSING_PLANNING_ERROR", "DATASET_CONTRACT_ERROR")

    # Verify no plan directory or files created
    plan_dir = models_store / "cache" / "preprocessing_plans" / "dup_test" / "v1.0"
    assert not plan_dir.exists()


# ==========================================
# 9. App Factory & Migration Verification
# ==========================================

def test_generator_app_factory_and_compatibility():
    """Verify app factory create_app, endpoint registration, and generator_main compatibility shim."""
    from systems.generator.app.main import app as canonical_app, create_app as factory_create_app
    from systems.generator.generator_main import app as legacy_app

    # 1. Repeatable create_app
    app2 = factory_create_app()
    assert app2 is not None
    assert app2.title == "Generator Domain API"

    # 2. Both canonical app and legacy app have /health, /preprocessing, /internal/train, /internal/retrain
    c_client = TestClient(canonical_app)
    l_client = TestClient(legacy_app)

    for tc in (c_client, l_client):
        assert tc.get("/health").status_code == 200
        # Check endpoints exist (422 validation on empty post proves route exists)
        assert tc.post("/preprocessing", json={}).status_code == 422
        assert tc.post("/internal/train", json={"force_reanalyze": "invalid"}).status_code == 422
        assert tc.post("/internal/retrain", json={"force_reanalyze": "invalid"}).status_code == 422


def test_preprocessing_endpoint_is_synchronous():
    """Verify post_preprocessing route endpoint is a regular sync def for threadpool execution."""
    from systems.generator.app.preprocessing.preprocessing_router import post_preprocessing
    assert not inspect.iscoroutinefunction(post_preprocessing)


def test_legacy_extraction_facade_compatibility(sample_wide_csv):
    """Verify legacy systems.generator.extraction import facades delegate correctly to preprocessing."""
    from systems.generator.extraction import (
        load_all_sources as legacy_load_all,
        extract_with_plan as legacy_extract_with_plan,
        build_extraction_plan as legacy_build_plan,
    )

    actual_file = str(PATHS.data_dir / sample_wide_csv)
    plan = legacy_build_plan(actual_file)
    assert "structure_type" in plan
    assert "selected_columns" in plan

    df = legacy_extract_with_plan(actual_file, plan)
    assert not df.empty
    assert len(df) == 3


# ==========================================
# 10. Structure Type Allowlist & Rejection Tests
# ==========================================

def test_structure_type_allowlist_and_pydantic_validation():
    """Pydantic schemas and models strictly reject unsupported structure_type values."""
    from pydantic import ValidationError
    from systems.generator.app.preprocessing.preprocessing_schema import (
        PreprocessingStructureResponse,
        PreprocessingPlanResponse,
        PreprocessingResultPayload,
    )

    # 1. Valid structure types pass
    s1 = PreprocessingStructureResponse(structure_type="tabular_column_as_attribute")
    assert s1.structure_type == "tabular_column_as_attribute"

    s2 = PreprocessingStructureResponse(structure_type="tabular_row_as_attribute")
    assert s2.structure_type == "tabular_row_as_attribute"

    # 2. Unsupported structure types fail validation
    for bad_st in ("wide_pivot", "unsupported", "matrix_format", ""):
        with pytest.raises(ValidationError):
            PreprocessingStructureResponse(structure_type=bad_st)

        with pytest.raises(ValidationError):
            PreprocessingPlanResponse(structure_type=bad_st)

        with pytest.raises(ValidationError):
            PreprocessingResultPayload(
                structure_type=bad_st,
                preprocessing_plan_uri="models_store/plan.json",
                preprocessing_plan_sha256="a" * 64,
            )


def test_structure_type_unsupported_fails_422_in_service(sample_wide_csv):
    """preprocess_with_plan raises PreprocessingPlanValidationError (422) on unsupported structure_type."""
    actual_file = str(PATHS.data_dir / sample_wide_csv)

    for bad_st in ("wide_pivot", "unsupported", "custom_format"):
        plan = {
            "structure_type": bad_st,
            "selected_columns": ["asset_id"],
        }
        with pytest.raises(PreprocessingPlanValidationError) as exc_info:
            preprocess_with_plan(actual_file, plan)
        assert "지원하지 않는 structure_type" in str(exc_info.value)


def test_repository_rejects_unsupported_structure_type(tmp_path):
    """Repository._validate_plan_content rejects unsupported structure_type with DatasetContractError."""
    models_store = tmp_path / "models_store"
    repo = PreprocessingRepository(base_dir=models_store / "cache" / "preprocessing_plans")

    for bad_st in ("wide_pivot", "unsupported", "invalid_type"):
        bad_plan = {
            "preprocessing_plan_id": "pp-00000000-0000-0000-0000-000000000001",
            "preprocessing_plan_version": "preprocessing-plan-0123456789abcdef",
            "dataset_id": "ds_test",
            "dataset_version": "v1.0",
            "source_dataset_uri": "data/test.csv",
            "source_dataset_sha256": "a" * 64,
            "source_schema_fingerprint": "b" * 64,
            "decision_source": "llm",
            "fallback_reason": None,
            "planner_version": PLANNER_VERSION,
            "structure_type": bad_st,
            "selected_columns": ["col1"],
            "duplicate_policy": "error",
        }
        with pytest.raises((DatasetContractError, PreprocessingPlanPublishError)) as exc_info:
            repo._validate_plan_content(bad_plan, "ds_test", "v1.0")
        assert "지원하지 않는 structure_type" in str(exc_info.value)

        with pytest.raises((DatasetContractError, PreprocessingPlanPublishError)):
            repo.publish_plan("ds_test", "v1.0", bad_plan)


# ==========================================
# 11. Logical URI Fail-Closed & Security Tests
# ==========================================

def test_logical_uri_fail_closed_and_sanitization(tmp_path, monkeypatch):
    """get_logical_uri converts paths within allowed roots and fails closed on outside paths."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    models_store = tmp_path / "models_store"
    models_store.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(PATHS, "data_dir", data_dir)
    monkeypatch.setattr(PATHS, "models_store", models_store)

    repo = PreprocessingRepository(base_dir=models_store / "cache" / "preprocessing_plans")

    # 1. Inside data_dir -> data/...
    sample_data = data_dir / "cnc" / "sample.csv"
    sample_data.parent.mkdir(parents=True, exist_ok=True)
    sample_data.touch()
    uri_data = repo.get_logical_uri(sample_data)
    assert uri_data.startswith("data/") or uri_data.endswith("sample.csv")
    assert not uri_data.startswith("C:")
    assert not uri_data.startswith("/")
    assert ".." not in uri_data

    # 2. Inside models_store -> models_store/...
    sample_plan = models_store / "cache" / "plan.json"
    sample_plan.parent.mkdir(parents=True, exist_ok=True)
    sample_plan.touch()
    uri_plan = repo.get_logical_uri(sample_plan)
    assert uri_plan.startswith("models_store/") or uri_plan.endswith("plan.json")
    assert not uri_plan.startswith("C:")
    assert not uri_plan.startswith("/")
    assert ".." not in uri_plan

    # 3. Path outside all allowed roots -> DatasetContractError (Fail-Closed)
    outside_dir = tmp_path / "completely_outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "secret_data.csv"
    outside_file.touch()

    # Clear CWD containment by creating a separate unrelated path
    with pytest.raises(DatasetContractError) as exc_info:
        # Pass path that cannot resolve into cwd, data_dir, or models_store
        repo.get_logical_uri(Path("Z:/outside_drive/forbidden_data.csv") if os.name == "nt" else Path("/opt/forbidden/data.csv"))

    err_msg = str(exc_info.value)
    assert "논리 URI로 변환할 수 없는 허용 범위 밖의 경로" in err_msg
    # Ensure full absolute path is not leaked (only filename)
    assert "Z:\\" not in err_msg
    assert "/opt/forbidden" not in err_msg
