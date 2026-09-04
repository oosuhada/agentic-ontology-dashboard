"""Unit and integration tests for Background Extraction Worker and Extraction Manager."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from systems.generator.generator_config import PATHS
from systems.generator.app.extraction.extraction_exception import (
    ExtractionCheckpointInvalidError,
    ExtractionConfigurationInvalidError,
    ExtractionFragmentConflictError,
    ExtractionFragmentVerifyFailedError,
    ExtractionFragmentWriteFailedError,
    ExtractionMappingConfigurationMissingError,
    ExtractionMappingRebuildNotImplementedError,
)
from systems.generator.app.extraction.extraction_manager import (
    ExtractionManager,
)
from systems.generator.app.extraction.extraction_worker import (
    ExtractionWorker,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
)
from systems.generator.app.extraction.mapping_validator import (
    compute_mapping_canonical_sha256,
)


@pytest.fixture
def sample_mapping():
    m = {
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
    m["mapping_sha256"] = compute_mapping_canonical_sha256(m)
    return m


def test_worker_config_validation(tmp_path, monkeypatch):
    """Validation strictly checks required extraction parameters."""
    monkeypatch.setattr(PATHS, "extraction_poll_interval_seconds", 0)
    with pytest.raises(ExtractionConfigurationInvalidError):
        PATHS.validate_extraction_config()

    monkeypatch.setattr(PATHS, "extraction_poll_interval_seconds", 5.0)
    monkeypatch.setattr(PATHS, "extraction_enabled", True)
    monkeypatch.setattr(PATHS, "gen_data_output_dir", None)
    with pytest.raises(ExtractionConfigurationInvalidError):
        PATHS.validate_extraction_config()


def test_worker_lifecycle_enabled_false(tmp_path, monkeypatch):
    """When extraction_enabled=False, start() does not launch background task."""
    async def _test():
        monkeypatch.setattr(PATHS, "extraction_enabled", False)
        manager = ExtractionManager()
        await manager.start()
        assert manager.running is False
        await manager.stop()

    asyncio.run(_test())


def test_worker_lifecycle_enabled_true(tmp_path, monkeypatch, sample_mapping):
    """When extraction_enabled=True, start() launches worker and stop() terminates cleanly."""
    async def _test():
        sensor_dir = tmp_path / "gen_data" / "sensor"
        sensor_dir.mkdir(parents=True)

        monkeypatch.setattr(PATHS, "extraction_enabled", True)
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_dir)
        monkeypatch.setattr(PATHS, "extraction_mapping_sha256", sample_mapping["mapping_sha256"])

        manager = ExtractionManager()
        await manager.start()
        assert manager.running is True
        await manager.stop()
        assert manager.running is False

    asyncio.run(_test())


def test_worker_polling_single_cycle(tmp_path, monkeypatch, sample_mapping):
    """Worker single cycle detects new sensor data, processes records, and publishes datasets."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        stream_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        stream_file.parent.mkdir(parents=True, exist_ok=True)

        # 13:00 and 14:00 records
        records = [
            {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:10:00Z", "torque_nm": 40.0},
            {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T14:05:00Z", "torque_nm": 45.0},
        ]
        raw_bytes = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in records)
        stream_file.write_bytes(raw_bytes)

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "observations_root", tmp_path / "data" / "observations")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)
        monkeypatch.setattr(PATHS, "extraction_mapping_sha256", sample_mapping["mapping_sha256"])

        manager = ExtractionManager()
        # Mock resolve_mapping_data to return sample_mapping
        monkeypatch.setattr(manager, "_resolve_mapping_data", lambda *args, **kwargs: sample_mapping)

        worker = ExtractionWorker(manager=manager)
        await worker.run_single_cycle()

        status = manager.get_status()
        assert status.discovered_source_count == 1
        src_stat = status.sources[0]
        assert src_stat.status == "waiting"
        assert src_stat.last_committed_offset == len(raw_bytes)
        assert src_stat.last_published_window is not None

    asyncio.run(_test())


