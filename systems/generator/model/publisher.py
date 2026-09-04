"""Atomic Model Artifact publisher and manifest validator for Generator."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import hashlib
import joblib
import jsonschema

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
class TrainingError(Exception):
    """Base exception for Generator domain training and model publishing operations."""

    status_code: int = 500
    code: str = "TRAINING_ERROR"

    def __init__(self, message: str, details: list[Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class ModelPublishError(TrainingError):
    """Base exception for Model Artifact publishing and activation."""

    code = "MODEL_PUBLISH_ERROR"


class ModelArtifactConflictError(TrainingError):
    status_code = 409
    code = "MODEL_ARTIFACT_CONFLICT"


class ModelArtifactValidationError(TrainingError):
    status_code = 422
    code = "MODEL_ARTIFACT_VALIDATION_ERROR"


class ModelArtifactPublishError(TrainingError):
    status_code = 500
    code = "MODEL_ARTIFACT_PUBLISH_ERROR"


class ModelActivationInProgressError(TrainingError):
    status_code = 409
    code = "MODEL_LATEST_UPDATE_IN_PROGRESS"


class ModelActivationTargetNotFoundError(TrainingError):
    status_code = 404
    code = "MODEL_LATEST_TARGET_NOT_FOUND"


class ModelActivationTargetInvalidError(TrainingError):
    status_code = 422
    code = "MODEL_LATEST_TARGET_INVALID"


class ModelActivationCommitError(TrainingError):
    status_code = 500
    code = "MODEL_LATEST_UPDATE_FAILED"


class ModelActivationVerifyError(TrainingError):
    status_code = 500
    code = "MODEL_LATEST_VERIFY_FAILED"


class TrainingContractError(TrainingError):
    status_code = 422
    code = "TRAINING_CONTRACT_ERROR"


logger = logging.getLogger(__name__)

_artifact_lock = threading.Lock()

ARTIFACT_TYPE = "predictive_maintenance_model"
ARTIFACT_SCHEMA_VERSION = "model-artifact-v1.0"
REQUIRED_ARTIFACT_ROLES = ("model", "feature_schema", "label_schema", "history_requirement", "metrics")
OFFICIAL_SCHEMA_PATH = Path("contracts/schemas/model-artifact.schema.json")


class ModelArtifactContractValidationError(ValueError):
    """Common exception raised when a Model Artifact fails contract or integrity validation."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.details = details or []


