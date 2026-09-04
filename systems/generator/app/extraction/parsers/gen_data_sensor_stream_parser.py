"""Append JSONL Parser for streaming gen_data sensor logs."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceNotFoundError,
    ExtractionSourceOffsetInvalidError,
    ExtractionSourceOffsetNotAlignedError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedGenDataRecord:
    """Represents a successfully parsed completed gen_data record."""

    byte_start: int
    byte_end: int
    line_number: int
    raw_sha256: str
    data: dict[str, Any]


@dataclass(frozen=True)
class RejectedGenDataRecord:
    """Represents a completed line that failed UTF-8, JSON, or object validation."""

    byte_start: int
    byte_end: int
    line_number: int
    raw_sha256: str
    error_code: str
    error_message: str
    raw_preview: str


@dataclass(frozen=True)
class GenDataReadResult:
    """Complete summary of a single batch read from an append JSONL file."""

    records: list[ParsedGenDataRecord]
    rejected_records: list[RejectedGenDataRecord]
    start_offset: int
    committed_candidate_offset: int
    deferred_offset: Optional[int]
    eof_offset: int
    has_incomplete_tail: bool


class GenDataSensorStreamParser:
    """Binary mode line-by-line append parser for streaming sensor_stream.jsonl."""

    def read_completed_records(
        self,
        source_path: Path,
        *,
        start_offset: int = 0,
        max_records: Optional[int] = 10000,
        max_bytes: Optional[int] = None,
    ) -> GenDataReadResult:
        """Sequentially read completed lines from start_offset in binary mode.

        Rules:
        1. Opens file strictly in 'rb' binary mode.
        2. Validates start_offset bounds and newline alignment.
        3. Only completed lines (ending in \n or \r\n) are parsed.
        4. Incomplete trailing bytes at EOF are deferred without raising or rejecting.
        5. Computes raw bytes SHA-256 for each completed line including its newline.
        6. Isolates UTF-8 decode, JSON parse, non-object, and empty line errors into RejectedGenDataRecord.
        """
        path = Path(source_path).resolve()
        if not path.is_file():
            raise ExtractionSourceNotFoundError(f"Source file not found: {path}")

        file_size = path.stat().st_size

        if start_offset < 0:
            raise ExtractionSourceOffsetInvalidError(
                f"start_offset cannot be negative: {start_offset}"
            )
        if start_offset > file_size:
            raise ExtractionSourceOffsetInvalidError(
                f"start_offset ({start_offset}) exceeds file size ({file_size})"
            )

        if start_offset > 0:
            with open(path, "rb") as probe:
                probe.seek(start_offset - 1)
                prev_byte = probe.read(1)
                if prev_byte != b"\n":
                    raise ExtractionSourceOffsetNotAlignedError(
                        f"start_offset ({start_offset}) is not aligned to the end of a previous complete line "
                        f"(preceding byte was {prev_byte!r}, expected b'\\n')"
                    )

        if start_offset == file_size:
            return GenDataReadResult(
                records=[],
                rejected_records=[],
                start_offset=start_offset,
                committed_candidate_offset=start_offset,
                deferred_offset=None,
                eof_offset=file_size,
                has_incomplete_tail=False,
            )

        records: list[ParsedGenDataRecord] = []
        rejected_records: list[RejectedGenDataRecord] = []
        committed_candidate_offset = start_offset
        deferred_offset: Optional[int] = None
        has_incomplete_tail = False
        line_no = 0

        with open(path, "rb") as stream:
            stream.seek(start_offset)

            while True:
                byte_start = stream.tell()

                # Check max_records batch limit
                if (
                    max_records is not None
                    and (len(records) + len(rejected_records)) >= max_records
                ):
                    deferred_offset = byte_start
                    break

                # Check max_bytes batch limit
                if max_bytes is not None and (byte_start - start_offset) >= max_bytes:
                    deferred_offset = byte_start
                    break

                raw_line = stream.readline()
                byte_end = stream.tell()

                if not raw_line:
                    # Clean EOF reached
                    break

                # Check completion: must end in \n or \r\n
                if not (raw_line.endswith(b"\n") or raw_line.endswith(b"\r\n")):
                    # Incomplete tail currently being written
                    has_incomplete_tail = True
                    deferred_offset = byte_start
                    break

                line_no += 1
                committed_candidate_offset = byte_end
                raw_sha256 = hashlib.sha256(raw_line).hexdigest()

                # Strip trailing CRLF/LF for JSON parsing
                content_bytes = raw_line.rstrip(b"\r\n")

                # 1. UTF-8 decode
                try:
                    decoded = content_bytes.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    rejected_records.append(
                        RejectedGenDataRecord(
                            byte_start=byte_start,
                            byte_end=byte_end,
                            line_number=line_no,
                            raw_sha256=raw_sha256,
                            error_code="GEN_DATA_UTF8_DECODE_ERROR",
                            error_message=f"UTF-8 decode failed: {u_err}",
                            raw_preview=repr(raw_line[:100]),
                        )
                    )
                    continue

                # 2. Empty line check
                if not decoded.strip():
                    rejected_records.append(
                        RejectedGenDataRecord(
                            byte_start=byte_start,
                            byte_end=byte_end,
                            line_number=line_no,
                            raw_sha256=raw_sha256,
                            error_code="GEN_DATA_EMPTY_RECORD",
                            error_message="Completed record line is empty or whitespace only",
                            raw_preview=decoded[:100],
                        )
                    )
                    continue

                # 3. JSON parse
                try:
                    parsed_obj = json.loads(decoded)
                except json.JSONDecodeError as j_err:
                    rejected_records.append(
                        RejectedGenDataRecord(
                            byte_start=byte_start,
                            byte_end=byte_end,
                            line_number=line_no,
                            raw_sha256=raw_sha256,
                            error_code="GEN_DATA_JSON_PARSE_ERROR",
                            error_message=f"JSON syntax error: {j_err}",
                            raw_preview=decoded[:200],
                        )
                    )
                    continue

                # 4. JSON object (dict) required
                if not isinstance(parsed_obj, dict):
                    rejected_records.append(
                        RejectedGenDataRecord(
                            byte_start=byte_start,
                            byte_end=byte_end,
                            line_number=line_no,
                            raw_sha256=raw_sha256,
                            error_code="GEN_DATA_JSON_OBJECT_REQUIRED",
                            error_message=f"Top-level JSON value must be an object (dict), got {type(parsed_obj).__name__}",
                            raw_preview=decoded[:200],
                        )
                    )
                    continue

                records.append(
                    ParsedGenDataRecord(
                        byte_start=byte_start,
                        byte_end=byte_end,
                        line_number=line_no,
                        raw_sha256=raw_sha256,
                        data=parsed_obj,
                    )
                )

            eof_offset = file_size

        return GenDataReadResult(
            records=records,
            rejected_records=rejected_records,
            start_offset=start_offset,
            committed_candidate_offset=committed_candidate_offset,
            deferred_offset=deferred_offset,
            eof_offset=eof_offset,
            has_incomplete_tail=has_incomplete_tail,
        )
