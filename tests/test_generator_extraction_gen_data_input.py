"""Unit tests for gen_data Source Exploration and Append JSONL Parser."""

import hashlib
import json
from pathlib import Path

import pytest

from systems.generator.app.extraction.extraction_exception import (
    ExtractionGenDataRootInvalidError,
    ExtractionGenDataRootNotConfiguredError,
    ExtractionGenDataSourcePathUnsupportedError,
    ExtractionSourceNotFoundError,
    ExtractionSourceOffsetInvalidError,
    ExtractionSourceOffsetNotAlignedError,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
    discover_gen_data_sensor_streams,
)
from systems.generator.app.extraction.parsers.gen_data_sensor_stream_parser import (
    GenDataReadResult,
    GenDataSensorStreamParser,
    ParsedGenDataRecord,
    RejectedGenDataRecord,
)


# =============================================================================
# 1. Source Discovery Tests
# =============================================================================


def test_discover_gen_data_sensor_streams_valid_hierarchy(tmp_path):
    """Discover sensor_stream.jsonl across fac{site}/line{cell} directories."""
    sensor_root = tmp_path / "sensor"
    s1_l1 = sensor_root / "facS01" / "lineL01"
    s1_l2 = sensor_root / "facS01" / "lineL02"
    s2_l1 = sensor_root / "facS02" / "lineL01"

    for p in (s1_l1, s1_l2, s2_l1):
        p.mkdir(parents=True, exist_ok=True)
        (p / "sensor_stream.jsonl").write_text('{"val": 1}\n', encoding="utf-8")

    streams = discover_gen_data_sensor_streams(sensor_root)
    assert len(streams) == 3

    assert streams[0].site_id == "S01"
    assert streams[0].cell_id == "L01"
    assert streams[0].facility_dir_name == "facS01"
    assert streams[0].line_dir_name == "lineL01"
    assert streams[0].source_uri == "sensor/facS01/lineL01/sensor_stream.jsonl"
    assert streams[0].source_path == s1_l1 / "sensor_stream.jsonl"

    assert streams[1].site_id == "S01"
    assert streams[1].cell_id == "L02"

    assert streams[2].site_id == "S02"
    assert streams[2].cell_id == "L01"


def test_discover_gen_data_sensor_streams_deterministic_sorting(tmp_path):
    """Discovered sources are deterministically sorted by (site_id, cell_id, source_uri)."""
    sensor_root = tmp_path / "sensor"
    paths = [
        sensor_root / "facB" / "line2",
        sensor_root / "facA" / "line2",
        sensor_root / "facB" / "line1",
        sensor_root / "facA" / "line1",
    ]
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
        (p / "sensor_stream.jsonl").write_text('{"v": 1}\n', encoding="utf-8")

    streams = discover_gen_data_sensor_streams(sensor_root)
    assert len(streams) == 4
    keys = [(s.site_id, s.cell_id) for s in streams]
    assert keys == [("A", "1"), ("A", "2"), ("B", "1"), ("B", "2")]


def test_discover_gen_data_sensor_streams_ignores_empty_and_non_stream_files(tmp_path):
    """Line directories without sensor_stream.jsonl or with other files are ignored."""
    sensor_root = tmp_path / "sensor"
    valid_dir = sensor_root / "facS01" / "lineL01"
    empty_dir = sensor_root / "facS01" / "lineL02"
    other_file_dir = sensor_root / "facS01" / "lineL03"

    valid_dir.mkdir(parents=True, exist_ok=True)
    empty_dir.mkdir(parents=True, exist_ok=True)
    other_file_dir.mkdir(parents=True, exist_ok=True)

    (valid_dir / "sensor_stream.jsonl").write_text('{"ok": true}\n', encoding="utf-8")
    (other_file_dir / "other_stream.jsonl").write_text('{"ok": true}\n', encoding="utf-8")

    streams = discover_gen_data_sensor_streams(sensor_root)
    assert len(streams) == 1
    assert streams[0].cell_id == "L01"