def test_worker_truncated_file_blocked(tmp_path, monkeypatch, sample_mapping):
    """When file size drops below last_committed_offset, source is set to blocked."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        stream_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        stream_file.parent.mkdir(parents=True, exist_ok=True)

        stream_file.write_bytes(b'{"asset_id":"CNC-01"}\n')

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)

        manager = ExtractionManager()
        source_key = "sensor/facS01/lineL01/sensor_stream.jsonl"
        from systems.generator.app.extraction.extraction_schema import ExtractionSourceStatus
        manager._source_states[source_key] = ExtractionSourceStatus(
            source_uri=source_key,
            site_id="S01",
            cell_id="L01",
            status="waiting",
            last_committed_offset=5000,  # larger than actual file
        )

        worker = ExtractionWorker(manager=manager)
        await worker.run_single_cycle()

        src_stat = manager._source_states[source_key]
        assert src_stat.status == "blocked"
        assert src_stat.error_code == "EXTRACTION_SOURCE_TRUNCATED"

    asyncio.run(_test())


def test_worker_isolation_one_failure_does_not_stop_others(tmp_path, monkeypatch, sample_mapping):
    """Failure in Source 1 does not affect successful extraction in Source 2."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        s1_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        s2_file = sensor_root / "facS02" / "lineL02" / "sensor_stream.jsonl"
        s1_file.parent.mkdir(parents=True, exist_ok=True)
        s2_file.parent.mkdir(parents=True, exist_ok=True)

        s1_file.write_bytes(b"invalid json stream\n")
        s2_records = [
            {"asset_id": "CNC-02", "site_id": "S02", "cell_id": "L02", "observed_at": "2026-08-28T13:10:00Z", "torque_nm": 30.0},
            {"asset_id": "CNC-02", "site_id": "S02", "cell_id": "L02", "observed_at": "2026-08-28T14:05:00Z", "torque_nm": 35.0},
        ]
        s2_file.write_bytes(b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in s2_records))

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "observations_root", tmp_path / "data" / "observations")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)
        monkeypatch.setattr(PATHS, "extraction_mapping_sha256", sample_mapping["mapping_sha256"])

        manager = ExtractionManager()
        monkeypatch.setattr(manager, "_resolve_mapping_data", lambda *args, **kwargs: sample_mapping)

        worker = ExtractionWorker(manager=manager)
        await worker.run_single_cycle()

        s2_key = "sensor/facS02/lineL02/sensor_stream.jsonl"
        assert s2_key in manager._source_states
        assert manager._source_states[s2_key].status == "waiting"
        assert manager._source_states[s2_key].last_committed_offset > 0

    asyncio.run(_test())


