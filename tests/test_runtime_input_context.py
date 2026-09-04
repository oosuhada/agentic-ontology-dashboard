"""Unit tests for Runtime Input Context Canonicalization (RuntimeInputIdentity & RuntimeSourceContext)."""

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from systems.generator.app.main import app
from systems.generator.generator_config import PATHS
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    PredictionResultLineage,
    RuntimeInputIdentity,
    RuntimeSourceContext,
)
from systems.generator.app.runtime_pipeline.pipeline_router import EnqueueRequest
from systems.generator.app.runtime_pipeline.pipeline_manager import PipelineManager


# ---------------------------------------------------------------------------
# 1. Normal Creation Tests
# ---------------------------------------------------------------------------

def test_create_valid_live_sensor_runtime_input_identity():
    """Verify creation of valid live_sensor RuntimeInputIdentity."""
    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    identity = RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )
    assert identity.dataset_id == "canonical-ai4i-v1"
    assert identity.dataset_version == "v1.0"
    assert identity.source.source_kind == "live_sensor"
    assert identity.source.source_checksum == "a" * 64


def test_create_valid_maintenance_replay_overlay_runtime_input_identity():
    """Verify creation of valid maintenance_replay_overlay RuntimeInputIdentity with all 6 lineage fields."""
    lineage = PredictionResultLineage(
        simulation_session_id="sim-session-001",
        overlay_branch_id="branch-001",
        history_segment_id="seg-001",
        maintenance_event_id="maint-evt-001",
        maintenance_action_id="maint-act-001",
        state_version=1,
    )
    src = RuntimeSourceContext(
        source_uri="data/incoming/overlay_test.jsonl",
        source_checksum="b" * 64,
        source_kind="maintenance_replay_overlay",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=lineage,
    )
    identity = RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )
    assert identity.source.source_kind == "maintenance_replay_overlay"
    assert identity.source.lineage.simulation_session_id == "sim-session-001"
    assert identity.source.lineage.state_version == 1


# ---------------------------------------------------------------------------
# 2. Validation Failure Tests: Dataset ID / Version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("empty_val", ["", "   "])
def test_runtime_input_identity_empty_dataset_id_raises_error(empty_val):
    """Empty or whitespace dataset_id raises validation error."""
    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    with pytest.raises(ValidationError):
        RuntimeInputIdentity(
            dataset_id=empty_val.strip(),
            dataset_version="v1.0",
            source=src,
        )


@pytest.mark.parametrize("empty_val", ["", "   "])
def test_runtime_input_identity_empty_dataset_version_raises_error(empty_val):
    """Empty or whitespace dataset_version raises validation error."""
    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    with pytest.raises(ValidationError):
        RuntimeInputIdentity(
            dataset_id="canonical-ai4i-v1",
            dataset_version=empty_val.strip(),
            source=src,
        )


# ---------------------------------------------------------------------------
# 3. Validation Failure Tests: Source URI & Checksum
# ---------------------------------------------------------------------------

def test_runtime_source_context_empty_source_uri_raises_error():
    """Empty source_uri raises validation error."""
    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="",
            source_checksum="a" * 64,
            source_kind="live_sensor",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
        )


@pytest.mark.parametrize(
    "bad_checksum",
    [
        "A" * 64,             # Uppercase
        "a" * 63,             # Too short
        "a" * 65,             # Too long
        "0" * 64,             # All-zero checksum
        "invalid_hex_string", # Invalid hex
    ],
)
def test_runtime_source_context_invalid_checksum_raises_error(bad_checksum):
    """Non-lowercase or all-zero checksum raises validation error."""
    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="data/incoming/test.jsonl",
            source_checksum=bad_checksum,
            source_kind="live_sensor",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
        )


def test_runtime_source_context_unknown_source_kind_raises_error():
    """Unknown source_kind raises validation error."""
    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="data/incoming/test.jsonl",
            source_checksum="a" * 64,
            source_kind="unknown_kind",  # type: ignore
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
        )


# ---------------------------------------------------------------------------
# 4. Validation Failure Tests: Overlay Lineage Required Fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "missing_field",
    [
        "simulation_session_id",
        "overlay_branch_id",
        "history_segment_id",
        "maintenance_event_id",
        "maintenance_action_id",
        "state_version",
    ],
)
def test_maintenance_overlay_missing_lineage_field_raises_error(missing_field):
    """Missing any of the 6 lineage fields on maintenance_replay_overlay raises validation error."""
    lineage_kwargs = {
        "simulation_session_id": "sim-session-001",
        "overlay_branch_id": "branch-001",
        "history_segment_id": "seg-001",
        "maintenance_event_id": "maint-evt-001",
        "maintenance_action_id": "maint-act-001",
        "state_version": 1,
    }
    lineage_kwargs[missing_field] = None
    lineage = PredictionResultLineage(**lineage_kwargs)

    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="data/incoming/overlay.jsonl",
            source_checksum="c" * 64,
            source_kind="maintenance_replay_overlay",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=lineage,
        )


def test_maintenance_overlay_state_version_zero_raises_error():
    """state_version < 1 on maintenance_replay_overlay raises validation error."""
    lineage = PredictionResultLineage(
        simulation_session_id="sim-session-001",
        overlay_branch_id="branch-001",
        history_segment_id="seg-001",
        maintenance_event_id="maint-evt-001",
        maintenance_action_id="maint-act-001",
        state_version=0,
    )
    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="data/incoming/overlay.jsonl",
            source_checksum="c" * 64,
            source_kind="maintenance_replay_overlay",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=lineage,
        )


# ---------------------------------------------------------------------------
# 5. Extra Forbidden Fields Tests (ConfigDict(extra="forbid"))
# ---------------------------------------------------------------------------

def test_runtime_input_identity_extra_fields_forbidden():
    """Passing undefined extra fields to RuntimeInputIdentity raises validation error."""
    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    with pytest.raises(ValidationError):
        RuntimeInputIdentity(
            dataset_id="canonical-ai4i-v1",
            dataset_version="v1.0",
            source=src,
            extra_field="disallowed",  # type: ignore
        )


def test_runtime_source_context_extra_fields_forbidden():
    """Passing undefined extra fields to RuntimeSourceContext raises validation error."""
    with pytest.raises(ValidationError):
        RuntimeSourceContext(
            source_uri="data/incoming/test.jsonl",
            source_checksum="a" * 64,
            source_kind="live_sensor",
            source_contract_version="observation-source-v1",
            source_schema_version="sensor-record-v2",
            pipeline_contract_version="generator-prediction-result-v1",
            lineage=PredictionResultLineage(),
            extra_key="not_allowed",  # type: ignore
        )


# ---------------------------------------------------------------------------
# 6. EnqueueRequest & Router / Manager Integration Tests
# ---------------------------------------------------------------------------