def test_discover_gen_data_sensor_streams_empty_and_nonexistent_root(tmp_path):
    """Empty or non-existent sensor_root returns empty list."""
    empty_root = tmp_path / "empty_sensor"
    empty_root.mkdir()
    assert discover_gen_data_sensor_streams(empty_root) == []

    nonexistent_root = tmp_path / "does_not_exist"
    assert discover_gen_data_sensor_streams(nonexistent_root) == []


def test_discover_gen_data_sensor_streams_not_configured_raises(monkeypatch):
    """When sensor_root=None and PATHS.gen_data_sensor_root is None, raises ExtractionGenDataRootNotConfiguredError."""
    from systems.generator.generator_config import PATHS

    monkeypatch.setattr(PATHS, "gen_data_sensor_root", None)
    with pytest.raises(ExtractionGenDataRootNotConfiguredError):
        discover_gen_data_sensor_streams(None)


def test_discover_gen_data_sensor_streams_file_as_root_raises(tmp_path):
    """Root path pointing to a file raises ExtractionGenDataRootInvalidError."""
    file_root = tmp_path / "not_a_dir.txt"
    file_root.write_text("hello", encoding="utf-8")
    with pytest.raises(ExtractionGenDataRootInvalidError):
        discover_gen_data_sensor_streams(file_root)


def test_discover_gen_data_sensor_streams_invalid_dir_names_raises(tmp_path):
    """Facility or line directories yielding empty site_id or cell_id raise ExtractionGenDataSourcePathUnsupportedError."""
    sensor_root = tmp_path / "sensor"
    bad_fac = sensor_root / "fac" / "line01"
    bad_fac.mkdir(parents=True, exist_ok=True)
    (bad_fac / "sensor_stream.jsonl").write_text("{}", encoding="utf-8")

    with pytest.raises(ExtractionGenDataSourcePathUnsupportedError):
        discover_gen_data_sensor_streams(sensor_root)


def test_discover_gen_data_sensor_streams_stream_dir_raises(tmp_path):
    """A directory named sensor_stream.jsonl raises ExtractionGenDataSourcePathUnsupportedError."""
    sensor_root = tmp_path / "sensor"
    stream_dir = sensor_root / "facS01" / "lineL01" / "sensor_stream.jsonl"
    stream_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ExtractionGenDataSourcePathUnsupportedError):
        discover_gen_data_sensor_streams(sensor_root)


# =============================================================================
# 2. Normal Parser Tests
# =============================================================================


def test_parser_reads_multiple_completed_records(tmp_path):
    """Parser reads valid completed JSONL records and computes raw_sha256 and byte offsets."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line1 = '{"asset_id": "M14860", "rpm": 1500}\n'.encode("utf-8")
    line2 = '{"asset_id": "M14861", "rpm": 1520}\n'.encode("utf-8")
    file_path.write_bytes(line1 + line2)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 2
    assert len(result.rejected_records) == 0
    assert result.has_incomplete_tail is False
    assert result.deferred_offset is None
    assert result.start_offset == 0
    assert result.committed_candidate_offset == len(line1) + len(line2)

    rec1 = result.records[0]
    assert rec1.byte_start == 0
    assert rec1.byte_end == len(line1)
    assert rec1.line_number == 1
    assert rec1.raw_sha256 == hashlib.sha256(line1).hexdigest()
    assert rec1.data == {"asset_id": "M14860", "rpm": 1500}

    rec2 = result.records[1]
    assert rec2.byte_start == len(line1)
    assert rec2.byte_end == len(line1) + len(line2)
    assert rec2.line_number == 2
    assert rec2.raw_sha256 == hashlib.sha256(line2).hexdigest()
    assert rec2.data == {"asset_id": "M14861", "rpm": 1520}


def test_parser_handles_crlf_and_lf(tmp_path):
    """Parser accepts both LF (\\n) and CRLF (\\r\\n) completed lines."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line1 = b'{"id": 1}\r\n'
    line2 = b'{"id": 2}\n'
    file_path.write_bytes(line1 + line2)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 2
    assert result.records[0].data == {"id": 1}
    assert result.records[1].data == {"id": 2}
    assert result.records[0].raw_sha256 == hashlib.sha256(line1).hexdigest()
    assert result.records[1].raw_sha256 == hashlib.sha256(line2).hexdigest()


