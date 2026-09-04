"""Parser for gen_data SensorRecord v2 protocol logs into Canonical Observation rows."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional, Union

import jsonschema

from systems.generator.generator_config import PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceIncompleteError,
    ExtractionSourceIntegrityError,
    ExtractionRequestInvalidError,
)
from systems.generator.app.extraction.mapping_validator import MappingValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedSourceRecord:
    """Represents a single parsed protocol record with byte boundaries and raw checksum."""
    byte_start: int
    byte_end: int
    line_number: int
    raw_sha256: str
    data: dict[str, Any]


def normalize_iso_utc(ts_raw: Union[str, datetime]) -> str:
    """Normalize datetime or timestamp string to ISO-8601 UTC string ending in 'Z'."""
    if isinstance(ts_raw, datetime):
        dt = ts_raw
    else:
        s = str(ts_raw).strip()
        if not s:
            raise ValueError("Timestamp is empty")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class SensorRecordParser:
    """Parses, validates, streams, and groups SensorRecord v2 protocol lines into Canonical Observations."""

    def __init__(
        self,
        mapping_validator: Optional[MappingValidator] = None,
        schema_path: Optional[Path] = None,
    ) -> None:
        self.mapping_validator = mapping_validator or MappingValidator()
        self.schema_path = schema_path or (
            PROJECT_ROOT / "contracts" / "schemas" / "generator-protocol-record.schema.json"
        )
        self._schema_cache: Optional[dict[str, Any]] = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            if not self.schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Protocol record schema file not found: {self.schema_path}")
            try:
                self._schema_cache = json.loads(self.schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExtractionRequestInvalidError(f"Failed to parse protocol record schema: {e}") from e
        return self._schema_cache

    def iter_protocol_records(
        self,
        source_path: Path,
        *,
        start_offset: int = 0,
        is_source_finalized: bool = True,
    ) -> Iterator[ParsedSourceRecord]:
        """Binary stream iterator yielding individual parsed protocol records with precise byte offsets."""
        if not source_path.is_file():
            raise ExtractionRequestInvalidError(f"Source file not found: {source_path}")

        with open(source_path, "rb") as stream:
            if start_offset > 0:
                stream.seek(start_offset)
            line_no = 0

            while True:
                byte_start = stream.tell()
                raw_line = stream.readline()
                byte_end = stream.tell()

                if not raw_line:
                    break

                line_no += 1
                raw_sha256 = hashlib.sha256(raw_line).hexdigest()
                line_str = raw_line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                except Exception as exc:
                    if is_source_finalized:
                        raise ExtractionSourceIntegrityError(
                            f"입력 파일이 finalized 상태이나 레코드가 손상되었습니다 (바이트 {byte_start}-{byte_end}): {exc}",
                            details=[{"byte_start": byte_start, "byte_end": byte_end, "raw": line_str[:100]}],
                        ) from exc
                    else:
                        raise ExtractionSourceIncompleteError(
                            f"입력 파일의 마지막 행이 완성되지 않은 불완전한 JSONL 레코드입니다 (바이트 {byte_start}-{byte_end}): {exc}",
                            details=[{"byte_start": byte_start, "byte_end": byte_end, "raw": line_str[:100]}],
                        ) from exc

                yield ParsedSourceRecord(
                    byte_start=byte_start,
                    byte_end=byte_end,
                    line_number=line_no,
                    raw_sha256=raw_sha256,
                    data=data,
                )

    def parse_file(
        self,
        source_path: Path,
        mapping_data: dict[str, Any],
        extraction_run_id: str,
        source_direction: str = "received",
        dedup_checker: Optional[Any] = None,
        source_identity: Optional[str] = None,
        is_source_finalized: bool = True,
        start_offset: int = 0,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        """Parse records starting from start_offset into canonical observations, provenance, and rejected records.

        Returns:
            (observations, provenance_records, rejected_records, processed_source_records, stats_dict)
        """
        schema = self._get_schema()
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

        mapping_id = mapping_data.get("mapping_id", "")
        mapping_version = mapping_data.get("mapping_version", "")
        mapping_sha256 = mapping_data.get("mapping_sha256", "")
        field_mappings = mapping_data.get("field_mappings", [])

        mapping_lookup: dict[str, dict[str, Any]] = {
            fm["source_field"]: fm for fm in field_mappings if "source_field" in fm
        }
        required_target_fields = [
            fm["target_field"] for fm in field_mappings if fm.get("required", False)
        ]
        target_column_order = [fm["target_field"] for fm in field_mappings if "target_field" in fm]

        grouping: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        group_ordering: list[tuple[str, str, str, str]] = []
        rejected_records: list[dict[str, Any]] = []
        provenance_records: list[dict[str, Any]] = []
        processed_source_records: list[dict[str, Any]] = []
        total_records = 0
        last_byte_offset = start_offset
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Stream records using binary iterator
        for parsed_rec in self.iter_protocol_records(
            source_path=source_path,
            start_offset=start_offset,
            is_source_finalized=is_source_finalized,
        ):
            last_byte_offset = parsed_rec.byte_end
            total_records += 1
            line_no = parsed_rec.line_number
            raw_sha256 = parsed_rec.raw_sha256
            rec = parsed_rec.data

            if not isinstance(rec, dict):
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": None,
                    "source_observation_id": None,
                    "error_code": "JSON_SCHEMA_TYPE_ERROR",
                    "error_message": "Record is not a JSON object",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": None,
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            # Validate against SensorRecord v2 schema
            try:
                validator.validate(rec)
            except jsonschema.ValidationError as exc:
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": rec.get("sequence"),
                    "source_observation_id": rec.get("observation_id"),
                    "error_code": "SCHEMA_VALIDATION_ERROR",
                    "error_message": f"Schema validation failed: {exc.message}",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": rec.get("run_id"),
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            # Strict direct field access (zero heuristic fallbacks)
            direction = rec["direction"]
            if direction != source_direction:
                continue

            observation_id = rec["observation_id"]
            run_id = rec["run_id"]
            branch_kind = rec["branch_kind"]
            asset_id = rec["asset_id"]
            raw_ts = rec["observed_at_source"]
            measurement_key = rec["measurement_key"]
            sequence = rec["sequence"]
            raw_val = rec["value"]
            status_code = rec.get("status_code", "Good")
            quality = rec.get("quality", "Good")

            # Check dedup ledger if available
            if dedup_checker and source_identity:
                if dedup_checker.is_record_processed(source_identity, observation_id):
                    logger.debug(f"[SensorRecordParser] Skipping duplicate record {observation_id}")
                    continue

            # Check if measurement_key is mapped
            fm = mapping_lookup.get(measurement_key)
            if not fm:
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": sequence,
                    "source_observation_id": observation_id,
                    "error_code": "UNMAPPED_MEASUREMENT_KEY",
                    "error_message": f"Unmapped measurement_key '{measurement_key}' not present in mapping table",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": run_id,
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            # Quality policy check: null value or Bad/Uncertain quality isolated to rejected
            if raw_val is None or quality in ("Bad", "Uncertain") or status_code in ("Bad", "Uncertain"):
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": sequence,
                    "source_observation_id": observation_id,
                    "error_code": "QUALITY_POLICY_NOT_IMPLEMENTED",
                    "error_message": f"Quality status '{quality}' / '{status_code}' or null value cannot be processed into observation",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": run_id,
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            target_field = fm.get("target_field", measurement_key)
            transform_name = fm.get("transform", "identity")
            target_type = fm.get("target_type", "float")

            try:
                transformed_val = self.mapping_validator.apply_transform(
                    raw_val,
                    transform=transform_name,
                    target_type=target_type,
                )
            except Exception as exc:
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": sequence,
                    "source_observation_id": observation_id,
                    "error_code": "TRANSFORM_ERROR",
                    "error_message": f"Transform '{transform_name}' failed: {exc}",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": run_id,
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            try:
                norm_ts = normalize_iso_utc(raw_ts)
            except Exception as exc:
                rejected_records.append({
                    "source_offset": parsed_rec.byte_start,
                    "source_sequence": sequence,
                    "source_observation_id": observation_id,
                    "error_code": "TIMESTAMP_NORMALIZATION_ERROR",
                    "error_message": f"Timestamp normalization failed for '{raw_ts}': {exc}",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": run_id,
                    "raw_record_checksum": raw_sha256,
                    "rejected_at": now_iso,
                })
                continue

            group_key = (run_id, branch_kind, asset_id, norm_ts)
            if group_key not in grouping:
                grouping[group_key] = {
                    "asset_id": asset_id,
                    "observed_at": norm_ts,
                    "run_id": run_id,
                    "branch_kind": branch_kind,
                    "direction": direction,
                    "measurements": {},
                    "measurement_provenances": {},
                    "conflicts": [],
                }
                group_ordering.append(group_key)

            grp = grouping[group_key]

            # Detect measurement conflict within same (run_id, branch_kind, asset_id, observed_at)
            if target_field in grp["measurements"]:
                prev_val = grp["measurements"][target_field]
                if prev_val != transformed_val:
                    grp["conflicts"].append({
                        "target_field": target_field,
                        "existing_value": prev_val,
                        "conflicting_value": transformed_val,
                        "observation_id": observation_id,
                        "required": fm.get("required", False),
                    })
                    rejected_records.append({
                        "source_offset": parsed_rec.byte_start,
                        "source_sequence": sequence,
                        "source_observation_id": observation_id,
                        "error_code": "MEASUREMENT_CONFLICT",
                        "error_message": f"Measurement conflict for '{target_field}': existing={prev_val}, conflicting={transformed_val}",
                        "mapping_id": mapping_id,
                        "mapping_version": mapping_version,
                        "run_id": run_id,
                        "raw_record_checksum": raw_sha256,
                        "rejected_at": now_iso,
                    })
                    continue
                else:
                    continue

            grp["measurements"][target_field] = transformed_val
            prov_item = {
                "asset_id": asset_id,
                "observed_at": norm_ts,
                "measurement_key": measurement_key,
                "source_observation_id": observation_id,
                "source_sequence": sequence,
                "source_direction": direction,
                "source_status_code": status_code or "Good",
                "source_quality": quality or "Good",
                "mapping_id": mapping_id,
                "mapping_version": mapping_version,
                "mapping_sha256": mapping_sha256,
                "extraction_run_id": extraction_run_id,
            }
            grp["measurement_provenances"][target_field] = prov_item
            processed_source_records.append({
                "observation_id": observation_id,
                "byte_start": parsed_rec.byte_start,
                "byte_end": parsed_rec.byte_end,
                "line_number": line_no,
                "asset_id": asset_id,
                "observed_at": norm_ts,
            })

        # 3. Assemble Flat Wide-Format Canonical Observations
        valid_observations: list[dict[str, Any]] = []
        asset_ids_set: set[str] = set()
        timestamps: list[str] = []

        for group_key in group_ordering:
            grp = grouping[group_key]

            has_required_conflict = any(c.get("required", False) for c in grp["conflicts"])
            if has_required_conflict:
                rejected_records.append({
                    "source_offset": None,
                    "source_sequence": None,
                    "source_observation_id": None,
                    "error_code": "OBSERVATION_ROW_REJECTED",
                    "error_message": f"Observation row rejected due to required field conflict on {grp['asset_id']} at {grp['observed_at']}",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": grp["run_id"],
                    "raw_record_checksum": None,
                    "rejected_at": now_iso,
                })
                continue

            missing_reqs = [rf for rf in required_target_fields if rf not in grp["measurements"]]
            if missing_reqs:
                rejected_records.append({
                    "source_offset": None,
                    "source_sequence": None,
                    "source_observation_id": None,
                    "error_code": "MISSING_REQUIRED_MEASUREMENT",
                    "error_message": f"Missing required mapped fields {missing_reqs} on {grp['asset_id']} at {grp['observed_at']}",
                    "mapping_id": mapping_id,
                    "mapping_version": mapping_version,
                    "run_id": grp["run_id"],
                    "raw_record_checksum": None,
                    "rejected_at": now_iso,
                })
                continue

            obs_row: dict[str, Any] = {
                "asset_id": grp["asset_id"],
                "observed_at": grp["observed_at"],
            }
            for col in target_column_order:
                if col in grp["measurements"]:
                    obs_row[col] = grp["measurements"][col]
            for col, val in sorted(grp["measurements"].items()):
                if col not in obs_row:
                    obs_row[col] = val

            valid_observations.append(obs_row)
            asset_ids_set.add(grp["asset_id"])
            timestamps.append(grp["observed_at"])

            for target_field, prov_entry in grp["measurement_provenances"].items():
                if target_field in obs_row:
                    provenance_records.append(prov_entry)

        min_time = min(timestamps) if timestamps else None
        max_time = max(timestamps) if timestamps else None

        stats = {
            "total_records": total_records,
            "parsed_records": total_records,
            "rejected_records": len(rejected_records),
            "observations_count": len(valid_observations),
            "asset_ids": sorted(asset_ids_set),
            "min_time": min_time,
            "max_time": max_time,
            "end_byte_offset": last_byte_offset,
        }

        return valid_observations, provenance_records, rejected_records, processed_source_records, stats
