"""Static mapping and Canonical Observation conversion for gen_data stream records."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from systems.generator.app.extraction.gen_data_source import GenDataSensorStreamSource
from systems.generator.app.extraction.mapping_validator import MappingValidator
from systems.generator.app.extraction.parsers.gen_data_sensor_stream_parser import (
    ParsedGenDataRecord,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalObservationCandidate:
    """In-memory candidate for a converted canonical observation row."""

    asset_id: str
    observed_at: str
    measurements: dict[str, Any]
    site_id: str
    cell_id: str
    source_uri: str
    source_byte_start: int
    source_byte_end: int
    source_line_number: int
    source_row_sha256: str
    mapping_id: str
    mapping_version: str
    mapping_sha256: str
    ignored_source_fields: tuple[str, ...]

    def to_observation_dict(self) -> dict[str, Any]:
        """Convert candidate to canonical observation dictionary in deterministic key order."""
        res: dict[str, Any] = {
            "asset_id": self.asset_id,
            "observed_at": self.observed_at,
        }
        res.update(self.measurements)
        return res

    def to_provenance_dict(self, extraction_run_id: str) -> dict[str, Any]:
        """Convert candidate to provenance row dictionary."""
        return {
            "asset_id": self.asset_id,
            "observed_at": self.observed_at,
            "site_id": self.site_id,
            "cell_id": self.cell_id,
            "source_uri": self.source_uri,
            "source_byte_start": self.source_byte_start,
            "source_byte_end": self.source_byte_end,
            "source_line_number": self.source_line_number,
            "source_row_sha256": self.source_row_sha256,
            "mapping_id": self.mapping_id,
            "mapping_version": self.mapping_version,
            "mapping_sha256": self.mapping_sha256,
            "extraction_run_id": extraction_run_id,
        }


@dataclass(frozen=True)
class RejectedMappingRecord:
    """Represents a record that failed identity, scope, timestamp, or mapping validation."""

    source_uri: str
    source_byte_start: int
    source_byte_end: int
    source_line_number: int
    raw_sha256: str
    asset_id: Optional[str]
    observed_at: Optional[str]
    error_code: str
    error_message: str
    mapping_id: str
    mapping_version: str


@dataclass(frozen=True)
class GenDataMappingResult:
    """Envelope containing either a valid observation candidate or a rejected mapping record."""

    observation: Optional[CanonicalObservationCandidate]
    rejected: Optional[RejectedMappingRecord]


def normalize_strict_iso_utc(ts_raw: Any) -> str:
    """Strictly normalize a datetime string with required timezone to UTC ISO-8601 string ending in 'Z'."""
    if not isinstance(ts_raw, str):
        raise ValueError("observed_at must be a string")
    s = ts_raw.strip()
    if not s:
        raise ValueError("observed_at is empty")

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"Invalid ISO-8601 datetime format: {exc}") from exc

    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp is missing required timezone offset")

    dt_utc = dt.astimezone(timezone.utc)
    if dt_utc.microsecond:
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


class GenDataStaticMappingConverter:
    """Converts ParsedGenDataRecord into CanonicalObservationCandidate using an approved static mapping table."""

    def __init__(self, mapping_validator: Optional[MappingValidator] = None) -> None:
        self.mapping_validator = mapping_validator or MappingValidator()

    def convert(
        self,
        *,
        record: ParsedGenDataRecord,
        source: GenDataSensorStreamSource,
        mapping_data: dict[str, Any],
    ) -> GenDataMappingResult:
        """Convert a parsed streaming gen_data record into CanonicalObservationCandidate or RejectedMappingRecord.

        Steps:
        1. Validate mapping table contract (source_format=gen_data_sensor_stream, approved, checksums, collisions).
        2. Validate required Identity fields (asset_id, site_id, cell_id, observed_at).
        3. Cross-validate site_id and cell_id against source stream path.
        4. Validate and normalize observed_at timestamp to UTC ISO-8601 (Z).
        5. Apply field mappings with strict bool/null checks and allowlisted transforms.
        6. Enforce at least 1 mapped sensor measurement.
        7. Isolate non-mapped fields into ignored_source_fields without failing.
        """
        # Step 1: Mapping table contract validation (fail-closed if mapping is invalid)
        self.mapping_validator.validate_mapping(
            mapping_data,
            expected_source_format="gen_data_sensor_stream",
        )

        mapping_id = mapping_data.get("mapping_id", "")
        mapping_version = mapping_data.get("mapping_version", "")
        mapping_sha256 = mapping_data.get("mapping_sha256", "")

        def make_rejected(
            error_code: str,
            error_message: str,
            asset_id: Optional[str] = None,
            observed_at: Optional[str] = None,
        ) -> GenDataMappingResult:
            return GenDataMappingResult(
                observation=None,
                rejected=RejectedMappingRecord(
                    source_uri=source.source_uri,
                    source_byte_start=record.byte_start,
                    source_byte_end=record.byte_end,
                    source_line_number=record.line_number,
                    raw_sha256=record.raw_sha256,
                    asset_id=asset_id,
                    observed_at=observed_at,
                    error_code=error_code,
                    error_message=error_message,
                    mapping_id=mapping_id,
                    mapping_version=mapping_version,
                ),
            )

        data = record.data

        # Step 2: Validate Identity fields
        asset_id_raw = data.get("asset_id")
        if not asset_id_raw or not str(asset_id_raw).strip() or not isinstance(asset_id_raw, (str, int)):
            return make_rejected("GEN_DATA_ASSET_ID_MISSING", "asset_id is missing, empty, or invalid type")
        asset_id = str(asset_id_raw).strip()

        site_id_raw = data.get("site_id")
        if not site_id_raw or not str(site_id_raw).strip() or not isinstance(site_id_raw, str):
            return make_rejected("GEN_DATA_SITE_ID_MISSING", "site_id is missing or empty", asset_id=asset_id)
        site_id = site_id_raw.strip()

        cell_id_raw = data.get("cell_id")
        if not cell_id_raw or not str(cell_id_raw).strip() or not isinstance(cell_id_raw, str):
            return make_rejected("GEN_DATA_CELL_ID_MISSING", "cell_id is missing or empty", asset_id=asset_id)
        cell_id = cell_id_raw.strip()

        # Step 3: Cross-validate site_id and cell_id against source stream path
        if site_id != source.site_id or cell_id != source.cell_id:
            return make_rejected(
                "GEN_DATA_SOURCE_SCOPE_MISMATCH",
                f"Record identity scope (site={site_id}, cell={cell_id}) does not match source stream scope (site={source.site_id}, cell={source.cell_id})",
                asset_id=asset_id,
            )

        observed_at_raw = data.get("observed_at")
        if not observed_at_raw or not str(observed_at_raw).strip():
            return make_rejected("GEN_DATA_OBSERVED_AT_MISSING", "observed_at is missing or empty", asset_id=asset_id)

        # Step 4: Strict UTC timestamp normalization
        try:
            normalized_observed_at = normalize_strict_iso_utc(observed_at_raw)
        except ValueError as exc:
            err_msg = str(exc)
            if "missing required timezone" in err_msg.lower():
                code = "GEN_DATA_TIMESTAMP_TIMEZONE_REQUIRED"
            else:
                code = "GEN_DATA_TIMESTAMP_INVALID"
            return make_rejected(
                code,
                f"Invalid observed_at timestamp '{observed_at_raw}': {err_msg}",
                asset_id=asset_id,
                observed_at=str(observed_at_raw),
            )

        # Step 5: Iterate field mappings
        field_mappings = mapping_data.get("field_mappings", [])
        measurements: dict[str, Any] = {}
        mapped_source_fields: set[str] = set()

        for fm in field_mappings:
            src_field = fm["source_field"]
            tgt_field = fm["target_field"]
            required = fm.get("required", False)
            transform = fm.get("transform", "identity")
            tgt_type = fm.get("target_type", "float")
            mapped_source_fields.add(src_field)

            if src_field not in data:
                if required:
                    return make_rejected(
                        "GEN_DATA_MAPPED_VALUE_MISSING",
                        f"Required field '{src_field}' is missing in source record",
                        asset_id=asset_id,
                        observed_at=normalized_observed_at,
                    )
                continue

            raw_val = data[src_field]
            if raw_val is None:
                return make_rejected(
                    "GEN_DATA_MAPPED_VALUE_MISSING",
                    f"Mapped field '{src_field}' has null value",
                    asset_id=asset_id,
                    observed_at=normalized_observed_at,
                )

            # Strict bool type requirement for boolean target types
            if tgt_type == "bool":
                if not isinstance(raw_val, bool):
                    return make_rejected(
                        "GEN_DATA_FIELD_TRANSFORM_FAILED",
                        f"Field '{src_field}' expects bool but got {type(raw_val).__name__} ({raw_val!r})",
                        asset_id=asset_id,
                        observed_at=normalized_observed_at,
                    )

            try:
                converted_val = self.mapping_validator.apply_transform(raw_val, transform, tgt_type)
            except Exception as exc:
                return make_rejected(
                    "GEN_DATA_FIELD_TRANSFORM_FAILED",
                    f"Transform '{transform}' to '{tgt_type}' failed on field '{src_field}' (value type={type(raw_val).__name__}): {exc}",
                    asset_id=asset_id,
                    observed_at=normalized_observed_at,
                )

            measurements[tgt_field] = converted_val

        # Step 6: Minimum sensor measurement validation
        if len(measurements) == 0:
            return make_rejected(
                "GEN_DATA_NO_MAPPED_MEASUREMENTS",
                "No sensor measurements were extracted for record (0 mapped fields)",
                asset_id=asset_id,
                observed_at=normalized_observed_at,
            )

        # Step 7: Isolate ignored non-mapped fields
        identity_fields = {"asset_id", "site_id", "cell_id", "observed_at"}
        ignored_fields = tuple(
            k for k in data.keys() if k not in mapped_source_fields and k not in identity_fields
        )

        candidate = CanonicalObservationCandidate(
            asset_id=asset_id,
            observed_at=normalized_observed_at,
            measurements=measurements,
            site_id=site_id,
            cell_id=cell_id,
            source_uri=source.source_uri,
            source_byte_start=record.byte_start,
            source_byte_end=record.byte_end,
            source_line_number=record.line_number,
            source_row_sha256=record.raw_sha256,
            mapping_id=mapping_id,
            mapping_version=mapping_version,
            mapping_sha256=mapping_sha256,
            ignored_source_fields=ignored_fields,
        )

        return GenDataMappingResult(observation=candidate, rejected=None)