def test_parser_handles_unicode_records(tmp_path):
    """Parser preserves UTF-8 multi-byte characters in keys and values."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line = '{"설비_ID": "절삭기_01", "상태": "가동중", "온도": 45.5}\n'.encode("utf-8")
    file_path.write_bytes(line)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 1
    assert result.records[0].data == {"설비_ID": "절삭기_01", "상태": "가동중", "온도": 45.5}


# =============================================================================
# 3. Append & Incomplete Line Processing Tests
# =============================================================================


def test_parser_append_incomplete_tail_deferred_and_resumed(tmp_path):
    """Incomplete line at EOF is deferred; once completed, resumed reading returns it cleanly."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line1 = b'{"seq": 1}\n'
    line2 = b'{"seq": 2}\n'
    incomplete_line3 = b'{"seq": 3, "part": "incomp'

    file_path.write_bytes(line1 + line2 + incomplete_line3)

    parser = GenDataSensorStreamParser()
    res1 = parser.read_completed_records(file_path, start_offset=0)

    # 1. First execution: 2 complete, 0 rejected, incomplete tail deferred
    assert len(res1.records) == 2
    assert len(res1.rejected_records) == 0
    assert res1.has_incomplete_tail is True
    assert res1.committed_candidate_offset == len(line1) + len(line2)
    assert res1.deferred_offset == len(line1) + len(line2)

    # 2. Generator/gen_data finishes writing line 3
    completed_line3 = b'{"seq": 3, "part": "complete"}\n'
    file_path.write_bytes(line1 + line2 + completed_line3)

    # 3. Second execution resumes from deferred_offset
    res2 = parser.read_completed_records(file_path, start_offset=res1.deferred_offset)
    assert len(res2.records) == 1
    assert len(res2.rejected_records) == 0
    assert res2.has_incomplete_tail is False
    assert res2.records[0].data == {"seq": 3, "part": "complete"}
    assert res2.committed_candidate_offset == len(line1) + len(line2) + len(completed_line3)


# =============================================================================
# 4. Error Isolation Tests
# =============================================================================


