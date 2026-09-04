"""Unit tests for UTC Window resolution, boundary checks, and Window Assembler."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from systems.generator.app.extraction.extraction_exception import (
    ExtractionDuplicateObservationNotSupportedError,
    ExtractionLateRecordNotSupportedError,
    ExtractionWindowConfigInvalidError,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.gen_data_mapping import (
    CanonicalObservationCandidate,
    RejectedMappingRecord,
)
from systems.generator.app.extraction.window_assembler import (
    ExtractionWindowAssembler,
)
from systems.generator.app.extraction.window_identity import (
    compute_window_dataset_identity,
    resolve_utc_window,
)


def test_resolve_utc_window_boundaries():
    """UTC Window correctly resolves half-open interval [start, end)."""
    w1 = resolve_utc_window("2026-08-28T13:00:00Z", window_minutes=60)
    assert w1.window_start_iso == "2026-08-28T13:00:00Z"
    assert w1.window_end_iso == "2026-08-28T14:00:00Z"
    assert w1.window_id == "20260828T130000Z"

    w2 = resolve_utc_window("2026-08-28T13:59:59Z", window_minutes=60)
    assert w2.window_start_iso == "2026-08-28T13:00:00Z"
    assert w2.window_end_iso == "2026-08-28T14:00:00Z"

    w3 = resolve_utc_window("2026-08-28T14:00:00Z", window_minutes=60)
    assert w3.window_start_iso == "2026-08-28T14:00:00Z"
    assert w3.window_end_iso == "2026-08-28T15:00:00Z"


def test_resolve_utc_window_invalid_configs():
    """Invalid window_minutes configurations are strictly rejected."""
    for invalid in [0, -10, True, False, "60", 30.5]:
        with pytest.raises(ExtractionWindowConfigInvalidError):
            resolve_utc_window("2026-08-28T13:00:00Z", window_minutes=invalid)  # type: ignore


def test_compute_window_dataset_identity():
    """Dataset ID and version are deterministic and match contract requirements."""
    dt = datetime(2026, 8, 28, 13, 0, 0, tzinfo=timezone.utc)
    ds_id, ds_ver = compute_window_dataset_identity(
        site_id="S01",
        cell_id="L01",
        window_start=dt,
        mapping_sha256="a1b2c3d4e5f6" + "0" * 52,
    )
    assert ds_id == "gen-data-S01-L01"
    assert ds_ver == "window-20260828T130000Z-map-a1b2c3d4"


def _make_candidate(asset_id: str, observed_at: str, mapping_sha: str = "a" * 64) -> CanonicalObservationCandidate:
    return CanonicalObservationCandidate(
        asset_id=asset_id,
        observed_at=observed_at,
        measurements={"torque_nm": 45.0},
        site_id="S01",
        cell_id="L01",
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        source_byte_start=0,
        source_byte_end=50,
        source_line_number=1,
        source_row_sha256="sha1",
        mapping_id="map-1",
        mapping_version="v1",
        mapping_sha256=mapping_sha,
        ignored_source_fields=(),
    )


def test_window_assembler_watermark_closing(tmp_path):
    """Assembler closes 13:00 window when 14:00 watermark arrives."""
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    assembler = ExtractionWindowAssembler(fragment_repo=frag_repo)
    mapping_sha = "a" * 64
    source_id = "f" * 64

    # Fragment 1: records at 13:10 and 13:40
    frag_dir_1, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id="b" * 64,
        source_identity=source_id,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        source_start_offset=0,
        source_end_offset=100,
        source_start_line=1,
        source_end_line=2,
        mapping_id="map-1",
        mapping_version="v1",
        mapping_sha256=mapping_sha,
        observations=[
            _make_candidate("CNC-01", "2026-08-28T13:10:00Z", mapping_sha),
            _make_candidate("CNC-02", "2026-08-28T13:40:00Z", mapping_sha),
        ],
        rejected_records=[],
    )

    # Fragment 2: record at 14:05 (advances watermark into 14:00)
    frag_dir_2, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id="c" * 64,
        source_identity=source_id,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        source_start_offset=100,
        source_end_offset=200,
        source_start_line=3,
        source_end_line=3,
        mapping_id="map-1",
        mapping_version="v1",
        mapping_sha256=mapping_sha,
        observations=[
            _make_candidate("CNC-01", "2026-08-28T14:05:00Z", mapping_sha),
        ],
        rejected_records=[],
    )

    windows = assembler.collect_publishable_windows(
        source_identity=source_id,
        fragment_dirs=[frag_dir_1, frag_dir_2],
        window_minutes=60,
    )

    # Only 13:00 window is closed and publishable
    assert len(windows) == 1
    assert windows[0].window_start == "2026-08-28T13:00:00Z"
    assert windows[0].window_end == "2026-08-28T14:00:00Z"
    assert len(windows[0].observations) == 2


def test_window_assembler_duplicate_rejected(tmp_path):
    """Duplicate observations (asset_id, observed_at) within a window raise ExtractionDuplicateObservationNotSupportedError."""
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    assembler = ExtractionWindowAssembler(fragment_repo=frag_repo)
    mapping_sha = "a" * 64
    source_id = "f" * 64

    frag_dir, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id="b" * 64,
        source_identity=source_id,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        source_start_offset=0,
        source_end_offset=100,
        source_start_line=1,
        source_end_line=2,
        mapping_id="map-1",
        mapping_version="v1",
        mapping_sha256=mapping_sha,
        observations=[
            _make_candidate("CNC-01", "2026-08-28T13:10:00Z", mapping_sha),
            _make_candidate("CNC-01", "2026-08-28T13:10:00Z", mapping_sha),  # Duplicate
        ],
        rejected_records=[],
    )

    with pytest.raises(ExtractionDuplicateObservationNotSupportedError):
        assembler.collect_publishable_windows(
            source_identity=source_id,
            fragment_dirs=[frag_dir],
            flush_before=datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc),
        )


def test_window_assembler_late_record_rejected(tmp_path):
    """Record arriving for an already closed window raises ExtractionLateRecordNotSupportedError."""
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    assembler = ExtractionWindowAssembler(fragment_repo=frag_repo)
    mapping_sha = "a" * 64
    source_id = "f" * 64

    frag_dir, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id="b" * 64,
        source_identity=source_id,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        source_start_offset=0,
        source_end_offset=100,
        source_start_line=1,
        source_end_line=1,
        mapping_id="map-1",
        mapping_version="v1",
        mapping_sha256=mapping_sha,
        observations=[
            _make_candidate("CNC-01", "2026-08-28T13:10:00Z", mapping_sha),
        ],
        rejected_records=[],
    )

    with pytest.raises(ExtractionLateRecordNotSupportedError):
        assembler.collect_publishable_windows(
            source_identity=source_id,
            fragment_dirs=[frag_dir],
            last_published_window_end=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc),
        )
