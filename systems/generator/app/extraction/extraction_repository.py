"""Repository for atomic directory publishing, same-parent staging, and full dataset integrity verification."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.extraction.extraction_exception import (
    ExtractionDatasetConflictError,
    ExtractionIntegrityError,
    ExtractionNoValidObservationsError,
    ExtractionPublishFailedError,
    ExtractionRequestInvalidError,
)

logger = logging.getLogger(__name__)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ExtractionRepository:
    """Handles staging, manifest generation, schema verification, and atomic publishing of Observation Datasets."""

    def __init__(
        self,
        observations_root: Optional[Path] = None,
        manifest_schema_path: Optional[Path] = None,
        runs_root: Optional[Path] = None,
    ) -> None:
        self.observations_root = (observations_root or PATHS.observations_root).resolve()
        self.runs_root = (runs_root or PATHS.extraction_runs_root).resolve()
        self.manifest_schema_path = manifest_schema_path or (
            PROJECT_ROOT / "contracts" / "schemas" / "generator-dataset-input-manifest.schema.json"
        )
        self._manifest_schema_cache: Optional[dict[str, Any]] = None

    def _get_manifest_schema(self) -> dict[str, Any]:
        if self._manifest_schema_cache is None:
            if not self.manifest_schema_path.is_file():
                raise ExtractionIntegrityError(f"Dataset Input Manifest schema not found: {self.manifest_schema_path}")
            try:
                self._manifest_schema_cache = json.loads(self.manifest_schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExtractionIntegrityError(f"Failed to parse manifest schema: {e}") from e
        return self._manifest_schema_cache

    def get_target_dir(self, dataset_id: str, dataset_version: str) -> Path:
        """Get canonical destination directory for versioned dataset."""
        return (self.observations_root / dataset_id / dataset_version).resolve()

    def get_staging_dir(self, dataset_id: str, dataset_version: str, run_id: str) -> Path:
        """Get atomic staging directory on same parent directory for atomic rename."""
        p = (self.observations_root / dataset_id / f".tmp_{dataset_version}_{run_id}_{int(time.time_ns())}").resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def validate_existing_dataset(
        self,
        dataset_id: str,
        dataset_version: str,
        expected_obs_sha256: Optional[str] = None,
        expected_prov_sha256: Optional[str] = None,
        expected_rej_sha256: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Fully validate existing published dataset for manifest schema, file presence, size, and SHA-256."""
        target_dir = self.get_target_dir(dataset_id, dataset_version)
        if not target_dir.exists() or not target_dir.is_dir():
            return None

        manifest_file = target_dir / "dataset_manifest.json"
        if not manifest_file.is_file():
            raise ExtractionDatasetConflictError(
                f"대상 데이터셋 디렉터리({dataset_id}/{dataset_version})에 dataset_manifest.json이 누락되어 있습니다.",
                details=[{"target_dir": str(target_dir)}],
            )

        try:
            manifest_dict = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ExtractionDatasetConflictError(
                f"기존 dataset_manifest.json 파싱 실패: {exc}",
                details=[{"target_dir": str(target_dir)}],
            ) from exc

        # Schema validation
        schema = self._get_manifest_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(manifest_dict)
        except jsonschema.ValidationError as exc:
            raise ExtractionDatasetConflictError(
                f"기존 dataset_manifest.json 스키마 검증 실패: {exc.message}",
                details=[{"target_dir": str(target_dir), "error": exc.message}],
            ) from exc

        # Verify dataset_id & dataset_version match
        if manifest_dict.get("dataset_id") != dataset_id or manifest_dict.get("dataset_version") != dataset_version:
            raise ExtractionDatasetConflictError(
                f"매니페스트 선언 ID/Version 불일치: manifest=({manifest_dict.get('dataset_id')}/{manifest_dict.get('dataset_version')}), target=({dataset_id}/{dataset_version})"
            )

        # Verify exactly one observations file
        files = manifest_dict.get("files", [])
        obs_entries = [f for f in files if f.get("role") == "observations"]
        if len(obs_entries) != 1:
            raise ExtractionDatasetConflictError(f"매니페스트에 observations 역할 파일이 정확히 1개 존재해야 합니다 (현재: {len(obs_entries)})")
        obs_entry = obs_entries[0]

        # Verify auxiliary_files: exactly 1 provenance, 1 rejected
        aux_files = manifest_dict.get("auxiliary_files", [])
        prov_entries = [f for f in aux_files if f.get("role") == "provenance"]
        rej_entries = [f for f in aux_files if f.get("role") == "rejected"]
        if len(prov_entries) != 1 or len(rej_entries) != 1 or len(aux_files) != 2:
            raise ExtractionDatasetConflictError(
                f"매니페스트에 provenance 및 rejected 보조 파일이 각각 정확히 1개씩(총 2개) 존재해야 합니다 (현재 aux_files: {len(aux_files)})"
            )

        # Validate all declared files exist, within directory, and match size/SHA-256
        all_declared = list(files) + list(aux_files)
        for entry in all_declared:
            rel_path = entry.get("path", "")
            if ".." in rel_path or Path(rel_path).is_absolute():
                raise ExtractionDatasetConflictError(f"매니페스트 경로에 비정상 경로 탐색이 포함되어 있습니다: '{rel_path}'")

            target_file = (target_dir / rel_path).resolve()
            if not target_file.is_file():
                raise ExtractionDatasetConflictError(f"선언된 데이터셋 파일이 존재하지 않습니다: '{rel_path}'")

            actual_size = target_file.stat().st_size
            declared_size = entry.get("size_bytes")
            if declared_size is not None and actual_size != declared_size:
                raise ExtractionDatasetConflictError(
                    f"파일 크기 불일치 '{rel_path}': 선언={declared_size}, 실제={actual_size}"
                )

            actual_sha = compute_file_sha256(target_file)
            declared_sha = entry.get("sha256")
            if declared_sha and actual_sha != declared_sha:
                raise ExtractionDatasetConflictError(
                    f"파일 SHA-256 불일치 '{rel_path}': 선언={declared_sha}, 실제={actual_sha}"
                )

        # Compare with expected values if provided
        if expected_obs_sha256:
            actual_obs_sha = compute_file_sha256(target_dir / obs_entry["path"])
            if actual_obs_sha != expected_obs_sha256:
                raise ExtractionDatasetConflictError(
                    f"동일한 데이터셋 버전({dataset_id}/{dataset_version})이 상이한 observations 데이터(체크섬={actual_obs_sha})로 이미 발행되어 있습니다.",
                    details=[{"existing_sha": actual_obs_sha, "new_sha": expected_obs_sha256}],
                )

        if expected_prov_sha256:
            actual_prov_sha = compute_file_sha256(target_dir / prov_entries[0]["path"])
            if actual_prov_sha != expected_prov_sha256:
                raise ExtractionDatasetConflictError(
                    f"동일한 데이터셋 버전({dataset_id}/{dataset_version})의 provenance 체크섬이 상이합니다.",
                    details=[{"existing_sha": actual_prov_sha, "new_sha": expected_prov_sha256}],
                )

        if expected_rej_sha256:
            actual_rej_sha = compute_file_sha256(target_dir / rej_entries[0]["path"])
            if actual_rej_sha != expected_rej_sha256:
                raise ExtractionDatasetConflictError(
                    f"동일한 데이터셋 버전({dataset_id}/{dataset_version})의 rejected 체크섬이 상이합니다.",
                    details=[{"existing_sha": actual_rej_sha, "new_sha": expected_rej_sha256}],
                )

        return manifest_dict

    def check_existing_dataset(
        self,
        dataset_id: str,
        dataset_version: str,
        expected_obs_sha256: Optional[str] = None,
        expected_prov_sha256: Optional[str] = None,
        expected_rej_sha256: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Alias for validate_existing_dataset."""
        return self.validate_existing_dataset(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_obs_sha256=expected_obs_sha256,
            expected_prov_sha256=expected_prov_sha256,
            expected_rej_sha256=expected_rej_sha256,
        )

    def stage_and_publish_dataset(
        self,
        run_id: str,
        dataset_id: str,
        dataset_version: str,
        observations: list[dict[str, Any]],
        provenance_records: list[dict[str, Any]],
        rejected_records: list[dict[str, Any]],
        schema_version: str = "canonical-observation-v1",
    ) -> tuple[Path, dict[str, Any]]:
        """Stage observations, rejected records, provenance, and manifest, then atomically publish via directory rename."""
        if not observations:
            raise ExtractionNoValidObservationsError(
                "유효한 Canonical Observation이 없어 Dataset을 발행할 수 없습니다.",
                details=[{
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "observations_count": 0,
                    "rejected_count": len(rejected_records),
                }],
            )

        target_dir = self.get_target_dir(dataset_id, dataset_version)
        target_parent = target_dir.parent
        target_parent.mkdir(parents=True, exist_ok=True)

        staging_dir = self.get_staging_dir(dataset_id, dataset_version, run_id)

        try:
            # Deterministic sorting
            # 1. observations: (asset_id, observed_at)
            sorted_obs = sorted(observations, key=lambda r: (r.get("asset_id", ""), r.get("observed_at", "")))
            # 2. provenance: (asset_id, observed_at, measurement_key, source_sequence, source_observation_id)
            sorted_prov = sorted(
                provenance_records,
                key=lambda r: (
                    r.get("asset_id", ""),
                    r.get("observed_at", ""),
                    r.get("measurement_key", ""),
                    r.get("source_sequence", 0),
                    r.get("source_observation_id", ""),
                ),
            )
            # 3. rejected: (source_offset, source_sequence)
            sorted_rej = sorted(
                rejected_records,
                key=lambda r: (
                    r.get("source_offset") or 0,
                    r.get("source_sequence") or 0,
                ),
            )

            # Helper to write, flush, fsync file
            def _write_jsonl(filename: str, records: list[dict[str, Any]]) -> tuple[str, int]:
                filepath = staging_dir / filename
                with open(filepath, "wb") as f:
                    for rec in records:
                        line = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        f.write((line + "\n").encode("utf-8"))
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                size_b = filepath.stat().st_size
                sha = compute_file_sha256(filepath)
                return sha, size_b

            obs_sha256, obs_size_bytes = _write_jsonl("observations.jsonl", sorted_obs)
            prov_sha256, prov_size_bytes = _write_jsonl("provenance.jsonl", sorted_prov)
            rej_sha256, rej_size_bytes = _write_jsonl("rejected.jsonl", sorted_rej)

            # Check existing dataset with conflict guard
            existing_manifest = self.validate_existing_dataset(
                dataset_id,
                dataset_version,
                expected_obs_sha256=obs_sha256,
                expected_prov_sha256=prov_sha256,
                expected_rej_sha256=rej_sha256,
            )
            if existing_manifest is not None:
                shutil.rmtree(staging_dir, ignore_errors=True)
                return target_dir, existing_manifest

            # Create and validate dataset_manifest.json with auxiliary_files
            manifest_payload = {
                "manifest_version": "generator-dataset-input-v1",
                "dataset_type": "observation",
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "schema_version": schema_version,
                "created_at": now_utc_iso(),
                "files": [
                    {
                        "role": "observations",
                        "path": "observations.jsonl",
                        "media_type": "application/x-ndjson",
                        "sha256": obs_sha256,
                        "size_bytes": obs_size_bytes,
                    }
                ],
                "auxiliary_files": [
                    {
                        "role": "provenance",
                        "path": "provenance.jsonl",
                        "media_type": "application/x-ndjson",
                        "sha256": prov_sha256,
                        "size_bytes": prov_size_bytes,
                    },
                    {
                        "role": "rejected",
                        "path": "rejected.jsonl",
                        "media_type": "application/x-ndjson",
                        "sha256": rej_sha256,
                        "size_bytes": rej_size_bytes,
                    },
                ],
            }

            schema = self._get_manifest_schema()
            try:
                validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
                validator.validate(manifest_payload)
            except jsonschema.ValidationError as exc:
                raise ExtractionIntegrityError(
                    f"발행용 dataset_manifest.json 스키마 검증 실패: {exc.message}",
                    details=[{"error": exc.message, "path": list(exc.path)}],
                ) from exc

            manifest_file = staging_dir / "dataset_manifest.json"
            with open(manifest_file, "wb") as f:
                f.write((json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            # Atomic directory publish via rename
            if target_dir.exists():
                existing = self.validate_existing_dataset(
                    dataset_id,
                    dataset_version,
                    expected_obs_sha256=obs_sha256,
                    expected_prov_sha256=prov_sha256,
                    expected_rej_sha256=rej_sha256,
                )
                if existing is not None:
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return target_dir, existing
                raise ExtractionDatasetConflictError(
                    f"대상 데이터셋 디렉터리({dataset_id}/{dataset_version})가 이미 존재합니다 (덮어쓰기 금지).",
                    details=[{"dataset_id": dataset_id, "dataset_version": dataset_version}],
                )

            try:
                os.rename(str(staging_dir), str(target_dir))
            except (FileExistsError, OSError) as exc:
                # Race condition or Windows atomic replace
                if target_dir.exists():
                    existing = self.validate_existing_dataset(
                        dataset_id,
                        dataset_version,
                        expected_obs_sha256=obs_sha256,
                        expected_prov_sha256=prov_sha256,
                        expected_rej_sha256=rej_sha256,
                    )
                    if existing is not None:
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        return target_dir, existing
                    raise ExtractionDatasetConflictError(
                        f"대상 데이터셋 디렉터리({dataset_id}/{dataset_version})가 이미 존재합니다.",
                        details=[{"dataset_id": dataset_id, "dataset_version": dataset_version}],
                    ) from exc
                else:
                    raise ExtractionPublishFailedError(f"데이터셋 원자적 디렉터리 이동 실패: {exc}") from exc

            return target_dir, manifest_payload

        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