def test_manager_transient_fragment_write_failure_queued_and_retryable(tmp_path, monkeypatch, sample_mapping):
    """When incremental service raises ExtractionFragmentWriteFailedError, source state transitions to queued with incremented attempt."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        stream_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_bytes(b'{"asset_id":"CNC-01","observed_at":"2026-08-28T13:00:00Z","torque_nm":45.0}\n')

        source = GenDataSensorStreamSource(
            site_id="S01",
            cell_id="L01",
            facility_dir_name="facS01",
            line_dir_name="lineL01",
            source_path=stream_file,
            source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        )

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)
        monkeypatch.setattr(PATHS, "extraction_max_attempts", 3)

        manager = ExtractionManager()
        monkeypatch.setattr(manager, "_resolve_mapping_data", lambda *args, **kwargs: sample_mapping)

        def mock_process_records(*args, **kwargs):
            raise ExtractionFragmentWriteFailedError("simulated transient fragment storage failure")

        monkeypatch.setattr(manager.incremental_service, "process_available_records", mock_process_records)

        # 1. First execution
        res = await manager.process_source_once(
            source=source,
            mapping_id="gen-data-sensor-stream-canonical",
            mapping_version="v1",
            mapping_sha256=sample_mapping["mapping_sha256"],
            raise_on_error=False,
        )

        source_key = source.source_uri
        state = manager._source_states[source_key]

        assert state.error_code == "EXTRACTION_FRAGMENT_WRITE_FAILED"
        assert state.retryable is True
        assert state.status == "queued"
        assert state.attempt == 1
        assert state.status != "blocked"
        assert res.status == "failed"

    asyncio.run(_test())


def test_manager_transient_failure_exhausts_max_attempts_transitions_to_failed(tmp_path, monkeypatch, sample_mapping):
    """When transient failure repeats up to max_attempts, source transitions to failed (EXTRACTION_RETRY_EXHAUSTED)."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        stream_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_bytes(b'{"asset_id":"CNC-01","observed_at":"2026-08-28T13:00:00Z","torque_nm":45.0}\n')

        source = GenDataSensorStreamSource(
            site_id="S01",
            cell_id="L01",
            facility_dir_name="facS01",
            line_dir_name="lineL01",
            source_path=stream_file,
            source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        )

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)
        monkeypatch.setattr(PATHS, "extraction_max_attempts", 3)

        manager = ExtractionManager()
        monkeypatch.setattr(manager, "_resolve_mapping_data", lambda *args, **kwargs: sample_mapping)

        def mock_process_records(*args, **kwargs):
            raise ExtractionFragmentWriteFailedError("simulated transient fragment storage failure")

        monkeypatch.setattr(manager.incremental_service, "process_available_records", mock_process_records)

        source_key = source.source_uri

        # Attempt 1
        await manager.process_source_once(source=source, raise_on_error=False)
        assert manager._source_states[source_key].status == "queued"
        assert manager._source_states[source_key].attempt == 1

        # Attempt 2
        await manager.process_source_once(source=source, raise_on_error=False)
        assert manager._source_states[source_key].status == "queued"
        assert manager._source_states[source_key].attempt == 2

        # Attempt 3 (reaches max_attempts)
        await manager.process_source_once(source=source, raise_on_error=False)
        assert manager._source_states[source_key].status == "failed"
        assert manager._source_states[source_key].error_code == "EXTRACTION_RETRY_EXHAUSTED"
        assert manager._source_states[source_key].attempt == 3

    asyncio.run(_test())


@pytest.mark.parametrize(
    "exception_cls, expected_error_code",
    [
        (ExtractionFragmentConflictError, "EXTRACTION_FRAGMENT_CONFLICT"),
        (ExtractionFragmentVerifyFailedError, "EXTRACTION_FRAGMENT_VERIFY_FAILED"),
        (ExtractionMappingRebuildNotImplementedError, "EXTRACTION_MAPPING_REBUILD_NOT_IMPLEMENTED"),
        (ExtractionCheckpointInvalidError, "EXTRACTION_CHECKPOINT_INVALID"),
    ],
)
def test_manager_non_retryable_failure_transitions_to_blocked(
    tmp_path, monkeypatch, sample_mapping, exception_cls, expected_error_code
):
    """When a non-retryable domain error occurs, retryable is False and state immediately transitions to blocked."""
    async def _test():
        sensor_root = tmp_path / "gen_data" / "sensor"
        stream_file = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_bytes(b'{"asset_id":"CNC-01","observed_at":"2026-08-28T13:00:00Z","torque_nm":45.0}\n')

        source = GenDataSensorStreamSource(
            site_id="S01",
            cell_id="L01",
            facility_dir_name="facS01",
            line_dir_name="lineL01",
            source_path=stream_file,
            source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
        )

        monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
        monkeypatch.setattr(PATHS, "data_preprocessed", tmp_path / "preprocessed")
        monkeypatch.setattr(PATHS, "gen_data_output_dir", tmp_path / "gen_data")
        monkeypatch.setattr(PATHS, "gen_data_sensor_root", sensor_root)

        manager = ExtractionManager()
        monkeypatch.setattr(manager, "_resolve_mapping_data", lambda *args, **kwargs: sample_mapping)

        exc_instance = exception_cls("simulated non-retryable contract error")
        assert exc_instance.retryable is False

        def mock_process_records(*args, **kwargs):
            raise exc_instance

        monkeypatch.setattr(manager.incremental_service, "process_available_records", mock_process_records)

        source_key = source.source_uri
        res = await manager.process_source_once(source=source, raise_on_error=False)

        state = manager._source_states[source_key]
        assert state.retryable is False
        assert state.status == "blocked"
        assert state.error_code == expected_error_code
        assert res.status == "blocked"

    asyncio.run(_test())
