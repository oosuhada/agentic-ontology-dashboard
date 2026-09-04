"""Fault injection, recovery, and robustness test suite for Generator Protocol Extraction (Issue #108)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
import pytest

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRequest,
    ExtractionResponse,
)
from systems.generator.app.extraction.extraction_exception import (
    ExtractionAlreadyRunningError,
    ExtractionLockLostError,
    ExtractionDatasetConflictError,
    ExtractionIdempotencyConflictError,
    ExtractionSourceIncompleteError,
    ExtractionSourceIntegrityError,
    ExtractionIntegrityError,
    ExtractionSchemaFingerprintMismatchError,
    ExtractionError,
)
from systems.generator.app.extraction.mapping_validator import (
    MappingValidator,
    compute_mapping_canonical_sha256,
    compute_source_schema_fingerprint,
)
from systems.generator.app.extraction.mapping_repository import MappingRepository
from systems.generator.app.extraction.parsers.sensor_record_parser import SensorRecordParser
from systems.generator.app.extraction.dedup_repository import DedupRepository
from systems.generator.app.extraction.checkpoint_repository import CheckpointRepository
from systems.generator.app.extraction.extraction_repository import ExtractionRepository
from systems.generator.app.extraction.extraction_service import (
    ExtractionService,
    ExtractionFailureInjector,
)


class MockFailureInjector(ExtractionFailureInjector):
    """Custom failure injector that triggers an exception at a specific point."""

    def __init__(self, fail_point: str, exception: Exception) -> None:
        self.fail_point = fail_point
        self.exception = exception
        self.hit_count = 0

    def hit(self, point: str) -> None:
        if point == self.fail_point:
            self.hit_count += 1
            raise self.exception


@pytest.fixture
def recovery_env(tmp_path):
    """Create isolated environment for fault injection tests."""
    data_dir = tmp_path / "data"
    preprocessed_dir = tmp_path / "data_preprocessed"
    obs_dir = data_dir / "observations"
    runs_dir = preprocessed_dir / "extraction_runs"
    state_dir = preprocessed_dir / "extraction_state"
    mappings_dir = tmp_path / "mappings"

    for p in (data_dir, preprocessed_dir, obs_dir, runs_dir, state_dir, mappings_dir):
        p.mkdir(parents=True, exist_ok=True)

    mapping_repo = MappingRepository(search_roots=[mappings_dir])
    mapping_validator = MappingValidator()
    parser = SensorRecordParser(mapping_validator=mapping_validator)
    dedup_repo = DedupRepository(state_root=state_dir)
    checkpoint_repo = CheckpointRepository(runs_root=runs_dir)
    extraction_repo = ExtractionRepository(observations_root=obs_dir, runs_root=runs_dir)

    service = ExtractionService(
        mapping_repo=mapping_repo,
        mapping_validator=mapping_validator,
        parser=parser,
        dedup_repo=dedup_repo,
        checkpoint_repo=checkpoint_repo,
        extraction_repo=extraction_repo,
        allowed_roots=[data_dir, preprocessed_dir, tmp_path, PROJECT_ROOT],
    )

    return {
        "tmp_path": tmp_path,
        "data_dir": data_dir,
        "preprocessed_dir": preprocessed_dir,
        "obs_dir": obs_dir,
        "runs_dir": runs_dir,
        "state_dir": state_dir,
        "mappings_dir": mappings_dir,
        "mapping_repo": mapping_repo,
        "mapping_validator": mapping_validator,
        "parser": parser,
        "dedup_repo": dedup_repo,
        "checkpoint_repo": checkpoint_repo,
        "extraction_repo": extraction_repo,
        "service": service,
    }


def get_current_protocol_schema_fingerprint() -> str:
    schema_path = PROJECT_ROOT / "contracts" / "schemas" / "generator-protocol-record.schema.json"
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
    return compute_source_schema_fingerprint(schema_data, algorithm_version="v1")


def make_proto_file(
    file_path: Path,
    num_timestamps: int = 3,
    asset_id: str = "CNC-S01-L01-01",
    direction: str = "received",
) -> tuple[Path, str, int]:
    lines = []
    seq = 1
    for t in range(num_timestamps):
        ts = f"2026-08-27T01:0{t}:00Z"
        rec1 = {
            "direction": direction,
            "schema_version": "sensor-record-v2",
            "observation_id": f"obs-{seq:04d}",
            "source_kind": "simulation",
            "record_kind": "observation",
            "quality": "Good",
            "run_id": "run-gen-001",
            "sequence": seq,
            "asset_id": asset_id,
            "measurement_key": "voltage",
            "node_id": f"{asset_id}.voltage",
            "data_type": "float",
            "unit": "V",
            "value": 220.0 + t,
            "status_code": "Good",
            "status_code_value": 0,
            "observed_at_source": ts,
            "source_timestamp": ts,
            "server_timestamp": ts,
            "received_at": ts,
            "branch_kind": "canonical",
            "overlay": False,
            "mapping_version": "v1.0",
        }
        seq += 1
        rec2 = {
            "direction": direction,
            "schema_version": "sensor-record-v2",
            "observation_id": f"obs-{seq:04d}",
            "source_kind": "simulation",
            "record_kind": "observation",
            "quality": "Good",
            "run_id": "run-gen-001",
            "sequence": seq,
            "asset_id": asset_id,
            "measurement_key": "rotation",
            "node_id": f"{asset_id}.rotation",
            "data_type": "float",
            "unit": "rpm",
            "value": 1500.0 + t * 5,
            "status_code": "Good",
            "status_code_value": 0,
            "observed_at_source": ts,
            "source_timestamp": ts,
            "server_timestamp": ts,
            "received_at": ts,
            "branch_kind": "canonical",
            "overlay": False,
            "mapping_version": "v1.0",
        }
        seq += 1
        lines.append(json.dumps(rec1, ensure_ascii=False))
        lines.append(json.dumps(rec2, ensure_ascii=False))

    content_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content_bytes)
    sha256 = compute_file_sha256(file_path)
    return file_path, sha256, len(content_bytes)


def make_run_manifest(
    manifest_path: Path,
    source_file_path: Path,
    source_sha256: str,
    source_size: int,
    status: str = "completed",
    run_id: str = "run-gen-001",
) -> tuple[Path, str]:
    manifest_payload = {
        "manifest_version": "generator-protocol-run-v1",
        "run_id": run_id,
        "status": status,
        "protocol_version": "v2",
        "source_schema_version": "sensor-record-v2",
        "finalized_at": "2026-08-27T01:05:00Z",
        "total_records": 6,
        "files": [
            {
                "role": "protocol_log",
                "path": str(source_file_path).replace("\\", "/"),
                "media_type": "application/x-ndjson",
                "sha256": source_sha256,
                "size_bytes": source_size,
                "record_count": 6,
                "last_sequence": 6,
            }
        ],
    }
    content = json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(content, encoding="utf-8")
    sha256 = compute_file_sha256(manifest_path)
    return manifest_path, sha256


def make_mapping(
    file_path: Path,
    status: str = "approved",
) -> tuple[dict[str, Any], Path, str]:
    fp = get_current_protocol_schema_fingerprint()
    mapping_dict = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-static-mapping-table.schema.json",
        "mapping_id": "test-sensor-mapping",
        "mapping_version": "v1.0",
        "status": status,
        "protocol_version": "v2",
        "source_schema_version": "sensor-record-v2",
        "source_schema_fingerprint": fp,
        "fingerprint_algorithm_version": "v1",
        "description": "Test static mapping table",
        "field_mappings": [
            {
                "source_field": "voltage",
                "target_field": "voltage",
                "source_type": "float",
                "target_type": "float",
                "required": True,
                "transform": "to_float",
                "unit": "V",
                "timezone": "UTC",
            },
            {
                "source_field": "rotation",
                "target_field": "rotation",
                "source_type": "float",
                "target_type": "float",
                "required": True,
                "transform": "to_float",
                "unit": "rpm",
                "timezone": "UTC",
            },
        ],
    }
    canonical_sha = compute_mapping_canonical_sha256(mapping_dict)
    mapping_dict["mapping_sha256"] = canonical_sha

    content = json.dumps(mapping_dict, indent=2, ensure_ascii=False) + "\n"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return mapping_dict, file_path, canonical_sha


# --- Fault Injection & Recovery Test Cases ---

def test_failure_after_idempotency_reserved_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-01",
        idempotency_key="idem-fi-01",
        run_id="run-fi-01",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-01",
        dataset_version="v1",
    )

    # 1. Inject failure after idempotency reservation
    injector = MockFailureInjector("after_idempotency_reserved", RuntimeError("Crash after idempotency reserved"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after idempotency reserved"):
        env["service"].execute_extraction(req)

    # Verify failed run state recorded
    state = env["checkpoint_repo"].get_run_state(req.run_id)
    assert state["status"] == "failed"

    # 2. Retry without failure injector
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_failure_after_lock_acquired_releases_lock(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-02",
        idempotency_key="idem-fi-02",
        run_id="run-fi-02",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-02",
        dataset_version="v1",
    )

    # Inject failure right after lock acquired
    injector = MockFailureInjector("after_lock_acquired", RuntimeError("Crash after lock acquired"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after lock acquired"):
        env["service"].execute_extraction(req)

    # Verify lock was released in finally block
    conn = env["dedup_repo"]._get_connection(req.dataset_id, req.dataset_version)
    cur = conn.execute("SELECT * FROM single_writer_locks WHERE dataset_key = ?", (f"{req.dataset_id}:{req.dataset_version}",))
    assert cur.fetchone() is None

    # Next run can acquire lock and succeed
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_failure_after_batch_pending_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-03",
        idempotency_key="idem-fi-03",
        run_id="run-fi-03",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-03",
        dataset_version="v1",
    )

    injector = MockFailureInjector("after_batch_pending", RuntimeError("Crash after batch pending"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after batch pending"):
        env["service"].execute_extraction(req)

    # Verify batch was saved as pending
    batches = env["dedup_repo"].list_batches(req.dataset_id, req.dataset_version, run_id=req.run_id)
    assert len(batches) == 1
    assert batches[0]["status"] == "pending"

    # Retry and complete
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"

    batches_after = env["dedup_repo"].list_batches(req.dataset_id, req.dataset_version, run_id=req.run_id)
    assert batches_after[0]["status"] == "committed"


def test_failure_after_fragment_written_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-04",
        idempotency_key="idem-fi-04",
        run_id="run-fi-04",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-04",
        dataset_version="v1",
    )

    injector = MockFailureInjector("after_fragment_written", RuntimeError("Crash after fragment written"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after fragment written"):
        env["service"].execute_extraction(req)

    # Retry and complete
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_failure_after_batch_staged_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-05",
        idempotency_key="idem-fi-05",
        run_id="run-fi-05",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-05",
        dataset_version="v1",
    )

    injector = MockFailureInjector("after_batch_staged", RuntimeError("Crash after batch staged"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after batch staged"):
        env["service"].execute_extraction(req)

    # Retry and complete
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_failure_after_checkpoint_written_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-06",
        idempotency_key="idem-fi-06",
        run_id="run-fi-06",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-06",
        dataset_version="v1",
    )

    injector = MockFailureInjector("after_checkpoint_written", RuntimeError("Crash after checkpoint written"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after checkpoint written"):
        env["service"].execute_extraction(req)

    chk = env["checkpoint_repo"].get_checkpoint(req.run_id)
    assert chk is not None

    # Retry and complete
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_failure_after_dataset_published_and_recovery(recovery_env):
    env = recovery_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = make_proto_file(source_p)
    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = make_run_manifest(manifest_p, source_p, actual_sha, size_b)
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = make_mapping(map_p)

    req = ExtractionRequest(
        request_id="req-fi-07",
        idempotency_key="idem-fi-07",
        run_id="run-fi-07",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="fi-dataset-07",
        dataset_version="v1",
    )

    # Fail right after directory publish
    injector = MockFailureInjector("after_dataset_published", RuntimeError("Crash after publish"))
    env["service"].failure_injector = injector

    with pytest.raises(RuntimeError, match="Crash after publish"):
        env["service"].execute_extraction(req)

    # Target directory already exists and is valid
    target_dir = env["obs_dir"] / "fi-dataset-07" / "v1"
    assert (target_dir / "observations.jsonl").is_file()

    # Retry with same idempotency key should safely validate disk and return success
    env["service"].failure_injector = None
    resp = env["service"].execute_extraction(req)
    assert resp.status == "succeeded"


def test_stale_lock_override(recovery_env):
    env = recovery_env
    dataset_id = "lock-override-ds"
    dataset_version = "v1"

    # 1. Acquire lock with 0.1s expiry
    env["dedup_repo"].acquire_lock(dataset_id, dataset_version, run_id="stale-run", timeout_seconds=0.1)
    time.sleep(0.2)  # wait for lock to become stale

    # 2. New run acquires lock successfully overtaking stale lock
    env["dedup_repo"].acquire_lock(dataset_id, dataset_version, run_id="active-run", timeout_seconds=30.0)

    conn = env["dedup_repo"]._get_connection(dataset_id, dataset_version)
    cur = conn.execute("SELECT run_id FROM single_writer_locks WHERE dataset_key = ?", (f"{dataset_id}:{dataset_version}",))
    row = cur.fetchone()
    assert row["run_id"] == "active-run"


def test_active_lock_conflict_raises_409(recovery_env):
    env = recovery_env
    dataset_id = "lock-conflict-ds"
    dataset_version = "v1"

    # Acquire active lock
    env["dedup_repo"].acquire_lock(dataset_id, dataset_version, run_id="run-owner", timeout_seconds=60.0)

    # Second run tries to acquire -> raises 409
    with pytest.raises(ExtractionAlreadyRunningError):
        env["dedup_repo"].acquire_lock(dataset_id, dataset_version, run_id="run-intruder", timeout_seconds=60.0)


def test_lock_loss_raises_409(recovery_env):
    env = recovery_env
    dataset_id = "lock-loss-ds"
    dataset_version = "v1"

    env["dedup_repo"].acquire_lock(dataset_id, dataset_version, run_id="run-original", timeout_seconds=60.0)

    # Release lock externally
    env["dedup_repo"].release_lock(dataset_id, dataset_version, run_id="run-original")

    # Heartbeat should detect lost lock
    with pytest.raises(ExtractionLockLostError):
        env["dedup_repo"].heartbeat_lock(dataset_id, dataset_version, run_id="run-original", lease_seconds=60.0)
