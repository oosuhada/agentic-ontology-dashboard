"""Label Schema Provider loading versioned label schema files and enforcing horizon contracts."""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from systems.generator.generator_config import PATHS
from systems.generator.app.feature.feature_exception import (
    FeatureSchemaMismatchError,
    FeatureContractError,
    FeatureInputNotFoundError,
)

logger = logging.getLogger(__name__)

OFFICIAL_PREDICTION_TASK = "binary_failure_within_horizon"


@dataclass
class LabelSchemaSpec:
    """Declared Label Schema Specification."""
    schema_version: str
    prediction_task: str
    prediction_horizon_hours: int
    anchor: str = "failure_point"
    exclusion_end: str | None = "period_end"
    positive_window: str = "pre_failure"
    active_failure_policy: str = "exclude"
    target_name: str = "label"
    schema_file_path: Path | None = None
    description: str = ""

    def compute_checksum(self) -> str:
        """Compute canonical SHA-256 hash of label schema configuration."""
        data = {
            "schema_version": self.schema_version,
            "prediction_task": self.prediction_task,
            "prediction_horizon_hours": self.prediction_horizon_hours,
            "anchor": self.anchor,
            "exclusion_end": self.exclusion_end,
            "positive_window": self.positive_window,
            "active_failure_policy": self.active_failure_policy,
            "target_name": self.target_name,
        }
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class LabelSchemaProvider:
    """Loads and validates versioned Label Schema definitions from schema files."""

    def __init__(self, search_dirs: list[Path] | None = None) -> None:
        if search_dirs is not None:
            self.search_dirs = [Path(d) for d in search_dirs]
        else:
            models_store = getattr(PATHS, "models_store", Path("models_store"))
            data_dir = getattr(PATHS, "data_dir", Path("data"))
            repo_root = Path.cwd()
            self.search_dirs = [
                repo_root / "systems" / "generator" / "schemas" / "labels",
                repo_root / "systems" / "generator" / "feature" / "schemas" / "labels",
                Path(models_store) / "schemas" / "labels",
                Path(data_dir) / "schemas" / "labels",
                repo_root / "schemas" / "labels",
            ]

    def find_schema_file(self, schema_version: str) -> Path:
        """Locate physical label schema JSON file."""
        clean_ver = schema_version.strip()
        if ".." in clean_ver or "/" in clean_ver or "\\" in clean_ver:
            raise FeatureContractError(f"안전하지 않은 label schema version 경로입니다: {schema_version}")

        filename = f"{clean_ver}.json" if not clean_ver.endswith(".json") else clean_ver

        for sdir in self.search_dirs:
            candidate = sdir / filename
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

        raise FeatureInputNotFoundError(f"Label Schema 파일을 찾을 수 없습니다: '{schema_version}'")

    def get_label_schema(
        self,
        schema_version: str,
        requested_horizon_hours: int | None = None,
    ) -> LabelSchemaSpec:
        """Resolve label schema specification from file and verify prediction task and horizon alignment."""
        if not schema_version or not schema_version.strip():
            raise FeatureContractError("label_schema_version이 지정되지 않았습니다.")

        clean_ver = schema_version.strip()
        schema_path = self.find_schema_file(clean_ver)

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            raise FeatureContractError(f"Label Schema 파일 파싱 실패 ({schema_path.name}): {exc}") from exc

        declared_version = (raw_data.get("label_schema_version") or raw_data.get("schema_version") or "").strip()
        if not declared_version:
            raise FeatureSchemaMismatchError(f"Label Schema 파일에 버전 필드가 누락되었습니다: {schema_path.name}")

        if declared_version != clean_ver:
            raise FeatureSchemaMismatchError(
                f"요청된 label_schema_version '{clean_ver}'과 "
                f"파일 내 선언 버전 '{declared_version}'이 일치하지 않습니다."
            )

        task = raw_data.get("prediction_task", OFFICIAL_PREDICTION_TASK)
        if task != OFFICIAL_PREDICTION_TASK:
            raise FeatureSchemaMismatchError(
                f"지원하지 않는 prediction_task입니다: '{task}'. '{OFFICIAL_PREDICTION_TASK}'만 지원됩니다."
            )

        horizon = raw_data.get("prediction_horizon_hours")
        if horizon is None or not isinstance(horizon, (int, float)) or horizon <= 0:
            raise FeatureSchemaMismatchError(
                f"Label Schema에 유효한 prediction_horizon_hours 설정이 필요합니다: {horizon}"
            )
        horizon = int(horizon)

        if requested_horizon_hours is not None and requested_horizon_hours != horizon:
            raise FeatureSchemaMismatchError(
                f"요청된 prediction_horizon_hours ({requested_horizon_hours})와 "
                f"Label Schema '{clean_ver}'의 설정 ({horizon})이 일치하지 않습니다."
            )

        return LabelSchemaSpec(
            schema_version=clean_ver,
            prediction_task=task,
            prediction_horizon_hours=horizon,
            anchor=raw_data.get("anchor", "failure_point"),
            exclusion_end=raw_data.get("exclusion_end", "period_end"),
            positive_window=raw_data.get("positive_window", "pre_failure"),
            active_failure_policy=raw_data.get("active_failure_policy", "exclude"),
            target_name=raw_data.get("target_name", "label"),
            schema_file_path=schema_path,
            description=raw_data.get("description", ""),
        )
