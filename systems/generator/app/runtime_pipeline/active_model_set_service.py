"""Service for safely managing active-model-set.json pointer with atomic updates and lock protection."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import jsonschema

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    ModelSetArtifactIntegrityError,
    ModelSetArtifactNotFoundError,
    ModelSetArtifactPathUnsupportedError,
    ModelSetAtomicPublishFailedError,
    ModelSetContractInvalidError,
    ModelSetModelNotRegisteredError,
    ModelSetNotConfiguredError,
    ModelSetOptionalModelPolicyNotImplementedError,
    ModelSetUpdateConflictError,
    ModelSetUpdateLockedError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ActiveModelConfig,
    ActiveModelSet,
    now_utc_iso,
)

logger = logging.getLogger(__name__)


def load_official_active_model_set_schema() -> dict[str, Any]:
    """Load the official active model set JSON schema file."""
    schema_path = PROJECT_ROOT / "contracts" / "schemas" / "generator-active-model-set.schema.json"
    if not schema_path.is_file():
        raise ModelSetContractInvalidError(
            f"공식 Active Model Set 스키마 파일이 존재하지 않습니다: {schema_path}",
            details=[{"path": str(schema_path), "reason": "active_model_set_schema_missing"}],
            retryable=False,
        )
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelSetContractInvalidError(
            f"공식 Active Model Set 스키마 파싱 실패: {exc}",
            details=[{"path": str(schema_path), "reason": "active_model_set_schema_parse_failed", "error": str(exc)}],
            retryable=False,
        ) from exc


format_checker = jsonschema.FormatChecker()


@format_checker.checks("date-time")
def _check_datetime_format(val: Any) -> bool:
    if not isinstance(val, str):
        return True
    try:
        sval = val.strip()
        if sval.endswith("Z"):
            sval = sval[:-1] + "+00:00"
        datetime.fromisoformat(sval)
        return True
    except Exception:
        return False


def validate_active_model_set_data(data: Any, schema: dict[str, Any], pointer_file: Optional[Path] = None) -> None:
    """Validate raw JSON data against official Active Model Set JSON schema."""
    try:
        validator = jsonschema.Draft202012Validator(
            schema,
            format_checker=format_checker,
        )
        validator.validate(data)
    except Exception as exc:
        msg = getattr(exc, "message", str(exc))
        raise ModelSetContractInvalidError(
            f"active-model-set.json 공식 Schema 검증 실패: {msg}",
            details=[{"path": str(pointer_file) if pointer_file else "", "reason": "active_model_set_schema_invalid", "error": str(msg)}],
            retryable=False,
        ) from exc


class ActiveModelSetService:
    """Manages active-model-set.json pointer with file locking, validation, and atomic replace."""

    def __init__(
        self,
        models_store_dir: Optional[Path] = None,
        pointer_filename: str = "active-model-set.json",
    ) -> None:
        self.models_store = Path(models_store_dir) if models_store_dir else PATHS.models_store
        self.artifacts_dir = self.models_store / "artifacts"
        self.pointer_file = self.models_store / pointer_filename
        self.lock_file = self.models_store / f"{pointer_filename}.lock"

    def load_active_model_set(self) -> ActiveModelSet:
        """Load and validate active-model-set.json pointer in strict fail-closed order.

        Order:
        1. File existence check -> ModelSetNotConfiguredError
        2. Raw JSON parsing -> ModelSetContractInvalidError (reason: active_model_set_json_parse_failed)
        3. Official Schema load -> ModelSetContractInvalidError (reason: active_model_set_schema_missing / parse_failed)
        4. Official Schema validation -> ModelSetContractInvalidError (reason: active_model_set_schema_invalid)
        5. Pydantic deserialization -> ModelSetContractInvalidError
        6. Models non-empty check -> ModelSetNotConfiguredError
        """
        if not self.pointer_file.exists():
            raise ModelSetNotConfiguredError(
                f"active-model-set.json 포인터 파일이 존재하지 않습니다: {self.pointer_file}",
                details=[{"path": str(self.pointer_file)}],
                retryable=False,
            )

        # Step 2: Raw JSON parsing
        try:
            with open(self.pointer_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise ModelSetContractInvalidError(
                f"active-model-set.json JSON 파싱 실패: {exc}",
                details=[{"path": str(self.pointer_file), "reason": "active_model_set_json_parse_failed", "error": str(exc)}],
                retryable=False,
            ) from exc

        # Step 3: Load official schema
        schema = load_official_active_model_set_schema()

        # Step 4: Official Schema validation
        validate_active_model_set_data(data, schema, pointer_file=self.pointer_file)

        # Step 5: Pydantic deserialization
        try:
            model_set = ActiveModelSet.model_validate(data)
        except Exception as exc:
            raise ModelSetContractInvalidError(
                f"active-model-set.json 파싱 또는 계약 역직렬화 실패: {exc}",
                details=[{"path": str(self.pointer_file), "error": str(exc)}],
                retryable=False,
            ) from exc

        # Step 6: Empty check
        if not model_set.models:
            raise ModelSetNotConfiguredError(
                "active-model-set.json에 정의된 모델 목록이 비어 있습니다.",
                details=[{"path": str(self.pointer_file)}],
                retryable=False,
            )

        return model_set

    def _resolve_model_id(self, base_or_id: str) -> str:
        """Resolve legacy algorithm aliases while preserving explicit artifact IDs."""
        clean = base_or_id.strip()
        if clean in {"lightgbm", "xgboost", "random_forest"}:
            return f"pdm-{clean}"
        return clean

    def update_active_model_set(
        self,
        new_set: ActiveModelSet,
        validate_artifacts: bool = True,
    ) -> ActiveModelSet:
        """Safely update active-model-set.json using file lock, artifact integrity check, and atomic replace."""
        self.models_store.mkdir(parents=True, exist_ok=True)

        # 1. Lock acquisition
        lock_fd = None
        try:
            lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except OSError as exc:
            raise ModelSetUpdateLockedError(
                f"active-model-set.json 잠금 획득 실패 (동시 갱신 경합): {exc}",
                details=[{"lock_path": str(self.lock_file)}],
                retryable=False,
            ) from exc

        try:
            # 2. Contract validation
            if not new_set.models:
                raise ModelSetContractInvalidError(
                    "active-model-set.json에 정의된 모델이 없습니다.",
                    retryable=False,
                )

            for base_or_id, config in new_set.models.items():
                model_id = self._resolve_model_id(base_or_id)
                if (
                    not model_id
                    or ".." in model_id
                    or "/" in model_id
                    or "\\" in model_id
                ):
                    raise ModelSetModelNotRegisteredError(
                        f"Model Set에 안전하지 않은 Model Artifact ID가 포함되어 있습니다: {base_or_id}",
                        details=[{"model": base_or_id}],
                        retryable=False,
                    )

                if not config.required:
                    raise ModelSetOptionalModelPolicyNotImplementedError(
                        f"선택 모델(required=false) 정책은 현재 지원되지 않습니다: {base_or_id}",
                        details=[{"model": base_or_id, "config": config.model_dump(mode="json")}],
                        retryable=False,
                    )

                if validate_artifacts:
                    mver_clean = config.model_version.strip()
                    if any(mver_clean.startswith(s) for s in ("http://", "https://", "s3://", "file://", "ftp://")) or ".." in mver_clean.split("/") or ".." in mver_clean.split("\\"):
                        raise ModelSetArtifactPathUnsupportedError(
                            f"아티팩트 버전 경로는 원격 URI 또는 '..' 상위 경로 이동을 허용하지 않습니다: '{config.model_version}'",
                            details=[{"model_id": base_or_id, "version": config.model_version}],
                        )

                    artifact_dir = self.artifacts_dir / model_id / config.model_version
                    from systems.generator.model.publisher import (
                        ModelArtifactContractValidationError,
                        validate_model_artifact,
                    )
                    try:
                        validate_model_artifact(
                            artifact_dir=artifact_dir,
                            expected_model_id=model_id,
                            expected_model_version=config.model_version,
                            load_model=True,
                            artifacts_root=self.artifacts_dir,
                        )
                    except ModelArtifactContractValidationError as exc:
                        if exc.reason == "artifact_not_found":
                            raise ModelSetArtifactNotFoundError(
                                exc.message,
                                details=exc.details or [{"model_id": model_id, "version": config.model_version}],
                            ) from exc
                        if exc.reason in {"external_uri_unsupported", "path_traversal", "path_outside_root", "invalid_relative_path"}:
                            raise ModelSetArtifactPathUnsupportedError(
                                exc.message,
                                details=exc.details or [{"model_id": model_id, "version": config.model_version}],
                            ) from exc
                        raise ModelSetArtifactIntegrityError(
                            exc.message,
                            details=exc.details or [{"model_id": model_id, "version": config.model_version}],
                        ) from exc

            # 3. Write temp file and atomic replace
            new_set.updated_at = datetime.now(timezone.utc)
            content_bytes = json.dumps(new_set.model_dump(mode="json"), indent=2, sort_keys=True).encode("utf-8")
            temp_file = self.models_store / f".tmp_{uuid.uuid4().hex}_active-model-set.json"

            try:
                with open(temp_file, "wb") as f:
                    f.write(content_bytes)
                    f.flush()
                    os.fsync(f.fileno())
                temp_file.replace(self.pointer_file)
            except Exception as io_exc:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                raise ModelSetAtomicPublishFailedError(
                    f"active-model-set.json 원자적 포인터 교체 실패: {io_exc}",
                    retryable=False,
                ) from io_exc

            logger.info(
                f"[ActiveModelSetService] Successfully updated active-model-set.json to "
                f"set_id='{new_set.model_set_id}', set_ver='{new_set.model_set_version}' with {len(new_set.models)} model(s)"
            )
            return new_set

        finally:
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
            if self.lock_file.exists():
                try:
                    self.lock_file.unlink()
                except Exception:
                    pass