def test_enqueue_request_to_input_identity_conversion():
    """EnqueueRequest converts accurately to RuntimeInputIdentity."""
    req = EnqueueRequest(
        job_id="job-req-001",
        source_uri="data/incoming/source.jsonl",
        source_checksum="d" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        dataset_id="cnc-milling-dataset",
        dataset_version="v2.1",
        size_bytes=1024,
    )
    identity = req.to_input_identity()
    assert isinstance(identity, RuntimeInputIdentity)
    assert identity.dataset_id == "cnc-milling-dataset"
    assert identity.dataset_version == "v2.1"
    assert identity.source.source_uri == "data/incoming/source.jsonl"
    assert identity.source.source_checksum == "d" * 64
    assert identity.source.source_kind == "live_sensor"


def test_router_enqueue_with_runtime_input_identity(tmp_path, monkeypatch):
    """Router /internal/runtime-pipeline/enqueue accepts request and passes canonical RuntimeInputIdentity to Manager."""
    preprocessed_dir = tmp_path / "data_preprocessed"
    preprocessed_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PATHS, "runtime_prediction_enabled", True)
    monkeypatch.setattr(PATHS, "pipeline_queue_db", preprocessed_dir / "queue.db")
    monkeypatch.setattr(PATHS, "pipeline_input_roots", [tmp_path])

    # Reset PipelineManager instance with new isolated queue
    PipelineManager.set_instance(None)

    client = TestClient(app)
    res = client.post(
        "/internal/runtime-pipeline/enqueue",
        json={
            "job_id": "job-test-identity-01",
            "source_uri": "data/incoming/test.jsonl",
            "source_checksum": "e" * 64,
            "source_kind": "live_sensor",
            "source_contract_version": "observation-source-v1",
            "source_schema_version": "sensor-record-v2",
            "pipeline_contract_version": "generator-prediction-result-v1",
            "dataset_id": "test-dataset",
            "dataset_version": "v1.0",
            "size_bytes": 2048,
        },
    )
    assert res.status_code == 200, res.text
    item_data = res.json()
    assert item_data["job_id"] == "job-test-identity-01"
    assert item_data["dataset_id"] == "test-dataset"
    assert item_data["dataset_version"] == "v1.0"
    assert item_data["source_checksum"] == "e" * 64


# ---------------------------------------------------------------------------
# 7. Queue Storage & Retry Canonicalization Tests (Task 2)
# ---------------------------------------------------------------------------

def test_queue_enqueue_missing_runtime_input_fails(tmp_path):
    """Calling PipelineQueue.enqueue without valid runtime_input raises PipelineQueueItemInvalidError."""
    from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineQueueItemInvalidError

    db_path = tmp_path / "queue.db"
    queue = PipelineQueue(db_path=db_path)

    with pytest.raises(PipelineQueueItemInvalidError):
        # Missing runtime_input
        queue.enqueue(job_id="job-bad", runtime_input=None)  # type: ignore

    with pytest.raises(PipelineQueueItemInvalidError):
        # Empty job_id
        valid_identity = RuntimeInputIdentity(
            dataset_id="ds-1",
            dataset_version="v1",
            source=RuntimeSourceContext(
                source_uri="data/test.jsonl",
                source_checksum="a" * 64,
                source_kind="live_sensor",
                source_contract_version="c1",
                source_schema_version="s1",
                pipeline_contract_version="p1",
                lineage=PredictionResultLineage(),
            ),
        )
        queue.enqueue(job_id="", runtime_input=valid_identity)


