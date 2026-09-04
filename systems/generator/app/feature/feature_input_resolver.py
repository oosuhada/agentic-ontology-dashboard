"""Feature Input Resolver loading, validating, and binding Versioned Datasets with Manifests."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema

from systems.generator.app.feature.feature_exception import (
    FeatureContractError,
    FeatureDatasetIntegrityError,
    FeatureInputNotFoundError,
    FeatureSchemaMismatchError,
)
from systems.generator.app.feature.feature_repository import FeatureRepository
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path("contracts/schemas/generator-dataset-input-manifest.schema.json")


@dataclass(frozen=True)
class ResolvedFeatureInput:
    """Represents a strictly resolved and integrity-verified dataset input."""

    dataset_type: Literal["observation", "failure"]
    dataset_id: str
    dataset_version: str
    schema_version: str
    manifest_path: Path
    manifest_sha256: str
    manifest_uri: str
    payload_path: Path
    payload_sha256: str
    payload_uri: str


class FeatureInputResolver:
    """Resolves and validates Versioned Dataset directories, Manifests, and payload files."""

    def __init__(self, feature_repo: FeatureRepository | None = None) -> None:
        self.feature_repo = feature_repo or FeatureRepository()
        self._schema_cache: dict[str, Any] | None = None

    def _get_manifest_schema(self) -> dict[str, Any]:
        """Load JSON Schema for dataset input manifest."""
        if self._schema_cache is None:
            schema_file = SCHEMA_PATH
            if not schema_file.exists():
                # Check relative to cwd
                schema_file = Path.cwd() / SCHEMA_PATH
            if not schema_file.exists():
                raise FeatureContractError(f"Dataset Input Manifest 스키마를 찾을 수 없습니다: {SCHEMA_PATH}")
            try:
                self._schema_cache = json.loads(schema_file.read_text(encoding="utf-8"))
            except Exception as exc:
                raise FeatureContractError(f"Manifest 스키마 파일 파싱 실패: {exc}") from exc
        return self._schema_cache

    def _is_within_allowed_root(self, path: Path) -> bool:
        """Check whether path is confined within project root or data directory."""
        try:
            resolved = path.resolve()
            root = Path.cwd().resolve()
            data_dir = getattr(PATHS, "data_dir", root / "data").resolve()
            return (
                resolved == root
                or root in resolved.parents
                or resolved == data_dir
                or data_dir in resolved.parents
            )
        except Exception:
            return False

    def resolve_dataset(
        self,
        dataset_type: Literal["observation", "failure"],
        dataset_id: str,
        dataset_version: str,
    ) -> ResolvedFeatureInput:
        """Strictly resolve and validate a Versioned Dataset directory and its Manifest."""
        clean_id = dataset_id.strip()
        clean_ver = dataset_version.strip()

        if ".." in clean_id or ".." in clean_ver or "/" in clean_id or "\\" in clean_id:
            raise FeatureContractError(
                f"안전하지 않은 데이터셋 식별자입니다: dataset_id='{dataset_id}', version='{dataset_version}'"
            )

        plural_type = "observations" if dataset_type == "observation" else "failures"
        data_dir = getattr(PATHS, "data_dir", Path("data"))

        # Primary search candidates in canonical versioned structure
        search_dirs = [
            Path(f"data/{plural_type}/{clean_id}/{clean_ver}"),
            Path(data_dir) / plural_type / clean_id / clean_ver,
            Path(data_dir) / clean_id / clean_ver,
        ]

        target_dir: Path | None = None
        for cand in search_dirs:
            if cand.exists() and cand.is_dir():
                if not self._is_within_allowed_root(cand):
                    raise FeatureContractError(f"안전하지 않은 데이터셋 경로 접근이 감지되었습니다: {cand}")
                manifest_file = cand / "dataset_manifest.json"
                if manifest_file.exists() and manifest_file.is_file():
                    target_dir = cand.resolve()
                    break

        if target_dir is None:
            raise FeatureInputNotFoundError(
                f"Versioned {dataset_type.capitalize()} 데이터셋(dataset_manifest.json 포함)을 찾을 수 없습니다: "
                f"dataset_id='{clean_id}', dataset_version='{clean_ver}'"
            )

        manifest_path = target_dir / "dataset_manifest.json"
        try:
            manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise FeatureContractError(f"dataset_manifest.json 파싱 실패 ({manifest_path.name}): {exc}") from exc

        # 1. JSON Schema Validation
        schema = self._get_manifest_schema()
        try:
            jsonschema.validate(instance=manifest_dict, schema=schema)
        except jsonschema.ValidationError as exc:
            raise FeatureSchemaMismatchError(f"dataset_manifest.json 스키마 검증 실패: {exc.message}") from exc

        # 2. Identity and Type Cross-Validation
        if manifest_dict.get("dataset_type") != dataset_type:
            raise FeatureSchemaMismatchError(
                f"Manifest의 dataset_type('{manifest_dict.get('dataset_type')}')이 "
                f"요청 타입('{dataset_type}')과 일치하지 않습니다."
            )
        if manifest_dict.get("dataset_id") != clean_id:
            raise FeatureSchemaMismatchError(
                f"Manifest의 dataset_id('{manifest_dict.get('dataset_id')}')가 "
                f"요청 ID('{clean_id}')와 일치하지 않습니다."
            )
        if manifest_dict.get("dataset_version") != clean_ver:
            raise FeatureSchemaMismatchError(
                f"Manifest의 dataset_version('{manifest_dict.get('dataset_version')}')이 "
                f"요청 버전('{clean_ver}')과 일치하지 않습니다."
            )

        schema_version = manifest_dict.get("schema_version", "")

        # 3. Payload File Integrity and Role Verification
        files = manifest_dict.get("files", [])
        expected_role = "observations" if dataset_type == "observation" else "failures"
        matching_files = [f for f in files if f.get("role") == expected_role]

        if len(matching_files) != 1:
            raise FeatureSchemaMismatchError(
                f"Manifest에 정확히 1개의 '{expected_role}' role 파일이 선언되어야 합니다. (발견: {len(matching_files)})"
            )

        # Ensure no duplicate roles
        roles = [f.get("role") for f in files]
        if len(roles) != len(set(roles)):
            raise FeatureSchemaMismatchError(f"Manifest에 중복된 role이 존재합니다: {roles}")

        target_file_entry = matching_files[0]
        rel_payload_path = target_file_entry.get("path", "").strip()

        if not rel_payload_path or ".." in rel_payload_path or rel_payload_path.startswith("/") or "\\" in rel_payload_path:
            raise FeatureContractError(f"Manifest의 payload 경로가 안전하지 않습니다: '{rel_payload_path}'")

        payload_path = (target_dir / rel_payload_path).resolve()
        if not payload_path.exists() or not payload_path.is_file():
            raise FeatureDatasetIntegrityError(
                f"Manifest가 선언한 payload 파일이 존재하지 않습니다: '{rel_payload_path}'"
            )
        if not self._is_within_allowed_root(payload_path):
            raise FeatureContractError(f"안전하지 않은 payload 경로 접근입니다: {payload_path}")

        # Check payload size and checksum
        actual_size = payload_path.stat().st_size
        declared_size = target_file_entry.get("size_bytes")
        if declared_size is not None and actual_size != declared_size:
            raise FeatureDatasetIntegrityError(
                f"Payload 파일 크기 불일치: 실제 {actual_size} != 선언 {declared_size}"
            )

        actual_sha256 = compute_file_sha256(payload_path)
        declared_sha256 = target_file_entry.get("sha256", "").strip().lower()
        if actual_sha256 != declared_sha256:
            raise FeatureDatasetIntegrityError(
                f"Payload 파일 체크섬 불일치 ({rel_payload_path}): 실제 '{actual_sha256}' != 선언 '{declared_sha256}'"
            )

        manifest_sha256 = compute_file_sha256(manifest_path)
        manifest_uri = self.feature_repo.get_logical_uri(manifest_path)
        payload_uri = self.feature_repo.get_logical_uri(payload_path)

        return ResolvedFeatureInput(
            dataset_type=dataset_type,
            dataset_id=clean_id,
            dataset_version=clean_ver,
            schema_version=schema_version,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            manifest_uri=manifest_uri,
            payload_path=payload_path,
            payload_sha256=actual_sha256,
            payload_uri=payload_uri,
        )