def test_parser_isolates_malformed_json_and_continues(tmp_path):
    """Malformed JSON line is isolated into rejected_records while valid lines before/after succeed."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line1 = b'{"seq": 1}\n'
    bad_line2 = b'{"seq": 2, malformed json...\n'
    line3 = b'{"seq": 3}\n'
    file_path.write_bytes(line1 + bad_line2 + line3)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 2
    assert len(result.rejected_records) == 1

    rej = result.rejected_records[0]
    assert rej.line_number == 2
    assert rej.error_code == "GEN_DATA_JSON_PARSE_ERROR"
    assert rej.raw_sha256 == hashlib.sha256(bad_line2).hexdigest()
    assert result.records[0].data == {"seq": 1}
    assert result.records[1].data == {"seq": 3}
    assert result.committed_candidate_offset == len(line1) + len(bad_line2) + len(line3)


def test_parser_isolates_invalid_utf8(tmp_path):
    """Invalid UTF-8 byte sequences are isolated into rejected_records."""
    file_path = tmp_path / "sensor_stream.jsonl"
    line1 = b'{"seq": 1}\n'
    bad_utf8 = b'\xff\xfe\xfd\x80\n'
    line3 = b'{"seq": 3}\n'
    file_path.write_bytes(line1 + bad_utf8 + line3)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 2
    assert len(result.rejected_records) == 1
    assert result.rejected_records[0].error_code == "GEN_DATA_UTF8_DECODE_ERROR"


def test_parser_isolates_non_object_json(tmp_path):
    """Completed JSON lines that are arrays, numbers, or strings are rejected (dict required)."""
    file_path = tmp_path / "sensor_stream.jsonl"
    content = b'[1, 2, 3]\n"just a string"\n12345\n{"valid": true}\n'
    file_path.write_bytes(content)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 1
    assert len(result.rejected_records) == 3
    for rej in result.rejected_records:
        assert rej.error_code == "GEN_DATA_JSON_OBJECT_REQUIRED"


def test_parser_isolates_empty_lines(tmp_path):
    """Completed lines that are empty or whitespace only are rejected with GEN_DATA_EMPTY_RECORD."""
    file_path = tmp_path / "sensor_stream.jsonl"
    content = b'{"seq": 1}\n\n   \r\n{"seq": 2}\n'
    file_path.write_bytes(content)

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=0)

    assert len(result.records) == 2
    assert len(result.rejected_records) == 2
    assert result.rejected_records[0].error_code == "GEN_DATA_EMPTY_RECORD"
    assert result.rejected_records[1].error_code == "GEN_DATA_EMPTY_RECORD"


# =============================================================================
# 5. Offset Validation & Boundary Tests
# =============================================================================


def test_parser_offset_validation_errors(tmp_path):
    """Invalid, out-of-bounds, and unaligned offsets raise explicit domain errors."""
    file_path = tmp_path / "sensor_stream.jsonl"
    file_path.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    file_size = file_path.stat().st_size

    parser = GenDataSensorStreamParser()

    # Negative offset
    with pytest.raises(ExtractionSourceOffsetInvalidError):
        parser.read_completed_records(file_path, start_offset=-1)

    # Beyond file size
    with pytest.raises(ExtractionSourceOffsetInvalidError):
        parser.read_completed_records(file_path, start_offset=file_size + 10)

    # Mid-line unaligned offset (byte 3 is inside '{"a": 1}')
    with pytest.raises(ExtractionSourceOffsetNotAlignedError):
        parser.read_completed_records(file_path, start_offset=3)


def test_parser_exact_eof_offset_returns_empty_clean_result(tmp_path):
    """Reading from exact EOF offset returns empty result without errors."""
    file_path = tmp_path / "sensor_stream.jsonl"
    file_path.write_bytes(b'{"a": 1}\n')
    file_size = file_path.stat().st_size

    parser = GenDataSensorStreamParser()
    result = parser.read_completed_records(file_path, start_offset=file_size)

    assert len(result.records) == 0
    assert len(result.rejected_records) == 0
    assert result.committed_candidate_offset == file_size
    assert result.deferred_offset is None
    assert result.has_incomplete_tail is False


def test_parser_nonexistent_file_raises_error(tmp_path):
    """Reading a non-existent file raises ExtractionSourceNotFoundError."""
    parser = GenDataSensorStreamParser()
    with pytest.raises(ExtractionSourceNotFoundError):
        parser.read_completed_records(tmp_path / "nonexistent.jsonl")


# =============================================================================
# 6. Batch Limits Tests
# =============================================================================


def test_parser_max_records_batching(tmp_path):
    """Parser respects max_records limit, halting safely and providing deferred_offset for the next batch."""
    file_path = tmp_path / "sensor_stream.jsonl"
    lines = [f'{{"seq": {i}}}\n'.encode("utf-8") for i in range(10)]
    file_path.write_bytes(b"".join(lines))

    parser = GenDataSensorStreamParser()

    # Batch 1: max_records=4
    b1 = parser.read_completed_records(file_path, start_offset=0, max_records=4)
    assert len(b1.records) == 4
    assert [r.data["seq"] for r in b1.records] == [0, 1, 2, 3]
    assert b1.deferred_offset is not None

    # Batch 2: resume from b1.deferred_offset, max_records=4
    b2 = parser.read_completed_records(file_path, start_offset=b1.deferred_offset, max_records=4)
    assert len(b2.records) == 4
    assert [r.data["seq"] for r in b2.records] == [4, 5, 6, 7]
    assert b2.deferred_offset is not None

    # Batch 3: resume from b2.deferred_offset, max_records=4 (remaining 2)
    b3 = parser.read_completed_records(file_path, start_offset=b2.deferred_offset, max_records=4)
    assert len(b3.records) == 2
    assert [r.data["seq"] for r in b3.records] == [8, 9]
    assert b3.deferred_offset is None
    assert b3.committed_candidate_offset == file_path.stat().st_size
