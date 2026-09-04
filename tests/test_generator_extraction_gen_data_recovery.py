"""Crash recovery regression tests across all failure injection points."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from systems.generator.app.extraction.checkpoint_repository import (
    GenDataExtractionCheckpointRepository,
)
from systems.generator.app.extraction.extraction_exception import (
    ExtractionFragmentConflictError,
)
from systems.generator.app.extraction.fragment_lifecycle import (
    GenDataFragmentLifecycleManager,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.gen_data_identity import (
    compute_extraction_batch_id,
    compute_gen_data_source_identity,
)
from systems.generator.app.extraction.gen_data_incremental_service import (
    GenDataIncrementalExtractionService,
)
from systems.generator.app.extraction.gen_data_mapping import (
    GenDataStaticMappingConverter,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
)
from systems.generator.app.extraction.mapping_validator import (
    compute_mapping_canonical_sha256,
)
from systems.generator.app.extraction.parsers.gen_data_sensor_stream_parser import (
    GenDataSensorStreamParser,
)
from systems.generator.app.extraction.window_assembler import (
    ExtractionWindowAssembler,
)
from systems.generator.app.extraction.window_publisher import (
    ExtractionWindowPublisher,
)
from systems.generator.app.extraction.window_publish_service import (
    ExtractionWindowPublishService,
)


@pytest.fixture
def mapping_fixture() -> dict:
    raw = {
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
            },
            {
                "source_field": "rotational_speed_rpm",
                "target_field": "rotational_speed_rpm",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
            },
        ],
    }
    raw["mapping_sha256"] = compute_mapping_canonical_sha256(raw)
    return raw


@pytest.fixture
def sample_source_stream(tmp_path) -> tuple[GenDataSensorStreamSource, bytes]:
    f = tmp_path / "sensor" / "facS01" / "lineL01" / "sensor_stream.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "torque_nm": 45.0},
        {"asset_id": "CNC-02", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:01:00Z", "rotational_speed_rpm": 1500.0},
        {"asset_id": "CNC-03", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:02:00Z", "torque_nm": 50.0},
    ]
    raw_lines = [json.dumps(r).encode("utf-8") + b"\n" for r in records]
    full_bytes = b"".join(raw_lines)
    f.write_bytes(full_bytes)

    source = GenDataSensorStreamSource(
        site_id="S01",
        cell_id="L01",
        facility_dir_name="facS01",
        line_dir_name="lineL01",
        source_path=f,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
    )
    return source, full_bytes


@pytest.mark.parametrize(
    "failure_point",
    [
        "after_lock_acquired",
        "after_processing_checkpoint",
        "after_fragment_files_written",
        "after_fragment_manifest_written",
        "after_fragment_renamed",
        "after_pending_checkpoint_written",
        "after_committed_checkpoint_written",
    ],
)
def test_crash_recovery_at_failure_injection_points(
    tmp_path, mapping_fixture, sample_source_stream, failure_point
):
    """Crash at any stage leaves system in a clean, recoverable state with zero duplicated records upon restart."""
    source, full_bytes = sample_source_stream

    chk_repo = GenDataExtractionCheckpointRepository(checkpoints_root=tmp_path / "checkpoints")
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    lock_dir = tmp_path / "locks"

    class InjectedCrash(Exception):
        pass

    def injector(point: str):
        if point == failure_point:
            raise InjectedCrash(f"Simulated crash at {point}")

    service_fail = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=injector,
    )

    # 1. First execution crashes at failure_point
    with pytest.raises(Exception) as exc_info:
        service_fail.process_available_records(
            source=source,
            mapping_data=mapping_fixture,
            run_id="run-crash-test",
        )
    # Ensure the crash was indeed triggered by the failure injector
    assert "Simulated crash at" in str(exc_info.value) or (
        exc_info.value.__cause__ is not None and "Simulated crash at" in str(exc_info.value.__cause__)
    )

    # 2. Restart and re-run recovery without crash
    service_recover = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=None,
    )

    res = service_recover.process_available_records(
        source=source,
        mapping_data=mapping_fixture,
        run_id="run-crash-test",
    )

    # 3. Recovery assertions
    assert res.status in ("fragment_committed", "no_data")
    assert res.committed_offset == len(full_bytes)

    # 4. Subsequent run produces no_data (cleanly caught up)
    res_subsequent = service_recover.process_available_records(
        source=source,
        mapping_data=mapping_fixture,
        run_id="run-crash-test",
    )
    assert res_subsequent.status == "no_data"
    assert res_subsequent.records_read == 0


def test_cross_run_crash_recovery_after_fragment_renamed(
    tmp_path, mapping_fixture, sample_source_stream
):
    """When crash occurs after fragment is renamed (run-A) and next cycle starts with run-B:

    1. run-B discovers and reuses the existing run-A fragment.
    2. No duplicate fragment is created in run-B directory.
    3. Checkpoint commits successfully with offset at EOF.
    4. Window publish publishes the dataset with exact record count and 0 duplicates.
    5. Next polling cycle run-C returns no_data.
    """
    source, full_bytes = sample_source_stream

    chk_repo = GenDataExtractionCheckpointRepository(checkpoints_root=tmp_path / "checkpoints")
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    lock_dir = tmp_path / "locks"

    class InjectedCrash(Exception):
        pass

    def injector(point: str):
        if point == "after_fragment_renamed":
            raise InjectedCrash("Simulated crash at after_fragment_renamed")

    # 1. Cycle A crashes right after fragment rename
    service_a = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=injector,
    )
    with pytest.raises(Exception):
        service_a.process_available_records(
            source=source,
            mapping_data=mapping_fixture,
            run_id="run-cycle-A",
        )

    # Verify run-A fragment exists
    run_a_frags = list((tmp_path / "runs" / "run-cycle-A" / "fragments").iterdir())
    assert len(run_a_frags) == 1
    batch_id = run_a_frags[0].name

    # 2. Cycle B runs with new run_id
    service_b = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=None,
    )
    res_b = service_b.process_available_records(
        source=source,
        mapping_data=mapping_fixture,
        run_id="run-cycle-B",
    )

    assert res_b.status == "fragment_committed"
    assert res_b.committed_offset == len(full_bytes)

    # Invariant: batch_id directory exists only once across all runs
    all_batch_dirs = list((tmp_path / "runs").glob(f"*/fragments/{batch_id}"))
    assert len(all_batch_dirs) == 1
    assert all_batch_dirs[0].parent.parent.name == "run-cycle-A"

    # Checkpoint verification
    first_peek = GenDataSensorStreamParser().read_completed_records(source.source_path, start_offset=0, max_records=1)
    source_identity = compute_gen_data_source_identity(
        source_uri=source.source_uri,
        site_id=source.site_id,
        cell_id=source.cell_id,
        first_record_sha256=first_peek.records[0].raw_sha256,
    )
    chk = chk_repo.load_checkpoint(source_identity)
    assert chk is not None
    assert chk.last_committed_batch_id == batch_id
    assert chk.last_committed_offset == len(full_bytes)
    assert chk.status == "idle"

    # 3. Publish window dataset
    assembler = ExtractionWindowAssembler(fragment_repo=frag_repo)
    publisher = ExtractionWindowPublisher(data_root=tmp_path / "datasets")
    lifecycle_mgr = GenDataFragmentLifecycleManager(
        consumption_root=tmp_path / "consumption",
        fragment_repo=frag_repo,
    )
    publish_service = ExtractionWindowPublishService(
        assembler=assembler,
        publisher=publisher,
        lifecycle_mgr=lifecycle_mgr,
        fragment_repo=frag_repo,
        runs_root=tmp_path / "runs",
    )

    from datetime import datetime, timezone
    now_dt = datetime.now(timezone.utc)
    pub_result = publish_service.publish_available_windows(
        source_identity=source_identity,
        run_id="run-cycle-B",
        flush_before=now_dt,
    )

    assert pub_result.status == "published"
    assert len(pub_result.published_datasets) == 1
    pub_ds = pub_result.published_datasets[0]

    # Verify observations in dataset: exactly 3 rows, no duplicate asset_id+observed_at
    obs_file = Path(pub_ds.dataset_dir) / "observations.jsonl"
    lines = [json.loads(l) for l in obs_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3
    seen_keys = set()
    for row in lines:
        k = (row["asset_id"], row["observed_at"])
        assert k not in seen_keys
        seen_keys.add(k)

    # 4. Next polling cycle run-C returns no_data
    service_c = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=None,
    )
    res_c = service_c.process_available_records(
        source=source,
        mapping_data=mapping_fixture,
        run_id="run-cycle-C",
    )
    assert res_c.status == "no_data"
    assert res_c.records_read == 0


def test_cross_run_conflicting_fragment_raises_error(
    tmp_path, mapping_fixture, sample_source_stream
):
    """When a fragment for the same batch_id in run-A has conflicting metadata (e.g. mapping_sha256 mismatch),
    run-B raises ExtractionFragmentConflictError and leaves checkpoint unchanged."""
    source, full_bytes = sample_source_stream

    chk_repo = GenDataExtractionCheckpointRepository(checkpoints_root=tmp_path / "checkpoints")
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    lock_dir = tmp_path / "locks"

    # 1. Normal run-A
    service_a = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=None,
    )
    res_a = service_a.process_available_records(
        source=source,
        mapping_data=mapping_fixture,
        run_id="run-cycle-A",
    )
    batch_id = res_a.batch_id

    # Tamper with the manifest mapping_sha256 in run-cycle-A
    manifest_file = tmp_path / "runs" / "run-cycle-A" / "fragments" / batch_id / "fragment_manifest.json"
    m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    m_data["mapping_sha256"] = "f" * 64
    manifest_file.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    # Reset checkpoint to offset 0 to simulate re-extraction attempt
    source_identity = res_a.source_identity
    chk = chk_repo.load_checkpoint(source_identity)
    chk.last_committed_offset = 0
    chk.last_committed_line = 0
    chk.last_committed_batch_id = None
    chk.committed_batch_ids = []
    chk_repo.save_checkpoint_atomic(chk)

    # 2. Run B attempts to process
    service_b = GenDataIncrementalExtractionService(
        checkpoint_repo=chk_repo,
        fragment_repo=frag_repo,
        lock_dir=lock_dir,
        failure_injector=None,
    )
    with pytest.raises(ExtractionFragmentConflictError):
        service_b.process_available_records(
            source=source,
            mapping_data=mapping_fixture,
            run_id="run-cycle-B",
        )


def test_fragment_atomic_rename_race_idempotent_reuse(tmp_path, mapping_fixture, sample_source_stream):
    """When atomic rename hits an existing identical fragment directory, reuses it without deleting final_batch_dir."""
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    from systems.generator.app.extraction.gen_data_mapping import CanonicalObservationCandidate

    now_iso = "2026-08-28T13:00:00Z"
    obs = [
        CanonicalObservationCandidate(
            source_uri="sensor/stream.jsonl",
            source_byte_start=0,
            source_byte_end=50,
            source_line_number=1,
            source_row_sha256="a" * 64,
            asset_id="CNC-01",
            site_id="S01",
            cell_id="L01",
            observed_at=now_iso,
            measurements={"torque_nm": 45.0},
            mapping_id="gen-data-sensor-stream-canonical",
            mapping_version="v1",
            mapping_sha256="c" * 64,
            ignored_source_fields=(),
        )
    ]

    batch_id = "b" * 64
    source_id = "d" * 64

    # 1. First save succeeds
    final_dir_1, manifest_1, sha_1 = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id=batch_id,
        source_identity=source_id,
        source_uri="sensor/stream.jsonl",
        source_start_offset=0,
        source_end_offset=50,
        source_start_line=1,
        source_end_line=1,
        mapping_id="gen-data-sensor-stream-canonical",
        mapping_version="v1",
        mapping_sha256="c" * 64,
        observations=obs,
        rejected_records=[],
    )

    assert final_dir_1.is_dir()

    # 2. Second save with identical params in the same run reuses existing directory
    final_dir_2, manifest_2, sha_2 = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id=batch_id,
        source_identity=source_id,
        source_uri="sensor/stream.jsonl",
        source_start_offset=0,
        source_end_offset=50,
        source_start_line=1,
        source_end_line=1,
        mapping_id="gen-data-sensor-stream-canonical",
        mapping_version="v1",
        mapping_sha256="c" * 64,
        observations=obs,
        rejected_records=[],
    )

    assert final_dir_2 == final_dir_1
    assert sha_2 == sha_1
    assert final_dir_1.is_dir()


def test_window_assembly_duplicate_batch_across_runs_raises_conflict(tmp_path, mapping_fixture, sample_source_stream):
    """When window assembler receives two fragment directories with the same batch_id, it raises ExtractionFragmentConflictError."""
    frag_repo = GenDataFragmentRepository(base_runs_dir=tmp_path / "runs")
    from systems.generator.app.extraction.gen_data_mapping import CanonicalObservationCandidate

    now_iso = "2026-08-28T13:00:00Z"
    obs = [
        CanonicalObservationCandidate(
            source_uri="sensor/stream.jsonl",
            source_byte_start=0,
            source_byte_end=50,
            source_line_number=1,
            source_row_sha256="a" * 64,
            asset_id="CNC-01",
            site_id="S01",
            cell_id="L01",
            observed_at=now_iso,
            measurements={"torque_nm": 45.0},
            mapping_id="gen-data-sensor-stream-canonical",
            mapping_version="v1",
            mapping_sha256="c" * 64,
            ignored_source_fields=(),
        )
    ]

    batch_id = "b" * 64
    source_id = "d" * 64

    # Create fragment in run-1
    final_dir_1, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-1",
        batch_id=batch_id,
        source_identity=source_id,
        source_uri="sensor/stream.jsonl",
        source_start_offset=0,
        source_end_offset=50,
        source_start_line=1,
        source_end_line=1,
        mapping_id="gen-data-sensor-stream-canonical",
        mapping_version="v1",
        mapping_sha256="c" * 64,
        observations=obs,
        rejected_records=[],
    )

    # Create fragment in run-2
    final_dir_2, _, _ = frag_repo.save_fragment_atomic(
        run_id="run-2",
        batch_id=batch_id,
        source_identity=source_id,
        source_uri="sensor/stream.jsonl",
        source_start_offset=0,
        source_end_offset=50,
        source_start_line=1,
        source_end_line=1,
        mapping_id="gen-data-sensor-stream-canonical",
        mapping_version="v1",
        mapping_sha256="c" * 64,
        observations=obs,
        rejected_records=[],
    )

    assembler = ExtractionWindowAssembler(fragment_repo=frag_repo)
    with pytest.raises(ExtractionFragmentConflictError):
        assembler.collect_publishable_windows(
            source_identity=source_id,
            fragment_dirs=[final_dir_1, final_dir_2],
        )