@dataclass
class ValidatedModelArtifact:
    """Validated model artifact snapshot metadata and loaded payloads."""

    model_id: str
    model_version: str
    artifact_dir: Path
    manifest: dict[str, Any]
    manifest_checksum: str
    feature_schema: dict[str, Any]
    label_schema: dict[str, Any]
    history_requirement: dict[str, Any]
    metrics: dict[str, Any]
    model: Any | None = None

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        if isinstance(self.manifest, dict) and key in self.manifest:
            return self.manifest[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def validate_model_artifact(
    artifact_dir: Path | str,
    *,
    expected_model_id: str | None = None,
    expected_model_version: str | None = None,
    load_model: bool = True,
    artifacts_root: Path | str | None = None,
    manifest_dict: dict[str, Any] | None = None,
) -> ValidatedModelArtifact:
    """Validate a local Model Artifact package against official contract and integrity rules."""
    path_str = str(artifact_dir).replace("\\", "/")
    version_str = str(expected_model_version).replace("\\", "/") if expected_model_version else ""

    # 1. Path unsupported / security checks
    if any(s.startswith(scheme) for scheme in ("http://", "https://", "s3://", "file://", "ftp://") for s in (path_str, version_str)):
        raise ModelArtifactContractValidationError(
            f"외부 URI 아티팩트 경로는 현재 지원되지 않습니다: '{expected_model_version or artifact_dir}'",
            reason="external_uri_unsupported",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "external_uri_unsupported"}],
        )

    if ".." in path_str.split("/") or ".." in version_str.split("/"):
        raise ModelArtifactContractValidationError(
            f"아티팩트 경로에 상위 이동('..') 문자가 포함되어 있어 지원되지 않습니다: '{expected_model_version or artifact_dir}'",
            reason="path_traversal",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_traversal"}],
        )

    target_dir = Path(artifact_dir)

    if artifacts_root is not None:
        root_dir = Path(artifacts_root).resolve()
        try:
            resolved_target = target_dir.resolve()
            if not resolved_target.is_relative_to(root_dir):
                raise ModelArtifactContractValidationError(
                    f"아티팩트 경로가 지정된 루트 디렉터리를 벗어났습니다: '{target_dir}' (root: '{root_dir}')",
                    reason="path_outside_root",
                    details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_outside_root"}],
                )
        except (ValueError, OSError) as exc:
            raise ModelArtifactContractValidationError(
                f"아티팩트 경로 검증 실패: {exc}",
                reason="path_outside_root",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_resolution_failed"}],
            ) from exc

    manifest_file = target_dir / "manifest.json"
    if manifest_dict is not None:
        manifest_data = manifest_dict
    else:
        if not target_dir.exists() or not target_dir.is_dir():
            raise ModelArtifactContractValidationError(
                f"Model Artifact 디렉터리가 존재하지 않습니다: {target_dir}",
                reason="artifact_not_found",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "artifact_dir_not_found"}],
            )

        if not manifest_file.exists() or not manifest_file.is_file():
            raise ModelArtifactContractValidationError(
                f"아티팩트 manifest.json이 누락되었습니다: {manifest_file}",
                reason="manifest_missing",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "manifest_missing"}],
            )

        try:
            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
        except Exception as exc:
            raise ModelArtifactContractValidationError(
                f"manifest.json 파싱 실패: {exc}",
                reason="manifest_json_parse_failed",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "manifest_json_parse_failed"}],
            ) from exc

    # 2. Official JSON Schema validation
    schema_cand = OFFICIAL_SCHEMA_PATH
    if not schema_cand.is_file():
        schema_cand = Path.cwd() / OFFICIAL_SCHEMA_PATH

    if not schema_cand.is_file():
        raise ModelArtifactContractValidationError(
            f"공식 Model Artifact Schema를 찾을 수 없습니다: {schema_cand}",
            reason="official_schema_missing",
            details=[{"schema_path": str(schema_cand)}],
        )

    try:
        schema_data = json.loads(schema_cand.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelArtifactContractValidationError(
            f"공식 Model Artifact Schema 파싱 실패: {exc}",
            reason="official_schema_parse_failed",
            details=[{"schema_path": str(schema_cand)}],
        ) from exc

    try:
        jsonschema.validate(instance=manifest_data, schema=schema_data)
    except jsonschema.ValidationError as exc:
        raise ModelArtifactContractValidationError(
            f"공식 Model Artifact Manifest 스키마 검증 실패: {exc.message}",
            reason="manifest_schema_invalid",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "error": exc.message}],
        ) from exc

    # 3. Manifest required fields check
    for key in ("model_id", "model_version", "artifact_files"):
        if key not in manifest_data or manifest_data[key] is None or manifest_data[key] == "":
            raise ModelArtifactContractValidationError(
                f"manifest.json에 필수 키 '{key}'가 누락되었습니다.",
                reason=f"manifest_field_missing:{key}",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": f"manifest_field_missing:{key}"}],
            )

    # 4. model_id & model_version match if expected
    actual_model_id = manifest_data.get("model_id")
    actual_model_version = manifest_data.get("model_version")
    if expected_model_id and actual_model_id != expected_model_id:
        raise ModelArtifactContractValidationError(
            f"manifest.json의 model_id 불일치 ({actual_model_id} vs {expected_model_id})",
            reason="model_id_version_mismatch",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "model_id_mismatch"}],
        )
    if expected_model_version and actual_model_version != expected_model_version:
        raise ModelArtifactContractValidationError(
            f"manifest.json의 model_version 불일치 ({actual_model_version} vs {expected_model_version})",
            reason="model_id_version_mismatch",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "model_version_mismatch"}],
        )

    # 5. Schema version check (must exist and be allowed)
    schema_ver = manifest_data.get("artifact_schema_version") or manifest_data.get("schema_version")
    if not schema_ver:
        raise ModelArtifactContractValidationError(
            "manifest.json에 artifact_schema_version / schema_version이 누락되었습니다.",
            reason="schema_version_missing",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "schema_version_missing"}],
        )

    allowed_schema_versions = {"1.0", "1.0.0", "v1", "model-artifact-v1.0"}
    if schema_ver not in allowed_schema_versions:
        raise ModelArtifactContractValidationError(
            f"지원되지 않는 Artifact Schema version 입니다: '{schema_ver}'",
            reason="schema_version_unsupported",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "schema_version_unsupported"}],
        )

    # 6. Check artifact_files array & roles & path resolution bounds
    artifact_files = manifest_data.get("artifact_files", [])
    if not isinstance(artifact_files, list):
        raise ModelArtifactContractValidationError(
            "manifest.json의 artifact_files 필드가 배열 형태가 아닙니다.",
            reason="artifact_files_not_list",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "artifact_files_not_list"}],
        )

    root_resolved = target_dir.resolve()
    seen_roles: set[str] = set()
    seen_paths: set[str] = set()
    for entry in artifact_files:
        if not isinstance(entry, dict):
            raise ModelArtifactContractValidationError(
                "artifact_files 항목은 객체여야 합니다.",
                reason="artifact_file_not_dict",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "artifact_file_not_dict"}],
            )
        role = entry.get("role")
        rel_path = entry.get("path")
        expected_sha = entry.get("sha256")
        if not role or not rel_path or not expected_sha:
            raise ModelArtifactContractValidationError(
                f"Role 항목 필수 필드 누락: {entry}",
                reason="role_entry_field_missing",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "role_entry_field_missing"}],
            )

        norm_role = "model" if role == "model_artifact" else role
        if norm_role in seen_roles:
            raise ModelArtifactContractValidationError(
                f"manifest artifact_files에 role 중복 발견: '{role}'",
                reason="role_duplicated",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "role_duplicated"}],
            )
        if rel_path in seen_paths:
            raise ModelArtifactContractValidationError(
                f"manifest artifact_files에 path 중복 발견: '{rel_path}'",
                reason="path_duplicated",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_duplicated"}],
            )
        if ".." in rel_path or Path(rel_path).is_absolute():
            raise ModelArtifactContractValidationError(
                f"Role '{role}'의 path에 비정상 경로가 포함되어 있습니다: '{rel_path}'",
                reason="invalid_relative_path",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "invalid_relative_path"}],
            )

        target_file = target_dir / rel_path
        try:
            target_file_resolved = target_file.resolve()
            if not target_file_resolved.is_relative_to(root_resolved):
                raise ModelArtifactContractValidationError(
                    f"선언된 아티팩트 파일 경로가 디렉터리 루트를 벗어났습니다: '{rel_path}'",
                    reason="path_outside_root",
                    details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_outside_root"}],
                )
        except (ValueError, OSError) as exc:
            raise ModelArtifactContractValidationError(
                f"선언된 아티팩트 파일 경로 검증 실패 ('{rel_path}'): {exc}",
                reason="path_outside_root",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "path_resolution_failed"}],
            ) from exc

        if not target_file.exists() or not target_file.is_file():
            raise ModelArtifactContractValidationError(
                f"선언된 아티팩트 파일이 존재하지 않습니다: {target_file}",
                reason="declared_file_missing",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "declared_file_missing"}],
            )

        actual_sha = compute_file_sha256(target_file)
        if actual_sha != expected_sha:
            raise ModelArtifactContractValidationError(
                f"아티팩트 파일 체크섬 불일치 ({rel_path}): 기대값={expected_sha}, 실제={actual_sha}",
                reason="checksum_mismatch",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "checksum_mismatch"}],
            )

        seen_roles.add(norm_role)
        seen_paths.add(rel_path)

    required_roles = {"model", "feature_schema", "label_schema", "history_requirement", "metrics"}
    missing_roles = required_roles - seen_roles
    if missing_roles:
        raise ModelArtifactContractValidationError(
            f"manifest artifact_files에 필수 role이 누락되었습니다: {missing_roles}",
            reason="required_role_missing",
            details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "required_role_missing"}],
        )

    # 7. Verify 4 JSON files parse successfully
    req_json_files = ["feature_schema.json", "label_schema.json", "history_requirement.json", "metrics.json"]
    parsed_jsons: dict[str, dict[str, Any]] = {}
    for jf in req_json_files:
        jpath = target_dir / jf
        if not jpath.is_file():
            raise ModelArtifactContractValidationError(
                f"필수 페이로드 파일 누락 ({jf}): {jpath}",
                reason=f"payload_file_missing:{jf}",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": f"payload_file_missing:{jf}"}],
            )
        try:
            with open(jpath, "r", encoding="utf-8") as f:
                parsed_jsons[jf] = json.load(f)
        except Exception as exc:
            raise ModelArtifactContractValidationError(
                f"페이로드 JSON 파일 파싱 실패 ({jf}): {exc}",
                reason=f"json_parse_failed:{jf}",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": f"json_parse_failed:{jf}"}],
            ) from exc

    # 8. Verify model.joblib loads successfully if load_model=True
    loaded_model_obj: Any | None = None
    if load_model:
        model_file = target_dir / "model.joblib"
        if not model_file.is_file():
            raise ModelArtifactContractValidationError(
                f"필수 모델 파일 누락 (model.joblib): {model_file}",
                reason="model_file_missing",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "model_file_missing"}],
            )
        try:
            loaded_model_obj = joblib.load(model_file)
        except Exception as exc:
            raise ModelArtifactContractValidationError(
                f"모델 파일 joblib.load() 로드 실패: {exc}",
                reason="joblib_load_failed",
                details=[{"model_id": expected_model_id, "version": expected_model_version, "reason": "joblib_load_failed"}],
            ) from exc

    if manifest_file.is_file():
        manifest_checksum = compute_file_sha256(manifest_file)
    else:
        manifest_bytes = json.dumps(manifest_data, sort_keys=True).encode("utf-8")
        manifest_checksum = hashlib.sha256(manifest_bytes).hexdigest()
    return ValidatedModelArtifact(
        model_id=actual_model_id,
        model_version=actual_model_version,
        artifact_dir=target_dir,
        manifest=manifest_data,
        manifest_checksum=manifest_checksum,
        feature_schema=parsed_jsons["feature_schema.json"],
        label_schema=parsed_jsons["label_schema.json"],
        history_requirement=parsed_jsons["history_requirement.json"],
        metrics=parsed_jsons["metrics.json"],
        model=loaded_model_obj,
    )


