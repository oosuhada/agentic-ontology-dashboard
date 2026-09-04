"""Training Configuration Provider loading, validating, and managing versioned training configs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from systems.generator.app.training.training_exception import (
    TrainingConfigNotFoundError,
    TrainingConfigValidationError,
    TrainingContractError,
)
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path("contracts/schemas/generator-training-config.schema.json")


@dataclass(frozen=True)
class TrainingConfigSpec:
    """Represents a validated in-memory training configuration specification."""

    training_config_version: str
    split_strategy: str
    split_ratio: dict[str, float]
    random_seed: int
    hyperparameters: dict[str, dict[str, Any]]
    metrics: list[str]
    primary_metric: str
    config_file_path: Path
    sha256: str
    uri: str
    description: str = ""
    raw_config: dict[str, Any] = None


class TrainingConfigProvider:
    """Provider for loading and validating Training Configuration files."""

    def __init__(self, search_dirs: list[Path] | None = None) -> None:
        if search_dirs is not None:
            self.search_dirs = [Path(d) for d in search_dirs]
        else:
            models_store = getattr(PATHS, "models_store", Path("models_store"))
            data_dir = getattr(PATHS, "data_dir", Path("data"))
            repo_root = Path.cwd()
            self.search_dirs = [
                repo_root / "systems" / "generator" / "schemas" / "training",
                repo_root / "contracts" / "examples" / "generator-training",
                Path(models_store) / "schemas" / "training",
                Path(models_store) / "training_configs",
                Path(data_dir) / "schemas" / "training",
                Path(data_dir) / "training_configs",
                repo_root / "schemas" / "training",
            ]
        self._schema_cache: dict[str, Any] | None = None

    def _get_schema(self) -> dict[str, Any]:
        """Load JSON Schema for training config."""
        if self._schema_cache is None:
            schema_file = SCHEMA_PATH
            if not schema_file.exists():
                schema_file = Path.cwd() / SCHEMA_PATH
            if not schema_file.exists():
                raise TrainingContractError(f"Training Config 스키마를 찾을 수 없습니다: {SCHEMA_PATH}")
            try:
                self._schema_cache = json.loads(schema_file.read_text(encoding="utf-8"))
            except Exception as exc:
                raise TrainingContractError(f"Training Config 스키마 파싱 실패: {exc}") from exc
        return self._schema_cache

    def get_logical_uri(self, path: Path) -> str:
        """Convert a path to canonical logical relative URI."""
        try:
            resolved = path.resolve()
            cwd = Path.cwd().resolve()
            models_store = getattr(PATHS, "models_store", Path("models_store")).resolve()
            data_dir = getattr(PATHS, "data_dir", Path("data")).resolve()

            if models_store in resolved.parents or resolved == models_store:
                return f"models_store/{resolved.relative_to(models_store).as_posix()}"
            if data_dir in resolved.parents or resolved == data_dir:
                return f"data/{resolved.relative_to(data_dir).as_posix()}"
            if cwd in resolved.parents:
                rel = resolved.relative_to(cwd).as_posix()
                if not rel.startswith(".."):
                    return rel
            return resolved.name
        except Exception:
            return path.name

    def load_training_config(self, config_version: str) -> TrainingConfigSpec:
        """Load, validate, and compute checksum for training configuration version."""
        clean_ver = str(config_version).strip()
        if ".." in clean_ver or "/" in clean_ver or "\\" in clean_ver:
            raise TrainingContractError(f"안전하지 않은 training_config_version입니다: '{config_version}'")

        target_file: Path | None = None
        for base_dir in self.search_dirs:
            if not base_dir.exists():
                continue
            cand_files = [
                base_dir / f"{clean_ver}.json",
                base_dir / clean_ver / "config.json",
                base_dir / f"{clean_ver}.yaml",
            ]
            for cand in cand_files:
                if cand.exists() and cand.is_file():
                    target_file = cand.resolve()
                    break
            if target_file:
                break

        if target_file is None:
            raise TrainingConfigNotFoundError(
                f"Training Configuration 버전을 찾을 수 없습니다: '{clean_ver}'"
            )

        try:
            raw_text = target_file.read_text(encoding="utf-8")
            config_dict = json.loads(raw_text)
        except Exception as exc:
            raise TrainingConfigValidationError(f"Training Config 파일 파싱 실패 ({target_file.name}): {exc}") from exc

        # 1. JSON Schema Validation
        schema = self._get_schema()
        try:
            jsonschema.validate(instance=config_dict, schema=schema)
        except jsonschema.ValidationError as exc:
            raise TrainingConfigValidationError(f"Training Config 스키마 검증 실패: {exc.message}") from exc

        # 2. Identity check
        declared_ver = config_dict.get("training_config_version")
        if declared_ver != clean_ver:
            raise TrainingConfigValidationError(
                f"Training Config 파일 내부 버전('{declared_ver}')과 요청 버전('{clean_ver}')이 일치하지 않습니다."
            )

        # 3. Ratio sum check
        split_ratio = config_dict.get("split_ratio", {})
        total_ratio = sum(split_ratio.values())
        if abs(total_ratio - 1.0) > 1e-5:
            raise TrainingConfigValidationError(
                f"split_ratio의 합은 1.0이어야 합니다. (현재 합: {total_ratio})"
            )

        file_sha256 = compute_file_sha256(target_file)
        logical_uri = self.get_logical_uri(target_file)

        return TrainingConfigSpec(
            training_config_version=clean_ver,
            split_strategy=config_dict.get("split_strategy", "asset_time_split"),
            split_ratio=split_ratio,
            random_seed=int(config_dict.get("random_seed", 42)),
            hyperparameters=config_dict.get("hyperparameters", {}),
            metrics=config_dict.get("metrics", ["f1", "accuracy", "precision", "recall", "roc_auc"]),
            primary_metric=config_dict.get("primary_metric", "f1"),
            config_file_path=target_file,
            sha256=file_sha256,
            uri=logical_uri,
            description=config_dict.get("description", ""),
            raw_config=config_dict,
        )
