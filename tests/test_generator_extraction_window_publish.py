"""Unit and integration tests for Immutable Dataset Bundle Publishing and FeatureInputResolver compatibility."""

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from systems.generator.app.extraction.extraction_exception import (
    ExtractionDatasetConflictError,
    ExtractionNoValidObservationsError,
)
from systems.generator.app.extraction.window_assembler import (
    AssembledExtractionWindow,
    FragmentReference,
)
from systems.generator.app.extraction.window_publisher import (
    ExtractionWindowPublisher,
)
from systems.generator.app.feature.feature_input_resolver import (
    FeatureInputResolver,
)


@pytest.fixture
def sample_assembled_window() -> AssembledExtractionWindow:
    return AssembledExtractionWindow(
        source_identity="f" * 64,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        site_id="S01",
        cell_id="L01",
        dataset_id="gen-data-S01-L01",
        dataset_version="window-20260828T130000Z-map-a1b2c3d4",
        window_start="2026-08-28T13:00:00Z",
        window_end="2026-08-28T14:00:00Z",
        mapping_id="gen-data-sensor-stream-canonical",
        mapping_version="v1",
        mapping_sha256="a1b2c3d4" + "0" * 56,
        observations=[
            {
                "asset_id": "CNC-01",
                "observed_at": "2026-08-28T13:00:00Z",
                "torque_nm": 45.0,
            }
        ],
        provenance_records=[
            {
                "asset_id": "CNC-01",
                "observed_at": "2026-08-28T13:00:00Z",
                "source_uri": "sensor/facS01/lineL01/sensor_stream.jsonl",
                "source_byte_start": 0,
                "source_byte_end": 50,
                "source_line_number": 1,
                "source_row_sha256": "0" * 64,
                "mapping_id": "gen-data-sensor-stream-canonical",
                "mapping_version": "v1",
                "mapping_sha256": "a1b2c3d4" + "0" * 56,
                "extraction_run_id": "run-001",
                "batch_id": "b" * 64,
            }
        ],
        rejected_records=[],
        source_fragment_refs=[
            FragmentReference(batch_id="b" * 64, fragment_manifest_sha256="0" * 64)
        ],
        source_start_offset=0,
        source_end_offset=50,
    )


def test_window_publisher_atomic_publish_and_receipt(tmp_path, sample_assembled_window):
    """Publisher creates 4 files in data/observations, validates manifest, and saves publication receipt."""
    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"

    publisher = ExtractionWindowPublisher(
        data_root=data_root,
        publications_root=pubs_root,
    )

    published = publisher.publish_window_dataset(sample_assembled_window, run_id="run-001")

    assert Path(published.dataset_dir).is_dir()
    assert (Path(published.dataset_dir) / "dataset_manifest.json").is_file()
    assert (Path(published.dataset_dir) / "observations.jsonl").is_file()
    assert (Path(published.dataset_dir) / "provenance.jsonl").is_file()
    assert (Path(published.dataset_dir) / "rejected.jsonl").is_file()
    assert published.observation_count == 1

    # Receipt exists
    receipt_file = pubs_root / sample_assembled_window.source_identity / f"{sample_assembled_window.dataset_version}.json"
    assert receipt_file.is_file()


def test_window_publisher_zero_observations_rejected(tmp_path, sample_assembled_window):
    """Publishing window with 0 observations raises ExtractionNoValidObservationsError."""
    data_root = tmp_path / "data" / "observations"
    publisher = ExtractionWindowPublisher(data_root=data_root)

    empty_win = copy.deepcopy(sample_assembled_window)
    empty_win.observations = []

    with pytest.raises(ExtractionNoValidObservationsError):
        publisher.publish_window_dataset(empty_win, run_id="run-001")


def test_window_publisher_idempotency_and_conflict(tmp_path, sample_assembled_window):
    """Re-publishing identical dataset is idempotent; publishing conflicting payload raises ExtractionDatasetConflictError."""
    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"

    publisher = ExtractionWindowPublisher(
        data_root=data_root,
        publications_root=pubs_root,
    )

    # 1. First publish
    p1 = publisher.publish_window_dataset(sample_assembled_window, run_id="run-001")

    # 2. Idempotent publish
    p2 = publisher.publish_window_dataset(sample_assembled_window, run_id="run-001")
    assert p1.manifest_sha256 == p2.manifest_sha256

    # 3. Conflicting publish (different observation content for same dataset_version)
    conflict_win = copy.deepcopy(sample_assembled_window)
    conflict_win.observations[0]["torque_nm"] = 999.9

    with pytest.raises(ExtractionDatasetConflictError):
        publisher.publish_window_dataset(conflict_win, run_id="run-002")


