"""Validation and transformation logic for static mapping tables."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import jsonschema

from systems.generator.generator_config import PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionMappingNotApprovedError,
    ExtractionMappingChecksumMismatchError,
    ExtractionSchemaFingerprintMismatchError,
    ExtractionFeatureNotImplementedError,
    ExtractionRequestInvalidError,
    ExtractionMappingSourceFormatMismatchError,
    ExtractionMappingDuplicateSourceFieldError,
    ExtractionMappingTargetCollisionError,
    ExtractionMappingReservedTargetFieldError,
    ExtractionMappingEmptyError,
)

logger = logging.getLogger(__name__)

ALLOWED_TRANSFORMS = {
    "identity",
    "to_float",
    "to_int",
    "to_string",
    "scale_10x",
    "kelvin_to_celsius",
    "celsius_to_kelvin",
}

RESERVED_TARGET_FIELDS = {
    "asset_id",
    "observed_at",
    "site_id",
    "cell_id",
    "label",
    "target",
    "failure",
    "degradation_start",
    "extraction_run_id",
    "source_uri",
    "source_checksum",
}


def compute_mapping_canonical_sha256(mapping_dict: dict[str, Any]) -> str:
    """Compute canonical SHA-256 over mapping dictionary excluding mapping_sha256 and $schema."""
    d = dict(mapping_dict)
    d.pop("mapping_sha256", None)
    d.pop("$schema", None)
    canonical_json = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_source_schema_fingerprint(schema_def: dict[str, Any], algorithm_version: str = "v1") -> str:
    """Compute deterministic SHA-256 fingerprint over structural definition of source schema."""
    properties = schema_def.get("properties", {})
    required = set(schema_def.get("required", []))

    canonical_fields = []
    for field_name in sorted(properties.keys()):
        prop = properties[field_name]
        field_struct = {
            "name": field_name,
            "type": prop.get("type"),
            "required": field_name in required,
            "enum": sorted(prop["enum"]) if "enum" in prop else None,
            "format": prop.get("format"),
        }
        canonical_fields.append(field_struct)

    canonical_repr = {
        "fields": canonical_fields,
        "schema_title": schema_def.get("title", ""),
        "algorithm_version": algorithm_version,
    }
    canonical_json = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class MappingValidator:
    """Validates static mapping table contracts, status, fingerprints, and transformations."""

    def __init__(self, schema_path: Optional[Path] = None) -> None:
        self.schema_path = schema_path or (PROJECT_ROOT / "contracts" / "schemas" / "generator-static-mapping-table.schema.json")
        self._schema_cache: Optional[dict[str, Any]] = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            if not self.schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Mapping schema file not found: {self.schema_path}")
            try:
                self._schema_cache = json.loads(self.schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExtractionRequestInvalidError(f"Failed to parse mapping schema: {e}") from e
        return self._schema_cache

    def validate_mapping(
        self,
        mapping_data: dict[str, Any],
        expected_mapping_id: Optional[str] = None,
        expected_mapping_version: Optional[str] = None,
        expected_mapping_sha256: Optional[str] = None,
        expected_source_schema_fingerprint: Optional[str] = None,
        expected_source_format: Optional[str] = None,
    ) -> None:
        """Strictly validate mapping against JSON schema, approved status, checksums, format, collisions, and transforms."""
        # 1. JSON Schema validation
        schema = self._get_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(mapping_data)
        except jsonschema.ValidationError as exc:
            raise ExtractionRequestInvalidError(
                f"정적 매핑 테이블 스키마 검증 실패: {exc.message}",
                details=[{"path": list(exc.path), "error": exc.message}],
            ) from exc

        # 2. Identity match
        if expected_mapping_id and mapping_data.get("mapping_id") != expected_mapping_id:
            raise ExtractionRequestInvalidError(
                f"매핑 ID 불일치: 요청={expected_mapping_id}, 매핑파일={mapping_data.get('mapping_id')}",
                details=[{"expected": expected_mapping_id, "actual": mapping_data.get("mapping_id")}],
            )
        if expected_mapping_version and mapping_data.get("mapping_version") != expected_mapping_version:
            raise ExtractionRequestInvalidError(
                f"매핑 버전 불일치: 요청={expected_mapping_version}, 매핑파일={mapping_data.get('mapping_version')}",
                details=[{"expected": expected_mapping_version, "actual": mapping_data.get("mapping_version")}],
            )

        # 3. Status must be 'approved'
        status = mapping_data.get("status")
        if status != "approved":
            raise ExtractionMappingNotApprovedError(
                f"승인되지 않은 매핑 테이블입니다: status='{status}' (요구: 'approved')",
                details=[{"mapping_id": mapping_data.get("mapping_id"), "status": status}],
            )

        # 4. Checksum verification: request SHA == declared SHA == canonical SHA
        declared_sha = mapping_data.get("mapping_sha256")
        canonical_sha = compute_mapping_canonical_sha256(mapping_data)

        if declared_sha != canonical_sha:
            raise ExtractionMappingChecksumMismatchError(
                f"매핑 테이블 선언 SHA-256('{declared_sha}')이 정규화 계산값('{canonical_sha}')과 일치하지 않습니다.",
                details=[{"declared": declared_sha, "canonical": canonical_sha}],
            )

        if expected_mapping_sha256 and expected_mapping_sha256 != canonical_sha:
            raise ExtractionMappingChecksumMismatchError(
                f"요청 mapping_sha256('{expected_mapping_sha256}')이 정규화 계산값('{canonical_sha}')과 일치하지 않습니다.",
                details=[{"expected": expected_mapping_sha256, "canonical": canonical_sha}],
            )

        # 5. Schema fingerprint verification
        mapping_fingerprint = mapping_data.get("source_schema_fingerprint")
        if expected_source_schema_fingerprint:
            if mapping_fingerprint != expected_source_schema_fingerprint:
                raise ExtractionSchemaFingerprintMismatchError(
                    f"소스 프로토콜 스키마 지문 불일치: 예상={expected_source_schema_fingerprint}, 매핑선언={mapping_fingerprint}",
                    details=[{"expected": expected_source_schema_fingerprint, "actual": mapping_fingerprint}],
                )

        # 6. Source format verification
        actual_source_format = mapping_data.get("source_format")
        if actual_source_format is None and "protocol_version" in mapping_data:
            actual_source_format = "sensor_record_v2"
        if expected_source_format:
            if actual_source_format != expected_source_format:
                raise ExtractionMappingSourceFormatMismatchError(
                    f"매핑 source_format 불일치: 요구='{expected_source_format}', 실제='{actual_source_format}'",
                    details=[{"expected": expected_source_format, "actual": actual_source_format}],
                )

        # 7. Field mappings integrity: duplicates, collisions, reserved fields, transforms
        field_mappings = mapping_data.get("field_mappings", [])
        if not field_mappings:
            raise ExtractionMappingEmptyError("매핑 테이블에 최소 1개 이상의 field_mappings가 정의되어야 합니다.")

        seen_sources: set[str] = set()
        seen_targets: set[str] = set()

        for fm in field_mappings:
            src = fm.get("source_field")
            tgt = fm.get("target_field")
            transform = fm.get("transform")

            # Check duplicate source_field
            if src in seen_sources:
                raise ExtractionMappingDuplicateSourceFieldError(
                    f"중복된 source_field 선언이 발견되었습니다: '{src}'",
                    details=[{"source_field": src}],
                )
            seen_sources.add(src)

            # Check target collision
            if tgt in seen_targets:
                raise ExtractionMappingTargetCollisionError(
                    f"중복된 target_field 선언이 발견되었습니다 (Target Collision): '{tgt}'",
                    details=[{"target_field": tgt}],
                )
            seen_targets.add(tgt)

            # Check reserved target field
            if tgt in RESERVED_TARGET_FIELDS:
                raise ExtractionMappingReservedTargetFieldError(
                    f"예약된 식별자/Provenance 필드는 target_field로 사용할 수 없습니다: '{tgt}'",
                    details=[{"target_field": tgt, "reserved_fields": sorted(RESERVED_TARGET_FIELDS)}],
                )

            # Check transform allowlist
            if transform not in ALLOWED_TRANSFORMS:
                raise ExtractionFeatureNotImplementedError(
                    f"지원하지 않는 변환(transform) 함수입니다: '{transform}' (허용: {sorted(ALLOWED_TRANSFORMS)})",
                    details=[{"field": src, "transform": transform}],
                )

    def apply_transform(
        self,
        value: Any,
        transform: str,
        target_type: str,
    ) -> Any:
        """Apply allowlisted transformation to a single measurement value."""
        if transform not in ALLOWED_TRANSFORMS:
            raise ExtractionFeatureNotImplementedError(f"지원하지 않는 변환 규칙: '{transform}'")

        try:
            if transform == "identity":
                val = value
            elif transform == "to_float":
                val = float(value)
            elif transform == "to_int":
                val = int(round(float(value)))
            elif transform == "to_string":
                val = str(value)
            elif transform == "scale_10x":
                val = float(value) * 10.0
            elif transform == "kelvin_to_celsius":
                val = float(value) - 273.15
            elif transform == "celsius_to_kelvin":
                val = float(value) + 273.15
            else:
                val = value

            # Type cast to target_type
            if target_type == "float":
                return float(val)
            elif target_type == "int":
                return int(round(float(val)))
            elif target_type == "string":
                return str(val)
            elif target_type == "bool":
                return bool(val)
            return val
        except (ValueError, TypeError) as exc:
            raise ValueError(f"변환 실행 실패 ({transform} -> {target_type}) 값 '{value}': {exc}") from exc
