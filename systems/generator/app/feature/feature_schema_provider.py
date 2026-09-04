"""Feature Schema Provider loading versioned schema files and enforcing recipe contracts."""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from systems.generator.generator_config import PATHS
from systems.generator.app.feature.feature_exception import (
    FeatureSchemaMismatchError,
    FeatureContractError,
    FeatureInputNotFoundError,
)

logger = logging.getLogger(__name__)

ALLOWED_OPERATIONS = {
    "raw",
    "rolling_mean",
    "rolling_std",
    "rolling_max",
    "rolling_min",
    "lag",
    "diff",
    "ewm_mean",
}

LEAKAGE_FORBIDDEN_COLUMNS = {
    "target",
    "label",
    "failure",
    "failure_type",
    "failure_occurred_at",
    "degradation_start",
    "degradation_started_at",
    "exclusion",
    "exclusion_start",
    "exclusion_end",
    "maintenance_start",
    "maintenance_started_at",
    "maintenance_end",
    "maintenance_completed_at",
    "is_failure",
    "failed",
}


@dataclass(frozen=True)
class FeatureItem:
    """Individual feature calculation recipe definition."""
    feature_name: str
    source_field: str
    dtype: str = "float64"
    operation: str = "raw"  # raw, rolling_mean, rolling_std, rolling_max, rolling_min, lag, diff, ewm_mean
    parameters: dict[str, Any] = field(default_factory=dict)
    missing_value_policy: str = "drop"  # drop, fill_zero, ffill, error