def test_published_dataset_compatible_with_feature_input_resolver(tmp_path, sample_assembled_window, monkeypatch):
    """Published observation dataset can be resolved and loaded by FeatureInputResolver."""
    data_dir = tmp_path / "data"
    obs_dir = data_dir / "observations"

    from systems.generator.generator_config import PATHS
    monkeypatch.setattr(PATHS, "data_dir", data_dir)

    publisher = ExtractionWindowPublisher(
        data_root=obs_dir,
        publications_root=tmp_path / "pubs",
    )

    published = publisher.publish_window_dataset(sample_assembled_window, run_id="run-001")

    # Resolve using FeatureInputResolver
    resolver = FeatureInputResolver()
    resolved = resolver.resolve_dataset(
        dataset_type="observation",
        dataset_id=sample_assembled_window.dataset_id,
        dataset_version=sample_assembled_window.dataset_version,
    )

    assert resolved.dataset_id == sample_assembled_window.dataset_id
    assert resolved.dataset_version == sample_assembled_window.dataset_version
    assert resolved.payload_path.is_file()
    assert resolved.manifest_path.is_file()


def test_concurrent_identical_dataset_publish_race_idempotent_reuse(tmp_path, sample_assembled_window, monkeypatch):
    """When concurrent workers publish identical datasets and rename encounters existing destination, it reuses existing."""
    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"
    publisher = ExtractionWindowPublisher(data_root=data_root, publications_root=pubs_root)

    # 1. Worker A publishes successfully
    p1 = publisher.publish_window_dataset(sample_assembled_window, run_id="run-worker-a")
    orig_manifest_bytes = (Path(p1.dataset_dir) / "dataset_manifest.json").read_bytes()

    # 2. Worker B attempts to publish identical window, but simulates os.replace failing due to existing destination
    real_replace = os.replace

    def mock_replace(src, dst):
        if Path(dst) == Path(p1.dataset_dir):
            raise OSError("Destination already exists")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    p2 = publisher.publish_window_dataset(sample_assembled_window, run_id="run-worker-b")

    # Worker B safely reused existing dataset
    assert p2.manifest_sha256 == p1.manifest_sha256
    assert p2.observations_sha256 == p1.observations_sha256
    # Invariant: final directory was never deleted or corrupted
    assert (Path(p1.dataset_dir) / "dataset_manifest.json").read_bytes() == orig_manifest_bytes


def test_concurrent_different_dataset_publish_race_raises_conflict(tmp_path, sample_assembled_window, monkeypatch):
    """When concurrent worker publishes conflicting payload with same version, first is preserved and second gets ExtractionDatasetConflictError."""
    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"
    publisher = ExtractionWindowPublisher(data_root=data_root, publications_root=pubs_root)

    # 1. Worker A publishes dataset A
    p1 = publisher.publish_window_dataset(sample_assembled_window, run_id="run-worker-a")
    orig_obs_bytes = (Path(p1.dataset_dir) / "observations.jsonl").read_bytes()

    # 2. Worker B has conflicting window with same dataset_version
    conflict_win = copy.deepcopy(sample_assembled_window)
    conflict_win.observations[0]["torque_nm"] = 888.88

    # When Worker B publishes (either pre-check or rename race), it detects conflict
    with pytest.raises(ExtractionDatasetConflictError):
        publisher.publish_window_dataset(conflict_win, run_id="run-worker-b")

    # Invariant: Worker A's final directory remains intact and untouched
    assert (Path(p1.dataset_dir) / "observations.jsonl").read_bytes() == orig_obs_bytes


def test_publish_atomic_rename_failure_cleans_temp_and_preserves_state(tmp_path, sample_assembled_window, monkeypatch):
    """When atomic rename fails and destination does not exist, raises ExtractionPublishFailedError and cleans temp."""
    from systems.generator.app.extraction.extraction_exception import ExtractionPublishFailedError

    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"
    publisher = ExtractionWindowPublisher(data_root=data_root, publications_root=pubs_root)

    def mock_replace_fail(src, dst):
        raise OSError("Permission denied or disk full")

    monkeypatch.setattr(os, "replace", mock_replace_fail)

    final_dir = data_root / sample_assembled_window.dataset_id / sample_assembled_window.dataset_version

    with pytest.raises(ExtractionPublishFailedError):
        publisher.publish_window_dataset(sample_assembled_window, run_id="run-fail")

    # Final destination was not created
    assert not final_dir.exists()
    # Staging parent directory has no leftover temp dirs
    target_parent = data_root / sample_assembled_window.dataset_id
    temp_dirs = [d for d in target_parent.iterdir() if d.name.startswith(".tmp_")]
    assert len(temp_dirs) == 0


def test_existing_corrupted_dataset_raises_conflict_without_deletion(tmp_path, sample_assembled_window):
    """When existing dataset directory on disk is corrupted, publisher raises ExtractionDatasetConflictError and never deletes it."""
    data_root = tmp_path / "data" / "observations"
    pubs_root = tmp_path / "extraction_state" / "publications"
    publisher = ExtractionWindowPublisher(data_root=data_root, publications_root=pubs_root)

    final_dir = data_root / sample_assembled_window.dataset_id / sample_assembled_window.dataset_version
    final_dir.mkdir(parents=True, exist_ok=True)
    # Write a corrupt/empty manifest
    (final_dir / "dataset_manifest.json").write_text("{corrupt json", encoding="utf-8")

    with pytest.raises(ExtractionDatasetConflictError):
        publisher.publish_window_dataset(sample_assembled_window, run_id="run-corrupt")

    # Invariant: final_dir is NOT deleted or auto-recovered
    assert final_dir.exists()
    assert (final_dir / "dataset_manifest.json").read_text(encoding="utf-8") == "{corrupt json"