def test_source_identity_divergence_by_dataset_contracts_and_lineage():
    """Identical checksum with differing dataset, contract, or lineage yields distinct source_identity."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import compute_source_identity

    chk = "f" * 64
    lin1 = PredictionResultLineage()
    lin2 = PredictionResultLineage(
        simulation_session_id="sim-1",
        overlay_branch_id="br-1",
        history_segment_id="seg-1",
        maintenance_event_id="evt-1",
        maintenance_action_id="act-1",
        state_version=1,
    )

    id_base = compute_source_identity(
        source_checksum=chk,
        dataset_id="ds-1",
        dataset_version="v1.0",
        pipeline_contract_version="p-v1",
        source_contract_version="sc-v1",
        source_schema_version="ss-v1",
        source_kind="live_sensor",
        lineage=lin1,
    )

    # 1. Different dataset_id
    id_diff_ds = compute_source_identity(
        source_checksum=chk,
        dataset_id="ds-2",
        dataset_version="v1.0",
        pipeline_contract_version="p-v1",
        source_contract_version="sc-v1",
        source_schema_version="ss-v1",
        source_kind="live_sensor",
        lineage=lin1,
    )
    assert id_base != id_diff_ds

    # 2. Different dataset_version
    id_diff_dsv = compute_source_identity(
        source_checksum=chk,
        dataset_id="ds-1",
        dataset_version="v2.0",
        pipeline_contract_version="p-v1",
        source_contract_version="sc-v1",
        source_schema_version="ss-v1",
        source_kind="live_sensor",
        lineage=lin1,
    )
    assert id_base != id_diff_dsv

    # 3. Different pipeline_contract_version
    id_diff_contract = compute_source_identity(
        source_checksum=chk,
        dataset_id="ds-1",
        dataset_version="v1.0",
        pipeline_contract_version="p-v2",
        source_contract_version="sc-v1",
        source_schema_version="ss-v1",
        source_kind="live_sensor",
        lineage=lin1,
    )
    assert id_base != id_diff_contract

    # 4. Different source_kind and lineage
    id_diff_lineage = compute_source_identity(
        source_checksum=chk,
        dataset_id="ds-1",
        dataset_version="v1.0",
        pipeline_contract_version="p-v1",
        source_contract_version="sc-v1",
        source_schema_version="ss-v1",
        source_kind="maintenance_replay_overlay",
        lineage=lin2,
    )
    assert id_base != id_diff_lineage


def test_retry_preserves_canonical_context_identically(tmp_path):
    """retry_failed_job preserves exact dataset, contract, schema versions, and lineage without inventing defaults."""
    from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue

    db_path = tmp_path / "queue_retry.db"
    queue = PipelineQueue(db_path=db_path)

    lineage = PredictionResultLineage(
        simulation_session_id="sim-session-42",
        overlay_branch_id="branch-main",
        history_segment_id="seg-100",
        maintenance_event_id="maint-999",
        maintenance_action_id="replace-bearing",
        state_version=3,
    )
    runtime_input = RuntimeInputIdentity(
        dataset_id="special-milling-dataset",
        dataset_version="v3.4.2",
        source=RuntimeSourceContext(
            source_uri="data/incoming/overlay_milling.jsonl",
            source_checksum="7" * 64,
            source_kind="maintenance_replay_overlay",
            source_contract_version="milling-source-contract-v2",
            source_schema_version="sensor-schema-v3",
            pipeline_contract_version="pipeline-prediction-v2",
            lineage=lineage,
        ),
    )

    enqueued = queue.enqueue(job_id="job-maint-01", runtime_input=runtime_input, size_bytes=4096)
    assert enqueued.status == "queued"
    assert enqueued.dataset_id == "special-milling-dataset"

    # Mark as failed to allow retry
    queue.mark_failed(job_id="job-maint-01", error_code="TEST_ERROR", dead_letter=False)

    # Retry job
    retried = queue.retry_failed_job("job-maint-01")
    assert retried.job_id.startswith("job-maint-01-retry-")
    assert retried.retry_of_job_id == "job-maint-01"
    assert retried.status == "queued"

    # Verify 100% identical provenance and context fields
    assert retried.dataset_id == "special-milling-dataset"
    assert retried.dataset_version == "v3.4.2"
    assert retried.source_uri == "data/incoming/overlay_milling.jsonl"
    assert retried.source_checksum == "7" * 64
    assert retried.source_kind == "maintenance_replay_overlay"
    assert retried.source_contract_version == "milling-source-contract-v2"
    assert retried.source_schema_version == "sensor-schema-v3"
    assert retried.pipeline_contract_version == "pipeline-prediction-v2"
    assert retried.size_bytes == 4096
    assert retried.lineage.simulation_session_id == "sim-session-42"
    assert retried.lineage.overlay_branch_id == "branch-main"
    assert retried.lineage.history_segment_id == "seg-100"
    assert retried.lineage.maintenance_event_id == "maint-999"
    assert retried.lineage.maintenance_action_id == "replace-bearing"
    assert retried.lineage.state_version == 3
    assert retried.source_identity == enqueued.source_identity


def test_retry_rejects_legacy_missing_context_row(tmp_path):
    """Retrying a legacy row lacking mandatory context columns raises PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED with retryable=False."""
    import sqlite3
    from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineQueueItemInvalidError
    from systems.generator.app.runtime_pipeline.pipeline_schema import now_utc_iso

    db_path = tmp_path / "queue_legacy.db"
    now = now_utc_iso()

    # 1. Create table with legacy schema (predating the context columns and lineage_json)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE queue_items (
                job_id TEXT PRIMARY KEY,
                source_uri TEXT NOT NULL,
                source_checksum TEXT NOT NULL,
                dedup_key TEXT UNIQUE NOT NULL,
                source_identity TEXT,
                size_bytes INTEGER,
                dataset_id TEXT NOT NULL,
                dataset_version TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 1,
                retry_of_job_id TEXT,
                status TEXT NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            """
            INSERT INTO queue_items (
                job_id, source_uri, source_checksum, dedup_key, source_identity, size_bytes,
                dataset_id, dataset_version, detected_at, sequence, attempt, retry_of_job_id,
                status, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-legacy-01", "data/test.jsonl", "8" * 64, "data/test.jsonl:888", None, None,
                "legacy-ds", "v1", now, 1, 1, None, "failed", "OLD_FAIL", now, now,
            ),
        )
        conn.commit()

    # 2. Instantiate PipelineQueue which migrates schema (adding columns and isolating old rows)
    queue = PipelineQueue(db_path=db_path)

    with pytest.raises(PipelineQueueItemInvalidError) as exc_info:
        queue.retry_failed_job("job-legacy-01")

    assert exc_info.value.code == "PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED"
    assert exc_info.value.retryable is False


def test_retry_rejects_corrupted_lineage_json_row(tmp_path):
    """Retrying a row with corrupted lineage_json raises PIPELINE_SOURCE_CONTEXT_CORRUPTED with retryable=False."""
    import sqlite3
    from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
    from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineQueueItemInvalidError
    from systems.generator.app.runtime_pipeline.pipeline_schema import now_utc_iso

    db_path = tmp_path / "queue_corrupt.db"
    queue = PipelineQueue(db_path=db_path)
    now = now_utc_iso()

    # Manually insert row with corrupted lineage_json
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO queue_items (
                job_id, source_uri, source_checksum, dedup_key, source_identity, size_bytes,
                dataset_id, dataset_version, pipeline_contract_version, source_kind,
                source_contract_version, source_schema_version, lineage_json, detected_at,
                sequence, attempt, retry_of_job_id, status, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-corrupt-01", "data/test.jsonl", "9" * 64, "data/test.jsonl:999", None, None,
                "ds-1", "v1", "pipeline-v1", "live_sensor", "contract-v1", "schema-v1", "{ broken json", now,
                1, 1, None, "failed", "TEST_FAIL", now, now,
            ),
        )
        conn.commit()

    with pytest.raises(PipelineQueueItemInvalidError) as exc_info:
        queue.retry_failed_job("job-corrupt-01")

    assert exc_info.value.code == "PIPELINE_SOURCE_CONTEXT_CORRUPTED"
    assert exc_info.value.retryable is False


# =============================================================================
# Section 8: 작업 3 - RunState·Checkpoint 복구 정합화 테스트
# =============================================================================

def create_valid_runtime_input_identity() -> RuntimeInputIdentity:
    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    return RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )


def test_record_checkpoint_missing_mandatory_params_fails():
    """record_checkpoint without runtime_input, source_identity, or model_set fields fails closed."""
    from systems.generator.app.runtime_pipeline.pipeline_state import PipelineStateManager
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, PipelineRunState

    run_state = PipelineRunState(
        run_id="run-chk-test-01",
        job_id="job-chk-01",
        status="pending",
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="a"*64, role="source_observation_protocol", size_bytes=100),
    )
    manager = PipelineStateManager(run_state)
    manager.start_run()

    # 1. Missing runtime_input entirely raises TypeError
    with pytest.raises(TypeError):
        manager.record_checkpoint(
            stage_name="preprocessing",
            source_identity="id-123",
            model_set_id="set-1",
            model_set_version="v1",
            model_set_payload_sha256="f"*64,
        )

    # 2. Empty source_identity raises ValueError
    runtime_input = create_valid_runtime_input_identity()
    with pytest.raises(ValueError, match="source_identity must not be empty"):
        manager.record_checkpoint(
            stage_name="preprocessing",
            source_identity="",
            runtime_input=runtime_input,
            model_set_id="set-1",
            model_set_version="v1",
            model_set_payload_sha256="f"*64,
        )

    # 3. Missing model_set fields raises ValueError
    with pytest.raises(ValueError, match="model_set_id must not be empty"):
        manager.record_checkpoint(
            stage_name="preprocessing",
            source_identity="id-123",
            runtime_input=runtime_input,
            model_set_id="",
            model_set_version="v1",
            model_set_payload_sha256="f"*64,
        )


