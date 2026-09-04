"""Unit and end-to-end tests for Fragment Consumption tracking, Lifecycle Management, and WindowPublishService."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from systems.generator.app.extraction.checkpoint_repository import (
    GenDataExtractionCheckpointRepository,
)
from systems.generator.app.extraction.fragment_lifecycle import (
    GenDataFragmentLifecycleManager,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.gen_data_incremental_service import (
    GenDataIncrementalExtractionService,
)
from systems.generator.app.extraction.gen_data_mapping import (
    CanonicalObservationCandidate,
    GenDataStaticMappingConverter,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
)
from systems.generator.app.extraction.mapping_validator import (
    compute_mapping_canonical_sha256,
)
from systems.generator.app.extraction.window_publish_service import (
    ExtractionWindowPublishService,
)
from systems.generator.app.extraction.window_publisher import (
    ExtractionWindowPublisher,
)


def test_fragment_lifecycle_consumption_tracking(tmp_path):
    """Lifecycle manager correctly transitions from partially_consumed to fully_consumed."""
    mgr = GenDataFragmentLifecycleManager(consumption_root=tmp_path / "consumption")

    batch_id = "b" * 64
    manifest_sha = "a" * 64
    windows = ["win-1", "win-2"]

    # 1. Publish win-1
    rec1 = mgr.record_window_publication(
        batch_id=batch_id,
        fragment_manifest_sha256=manifest_sha,
        all_referenced_windows=windows,
        published_window="win-1",
    )
    assert rec1.status == "partially_consumed"
    assert rec1.pending_windows == ["win-2"]

    # 2. Publish win-2
    rec2 = mgr.record_window_publication(
        batch_id=batch_id,
        fragment_manifest_sha256=manifest_sha,
        all_referenced_windows=windows,
        published_window="win-2",
    )
    assert rec2.status == "fully_consumed"
    assert rec2.pending_windows == []


def test_fragment_cleanup_retains_partially_consumed(tmp_path):
    """Partially consumed fragment is retained on disk."""
    frag_dir = tmp_path / "fragments" / ("b" * 64)
    frag_dir.mkdir(parents=True)
    (frag_dir / "fragment_manifest.json").write_text("{}", encoding="utf-8")

    mgr = GenDataFragmentLifecycleManager(consumption_root=tmp_path / "consumption")
    mgr.record_window_publication(
        batch_id="b" * 64,
        fragment_manifest_sha256="a" * 64,
        all_referenced_windows=["win-1", "win-2"],
        published_window="win-1",
    )

    cleaned = mgr.safe_cleanup_fragment(fragment_dir=frag_dir, batch_id="b" * 64)
    assert cleaned is False
    assert frag_dir.is_dir()


def test_fragment_cleanup_deletes_fully_consumed(tmp_path):
    """Fully consumed fragment is safely removed."""
    frag_dir = tmp_path / "fragments" / ("b" * 64)
    frag_dir.mkdir(parents=True)
    (frag_dir / "fragment_manifest.json").write_text("{}", encoding="utf-8")

    mgr = GenDataFragmentLifecycleManager(consumption_root=tmp_path / "consumption")
    mgr.record_window_publication(
        batch_id="b" * 64,
        fragment_manifest_sha256="a" * 64,
        all_referenced_windows=["win-1"],
        published_window="win-1",
    )

    cleaned = mgr.safe_cleanup_fragment(fragment_dir=frag_dir, batch_id="b" * 64)
    assert cleaned is True
    assert not frag_dir.exists()


def test_end_to_end_window_publish_service(tmp_path, monkeypatch):
    """Full cycle: incremental extraction creates fragment, and WindowPublishService publishes closed window dataset."""
    runs_dir = tmp_path / "runs"
    data_dir = tmp_path / "data"
    obs_dir = data_dir / "observations"
    pubs_dir = tmp_path / "pubs"
    consumption_dir = tmp_path / "consumption"
    checkpoints_dir = tmp_path / "checkpoints"
    locks_dir = tmp_path / "locks"

    from systems.generator.generator_config import PATHS
    monkeypatch.setattr(PATHS, "data_dir", data_dir)
    monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")

    # Mapping fixture
    mapping_data = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-static-mapping-table.schema.json",
        "mapping_id": "gen-data-sensor-stream-canonical",
        "mapping_version": "v1",
        "status": "approved",
        "source_format": "gen_data_sensor_stream",
        "source_schema_version": "gen-data-sensor-stream-v1",
        "source_schema_fingerprint": "0" * 64,
        "fingerprint_algorithm_version": "v1",
        "field_mappings": [
            {
                "source_field": "torque_nm",
                "target_field": "torque_nm",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
            }
        ],
    }
    mapping_data["mapping_sha256"] = compute_mapping_canonical_sha256(mapping_data)

    # Sensor stream with records in 13:00 hour and 14:00 hour
    stream_file = tmp_path / "sensor" / "facS01" / "lineL01" / "sensor_stream.jsonl"
    stream_file.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:10:00Z", "torque_nm": 40.0},
        {"asset_id": "CNC-02", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:50:00Z", "torque_nm": 42.0},
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "torque_nm": 45.0},
    ]
    raw_bytes = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in records)
    stream_file.write_bytes(raw_bytes)

    source = GenDataSensorStreamSource(
        site_id="S01",
        cell_id="L01",
        facility_dir_name="facS01",
        line_dir_name="lineL01",
        source_path=stream_file,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
    )

    chk_repo = GenDataExtractionCheckpointRepository(checkpoints_root=checkpoints_dir)
    frag_repo = GenDataFragmentRepository(base_runs_dir=runs_dir)

    # 1. Incremental Extraction
    inc_service = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=locks_dir,
    )
    inc_res = inc_service.process_available_records(
        source=source,
        mapping_data=mapping_data,
        run_id="run-e2e-001",
    )
    assert inc_res.status == "fragment_committed"

    # 2. Window Publish Service
    publisher = ExtractionWindowPublisher(
        data_root=obs_dir,
        publications_root=pubs_dir,
    )
    lifecycle_mgr = GenDataFragmentLifecycleManager(
        consumption_root=consumption_dir,
        fragment_repo=frag_repo,
    )
    pub_service = ExtractionWindowPublishService(
        publisher=publisher,
        lifecycle_mgr=lifecycle_mgr,
        fragment_repo=frag_repo,
        runs_root=runs_dir,
    )

    pub_res = pub_service.publish_available_windows(
        source_identity=inc_res.source_identity,
        run_id="run-e2e-001",
        window_minutes=60,
    )

    assert len(pub_res.published_datasets) == 1
    ds = pub_res.published_datasets[0]
    assert ds.dataset_id == "gen-data-S01-L01"
    assert ds.window_start == "2026-08-28T13:00:00Z"
    assert ds.window_end == "2026-08-28T14:00:00Z"
    assert ds.observation_count == 2