@dataclass
class FeatureSchemaSpec:
    """Declared Feature Schema Specification."""
    schema_version: str
    features: list[FeatureItem]
    schema_file_path: Path | None = None
    description: str = ""

    @property
    def feature_names(self) -> list[str]:
        return [f.feature_name for f in self.features]

    def compute_checksum(self) -> str:
        """Compute canonical SHA-256 hash of declared features."""
        canonical_list = [
            {
                "feature_name": f.feature_name,
                "source_field": f.source_field,
                "dtype": f.dtype,
                "operation": f.operation,
                "parameters": dict(sorted(f.parameters.items())),
                "missing_value_policy": f.missing_value_policy,
            }
            for f in self.features
        ]
        serialized = json.dumps(
            {"schema_version": self.schema_version, "features": canonical_list},
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class FeatureSchemaProvider:
    """Loads and validates versioned Feature Schema definitions from schema files."""

    def __init__(self, search_dirs: list[Path] | None = None) -> None:
        if search_dirs is not None:
            self.search_dirs = [Path(d) for d in search_dirs]
        else:
            models_store = getattr(PATHS, "models_store", Path("models_store"))
            data_dir = getattr(PATHS, "data_dir", Path("data"))
            repo_root = Path.cwd()
            self.search_dirs = [
                repo_root / "systems" / "generator" / "schemas" / "features",
                repo_root / "systems" / "generator" / "feature" / "schemas",
                Path(models_store) / "schemas" / "features",
                Path(data_dir) / "schemas" / "features",
                repo_root / "schemas" / "features",
            ]

    def find_schema_file(self, schema_version: str) -> Path:
        """Locate physical schema JSON file."""
        clean_ver = schema_version.strip()
        if ".." in clean_ver or "/" in clean_ver or "\\" in clean_ver:
            raise FeatureContractError(f"안전하지 않은 schema version 경로입니다: {schema_version}")

        filename = f"{clean_ver}.json" if not clean_ver.endswith(".json") else clean_ver

        for sdir in self.search_dirs:
            candidate = sdir / filename
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

        raise FeatureInputNotFoundError(f"Feature Schema 파일을 찾을 수 없습니다: '{schema_version}'")

    def get_feature_schema(
        self,
        schema_version: str,
        available_columns: list[str] | None = None,
        custom_items: list[FeatureItem] | None = None,
    ) -> FeatureSchemaSpec:
        """Resolve feature schema specification and validate against leakage and operations."""
        if not schema_version or not schema_version.strip():
            raise FeatureContractError("feature_schema_version이 지정되지 않았습니다.")

        clean_ver = schema_version.strip()
        schema_path: Path | None = None
        description = ""

        if custom_items is not None:
            features = custom_items
        else:
            schema_path = self.find_schema_file(clean_ver)
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception as exc:
                raise FeatureContractError(f"Feature Schema 파일 파싱 실패 ({schema_path.name}): {exc}") from exc

            declared_version = (raw_data.get("feature_schema_version") or raw_data.get("schema_version") or "").strip()
            if not declared_version:
                raise FeatureSchemaMismatchError(f"Feature Schema 파일에 버전 필드가 누락되었습니다: {schema_path.name}")

            if declared_version != clean_ver:
                raise FeatureSchemaMismatchError(
                    f"요청된 feature_schema_version '{clean_ver}'과 "
                    f"파일 내 선언 버전 '{declared_version}'이 일치하지 않습니다."
                )

            description = raw_data.get("description", "")
            raw_features = raw_data.get("features", [])
            if not raw_features:
                raise FeatureSchemaMismatchError(f"Feature Schema '{clean_ver}'에 정의된 Feature가 없습니다.")

            features = []
            for item in raw_features:
                if isinstance(item, str):
                    feat_item = FeatureItem(feature_name=item, source_field=item, operation="raw")
                elif isinstance(item, dict):
                    fname = item.get("feature_name") or item.get("name")
                    src = item.get("source_field") or item.get("source") or fname
                    dtype = item.get("dtype", "float64")
                    op = item.get("operation", "raw")
                    params = item.get("parameters", {})
                    mv_policy = item.get("missing_value_policy", "drop")
                    if not fname or not src:
                        raise FeatureSchemaMismatchError(f"Feature 정의에 필수 필드가 누락되었습니다: {item}")
                    feat_item = FeatureItem(
                        feature_name=fname,
                        source_field=src,
                        dtype=dtype,
                        operation=op,
                        parameters=params,
                        missing_value_policy=mv_policy,
                    )
                else:
                    raise FeatureSchemaMismatchError(f"잘못된 Feature 항목 형식입니다: {item}")
                features.append(feat_item)

        # Validate operations, duplicates, and leakage
        seen_names = set()
        for item in features:
            if item.operation not in ALLOWED_OPERATIONS:
                raise FeatureSchemaMismatchError(
                    f"지원하지 않는 Feature 연산(operation)입니다: '{item.operation}'. "
                    f"지원 목록: {sorted(list(ALLOWED_OPERATIONS))}"
                )

            if item.feature_name in seen_names:
                raise FeatureSchemaMismatchError(f"중복된 Feature 이름이 선언되었습니다: '{item.feature_name}'")
            seen_names.add(item.feature_name)

            lower_name = item.feature_name.lower()
            lower_src = item.source_field.lower()
            if any(forbidden in lower_name for forbidden in LEAKAGE_FORBIDDEN_COLUMNS) or \
               any(forbidden in lower_src for forbidden in LEAKAGE_FORBIDDEN_COLUMNS):
                raise FeatureSchemaMismatchError(
                    f"Target leakage 위험 컬럼은 Feature Schema에 포함될 수 없습니다: '{item.feature_name}'"
                )

        return FeatureSchemaSpec(
            schema_version=clean_ver,
            features=features,
            schema_file_path=schema_path,
            description=description,
        )

    def parse_schema_dict(self, raw_data: dict[str, Any]) -> FeatureSchemaSpec:
        """Parse in-memory Feature Schema dictionary into FeatureSchemaSpec with validation."""
        declared_version = (raw_data.get("feature_schema_version") or raw_data.get("schema_version") or "1.0").strip()
        description = raw_data.get("description", "")
        raw_features = raw_data.get("features", [])
        if not raw_features:
            raise FeatureSchemaMismatchError("Feature Schema에 정의된 Feature가 없습니다.")

        features: list[FeatureItem] = []
        for item in raw_features:
            if isinstance(item, str):
                feat_item = FeatureItem(feature_name=item, source_field=item, operation="raw")
            elif isinstance(item, dict):
                fname = item.get("feature_name") or item.get("name")
                src = item.get("source_field") or item.get("source") or fname
                dtype = item.get("dtype", "float64")
                op = item.get("operation", "raw")
                params = item.get("parameters", {})
                mv_policy = item.get("missing_value_policy", "drop")
                if not fname or not src:
                    raise FeatureSchemaMismatchError(f"Feature 정의에 필수 필드가 누락되었습니다: {item}")
                feat_item = FeatureItem(
                    feature_name=fname,
                    source_field=src,
                    dtype=dtype,
                    operation=op,
                    parameters=params,
                    missing_value_policy=mv_policy,
                )
            else:
                raise FeatureSchemaMismatchError(f"잘못된 Feature 항목 형식입니다: {item}")
            features.append(feat_item)

        # Validate operations, duplicates, and leakage
        seen_names = set()
        for item in features:
            if item.operation not in ALLOWED_OPERATIONS:
                raise FeatureSchemaMismatchError(
                    f"지원하지 않는 Feature 연산(operation)입니다: '{item.operation}'. "
                    f"지원 목록: {sorted(list(ALLOWED_OPERATIONS))}"
                )
            if item.feature_name in seen_names:
                raise FeatureSchemaMismatchError(f"중복된 Feature 이름이 선언되었습니다: '{item.feature_name}'")
            seen_names.add(item.feature_name)

            lower_name = item.feature_name.lower()
            lower_src = item.source_field.lower()
            if any(forbidden in lower_name for forbidden in LEAKAGE_FORBIDDEN_COLUMNS) or \
               any(forbidden in lower_src for forbidden in LEAKAGE_FORBIDDEN_COLUMNS):
                raise FeatureSchemaMismatchError(
                    f"Target leakage 위험 컬럼은 Feature Schema에 포함될 수 없습니다: '{item.feature_name}'"
                )

        return FeatureSchemaSpec(
            schema_version=declared_version,
            features=features,
            description=description,
        )