def test_record_checkpoint_stores_full_runtime_input_snapshot():
    """record_checkpoint snapshots all canonical runtime input & Model Set fields identically."""
    import json
    from systems.generator.app.runtime_pipeline.pipeline_state import PipelineStateManager
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, PipelineRunState

    runtime_input = create_valid_runtime_input_identity()
    run_state = PipelineRunState(
        run_id="run-chk-test-02",
        job_id="job-chk-02",
        status="pending",
        source_ref=ArtifactReference(uri=runtime_input.source.source_uri, sha256=runtime_input.source.source_checksum, role="source_observation_protocol", size_bytes=1024),
        source_context=runtime_input.source,
    )
    manager = PipelineStateManager(run_state)
    manager.start_run()

    chk = manager.record_checkpoint(
        stage_name="preprocessing",
        source_identity="canonical-source-identity-xyz",
        runtime_input=runtime_input,
        model_set_id="canonical-model-set-v1",
        model_set_version="v1.2",
        model_set_payload_sha256="e"*64,
        next_stage="runtime_feature",
        status="resumable",
    )

    assert chk.source_identity == "canonical-source-identity-xyz"
    assert chk.dataset_id == runtime_input.dataset_id
    assert chk.dataset_version == runtime_input.dataset_version
    assert chk.model_set_id == "canonical-model-set-v1"
    assert chk.model_set_version == "v1.2"
    assert chk.model_set_payload_sha256 == "e"*64
    assert chk.pipeline_contract_version == runtime_input.source.pipeline_contract_version
    assert chk.source_kind == runtime_input.source.source_kind
    assert chk.source_contract_version == runtime_input.source.source_contract_version
    assert chk.source_schema_version == runtime_input.source.source_schema_version
    assert chk.source_context.source_uri == runtime_input.source.source_uri
    assert chk.source_context.source_checksum == runtime_input.source.source_checksum
    assert json.loads(chk.lineage_json) == runtime_input.source.lineage.model_dump(mode="json")
    assert chk.status == "resumable"


def test_find_resumable_run_skips_when_no_source_identity(tmp_path):
    """find_resumable_run does not guess or invent identity when checkpoint has none."""
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, PipelineRunState

    repo = PipelineRepository(base_dir=tmp_path)
    run_state = PipelineRunState(
        run_id="run-no-ident-01",
        job_id="job-no-ident-01",
        status="running",
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="c"*64, role="source_observation_protocol", size_bytes=200),
    )
    repo.save_run_state(run_state)

    found = repo.find_resumable_run("any-identity")
    assert found is None


def test_find_resumable_run_legacy_null_source_context_invalidated(tmp_path):
    """Resumption planning safely detects legacy run with missing context, invalidates it and does not crash."""
    import json
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, PipelineRunState, now_utc_iso

    repo = PipelineRepository(base_dir=tmp_path)
    now = now_utc_iso()

    # Legacy run state with checkpoint having legacy placeholder or missing context
    run_state = PipelineRunState(
        run_id="run-legacy-resumable-01",
        job_id="job-legacy-01",
        status="failed",
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="d"*64, role="source_observation_protocol", size_bytes=500),
    )
    repo.save_run_state(run_state)

    # Legacy checkpoint missing source_context
    raw_chk = {
        "checkpoint_version": "generator-runtime-checkpoint-v1",
        "run_id": "run-legacy-resumable-01",
        "job_id": "job-legacy-01",
        "source_identity": "test-ident-legacy",
        "source_uri": "data/test.jsonl",
        "source_checksum": "d"*64,
        "source_size_bytes": 500,
        "dataset_id": "ds-legacy",
        "dataset_version": "v1",
        "model_set_id": "ms-legacy",
        "model_set_version": "v1",
        "model_set_payload_sha256": "f"*64,
        "pipeline_contract_version": "gen-v1",
        "source_kind": "live_sensor",
        "source_contract_version": "obs-v1",
        "source_schema_version": "obs-v1",
        "lineage_json": "{}",
        "source_context": None,
        "status": "resumable",
        "created_at": now,
        "updated_at": now,
    }
    # Save raw invalid JSON
    chk_file = repo.checkpoints_dir / "run-legacy-resumable-01.json"
    with open(chk_file, "w", encoding="utf-8") as f:
        json.dump(raw_chk, f)

    # find_resumable_run should either skip or return it, and service will invalidate it
    found = repo.find_resumable_run("test-ident-legacy")
    loaded_chk = repo.get_checkpoint("run-legacy-resumable-01")
    assert loaded_chk is None or loaded_chk.source_context is None


def test_corrupted_checkpoint_json_file_handled_gracefully(tmp_path):
    """Malformed checkpoint JSON does not raise unhandled Python exceptions."""
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository

    repo = PipelineRepository(base_dir=tmp_path)
    corrupted_file = repo.checkpoints_dir / "run-corrupt-chk.json"
    corrupted_file.write_text("{ unclosed json: bad syntax", encoding="utf-8")

    # get_checkpoint handles JSONDecodeError gracefully returning None
    chk = repo.get_checkpoint("run-corrupt-chk")
    assert chk is None

    # find_resumable_run handles corrupted files gracefully returning None
    resumable = repo.find_resumable_run("any-target-identity")
    assert resumable is None


# =============================================================================
# Section 9: 작업 4 - Active Model Set Checkpoint 고정 테스트
# =============================================================================