@dataclass(frozen=True)
class ModelArtifactPublicationResult:
    """Explicit result of publishing an immutable Model Artifact and updating its latest pointer."""

    model_id: str
    model_version: str
    published: bool
    artifact_uri: str | None
    latest_updated: bool
    latest_error_code: str | None = None
    latest_error_message: str | None = None


import errno

class ModelActivationLock:
    """Non-blocking OS-level advisory file lock for model latest pointer updates."""

    def __init__(self, lock_file_path: Path, model_id: str, requested_version: str | None = None) -> None:
        self.lock_file_path = lock_file_path
        self.model_id = model_id
        self.requested_version = requested_version
        self._file_obj = None

    def __enter__(self) -> "ModelActivationLock":
        try:
            self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_obj = open(self.lock_file_path, "a+", encoding="utf-8")
        except OSError as exc:
            logger.warning(f"[ModelActivationLock] Lock file open/prepare failed: {exc}")
            raise ModelActivationCommitError(
                f"최신 포인터 잠금 파일 준비 실패: {exc}",
                details=[{
                    "stage": "latest_pointer_lock_open",
                    "model_id": self.model_id,
                    "requested_version": self.requested_version,
                }],
            ) from exc

        locked = False
        try:
            if sys.platform != "win32":
                import fcntl
                fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            else:
                import msvcrt
                self._file_obj.seek(0)
                msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
        except (BlockingIOError, OSError) as exc:
            if self._file_obj:
                try:
                    self._file_obj.close()
                except Exception:
                    pass
                self._file_obj = None

            # Check if this is a genuine lock contention
            is_contention = False
            if sys.platform != "win32":
                if isinstance(exc, BlockingIOError) or exc.errno in (errno.EACCES, errno.EAGAIN, getattr(errno, "EWOULDBLOCK", errno.EAGAIN)):
                    is_contention = True
            else:
                # On Windows, lock violation raises PermissionError (EACCES) or EDEADLK or winerror 32/33
                if exc.errno in (errno.EACCES, getattr(errno, "EDEADLK", 36)) or getattr(exc, "winerror", None) in (32, 33):
                    is_contention = True

            if is_contention:
                raise ModelActivationInProgressError(
                    "해당 모델의 최신 포인터 갱신 작업이 이미 진행 중입니다.",
                    details=[{"model_id": self.model_id, "requested_version": self.requested_version}],
                ) from exc

            # Otherwise, it's a general I/O or descriptor failure
            logger.warning(f"[ModelActivationLock] Lock acquisition failed with I/O error: {exc}")
            raise ModelActivationCommitError(
                f"최신 포인터 잠금 획득 중 I/O 실패: {exc}",
                details=[{
                    "stage": "latest_pointer_lock_acquire",
                    "model_id": self.model_id,
                    "requested_version": self.requested_version,
                }],
            ) from exc

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._file_obj:
            try:
                if sys.platform != "win32":
                    import fcntl
                    fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_UN)
                else:
                    import msvcrt
                    self._file_obj.seek(0)
                    msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            try:
                self._file_obj.close()
            except Exception:
                pass
            self._file_obj = None


