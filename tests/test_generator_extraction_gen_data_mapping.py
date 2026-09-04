"""Unit tests for gen_data Wide-format Static Mapping and Canonical Observation Conversion."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from systems.generator.app.extraction.extraction_exception import (
    ExtractionFeatureNotImplementedError,
    ExtractionMappingChecksumMismatchError,
    ExtractionMappingDuplicateSourceFieldError,
    ExtractionMappingEmptyError,
    ExtractionMappingNotApprovedError,
    ExtractionMappingReservedTargetFieldError,
    ExtractionMappingSourceFormatMismatchError,
    ExtractionMappingTargetCollisionError,
    ExtractionRequestInvalidError,
)
from systems.generator.app.extraction.gen_data_mapping import (
    CanonicalObservationCandidate,
    GenDataMappingResult,
    GenDataStaticMappingConverter,
    RejectedMappingRecord,
    normalize_strict_iso_utc,
)
from systems.generator.app.extraction.gen_data_source import GenDataSensorStreamSource
from systems.generator.app.extraction.mapping_validator import (
    MappingValidator,
    compute_mapping_canonical_sha256,
    compute_source_schema_fingerprint,
)
from systems.generator.app.extraction.parsers.gen_data_sensor_stream_parser import (
    ParsedGenDataRecord,
)


@pytest.fixture
def source_stream_fixture(tmp_path) -> GenDataSensorStreamSource:
    path = tmp_path / "sensor" / "facS01" / "lineL01" / "sensor_stream.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return GenDataSensorStreamSource(
        site_id="S01",
        cell_id="L01",
        facility_dir_name="facS01",
        line_dir_name="lineL01",
        source_path=path,
        source_uri="sensor/facS01/lineL01/sensor_stream.jsonl",
    )


@pytest.fixture
def valid_gen_data_mapping_data() -> dict:
    raw_mapping = {
        "$schema": "https://ontology-dashboard.local/schemas/generator-static-mapping-table.schema.json",
        "mapping_id": "gen-data-sensor-stream-canonical",
        "mapping_version": "v1",
        "status": "approved",
        "source_format": "gen_data_sensor_stream",
        "source_schema_version": "gen-data-sensor-stream-v1",
        "source_schema_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
        "fingerprint_algorithm_version": "v1",
        "description": "Static wide-format mapping for gen_data sensor_stream.jsonl",
        "field_mappings": [
            {
                "source_field": "air_temperature_k",
                "target_field": "air_temperature_k",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "K",
            },
            {
                "source_field": "process_temperature_k",
                "target_field": "process_temperature_k",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "K",
            },
            {
                "source_field": "rotational_speed_rpm",
                "target_field": "rotational_speed_rpm",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "rpm",
            },
            {
                "source_field": "torque_nm",
                "target_field": "torque_nm",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "N·m",
            },
            {
                "source_field": "tool_wear_min",
                "target_field": "tool_wear_min",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "min",
            },
            {
                "source_field": "voltage_raw",
                "target_field": "voltage",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "V",
            },
            {
                "source_field": "rotation_raw",
                "target_field": "rotation",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
                "unit": "rpm",
            },
            {
                "source_field": "pressure_raw",
                "target_field": "pressure",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
            },
            {
                "source_field": "vibration_raw",
                "target_field": "vibration",
                "source_type": "number",
                "target_type": "float",
                "required": False,
                "transform": "to_float",
            },
            {
                "source_field": "is_operating",
                "target_field": "is_operating",
                "source_type": "bool",
                "target_type": "bool",
                "required": False,
                "transform": "identity",
            },
        ],
    }
    raw_mapping["mapping_sha256"] = compute_mapping_canonical_sha256(raw_mapping)
    return raw_mapping


# =============================================================================
# 1. Mapping Contract & Validator Tests
# =============================================================================


def test_mapping_validator_approved_passes(valid_gen_data_mapping_data):
    validator = MappingValidator()
    validator.validate_mapping(valid_gen_data_mapping_data, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_draft_status_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["status"] = "draft"
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingNotApprovedError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_checksum_mismatch_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["mapping_sha256"] = "a" * 64
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingChecksumMismatchError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_source_format_mismatch_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["source_format"] = "sensor_record_v2"
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingSourceFormatMismatchError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_duplicate_source_field_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["field_mappings"].append(
        {
            "source_field": "air_temperature_k",
            "target_field": "air_temp_dup",
            "source_type": "number",
            "target_type": "float",
            "required": False,
            "transform": "to_float",
        }
    )
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingDuplicateSourceFieldError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_target_collision_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["field_mappings"].append(
        {
            "source_field": "temp_secondary",
            "target_field": "air_temperature_k",
            "source_type": "number",
            "target_type": "float",
            "required": False,
            "transform": "to_float",
        }
    )
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingTargetCollisionError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_reserved_target_field_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["field_mappings"].append(
        {
            "source_field": "custom_asset",
            "target_field": "asset_id",
            "source_type": "string",
            "target_type": "string",
            "required": False,
            "transform": "identity",
        }
    )
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    with pytest.raises(ExtractionMappingReservedTargetFieldError):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


def test_mapping_validator_unsupported_transform_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["field_mappings"][0]["transform"] = "unsupported_func"
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    # Schema validation or allowlist check rejects invalid transform
    with pytest.raises((ExtractionFeatureNotImplementedError, ExtractionRequestInvalidError)):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")

    # Direct apply_transform call raises ExtractionFeatureNotImplementedError
    with pytest.raises(ExtractionFeatureNotImplementedError):
        validator.apply_transform(100.0, "unsupported_func", "float")


def test_mapping_validator_empty_mappings_rejected(valid_gen_data_mapping_data):
    bad = copy.deepcopy(valid_gen_data_mapping_data)
    bad["field_mappings"] = []
    bad["mapping_sha256"] = compute_mapping_canonical_sha256(bad)
    validator = MappingValidator()
    # Schema minItems validation or empty mappings check rejects empty mappings
    with pytest.raises((ExtractionMappingEmptyError, ExtractionRequestInvalidError)):
        validator.validate_mapping(bad, expected_source_format="gen_data_sensor_stream")


# =============================================================================
# 2. CNC Record Conversion Tests
# =============================================================================


def test_converter_cnc_record_success(source_stream_fixture, valid_gen_data_mapping_data):
    record_data = {
        "asset_id": "CNC-S01-L01-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T22:00:00+09:00",
        "air_temperature_k": 300.1,
        "process_temperature_k": 310.2,
        "rotational_speed_rpm": 1502.1,
        "torque_nm": 40.2,
        "tool_wear_min": 12.0,
        "is_operating": True,
        "debug_raw_val": 9999,
        "extra_info": "ignored",
    }
    raw_line = json.dumps(record_data).encode("utf-8") + b"\n"
    parsed_record = ParsedGenDataRecord(
        byte_start=0,
        byte_end=len(raw_line),
        line_number=1,
        raw_sha256=hashlib.sha256(raw_line).hexdigest(),
        data=record_data,
    )

    converter = GenDataStaticMappingConverter()
    result = converter.convert(
        record=parsed_record,
        source=source_stream_fixture,
        mapping_data=valid_gen_data_mapping_data,
    )

    assert result.rejected is None
    assert result.observation is not None

    cand = result.observation
    assert cand.asset_id == "CNC-S01-L01-01"
    assert cand.observed_at == "2026-08-28T13:00:00Z"
    assert cand.site_id == "S01"
    assert cand.cell_id == "L01"
    assert cand.ignored_source_fields == ("debug_raw_val", "extra_info")

    obs_dict = cand.to_observation_dict()
    assert obs_dict == {
        "asset_id": "CNC-S01-L01-01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": 300.1,
        "process_temperature_k": 310.2,
        "rotational_speed_rpm": 1502.1,
        "torque_nm": 40.2,
        "tool_wear_min": 12.0,
        "is_operating": True,
    }

    prov_dict = cand.to_provenance_dict(extraction_run_id="run-12345")
    assert prov_dict["extraction_run_id"] == "run-12345"
    assert prov_dict["source_uri"] == "sensor/facS01/lineL01/sensor_stream.jsonl"
    assert prov_dict["source_byte_start"] == 0
    assert prov_dict["source_row_sha256"] == parsed_record.raw_sha256


# =============================================================================
# 3. Compressor Record Conversion Tests
# =============================================================================


def test_converter_compressor_record_success(source_stream_fixture, valid_gen_data_mapping_data):
    record_data = {
        "asset_id": "CMP-S01-L01-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "voltage_raw": 220.5,
        "rotation_raw": 1780.0,
        "pressure_raw": 6.8,
        "vibration_raw": 0.045,
        "is_operating": True,
    }
    raw_line = json.dumps(record_data).encode("utf-8") + b"\n"
    parsed_record = ParsedGenDataRecord(
        byte_start=100,
        byte_end=100 + len(raw_line),
        line_number=2,
        raw_sha256=hashlib.sha256(raw_line).hexdigest(),
        data=record_data,
    )

    converter = GenDataStaticMappingConverter()
    result = converter.convert(
        record=parsed_record,
        source=source_stream_fixture,
        mapping_data=valid_gen_data_mapping_data,
    )

    assert result.rejected is None
    assert result.observation is not None
    obs_dict = result.observation.to_observation_dict()
    assert obs_dict == {
        "asset_id": "CMP-S01-L01-01",
        "observed_at": "2026-08-28T13:00:00Z",
        "voltage": 220.5,
        "rotation": 1780.0,
        "pressure": 6.8,
        "vibration": 0.045,
        "is_operating": True,
    }


# =============================================================================
# 4. Identity & Scope Mismatch Tests
# =============================================================================


def test_converter_missing_asset_id(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": 300.0,
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_ASSET_ID_MISSING"


def test_converter_scope_mismatch_site_id(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S02",  # Mismatch with source S01
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": 300.0,
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_SOURCE_SCOPE_MISMATCH"


def test_converter_scope_mismatch_cell_id(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L02",  # Mismatch with source L01
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": 300.0,
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_SOURCE_SCOPE_MISMATCH"


# =============================================================================
# 5. Timestamp Normalization & Timezone Tests
# =============================================================================


def test_converter_timestamp_timezone_required(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00",  # No timezone
        "air_temperature_k": 300.0,
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_TIMESTAMP_TIMEZONE_REQUIRED"


def test_converter_timestamp_invalid_format(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "invalid-datetime-string",
        "air_temperature_k": 300.0,
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_TIMESTAMP_INVALID"


# =============================================================================
# 6. Sensor Field & Transform Tests
# =============================================================================


def test_converter_mapped_null_rejected(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": None,  # Mapped field is null
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_MAPPED_VALUE_MISSING"


def test_converter_no_mapped_measurements_rejected(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        # No sensor fields at all
        "unknown_foo": "bar",
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_NO_MAPPED_MEASUREMENTS"


def test_converter_string_boolean_rejected(source_stream_fixture, valid_gen_data_mapping_data):
    """String 'false' or integer 0 for boolean target type must not be silently coerced to True/False."""
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": 300.0,
        "is_operating": "false",  # Invalid bool type
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_FIELD_TRANSFORM_FAILED"


def test_converter_unconvertible_string_for_float_rejected(source_stream_fixture, valid_gen_data_mapping_data):
    data = {
        "asset_id": "CNC-01",
        "site_id": "S01",
        "cell_id": "L01",
        "observed_at": "2026-08-28T13:00:00Z",
        "air_temperature_k": "not-a-number",
    }
    parsed = ParsedGenDataRecord(0, 10, 1, "sha", data)
    res = GenDataStaticMappingConverter().convert(
        record=parsed, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data
    )
    assert res.observation is None
    assert res.rejected is not None
    assert res.rejected.error_code == "GEN_DATA_FIELD_TRANSFORM_FAILED"


# =============================================================================
# 7. Batch Stream Processing Tests
# =============================================================================


def test_converter_batch_processing_isolates_failures(source_stream_fixture, valid_gen_data_mapping_data):
    records = [
        # 1. Valid CNC
        ParsedGenDataRecord(
            0, 50, 1, "sha1",
            {"asset_id": "CNC-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "torque_nm": 45.0}
        ),
        # 2. Scope mismatch failure
        ParsedGenDataRecord(
            50, 100, 2, "sha2",
            {"asset_id": "CNC-02", "site_id": "S99", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "torque_nm": 45.0}
        ),
        # 3. Valid Compressor
        ParsedGenDataRecord(
            100, 150, 3, "sha3",
            {"asset_id": "CMP-01", "site_id": "S01", "cell_id": "L01", "observed_at": "2026-08-28T13:00:00Z", "voltage_raw": 220.0}
        ),
    ]

    converter = GenDataStaticMappingConverter()
    results = [converter.convert(record=r, source=source_stream_fixture, mapping_data=valid_gen_data_mapping_data) for r in records]

    obs = [r.observation for r in results if r.observation is not None]
    rej = [r.rejected for r in results if r.rejected is not None]

    assert len(obs) == 2
    assert len(rej) == 1
    assert obs[0].asset_id == "CNC-01"
    assert obs[1].asset_id == "CMP-01"
    assert rej[0].asset_id == "CNC-02"
    assert rej[0].error_code == "GEN_DATA_SOURCE_SCOPE_MISMATCH"