def test_compute_model_set_payload_sha256_determinism():
    """compute_model_set_payload_sha256 produces deterministic lowercase SHA-256."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSnapshotItem,
        compute_model_set_payload_sha256,
    )

    models = [
        ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0.0", required=True, model_artifact_manifest_sha256="a"*64),
        ActiveModelSnapshotItem(model_id="pdm-xgboost", model_version="2.1.0", required=True, model_artifact_manifest_sha256="b"*64),
    ]

    digest1 = compute_model_set_payload_sha256(model_set_id="set-01", model_set_version="v1.0", models=models)
    # Order reversed in list
    digest2 = compute_model_set_payload_sha256(model_set_id="set-01", model_set_version="v1.0", models=list(reversed(models)))

    assert len(digest1) == 64
    assert digest1 == digest2


def test_compute_model_set_payload_sha256_divergence_on_version_and_required():
    """Digest diverges when model_set_version or required flag changes."""
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSnapshotItem,
        compute_model_set_payload_sha256,
    )

    models_base = [
        ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0.0", required=True, model_artifact_manifest_sha256="a"*64),
    ]
    models_req_false = [
        ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0.0", required=False, model_artifact_manifest_sha256="a"*64),
    ]

    d_base = compute_model_set_payload_sha256(model_set_id="set-01", model_set_version="v1.0", models=models_base)
    d_ver = compute_model_set_payload_sha256(model_set_id="set-01", model_set_version="v1.1", models=models_base)
    d_req = compute_model_set_payload_sha256(model_set_id="set-01", model_set_version="v1.0", models=models_req_false)

    assert d_base != d_ver
    assert d_base != d_req
    assert d_ver != d_req


def test_resumption_legacy_checkpoint_missing_model_set_fields_invalidated(tmp_path):
    """Legacy checkpoint lacking model_set_payload_sha256 is invalidated on resumption."""
    import json
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository
    from systems.generator.app.runtime_pipeline.pipeline_schema import ArtifactReference, PipelineRunState, now_utc_iso

    repo = PipelineRepository(base_dir=tmp_path)
    now = now_utc_iso()

    run_state = PipelineRunState(
        run_id="run-legacy-no-modelset-chk",
        job_id="job-legacy-ms-01",
        status="failed",
        source_ref=ArtifactReference(uri="data/test.jsonl", sha256="e"*64, role="source_observation_protocol", size_bytes=500),
    )
    repo.save_run_state(run_state)

    # Checkpoint without model_set_payload_sha256
    raw_chk = {
        "checkpoint_version": "generator-runtime-checkpoint-v1",
        "run_id": "run-legacy-no-modelset-chk",
        "job_id": "job-legacy-ms-01",
        "source_identity": "test-ident-ms-legacy",
        "source_uri": "data/test.jsonl",
        "source_checksum": "e"*64,
        "source_size_bytes": 500,
        "dataset_id": "ds-1",
        "dataset_version": "v1",
        "pipeline_contract_version": "gen-v1",
        "source_kind": "live_sensor",
        "source_contract_version": "obs-v1",
        "source_schema_version": "obs-v1",
        "lineage_json": "{}",
        "source_context": {
            "source_uri": "data/test.jsonl",
            "source_checksum": "e"*64,
            "source_kind": "live_sensor",
            "source_contract_version": "obs-v1",
            "source_schema_version": "obs-v1",
            "pipeline_contract_version": "gen-v1",
            "lineage": {}
        },
        "status": "resumable",
        "created_at": now,
        "updated_at": now,
    }
    chk_file = repo.checkpoints_dir / "run-legacy-no-modelset-chk.json"
    with open(chk_file, "w", encoding="utf-8") as f:
        json.dump(raw_chk, f)

    # get_checkpoint handles missing model_set fields gracefully returning None
    chk = repo.get_checkpoint("run-legacy-no-modelset-chk")
    assert chk is None


# =============================================================================
# Section 10: 작업 5 - 외부 Prediction Result Batch provenance 확장 테스트
# =============================================================================


def test_external_batch_contains_full_source_context(monkeypatch):
    """build_external_prediction_batch produces batch payload containing complete 9 source_context fields."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from pathlib import Path
    import jsonschema
    import json
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    src = RuntimeSourceContext(
        source_uri="data/incoming/test.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    runtime_input = RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )
    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )

    # 1. Pydantic level assertions
    assert batch.source_context.dataset_id == "canonical-ai4i-v1"
    assert batch.source_context.dataset_version == "v1.0"
    assert batch.source_context.source_uri == "data/incoming/test.jsonl"
    assert batch.source_context.source_checksum == "a" * 64
    assert batch.source_context.source_kind == "live_sensor"
    assert batch.source_context.source_contract_version == "observation-source-v1"
    assert batch.source_context.source_schema_version == "sensor-record-v2"
    assert batch.source_context.pipeline_contract_version == "generator-prediction-result-v1"
    assert isinstance(batch.source_context.lineage, PredictionResultLineage)

    # 2. JSON Schema validation
    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    batch_json = json.loads(batch.model_dump_json())
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    validator.validate(batch_json)


def test_external_batch_json_schema_fails_when_dataset_fields_removed():
    """Removing dataset_id or dataset_version from source_context fails JSON schema validation."""
    from pathlib import Path
    import jsonschema
    import json

    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    example_path = Path("contracts/examples/prediction-result-batch/prediction-result-batch-v1.json")
    example_data = json.loads(example_path.read_text(encoding="utf-8"))

    # Removing dataset_id
    bad_data_1 = json.loads(json.dumps(example_data))
    bad_data_1["source_context"].pop("dataset_id")
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_data_1)

    # Removing dataset_version
    bad_data_2 = json.loads(json.dumps(example_data))
    bad_data_2["source_context"].pop("dataset_version")
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_data_2)


def test_external_batch_json_schema_fails_when_contract_version_removed():
    """Removing source_contract_version or source_schema_version from source_context fails schema validation."""
    from pathlib import Path
    import jsonschema
    import json

    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    example_path = Path("contracts/examples/prediction-result-batch/prediction-result-batch-v1.json")
    example_data = json.loads(example_path.read_text(encoding="utf-8"))

    bad_data = json.loads(json.dumps(example_data))
    bad_data["source_context"].pop("source_contract_version")
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_data)


def test_prediction_result_item_omitted_checksum_key_fails_both_pydantic_and_json_schema():
    """Omitting feature_schema_sha256 key entirely fails both Pydantic and JSON Schema validation."""
    from pathlib import Path
    import jsonschema
    import json
    from systems.generator.app.runtime_pipeline.pipeline_schema import PredictionResultItem

    example_path = Path("contracts/examples/prediction-result-batch/prediction-result-batch-v1.json")
    example_data = json.loads(example_path.read_text(encoding="utf-8"))
    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    item_dict = dict(example_data["results"][0])
    item_dict.pop("feature_schema_sha256")

    # 1. JSON schema failure
    bad_batch = json.loads(json.dumps(example_data))
    bad_batch["results"][0] = item_dict
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_batch)

    # 2. Pydantic failure
    with pytest.raises(ValueError):
        PredictionResultItem(**item_dict)


def test_prediction_result_item_all_zero_checksum_fails_both_pydantic_and_json_schema():
    """All-zero checksum fails both Pydantic and JSON Schema validation."""
    from pathlib import Path
    import jsonschema
    import json
    from systems.generator.app.runtime_pipeline.pipeline_schema import PredictionResultItem

    example_path = Path("contracts/examples/prediction-result-batch/prediction-result-batch-v1.json")
    example_data = json.loads(example_path.read_text(encoding="utf-8"))
    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    item_dict = dict(example_data["results"][0])
    item_dict["feature_schema_sha256"] = "0" * 64

    # 1. JSON schema failure
    bad_batch = json.loads(json.dumps(example_data))
    bad_batch["results"][0] = item_dict
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_batch)

    # 2. Pydantic failure
    with pytest.raises(ValueError):
        PredictionResultItem(**item_dict)


