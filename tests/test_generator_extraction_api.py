"""Unit and integration tests for Generator Protocol Extraction API and domain."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.main import app
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRequest,
    ExtractionResponse,
)
from systems.generator.app.extraction.extraction_exception import (
    ExtractionMappingNotApprovedError,
    ExtractionMappingChecksumMismatchError,
    ExtractionSchemaFingerprintMismatchError,
    ExtractionFeatureNotImplementedError,
    ExtractionSourceIncompleteError,
    ExtractionSourceIntegrityError,
    ExtractionDatasetConflictError,
    ExtractionAlreadyRunningError,
    ExtractionIdempotencyConflictError,
    ExtractionSourceNotFoundError,
    ExtractionSourceChecksumMismatchError,
    ExtractionSourceManifestRequiredError,
    ExtractionSourceNotFinalizedError,
    ExtractionSourceDescriptorMismatchError,
    ExtractionNoValidObservationsError,
    ExtractionRequestInvalidError,
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
from systems.generator.app.extraction.extraction_service import ExtractionService


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def isolated_extraction_env(tmp_path):
    """Create clean isolated environment for extraction testing."""
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


def create_sample_protocol_file(
    file_path: Path,
    num_timestamps: int = 3,
    asset_id: str = "CNC-S01-L01-01",
    direction: str = "received",
) -> tuple[Path, str, int]:
    """Helper to create sample protocol jsonl file and return (path, sha256, size_bytes)."""
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


def create_sample_run_manifest(
    manifest_path: Path,
    source_file_path: Path,
    source_sha256: str,
    source_size: int,
    status: str = "completed",
    run_id: str = "run-gen-001",
) -> tuple[Path, str]:
    """Helper to create sample upstream gen_data run manifest and return (path, sha256)."""
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


def create_sample_mapping_file(
    file_path: Path,
    status: str = "approved",
) -> tuple[dict[str, Any], Path, str]:
    """Helper to create sample static mapping table file with valid canonical checksum & fingerprint."""
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


# --- Test Cases ---

def test_static_mapping_unapproved_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    map_p = env["mappings_dir"] / "test-map.json"
    mapping_data, _, _ = create_sample_mapping_file(map_p, status="draft")

    with pytest.raises(ExtractionMappingNotApprovedError):
        env["mapping_validator"].validate_mapping(mapping_data)


def test_static_mapping_checksum_mismatch_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    map_p = env["mappings_dir"] / "test-map.json"
    mapping_data, _, canonical_sha = create_sample_mapping_file(map_p, status="approved")

    # Mismatched requested sha
    with pytest.raises(ExtractionMappingChecksumMismatchError):
        env["mapping_validator"].validate_mapping(
            mapping_data,
            expected_mapping_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )


def test_static_mapping_fingerprint_mismatch_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    map_p = env["mappings_dir"] / "test-map.json"
    mapping_data, _, _ = create_sample_mapping_file(map_p, status="approved")

    with pytest.raises(ExtractionSchemaFingerprintMismatchError):
        env["mapping_validator"].validate_mapping(
            mapping_data,
            expected_source_schema_fingerprint="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )


def test_static_mapping_unsupported_transform_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    map_p = env["mappings_dir"] / "test-map.json"
    mapping_data, _, _ = create_sample_mapping_file(map_p, status="approved")
    mapping_data["field_mappings"][0]["transform"] = "unsupported_magic_transform"

    with pytest.raises(ExtractionRequestInvalidError):
        env["mapping_validator"].validate_mapping(mapping_data)

    with pytest.raises(ExtractionFeatureNotImplementedError):
        env["mapping_validator"].apply_transform(100.0, "unsupported_magic_transform", "float")


def test_source_file_not_found_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    mapping_data, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-001",
        idempotency_key="idem-001",
        run_id="run-001",
        source_uri="data/non_existent.jsonl",
        source_sha256="a" * 64,
        source_run_manifest_uri="data/non_existent_manifest.json",
        source_run_manifest_sha256="b" * 64,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="canonical-obs",
        dataset_version="v1",
    )

    with pytest.raises((ExtractionSourceNotFoundError, ExtractionSourceChecksumMismatchError)):
        env["service"].execute_extraction(req)


def test_source_checksum_mismatch_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    mapping_data, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-002",
        idempotency_key="idem-002",
        run_id="run-002",
        source_uri=str(source_p),
        source_sha256="0" * 64,  # wrong sha
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="canonical-obs",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionSourceChecksumMismatchError):
        env["service"].execute_extraction(req)


def test_source_unfinalized_raises_409(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b, status="running")

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    mapping_data, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-003",
        idempotency_key="idem-003",
        run_id="run-003",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="canonical-obs",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionSourceNotFinalizedError):
        env["service"].execute_extraction(req)


def test_source_descriptor_mismatch_raises_error(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    # Create manifest with mismatched size
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b + 999)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    mapping_data, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-004",
        idempotency_key="idem-004",
        run_id="run-004",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="canonical-obs",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionSourceDescriptorMismatchError):
        env["service"].execute_extraction(req)


def test_successful_extraction_end_to_end(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p, num_timestamps=3)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    mapping_data, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-100",
        idempotency_key="idem-100",
        run_id="run-100",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="cnc-milling-dataset",
        dataset_version="v1",
    )

    resp = env["service"].execute_extraction(req)

    assert resp.status == "succeeded"
    assert resp.dataset_id == "cnc-milling-dataset"
    assert resp.dataset_version == "v1"
    assert resp.result.observations_count == 3
    assert resp.result.rejected_count == 0
    assert len(resp.result.asset_ids) == 1

    # Verify published files on disk
    target_dir = env["obs_dir"] / "cnc-milling-dataset" / "v1"
    assert (target_dir / "dataset_manifest.json").is_file()
    assert (target_dir / "observations.jsonl").is_file()
    assert (target_dir / "provenance.jsonl").is_file()
    assert (target_dir / "rejected.jsonl").is_file()

    # Verify manifest integrity
    manifest = json.loads((target_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_id"] == "cnc-milling-dataset"
    assert len(manifest["files"]) == 1
    assert len(manifest["auxiliary_files"]) == 2


def test_idempotent_retry_returns_cached_response(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-200",
        idempotency_key="idem-200",
        run_id="run-200",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="cnc-dataset-idem",
        dataset_version="v1",
    )

    resp1 = env["service"].execute_extraction(req)
    resp2 = env["service"].execute_extraction(req)

    assert resp1.result.manifest_sha256 == resp2.result.manifest_sha256
    assert resp1.result.observations_sha256 == resp2.result.observations_sha256


def test_idempotency_conflict_raises_409(isolated_extraction_env):
    env = isolated_extraction_env
    source_p = env["data_dir"] / "protocol.jsonl"
    _, actual_sha, size_b = create_sample_protocol_file(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, size_b)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = create_sample_mapping_file(map_p)

    req1 = ExtractionRequest(
        request_id="req-301",
        idempotency_key="idem-same-key",
        run_id="run-301",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="dataset-a",
        dataset_version="v1",
    )
    env["service"].execute_extraction(req1)

    req2 = ExtractionRequest(
        request_id="req-302",
        idempotency_key="idem-same-key",  # same key, different dataset
        run_id="run-302",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="dataset-b",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionIdempotencyConflictError):
        env["service"].execute_extraction(req2)


def test_dataset_overwrite_conflict_raises_409(isolated_extraction_env):
    env = isolated_extraction_env
    source_p1 = env["data_dir"] / "protocol_1.jsonl"
    _, sha1, size1 = create_sample_protocol_file(source_p1, num_timestamps=2)
    manifest_p1 = env["data_dir"] / "manifest_1.json"
    _, man_sha1 = create_sample_run_manifest(manifest_p1, source_p1, sha1, size1, run_id="run-1")

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = create_sample_mapping_file(map_p)

    req1 = ExtractionRequest(
        request_id="req-401",
        idempotency_key="idem-401",
        run_id="run-401",
        source_uri=str(source_p1),
        source_sha256=sha1,
        source_run_manifest_uri=str(manifest_p1),
        source_run_manifest_sha256=man_sha1,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="shared-dataset",
        dataset_version="v1",
    )
    env["service"].execute_extraction(req1)

    # Second run trying to publish different contents to same dataset/version
    source_p2 = env["data_dir"] / "protocol_2.jsonl"
    _, sha2, size2 = create_sample_protocol_file(source_p2, num_timestamps=4)
    manifest_p2 = env["data_dir"] / "manifest_2.json"
    _, man_sha2 = create_sample_run_manifest(manifest_p2, source_p2, sha2, size2, run_id="run-2")

    req2 = ExtractionRequest(
        request_id="req-402",
        idempotency_key="idem-402",
        run_id="run-402",
        source_uri=str(source_p2),
        source_sha256=sha2,
        source_run_manifest_uri=str(manifest_p2),
        source_run_manifest_sha256=man_sha2,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="shared-dataset",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionDatasetConflictError):
        env["service"].execute_extraction(req2)


def test_empty_observations_raises_422(isolated_extraction_env):
    env = isolated_extraction_env
    # Create empty source protocol file
    source_p = env["data_dir"] / "empty_protocol.jsonl"
    source_p.write_bytes(b"")
    actual_sha = compute_file_sha256(source_p)

    manifest_p = env["data_dir"] / "run_manifest.json"
    _, man_sha = create_sample_run_manifest(manifest_p, source_p, actual_sha, 0)

    map_p = env["mappings_dir"] / "test-sensor-mapping" / "v1.0" / "mapping.json"
    _, _, map_sha = create_sample_mapping_file(map_p)

    req = ExtractionRequest(
        request_id="req-empty",
        idempotency_key="idem-empty",
        run_id="run-empty",
        source_uri=str(source_p),
        source_sha256=actual_sha,
        source_run_manifest_uri=str(manifest_p),
        source_run_manifest_sha256=man_sha,
        source_schema_version="sensor-record-v2",
        protocol_version="v2",
        mapping_id="test-sensor-mapping",
        mapping_version="v1.0",
        mapping_sha256=map_sha,
        dataset_id="empty-dataset",
        dataset_version="v1",
    )

    with pytest.raises(ExtractionNoValidObservationsError):
        env["service"].execute_extraction(req)