def build_history_requirement_from_feature_schema(feature_schema: dict[str, Any]) -> dict[str, Any]:
    """Deterministically derive history requirements from verified Feature Schema recipe."""
    feature_schema_ver = feature_schema.get("feature_schema_version") or feature_schema.get("schema_version", "unknown")
    engineering = feature_schema.get("feature_engineering") or {}
    if engineering.get("kind") == "cnc-temporal-v1":
        runtime_context = engineering.get("runtime_context") or {}
        prior_rows = int(runtime_context.get("recent_history_rows_required", 35))
        required_columns = list(engineering.get("base_sensors") or [])
        return {
            "history_requirement_version": f"hist-req-{feature_schema_ver}",
            "feature_executor_version": "cnc-temporal-v1",
            "minimum_history_rows": prior_rows + 1,
            "prior_observations_required": prior_rows,
            "current_observation_required": True,
            "required_columns": required_columns,
            "missing_history_policy": "fail_closed",
            "expected_cadence_minutes": float(engineering.get("expected_cadence_minutes", 10.0)),
            "ordering": runtime_context.get(
                "history_order", "strictly_ascending_before_current_observation"
            ),
            "new_asset_policy": runtime_context.get(
                "new_asset_policy", "calibrate_baseline_before_inference"
            ),
        }
    features_list = feature_schema.get("features", [])

    raw_fields: list[str] = []
    max_lag = 0
    max_rolling = 0
    max_ewm = 0
    rolling_min_periods = 0

    for feat in features_list:
        if isinstance(feat, dict):
            src = feat.get("source_field")
            if src and isinstance(src, str) and src not in raw_fields:
                raw_fields.append(src)
            op = feat.get("operation", "raw")
            params = feat.get("parameters", {}) or {}
            if op in ("lag", "diff"):
                p = int(params.get("periods", 1))
                if p > max_lag:
                    max_lag = p
            elif "rolling" in op:
                w = int(params.get("window", 1))
                mp = int(params.get("min_periods", w))
                if w > max_rolling:
                    max_rolling = w
                if mp > rolling_min_periods:
                    rolling_min_periods = mp
            elif "ewm" in op:
                s = int(params.get("span", 1))
                if s > max_ewm:
                    max_ewm = s

    min_history = max(1, max_lag + 1 if max_lag > 0 else 1, max_rolling, max_ewm)

    return {
        "history_requirement_version": f"hist-req-{feature_schema_ver}",
        "feature_executor_version": "feature-engine-v1",
        "minimum_history_rows": min_history,
        "required_columns": raw_fields,
        "missing_history_policy": "zero_pad",
        "max_lag_periods": max_lag,
        "max_rolling_window": max_rolling,
        "rolling_min_periods": rolling_min_periods,
    }