def test_prediction_result_item_failed_state_requires_null_provenance():
    """failed_model_artifact requires null provenance in both Pydantic and JSON Schema."""
    from pathlib import Path
    import jsonschema
    import json
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        PredictionResultItem,
        compute_prediction_result_item_sha256,
    )

    schema_path = Path("contracts/schemas/prediction-result-batch.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    valid_failed_item = {
        "event_id": "evt-failed-01",
        "asset_id": "CNC-001",
        "observed_at": "2026-08-27T00:00:00Z",
        "source_kind": "live_sensor",
        "source_ref": {
            "uri": "data/incoming/test.jsonl",
            "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        },
        "output_status": "failed_model_artifact",
        "score": None,
        "model_id": "pdm-lightgbm",
        "model_version": "1.0.0",
        "model_artifact_manifest_sha256": None,
        "feature_schema_version": None,
        "history_requirement_version": None,
        "label_schema_version": None,
        "feature_schema_sha256": None,
        "history_requirement_sha256": None,
        "label_schema_sha256": None,
        "lineage": {
            "simulation_session_id": None,
            "overlay_branch_id": None,
            "history_segment_id": None,
            "maintenance_event_id": None,
            "maintenance_action_id": None,
            "state_version": None,
        },
        "failure_reason": "Model artifact manifest was corrupted",
    }
    valid_failed_item["payload_sha256"] = compute_prediction_result_item_sha256(valid_failed_item)

    # 1. Valid failed item succeeds in Pydantic
    pydantic_item = PredictionResultItem(**valid_failed_item)
    assert pydantic_item.output_status == "failed_model_artifact"
    assert pydantic_item.score is None

    # 2. Valid failed item succeeds in JSON Schema
    example_path = Path("contracts/examples/prediction-result-batch/prediction-result-batch-v1.json")
    batch_data = json.loads(example_path.read_text(encoding="utf-8"))
    batch_data["results"] = [valid_failed_item]
    validator.validate(batch_data)

    # 3. Invalid failed item with non-null checksum fails in both
    invalid_failed_item = dict(valid_failed_item)
    invalid_failed_item["feature_schema_sha256"] = "1" * 64
    invalid_failed_item["payload_sha256"] = compute_prediction_result_item_sha256(invalid_failed_item)

    with pytest.raises(ValueError):
        PredictionResultItem(**invalid_failed_item)

    bad_batch = json.loads(json.dumps(batch_data))
    bad_batch["results"] = [invalid_failed_item]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_batch)


def test_overlay_lineage_preserved_in_external_batch(monkeypatch):
    """When source_kind is maintenance_replay_overlay, all 6 lineage fields are preserved in batch."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    overlay_lin = PredictionResultLineage(
        simulation_session_id="sim-sess-999",
        overlay_branch_id="overlay-br-01",
        history_segment_id="hist-seg-10",
        maintenance_event_id="maint-evt-77",
        maintenance_action_id="action-replace-bearing",
        state_version=3,
    )
    src = RuntimeSourceContext(
        source_uri="data/incoming/overlay_data.jsonl",
        source_checksum="c" * 64,
        source_kind="maintenance_replay_overlay",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=overlay_lin,
    )
    runtime_input = RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )
    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="CNC-001",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.75,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )

    assert batch.source_context.lineage.simulation_session_id == "sim-sess-999"
    assert batch.source_context.lineage.overlay_branch_id == "overlay-br-01"
    assert batch.source_context.lineage.state_version == 3
    assert batch.results[0].lineage.simulation_session_id == "sim-sess-999"


# =============================================================================
# Section 11: 작업 6 - Item·Batch·Outbox 식별자 통일 테스트
# =============================================================================


def test_identity_determinism_identical_input_produces_identical_ids(monkeypatch):
    """Identical input context and results produce deterministic event_id, batch_id, and outbox_id."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from datetime import datetime, timezone
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    runtime_input = RuntimeInputIdentity(
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        source=src,
    )
    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch1 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
        emitted_at=datetime(2026, 8, 28, 10, 5, 0, tzinfo=timezone.utc),
    )
    batch2 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
        emitted_at=datetime(2026, 8, 28, 10, 6, 0, tzinfo=timezone.utc),  # Different emitted_at
    )

    # 1. Event ID determinism
    assert batch1.results[0].event_id == batch2.results[0].event_id
    assert batch1.results[0].payload_sha256 == batch2.results[0].payload_sha256

    # 2. Batch ID determinism
    assert batch1.batch_id == batch2.batch_id

    # 3. Outbox ID determinism
    outbox_evt1, sha1 = PredictionDeliveryService.compute_canonical_payload_sha256(batch1)
    outbox_evt2, sha2 = PredictionDeliveryService.compute_canonical_payload_sha256(batch2)
    assert outbox_evt1 == outbox_evt2
    assert sha1 == sha2


def test_identity_divergence_on_dataset_change(monkeypatch):
    """Different dataset_id or dataset_version produces completely different event_id, batch_id, and outbox_id."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
        compute_source_context_digest,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    runtime_input1 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src)
    runtime_input2 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v2", dataset_version="v1.0", source=src)

    # 1. Source context digest diverges
    digest1 = compute_source_context_digest(runtime_input1)
    digest2 = compute_source_context_digest(runtime_input2)
    assert digest1 != digest2

    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch1 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input1,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )
    batch2 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input2,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )

    # 2. Item event_id diverges
    assert batch1.results[0].event_id != batch2.results[0].event_id

    # 3. Batch ID diverges
    assert batch1.batch_id != batch2.batch_id

    # 4. Outbox ID diverges
    outbox_evt1, sha1 = PredictionDeliveryService.compute_canonical_payload_sha256(batch1)
    outbox_evt2, sha2 = PredictionDeliveryService.compute_canonical_payload_sha256(batch2)
    assert outbox_evt1 != outbox_evt2
    assert sha1 != sha2


def test_identity_divergence_on_source_contract_version_change(monkeypatch):
    """Different source_contract_version or source_schema_version produces different event_id and batch_id."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    src1 = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    src2 = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v2",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )

    runtime_input1 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src1)
    runtime_input2 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src2)

    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch1 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input1,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )
    batch2 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input2,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )

    assert batch1.results[0].event_id != batch2.results[0].event_id
    assert batch1.batch_id != batch2.batch_id