class ModelArtifactPublisher:
    """Publishes immutable 6-file Model Artifact packages and manages active version pointers."""

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            models_store = getattr(PATHS, "models_store", Path("models_store"))
            self.base_dir = Path(models_store) / "artifacts"
        else:
            self.base_dir = Path(base_dir)
        self._schema_cache: dict[str, Any] | None = None

    def _get_official_schema(self) -> dict[str, Any]:
        """Load official Model Artifact JSON Schema."""
        if self._schema_cache is None:
            cand = OFFICIAL_SCHEMA_PATH
            if not cand.exists():
                cand = Path.cwd() / OFFICIAL_SCHEMA_PATH
            if not cand.exists():
                raise TrainingContractError(f"Model Artifact 스키마를 찾을 수 없습니다: {OFFICIAL_SCHEMA_PATH}")
            try:
                self._schema_cache = json.loads(cand.read_text(encoding="utf-8"))
            except Exception as exc:
                raise TrainingContractError(f"Model Artifact 스키마 파싱 실패: {exc}") from exc
        return self._schema_cache

    def get_artifact_dir(self, model_id: str, model_version: str) -> Path:
        clean_id = model_id.strip()
        clean_ver = model_version.strip()
        if ".." in clean_id or "/" in clean_id or "\\" in clean_id:
            raise TrainingContractError(f"model_id에 경로 탈출 문자가 포함되어 있습니다: {model_id}")
        if ".." in clean_ver or "/" in clean_ver or "\\" in clean_ver:
            raise TrainingContractError(f"model_version에 경로 탈출 문자가 포함되어 있습니다: {model_version}")
        return self.base_dir / clean_id / clean_ver

    def get_logical_uri(self, path: Path) -> str:
        try:
            rel = path.relative_to(Path.cwd())
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def validate_manifest(self, manifest: dict[str, Any], artifact_dir: Path) -> None:
        """Strictly validate manifest structure, payload roles, relative paths, and checksums using common validator."""
        model_id = manifest.get("model_id") if isinstance(manifest, dict) else None
        model_version = manifest.get("model_version") if isinstance(manifest, dict) else None
        try:
            validate_model_artifact(
                artifact_dir=artifact_dir,
                expected_model_id=model_id,
                expected_model_version=model_version,
                load_model=False,
                artifacts_root=None,
                manifest_dict=manifest,
            )
        except ModelArtifactContractValidationError as exc:
            raise ModelArtifactValidationError(exc.message) from exc

    def publish_artifact(
        self,
        *,
        model_id: str,
        model_version: str,
        base_model: str,
        model_obj: Any,
        dataset_id: str,
        dataset_version: str,
        feature_dataset_version: str,
        feature_schema: dict[str, Any],
        label_schema: dict[str, Any],
        history_requirement: dict[str, Any],
        metrics: dict[str, Any],
        training_config: dict[str, Any],
        provenance: dict[str, Any],
        activation_policy: str | None = None,
    ) -> ModelArtifactPublicationResult:
        """Atomically stage, validate, and publish an immutable Model Artifact package, then update latest pointer."""
        with _artifact_lock:
            dest_dir = self.get_artifact_dir(model_id, model_version)
            model_root = dest_dir.parent
            model_root.mkdir(parents=True, exist_ok=True)

            feature_schema_ver = feature_schema.get("feature_schema_version") or feature_schema.get("schema_version", "unknown-feature-schema")
            label_schema_ver = label_schema.get("label_schema_version") or label_schema.get("schema_version", "unknown-label-schema")
            training_cfg_ver = training_config.get("training_config_version", "training-config-v1")

            # Check if artifact directory already exists
            if dest_dir.exists():
                manifest_file = dest_dir / "manifest.json"
                if not manifest_file.is_file():
                    raise ModelArtifactConflictError(
                        f"Model Artifact '{model_id}/{model_version}' 디렉터리가 불완전한 상태로 이미 존재합니다."
                    )
                try:
                    existing_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    self.validate_manifest(existing_manifest, dest_dir)
                except Exception as exc:
                    raise ModelArtifactConflictError(
                        f"Model Artifact '{model_id}/{model_version}'가 이미 존재하며 유효성 검증에 실패했습니다: {exc}"
                    ) from exc

                # Check input fingerprint match for idempotent pointer recovery
                em = existing_manifest
                em_cfg = em.get("training_config", {})
                em_prov = em.get("provenance", {})

                inputs_match = (
                    em.get("dataset_version") == dataset_version
                    and em.get("feature_schema_version") == feature_schema_ver
                    and em.get("label_schema_version") == label_schema_ver
                    and em_cfg.get("training_config_version") == training_cfg_ver
                    and em_cfg.get("training_config_sha256") == training_config.get("training_config_sha256")
                    and em_prov.get("feature_dataset_metadata_sha256") == provenance.get("feature_dataset_metadata_sha256")
                    and em_prov.get("prediction_horizon_hours") == provenance.get("prediction_horizon_hours")
                )

                if not inputs_match:
                    raise ModelArtifactConflictError(
                        f"Model Artifact '{model_id}/{model_version}'가 이미 다른 입력으로 존재합니다. "
                        "불변 아티팩트 정책에 따라 동일 버전 재발행 및 덮어쓰기는 금지됩니다."
                    )

                # Check if already pointing in latest.json
                final_pointer = model_root / "latest.json"
                already_latest = False
                if final_pointer.is_file():
                    try:
                        ptr_data = json.loads(final_pointer.read_text(encoding="utf-8"))
                        if ptr_data.get("model_version") == model_version or ptr_data.get("active_version") == model_version:
                            already_latest = True
                    except Exception:
                        pass

                if already_latest:
                    raise ModelArtifactConflictError(
                        f"Model Artifact '{model_id}/{model_version}'가 이미 정상 발행되어 최신 포인터로 활성화되어 있습니다. "
                        "불변 아티팩트 정책에 따라 동일 버전 재발행 및 덮어쓰기는 금지됩니다."
                    )

                # Inputs match and not yet in latest.json -> Retry pointer update!
                try:
                    self.update_active_pointer(model_id, model_version)
                    return ModelArtifactPublicationResult(
                        model_id=model_id,
                        model_version=model_version,
                        published=True,
                        artifact_uri=self.get_logical_uri(dest_dir),
                        latest_updated=True,
                    )
                except Exception as p_exc:
                    err_code = getattr(p_exc, "code", type(p_exc).__name__)
                    return ModelArtifactPublicationResult(
                        model_id=model_id,
                        model_version=model_version,
                        published=True,
                        artifact_uri=self.get_logical_uri(dest_dir),
                        latest_updated=False,
                        latest_error_code=err_code,
                        latest_error_message=str(p_exc),
                    )

            # Phase A: Staging and immutable Artifact publish
            current_stage = "artifact_staging_create"
            staging_dir = model_root / f".tmp_{uuid.uuid4().hex}"
            staging_dir.mkdir(parents=True, exist_ok=True)

            try:
                # 1. Write model.joblib
                current_stage = "artifact_model_write"
                model_file = staging_dir / "model.joblib"
                joblib.dump(model_obj, model_file, compress=3)

                # 2. Write feature_schema.json (full snapshot)
                current_stage = "artifact_schema_write"
                feat_schema_file = staging_dir / "feature_schema.json"
                with open(feat_schema_file, "w", encoding="utf-8") as f:
                    json.dump(feature_schema, f, indent=2, ensure_ascii=False)

                # 3. Write label_schema.json (full snapshot)
                label_schema_file = staging_dir / "label_schema.json"
                with open(label_schema_file, "w", encoding="utf-8") as f:
                    json.dump(label_schema, f, indent=2, ensure_ascii=False)

                # 4. Write history_requirement.json
                hist_req_file = staging_dir / "history_requirement.json"
                with open(hist_req_file, "w", encoding="utf-8") as f:
                    json.dump(history_requirement, f, indent=2, ensure_ascii=False)

                # 5. Write metrics.json
                metrics_file = staging_dir / "metrics.json"
                with open(metrics_file, "w", encoding="utf-8") as f:
                    json.dump(metrics, f, indent=2, ensure_ascii=False)

                # 6. Calculate checksums for the 5 payload files
                current_stage = "artifact_checksum_calc"
                checksum_dict = {
                    "model.joblib": compute_file_sha256(model_file),
                    "feature_schema.json": compute_file_sha256(feat_schema_file),
                    "label_schema.json": compute_file_sha256(label_schema_file),
                    "history_requirement.json": compute_file_sha256(hist_req_file),
                    "metrics.json": compute_file_sha256(metrics_file),
                }

                artifact_files_list = [
                    {
                        "role": "model",
                        "path": "model.joblib",
                        "sha256": checksum_dict["model.joblib"],
                    },
                    {
                        "role": "feature_schema",
                        "path": "feature_schema.json",
                        "sha256": checksum_dict["feature_schema.json"],
                    },
                    {
                        "role": "label_schema",
                        "path": "label_schema.json",
                        "sha256": checksum_dict["label_schema.json"],
                    },
                    {
                        "role": "history_requirement",
                        "path": "history_requirement.json",
                        "sha256": checksum_dict["history_requirement.json"],
                    },
                    {
                        "role": "metrics",
                        "path": "metrics.json",
                        "sha256": checksum_dict["metrics.json"],
                    },
                ]

                # 7. Construct and write manifest.json conforming to model-artifact.schema.json
                hist_req_ver = history_requirement.get("history_requirement_version", f"hist-req-{feature_schema_ver}")

                manifest = {
                    "artifact_type": ARTIFACT_TYPE,
                    "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                    "model_id": model_id,
                    "model_version": model_version,
                    "dataset_version": dataset_version,
                    "feature_schema_version": feature_schema_ver,
                    "label_schema_version": label_schema_ver,
                    "history_requirement_version": hist_req_ver,
                    "metrics_schema_version": "pdm-metrics-v1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "training_config": training_config,
                    "metrics": metrics,
                    "checksum": {
                        "algorithm": "sha256",
                        "files": checksum_dict,
                    },
                    "provenance": provenance,
                    "compatibility": {"runtime": "app.diagnosis"},
                    "artifact_files": artifact_files_list,
                }

                manifest_file = staging_dir / "manifest.json"
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)

                # 8. Full validation of staging directory
                current_stage = "artifact_validation"
                self.validate_manifest(manifest, staging_dir)

                # 9. Atomic rename / move staging -> dest_dir (Phase A completed!)
                current_stage = "artifact_commit"
                try:
                    staging_dir.rename(dest_dir)
                except FileExistsError as exc:
                    raise ModelArtifactConflictError(
                        f"Model Artifact '{model_id}/{model_version}'가 동시에 발행되었거나 이미 존재합니다."
                    ) from exc

                logger.info(f"[ModelArtifactPublisher] Published Model Artifact to {dest_dir}")

            except Exception as exc:
                cleanup_error = None
                if staging_dir.exists():
                    try:
                        shutil.rmtree(staging_dir, ignore_errors=False)
                    except Exception as c_exc:
                        cleanup_error = c_exc
                        logger.warning(f"[ModelArtifactPublisher] Failed to cleanup staging directory {staging_dir}: {c_exc}")

                if isinstance(exc, (ModelArtifactConflictError, ModelArtifactValidationError, TrainingContractError)):
                    raise

                logger.exception(f"[ModelArtifactPublisher] Failed to publish model artifact during {current_stage}: {exc}")
                raise ModelArtifactPublishError(
                    f"Model Artifact 원자적 발행 실패: {exc}",
                    details=[{
                        "stage": current_stage,
                        "model_id": model_id,
                        "model_version": model_version,
                        "published": False,
                        "cleanup_failed": cleanup_error is not None,
                    }],
                ) from exc

            # Phase B: Latest pointer update
            try:
                self.update_active_pointer(model_id, model_version)
                return ModelArtifactPublicationResult(
                    model_id=model_id,
                    model_version=model_version,
                    published=True,
                    artifact_uri=self.get_logical_uri(dest_dir),
                    latest_updated=True,
                )
            except Exception as p_exc:
                err_code = getattr(p_exc, "code", type(p_exc).__name__)
                logger.warning(
                    f"[ModelArtifactPublisher] Artifact published at {dest_dir} but latest pointer update failed: {p_exc}"
                )
                return ModelArtifactPublicationResult(
                    model_id=model_id,
                    model_version=model_version,
                    published=True,
                    artifact_uri=self.get_logical_uri(dest_dir),
                    latest_updated=False,
                    latest_error_code=err_code,
                    latest_error_message=str(p_exc),
                )

    def update_active_pointer(self, model_id: str, model_version: str) -> None:
        """Atomically update latest.json system-managed pointer for model_id with OS locking and validation."""
        model_root = self.base_dir / model_id
        model_root.mkdir(parents=True, exist_ok=True)
        lock_file = model_root / ".latest.lock"

        with ModelActivationLock(lock_file, model_id=model_id, requested_version=model_version):
            # 2. Check target artifact dir and manifest exist
            target_dir = self.get_artifact_dir(model_id, model_version)
            manifest_file = target_dir / "manifest.json"
            if not target_dir.is_dir() or not manifest_file.is_file():
                raise ModelActivationTargetNotFoundError(
                    f"최신 포인터 갱신 대상 모델 아티팩트가 존재하지 않습니다: {model_id}/{model_version}"
                )

            # 3. Checksum verification of target artifact files
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                self.validate_manifest(manifest_data, target_dir)
            except Exception as exc:
                if isinstance(exc, ModelArtifactValidationError):
                    raise ModelActivationTargetInvalidError(
                        f"최신 포인터 갱신 대상 모델 아티팩트 검증 실패: {exc.message}"
                    ) from exc
                raise ModelActivationTargetInvalidError(
                    f"최신 포인터 갱신 대상 모델 아티팩트 매니페스트 파싱 실패: {exc}"
                ) from exc

            # 4. Read existing latest.json for idempotency
            final_pointer = model_root / "latest.json"
            if final_pointer.is_file():
                try:
                    existing_pointer = json.loads(final_pointer.read_text(encoding="utf-8"))
                    if existing_pointer.get("model_version") == model_version or existing_pointer.get("active_version") == model_version:
                        logger.info(f"[ModelArtifactPublisher] latest.json is already pointing to {model_version} (idempotent success)")
                        return
                except Exception:
                    pass

            # 5-8. Atomic write to temp file, flush, fsync, os.replace
            tx_id = uuid.uuid4().hex
            temp_pointer = model_root / f".latest.{tx_id}.tmp"
            logical_uri = f"models_store/artifacts/{model_id}/{model_version}"
            now_iso = datetime.now(timezone.utc).isoformat()
            pointer_data = {
                "model_id": model_id,
                "model_version": model_version,
                "active_version": model_version,
                "artifact_uri": logical_uri,
                "updated_at": now_iso,
                "activated_at": now_iso,
                "manifest_path": f"{model_version}/manifest.json",
                "model_path": f"{model_version}/model.joblib",
            }

            try:
                with open(temp_pointer, "w", encoding="utf-8") as f:
                    json.dump(pointer_data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(temp_pointer, final_pointer)

                if sys.platform != "win32":
                    dir_fd = None
                    try:
                        dir_fd = os.open(str(model_root), os.O_RDONLY)
                        os.fsync(dir_fd)
                    except Exception:
                        pass
                    finally:
                        if dir_fd is not None:
                            try:
                                os.close(dir_fd)
                            except Exception:
                                pass
            except Exception as exc:
                cleanup_error = None
                if temp_pointer.exists():
                    try:
                        temp_pointer.unlink(missing_ok=True)
                    except Exception as c_exc:
                        cleanup_error = c_exc
                        logger.warning(f"[ModelArtifactPublisher] Failed to cleanup temp pointer {temp_pointer}: {c_exc}")

                if isinstance(exc, (ModelActivationCommitError, ModelActivationInProgressError, ModelActivationTargetNotFoundError, ModelActivationTargetInvalidError, ModelActivationVerifyError)):
                    raise

                raise ModelActivationCommitError(
                    f"latest.json 원자적 교체 실패: {exc}",
                    details=[{
                        "stage": "latest_pointer_commit",
                        "model_id": model_id,
                        "model_version": model_version,
                        "cleanup_failed": cleanup_error is not None,
                    }],
                ) from exc

            # 9-10. Read-back verification
            try:
                readback_data = json.loads(final_pointer.read_text(encoding="utf-8"))
                rb_ver = readback_data.get("model_version") or readback_data.get("active_version")
                if rb_ver != model_version or readback_data.get("model_id") != model_id:
                    raise ModelActivationVerifyError(
                        f"latest.json read-back 불일치: 기대값={model_version}, 실제={rb_ver}"
                    )
            except Exception as exc:
                if isinstance(exc, ModelActivationVerifyError):
                    raise
                raise ModelActivationVerifyError(f"latest.json read-back 검증 실패: {exc}") from exc

            logger.info(f"[ModelArtifactPublisher] Updated latest pointer for {model_id} -> {model_version}")
    update_latest_pointer = update_active_pointer