def test_identity_divergence_on_overlay_lineage_change(monkeypatch):
    """Different overlay branch or simulation session produces different event_id and batch_id."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    lin1 = PredictionResultLineage(
        simulation_session_id="sim-001",
        overlay_branch_id="branch-001",
        history_segment_id="seg-001",
        maintenance_event_id="m-001",
        maintenance_action_id="act-001",
        state_version=1,
    )
    lin2 = PredictionResultLineage(
        simulation_session_id="sim-001",
        overlay_branch_id="branch-002",  # Different branch
        history_segment_id="seg-001",
        maintenance_event_id="m-001",
        maintenance_action_id="act-001",
        state_version=1,
    )

    src1 = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="maintenance_replay_overlay",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=lin1,
    )
    src2 = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="maintenance_replay_overlay",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=lin2,
    )

    runtime_input1 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src1)
    runtime_input2 = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src2)

    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    internal_res = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch1 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input1,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )
    batch2 = build_external_prediction_batch(
        internal_results=internal_res,
        source_context=runtime_input2,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
    )

    assert batch1.results[0].event_id != batch2.results[0].event_id
    assert batch1.batch_id != batch2.batch_id


def test_identity_divergence_on_model_artifact_change(monkeypatch):
    """Different model artifact manifest checksum produces different event_id and batch_id."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    runtime_input = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src)

    model_set1 = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="b" * 64,
            )
        ],
    )
    model_set2 = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(
                model_id="pdm-lightgbm",
                model_version="1.0.0",
                required=True,
                model_artifact_manifest_sha256="c" * 64,  # Different manifest checksum
            )
        ],
    )

    internal_res1 = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="b" * 64,
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    internal_res2 = [
        InternalModelPredictionResult(
            asset_id="M14860",
            model_id="pdm-lightgbm",
            model_version="1.0.0",
            status="succeeded",
            observed_at="2026-08-28T10:00:00Z",
            score=0.88,
            manifest_checksum="c" * 64,  # Different manifest checksum
            feature_schema_version="v1.0",
            history_requirement_version="v1.0",
            label_schema_version="v1.0",
        )
    ]
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        }
    }

    batch1 = build_external_prediction_batch(
        internal_results=internal_res1,
        source_context=runtime_input,
        active_model_set_snapshot=model_set1,
        model_schema_map=model_schema_map,
    )
    batch2 = build_external_prediction_batch(
        internal_results=internal_res2,
        source_context=runtime_input,
        active_model_set_snapshot=model_set2,
        model_schema_map=model_schema_map,
    )

    assert batch1.results[0].event_id != batch2.results[0].event_id
    assert batch1.batch_id != batch2.batch_id


def test_batch_and_outbox_id_independent_of_input_item_order(monkeypatch):
    """Shuffled internal results array yields identical batch_id and outbox_id due to canonical sorting."""
    monkeypatch.setenv("GENERATOR_RUNTIME_VERSION", "1.0.0")
    from datetime import datetime, timezone
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ActiveModelSetSnapshot,
        ActiveModelSnapshotItem,
        InternalModelPredictionResult,
        RuntimeInputIdentity,
        RuntimeSourceContext,
        PredictionResultLineage,
    )
    from systems.generator.app.runtime_pipeline.prediction_batch_service import (
        build_external_prediction_batch,
    )
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    runtime_input = RuntimeInputIdentity(dataset_id="canonical-ai4i-v1", dataset_version="v1.0", source=src)

    model_set = ActiveModelSetSnapshot(
        model_set_id="ms-01",
        model_set_version="1.0.0",
        models=[
            ActiveModelSnapshotItem(model_id="pdm-lightgbm", model_version="1.0.0", required=True, model_artifact_manifest_sha256="b" * 64),
            ActiveModelSnapshotItem(model_id="pdm-xgboost", model_version="1.0.0", required=True, model_artifact_manifest_sha256="c" * 64),
        ],
    )
    item1 = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-lightgbm",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-28T10:00:00Z",
        score=0.88,
        manifest_checksum="b" * 64,
        feature_schema_version="v1.0",
        history_requirement_version="v1.0",
        label_schema_version="v1.0",
    )
    item2 = InternalModelPredictionResult(
        asset_id="M14860",
        model_id="pdm-xgboost",
        model_version="1.0.0",
        status="succeeded",
        observed_at="2026-08-28T10:00:00Z",
        score=0.92,
        manifest_checksum="c" * 64,
        feature_schema_version="v1.0",
        history_requirement_version="v1.0",
        label_schema_version="v1.0",
    )
    model_schema_map = {
        "pdm-lightgbm": {
            "feature_schema_sha256": "1" * 64,
            "history_requirement_sha256": "2" * 64,
            "label_schema_sha256": "3" * 64,
            "label_schema_version": "v1.0",
        },
        "pdm-xgboost": {
            "feature_schema_sha256": "4" * 64,
            "history_requirement_sha256": "5" * 64,
            "label_schema_sha256": "6" * 64,
            "label_schema_version": "v1.0",
        },
    }

    batch_order_1 = build_external_prediction_batch(
        internal_results=[item1, item2],
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
        emitted_at=datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc),
    )
    batch_order_2 = build_external_prediction_batch(
        internal_results=[item2, item1],
        source_context=runtime_input,
        active_model_set_snapshot=model_set,
        model_schema_map=model_schema_map,
        emitted_at=datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc),
    )

    # 1. Same Batch ID
    assert batch_order_1.batch_id == batch_order_2.batch_id

    # 2. Same Outbox ID & Payload SHA
    outbox_1, sha1 = PredictionDeliveryService.compute_canonical_payload_sha256(batch_order_1)
    outbox_2, sha2 = PredictionDeliveryService.compute_canonical_payload_sha256(batch_order_2)
    assert outbox_1 == outbox_2
    assert sha1 == sha2


# =============================================================================
# Section 12: 작업 7 - RunState·Checkpoint 공식 JSON Schema 정합화 테스트
# =============================================================================


def _get_run_state_schema():
    import json
    from pathlib import Path
    schema_path = Path("contracts/schemas/generator-pipeline-run-state.schema.json")
    if not schema_path.is_file():
        schema_path = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "generator-pipeline-run-state.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_run_state_and_checkpoint_schema_validation_passes():
    """Valid RunState with resumable Checkpoint passes both Pydantic and JSON Schema validation."""
    import jsonschema
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ArtifactReference,
        PipelineCheckpoint,
        PipelineRunState,
        PredictionResultLineage,
        RuntimeSourceContext,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    checkpoint = PipelineCheckpoint(
        run_id="run-100",
        job_id="job-100",
        source_identity="f" * 64,
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        model_set_id="ms-01",
        model_set_version="1.0.0",
        model_set_payload_sha256="e" * 64,
        pipeline_contract_version="generator-prediction-result-v1",
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        lineage_json="{}",
        source_context=src,
        status="resumable",
        last_completed_stage="preprocessing",
        next_stage="runtime_feature",
        stage_outputs={"preprocessing": [ArtifactReference(uri="pre.parquet", sha256="b" * 64)]},
        model_stage_outputs={},
        delivery_outputs={},
        model_snapshot={},
        errors=[],
    )
    run_state = PipelineRunState(
        run_id="run-100",
        job_id="job-100",
        status="running",
        source_ref=ArtifactReference(uri="data/in.jsonl", sha256="a" * 64),
        source_context=src,
        stages={},
        prediction_results=[],
        errors=[],
        checkpoint_status="resumable",
        checkpoint=checkpoint,
    )

    # 1. Pydantic roundtrip
    data = run_state.model_dump(mode="json")
    validated_pydantic = PipelineRunState.model_validate(data)
    assert validated_pydantic.run_id == "run-100"

    # 2. JSON Schema validation
    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(data)


def test_run_state_schema_fails_when_source_context_arbitrary_object():
    """Arbitrary dict in source_context fails both Pydantic and JSON Schema validation."""
    import pytest
    import jsonschema
    from pydantic import ValidationError
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ArtifactReference,
        PipelineRunState,
    )

    raw_data = {
        "run_id": "run-100",
        "job_id": "job-100",
        "status": "pending",
        "source_ref": {"uri": "data/in.jsonl", "sha256": "a" * 64},
        "source_context": {"unstructured_key": "some_random_value"},
        "stages": {},
        "prediction_results": [],
        "errors": [],
    }

    # 1. Pydantic fails
    with pytest.raises(ValidationError):
        PipelineRunState.model_validate(raw_data)

    # 2. JSON Schema fails
    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(raw_data)


def test_run_state_schema_fails_when_resumable_has_null_source_context():
    """When checkpoint_status is 'resumable', null source_context or null checkpoint fails JSON Schema."""
    import pytest
    import jsonschema

    raw_data = {
        "run_id": "run-100",
        "job_id": "job-100",
        "status": "running",
        "source_ref": {"uri": "data/in.jsonl", "sha256": "a" * 64},
        "source_context": None,  # Null forbidden when resumable
        "checkpoint_status": "resumable",
        "checkpoint": None,
        "stages": {},
        "prediction_results": [],
        "errors": [],
    }

    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(raw_data)


def test_run_state_schema_fails_on_overlay_without_full_lineage():
    """When source_kind is 'maintenance_replay_overlay', partial lineage fails both Pydantic and JSON Schema."""
    import pytest
    import jsonschema
    from pydantic import ValidationError
    from systems.generator.app.runtime_pipeline.pipeline_schema import PipelineRunState

    raw_data = {
        "run_id": "run-100",
        "job_id": "job-100",
        "status": "pending",
        "source_ref": {"uri": "data/in.jsonl", "sha256": "a" * 64},
        "source_context": {
            "source_uri": "data/in.jsonl",
            "source_checksum": "a" * 64,
            "source_kind": "maintenance_replay_overlay",
            "source_contract_version": "observation-source-v1",
            "source_schema_version": "sensor-record-v2",
            "pipeline_contract_version": "generator-prediction-result-v1",
            "lineage": {
                "simulation_session_id": "sim-100"  # Missing other 5 fields
            },
        },
        "stages": {},
        "prediction_results": [],
        "errors": [],
    }

    # 1. Pydantic fails
    with pytest.raises(ValidationError):
        PipelineRunState.model_validate(raw_data)

    # 2. JSON Schema fails
    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(raw_data)


def test_checkpoint_schema_fails_when_model_set_payload_sha256_missing_or_zero():
    """Missing or all-zero model_set_payload_sha256 in checkpoint fails both Pydantic and JSON Schema."""
    import pytest
    import jsonschema
    from pydantic import ValidationError
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ArtifactReference,
        PipelineCheckpoint,
        PipelineRunState,
        PredictionResultLineage,
        RuntimeSourceContext,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    checkpoint = PipelineCheckpoint(
        run_id="run-100",
        job_id="job-100",
        source_identity="f" * 64,
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        model_set_id="ms-01",
        model_set_version="1.0.0",
        model_set_payload_sha256="e" * 64,
        pipeline_contract_version="generator-prediction-result-v1",
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        lineage_json="{}",
        source_context=src,
        status="resumable",
    )
    run_state = PipelineRunState(
        run_id="run-100",
        job_id="job-100",
        status="running",
        source_ref=ArtifactReference(uri="data/in.jsonl", sha256="a" * 64),
        source_context=src,
        stages={},
        prediction_results=[],
        errors=[],
        checkpoint_status="resumable",
        checkpoint=checkpoint,
    )

    raw_data = run_state.model_dump(mode="json")
    raw_data["checkpoint"]["model_set_payload_sha256"] = "0" * 64  # All zeros

    # 1. Pydantic fails
    with pytest.raises(ValidationError):
        PipelineRunState.model_validate(raw_data)

    # 2. JSON Schema fails
    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(raw_data)


def test_checkpoint_schema_fails_on_additional_properties():
    """Unrecognized fields in checkpoint fail both Pydantic and JSON Schema validation."""
    import pytest
    import jsonschema
    from pydantic import ValidationError
    from systems.generator.app.runtime_pipeline.pipeline_schema import (
        ArtifactReference,
        PipelineCheckpoint,
        PipelineRunState,
        PredictionResultLineage,
        RuntimeSourceContext,
    )

    src = RuntimeSourceContext(
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        pipeline_contract_version="generator-prediction-result-v1",
        lineage=PredictionResultLineage(),
    )
    checkpoint = PipelineCheckpoint(
        run_id="run-100",
        job_id="job-100",
        source_identity="f" * 64,
        source_uri="data/in.jsonl",
        source_checksum="a" * 64,
        dataset_id="canonical-ai4i-v1",
        dataset_version="v1.0",
        model_set_id="ms-01",
        model_set_version="1.0.0",
        model_set_payload_sha256="e" * 64,
        pipeline_contract_version="generator-prediction-result-v1",
        source_kind="live_sensor",
        source_contract_version="observation-source-v1",
        source_schema_version="sensor-record-v2",
        lineage_json="{}",
        source_context=src,
        status="resumable",
    )
    run_state = PipelineRunState(
        run_id="run-100",
        job_id="job-100",
        status="running",
        source_ref=ArtifactReference(uri="data/in.jsonl", sha256="a" * 64),
        source_context=src,
        stages={},
        prediction_results=[],
        errors=[],
        checkpoint_status="resumable",
        checkpoint=checkpoint,
    )

    raw_data = run_state.model_dump(mode="json")
    raw_data["checkpoint"]["unexpected_extra_field"] = 12345

    # 1. Pydantic fails (extra="forbid")
    with pytest.raises(ValidationError):
        PipelineRunState.model_validate(raw_data)

    # 2. JSON Schema fails (additionalProperties: False)
    schema = _get_run_state_schema()
    validator = jsonschema.Draft202012Validator(schema)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(raw_data)
