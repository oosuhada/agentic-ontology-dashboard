"""Repository for immutable versioned Preprocessing Plan storage and latest pointer management."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import pandas as pd

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.preprocessing.preprocessing_exception import (
    DatasetNotFoundError,
    DatasetContractError,
    PreprocessingPlanPublishError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedPreprocessingPlan:
    preprocessing_plan_id: str
    preprocessing_plan_version: str
    preprocessing_plan_uri: str
    sha256: str


def canonicalize_dtype(dtype: Any) -> str:
    """Map pandas/numpy dtype to stable canonical dtype family string."""
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    elif pd.api.types.is_integer_dtype(dtype):
        return "integer"
    elif pd.api.types.is_float_dtype(dtype):
        return "float"
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    elif pd.api.types.is_timedelta64_dtype(dtype):
        return "timedelta"
    elif isinstance(dtype, pd.CategoricalDtype) or (hasattr(dtype, "name") and dtype.name == "category"):
        return "category"
    elif pd.api.types.is_string_dtype(dtype):
        return "string"
    else:
        return "object"


def compute_source_schema_fingerprint(df: pd.DataFrame) -> str:
    """Compute deterministic 64-character SHA-256 fingerprint for dataframe column names, order, and canonical dtypes."""
    import hashlib
    canonical_schema = [
        {
            "index": index,
            "name": str(column),
            "dtype": canonicalize_dtype(df[column].dtype),
        }
        for index, column in enumerate(df.columns)
    ]
    canonical_json = json.dumps(
        canonical_schema,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_preprocessing_plan_version(
    dataset_id: str,
    dataset_version: str,
    plan_data: dict[str, Any],
) -> str:
    """Compute deterministic 16-character SHA-256 version for preprocessing plan."""
    import hashlib
    canonical = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "source_dataset_sha256": plan_data.get("source_dataset_sha256"),
        "source_schema_fingerprint": plan_data.get("source_schema_fingerprint"),
        "decision_source": plan_data.get("decision_source"),
        "fallback_reason": plan_data.get("fallback_reason"),
        "planner_version": plan_data.get("planner_version"),
        "structure_type": plan_data.get("structure_type"),
        "selected_columns": plan_data.get("selected_columns"),
        "id_column": plan_data.get("id_column"),
        "time_column": plan_data.get("time_column"),
        "attribute_column": plan_data.get("attribute_column"),
        "value_column": plan_data.get("value_column"),
        "duplicate_policy": plan_data.get("duplicate_policy"),
        "aggregation": plan_data.get("aggregation"),
    }
    canonical_json = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
    return f"preprocessing-plan-{h}"


class PreprocessingRepository:
    """Manages immutable versioned storage of Preprocessing Plans and dataset latest pointers."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = (base_dir or (PATHS.models_store / "cache" / "preprocessing_plans")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_path_segment(self, segment: str, name: str) -> str:
        s = str(segment).strip()
        if not s or ".." in s or "/" in s or "\\" in s:
            raise DatasetContractError(f"{name}에 유효하지 않은 경로 문자열(..) 또는 구분자가 포함되어 있습니다: '{segment}'")
        return s

    def get_dataset_plan_dir(self, dataset_id: str, dataset_version: str) -> Path:
        safe_id = self._sanitize_path_segment(dataset_id, "dataset_id")
        safe_ver = self._sanitize_path_segment(dataset_version, "dataset_version")
        target_dir = (self.base_dir / safe_id / safe_ver).resolve()
        if not target_dir.is_relative_to(self.base_dir):
            raise DatasetContractError(f"허용된 Preprocessing Plan 루트를 벗어난 경로입니다: {target_dir}")
        return target_dir

    def get_latest_pointer_path(self, dataset_id: str, dataset_version: str) -> Path:
        return self.get_dataset_plan_dir(dataset_id, dataset_version) / "latest.json"

    def get_logical_uri(self, target_path: Path | str) -> str:
        """Convert a path inside allowed roots to a canonical logical relative URI.

        Raises DatasetContractError (Fail-Closed) if target_path is outside all allowed roots.
        """
        p = Path(target_path) if isinstance(target_path, str) else target_path
        resolved = p.resolve()

        # 1. PATHS.data_dir (most specific for raw and preprocessed datasets)
        try:
            data_dir = getattr(PATHS, "data_dir", Path("data")).resolve()
            if resolved == data_dir:
                return "data"
            if data_dir in resolved.parents:
                return f"data/{resolved.relative_to(data_dir).as_posix()}"
        except Exception:
            pass

        # 2. PATHS.models_store (for plans and model artifacts)
        try:
            models_store = getattr(PATHS, "models_store", Path("models_store")).resolve()
            if resolved == models_store:
                return "models_store"
            if models_store in resolved.parents:
                return f"models_store/{resolved.relative_to(models_store).as_posix()}"
        except Exception:
            pass

        # 3. self.base_dir (if repository was initialized with custom base_dir)
        try:
            if hasattr(self, "base_dir") and self.base_dir:
                base_dir = self.base_dir.resolve()
                if resolved == base_dir:
                    return "models_store/cache/preprocessing_plans"
                if base_dir in resolved.parents:
                    rel = resolved.relative_to(base_dir).as_posix()
                    return f"models_store/cache/preprocessing_plans/{rel}"
        except Exception:
            pass

        # 4. Project workspace / repo root
        try:
            cwd = Path.cwd().resolve()
            if resolved == cwd:
                return "."
            if cwd in resolved.parents:
                rel = resolved.relative_to(cwd).as_posix()
                if not rel.startswith(".."):
                    return rel
        except Exception:
            pass

        # 5. Fail-closed: outside all allowed roots
        raise DatasetContractError(
            f"논리 URI로 변환할 수 없는 허용 범위 밖의 경로입니다: '{p.name}'"
        )

    def _validate_plan_content(
        self,
        plan_data: dict[str, Any],
        dataset_id: str,
        dataset_version: str,
        expected_plan_id: Optional[str] = None,
    ) -> None:
        """Strict validation of plan structure, provenance fields, duplicate policies, and content hashes."""
        if not isinstance(plan_data, dict):
            raise DatasetContractError(f"Preprocessing Plan 형식이 올바르지 않습니다 (dict 기대, {type(plan_data).__name__} 수신)")

        # 1. Required identity and provenance fields
        required_fields = [
            "preprocessing_plan_id",
            "preprocessing_plan_version",
            "dataset_id",
            "dataset_version",
            "source_dataset_uri",
            "source_dataset_sha256",
            "source_schema_fingerprint",
            "decision_source",
            "planner_version",
            "structure_type",
            "selected_columns",
            "duplicate_policy",
        ]
        for rf in required_fields:
            if rf not in plan_data or plan_data[rf] is None or (isinstance(plan_data[rf], str) and not plan_data[rf].strip()):
                raise DatasetContractError(f"Preprocessing Plan에 필수 필드 '{rf}'가 누락되었거나 비어 있습니다.")

        # 2. Validate source_dataset_sha256 and source_schema_fingerprint format (64-char hex)
        src_sha = plan_data.get("source_dataset_sha256", "")
        if not isinstance(src_sha, str) or len(src_sha) != 64 or not all(c in "0123456789abcdefABCDEF" for c in src_sha):
            raise DatasetContractError(f"Plan 내부 source_dataset_sha256 형식이 올바르지 않습니다 (64자리 hex 기대): '{src_sha}'")

        schema_fp = plan_data.get("source_schema_fingerprint", "")
        if not isinstance(schema_fp, str) or len(schema_fp) != 64 or not all(c in "0123456789abcdefABCDEF" for c in schema_fp):
            raise DatasetContractError(f"Plan 내부 source_schema_fingerprint 형식이 올바르지 않습니다 (64자리 hex 기대): '{schema_fp}'")

        # 3. Validate Planner decision provenance
        decision_src = plan_data.get("decision_source")
        if decision_src not in ("llm", "rule_fallback"):
            raise DatasetContractError(f"Plan 내부 decision_source는 'llm' 또는 'rule_fallback'이어야 합니다: '{decision_src}'")

        fallback_reason = plan_data.get("fallback_reason")
        if decision_src == "llm":
            if fallback_reason is not None:
                raise DatasetContractError(f"decision_source='llm'일 때는 fallback_reason이 null이어야 합니다: '{fallback_reason}'")
        elif decision_src == "rule_fallback":
            if not fallback_reason or not str(fallback_reason).strip():
                raise DatasetContractError("decision_source='rule_fallback'일 때는 유효한 fallback_reason이 필수입니다.")

        # 4. Validate source_dataset_uri format (relative logical path only, no absolute or ..)
        src_uri = plan_data.get("source_dataset_uri", "")
        uri_path = Path(src_uri)
        if uri_path.is_absolute() or ".." in uri_path.parts:
            raise DatasetContractError(f"Plan 내부 source_dataset_uri에 절대경로 또는 상위경로(..)가 포함되어 있습니다: '{src_uri}'")

        # 5. Identity alignment
        if plan_data.get("dataset_id") != dataset_id:
            raise DatasetContractError(
                f"Plan 내부 dataset_id ('{plan_data.get('dataset_id')}')가 요청된 dataset_id ('{dataset_id}')와 일치하지 않습니다."
            )
        if plan_data.get("dataset_version") != dataset_version:
            raise DatasetContractError(
                f"Plan 내부 dataset_version ('{plan_data.get('dataset_version')}')가 요청된 dataset_version ('{dataset_version}')와 일치하지 않습니다."
            )
        if expected_plan_id and plan_data.get("preprocessing_plan_id") != expected_plan_id:
            raise DatasetContractError(
                f"Plan 내부 preprocessing_plan_id ('{plan_data.get('preprocessing_plan_id')}')가 "
                f"요청된 ID ('{expected_plan_id}')와 일치하지 않습니다."
            )

        # 6. Duplicate policy & aggregation contract
        dup_policy = plan_data.get("duplicate_policy")
        agg = plan_data.get("aggregation")
        if dup_policy == "aggregate":
            if agg not in ("mean", "first", "sum"):
                raise DatasetContractError(f"duplicate_policy='aggregate'는 유효한 aggregation ('mean', 'first', 'sum')이 필요합니다: '{agg}'")
        elif dup_policy == "error":
            if agg is not None:
                raise DatasetContractError("duplicate_policy='error'일 때는 aggregation이 None이어야 합니다.")
        else:
            raise DatasetContractError(f"지원하지 않는 duplicate_policy입니다: '{dup_policy}'")

        # 7. Structure-specific role & selected columns validation
        st = plan_data.get("structure_type")
        selected_cols = plan_data.get("selected_columns")
        if not isinstance(selected_cols, list) or not selected_cols:
            raise DatasetContractError("Preprocessing Plan에 'selected_columns' 목록이 누락되었거나 비어 있습니다.")

        if st == "tabular_column_as_attribute":
            id_col = plan_data.get("id_column")
            time_col = plan_data.get("time_column")
            if id_col and id_col not in selected_cols:
                raise DatasetContractError(f"Wide 구조 Plan의 선언된 id_column '{id_col}'이 selected_columns에 포함되지 않았습니다.")
            if time_col and time_col not in selected_cols:
                raise DatasetContractError(f"Wide 구조 Plan의 선언된 time_column '{time_col}'이 selected_columns에 포함되지 않았습니다.")
        elif st == "tabular_row_as_attribute":
            id_col = plan_data.get("id_column")
            attr_col = plan_data.get("attribute_column")
            val_col = plan_data.get("value_column")
            time_col = plan_data.get("time_column")

            for role_name, role_val in (("id_column", id_col), ("attribute_column", attr_col), ("value_column", val_col)):
                if not role_val or not str(role_val).strip():
                    raise DatasetContractError(f"Long 구조 Preprocessing Plan에 필수 역할 '{role_name}'이 누락되었습니다.")

            roles = [id_col, attr_col, val_col]
            if time_col and str(time_col).strip():
                roles.append(time_col)

            if len(roles) != len(set(roles)):
                raise DatasetContractError(f"Long 구조 역할 컬럼은 고유해야 합니다: {roles}")

            missing_in_selected = [r for r in roles if r not in selected_cols]
            if missing_in_selected:
                raise DatasetContractError(f"Long 구조 역할 컬럼 {missing_in_selected}이 selected_columns에 포함되지 않았습니다.")
        else:
            raise DatasetContractError(f"지원하지 않는 structure_type입니다: '{st}'")

        # 8. Content-derived version check
        computed_ver = compute_preprocessing_plan_version(dataset_id, dataset_version, plan_data)
        if plan_data.get("preprocessing_plan_version") != computed_ver:
            raise DatasetContractError(
                f"Plan 내부 preprocessing_plan_version ('{plan_data.get('preprocessing_plan_version')}')가 "
                f"내용 기반 계산 버전 ('{computed_ver}')과 일치하지 않습니다."
            )

    def find_latest_plan(self, dataset_id: str, dataset_version: str) -> Optional[dict[str, Any]]:
        """Find and validate latest published plan for a dataset/version, or return None."""
        pointer_path = self.get_latest_pointer_path(dataset_id, dataset_version)
        if not pointer_path.is_file():
            return None

        try:
            with open(pointer_path, "r", encoding="utf-8") as f:
                pointer_data = json.load(f)
        except Exception as exc:
            raise DatasetContractError(f"latest.json 포인터 파일 파싱 실패 ({pointer_path.name}): {exc}") from exc

        if not isinstance(pointer_data, dict):
            raise DatasetContractError(f"latest.json 포인터 형식이 올바르지 않습니다 (dict 기대, {type(pointer_data).__name__} 수신)")

        # Validate pointer metadata
        ptr_ds_id = pointer_data.get("dataset_id")
        ptr_ds_ver = pointer_data.get("dataset_version")
        plan_id = pointer_data.get("preprocessing_plan_id")
        plan_ver = pointer_data.get("preprocessing_plan_version")
        rel_path = pointer_data.get("path")
        expected_sha = pointer_data.get("sha256")

        if ptr_ds_id != dataset_id or ptr_ds_ver != dataset_version:
            raise DatasetContractError(
                f"latest.json 내부 dataset 식별자('{ptr_ds_id}:{ptr_ds_ver}')가 요청('{dataset_id}:{dataset_version}')과 일치하지 않습니다."
            )

        if not plan_id or not rel_path or not expected_sha:
            raise DatasetContractError("latest.json 포인터 파일에 필수 필드(preprocessing_plan_id, path, sha256)가 누락되었습니다.")

        plan_dir = self.get_dataset_plan_dir(dataset_id, dataset_version)
        target_file = (plan_dir / rel_path).resolve()
        if not target_file.is_relative_to(plan_dir) or not target_file.is_file():
            raise DatasetContractError(f"latest.json이 가리키는 Plan 파일이 디렉터리에 존재하지 않습니다: {rel_path}")

        actual_sha = compute_file_sha256(target_file)
        if actual_sha != expected_sha:
            raise DatasetContractError(
                f"latest.json이 가리키는 Plan 파일의 SHA-256 체크섬 불일치 ({actual_sha} != {expected_sha})"
            )

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
        except Exception as exc:
            raise DatasetContractError(f"Plan JSON 파일 파싱 실패 ({target_file.name}): {exc}") from exc

        # Strict validation of plan content
        self._validate_plan_content(
            plan_data=plan_data,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_plan_id=plan_id,
        )

        if plan_ver != plan_data.get("preprocessing_plan_version"):
            raise DatasetContractError(
                f"latest.json의 plan_version ('{plan_ver}')과 Plan 내부 version ('{plan_data.get('preprocessing_plan_version')}')이 일치하지 않습니다."
            )

        return plan_data

    find_plan = find_latest_plan

    def load_plan(
        self,
        dataset_id: str,
        dataset_version: str,
        preprocessing_plan_id: str,
    ) -> dict[str, Any]:
        """Load and strictly validate an immutable Preprocessing Plan by its unique plan ID."""
        safe_plan_id = self._sanitize_path_segment(preprocessing_plan_id, "preprocessing_plan_id")
        plan_dir = self.get_dataset_plan_dir(dataset_id, dataset_version)

        filename = safe_plan_id if safe_plan_id.endswith(".json") else f"{safe_plan_id}.json"
        target_path = (plan_dir / filename).resolve()

        if not target_path.is_relative_to(plan_dir) or not target_path.is_file():
            raise DatasetNotFoundError(
                f"Preprocessing Plan 파일을 찾을 수 없습니다: "
                f"dataset='{dataset_id}:{dataset_version}', plan_id='{preprocessing_plan_id}'"
            )

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
        except Exception as exc:
            raise DatasetContractError(f"Preprocessing Plan JSON 파싱 실패 ({target_path.name}): {exc}") from exc

        expected_plan_id = safe_plan_id[:-5] if safe_plan_id.endswith(".json") else safe_plan_id
        self._validate_plan_content(
            plan_data=plan_data,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_plan_id=expected_plan_id,
        )

        return plan_data

    def publish_plan(
        self,
        dataset_id: str,
        dataset_version: str,
        plan_data: dict[str, Any],
    ) -> PublishedPreprocessingPlan:
        """Publish an immutable Plan file with dataset provenance and schema fingerprint, then atomically advance latest.json."""
        plan_dir = self.get_dataset_plan_dir(dataset_id, dataset_version)
        plan_dir.mkdir(parents=True, exist_ok=True)

        plan_id = f"pp-{uuid.uuid4()}"

        # Require provenance fields in plan_data before publishing
        src_uri = plan_data.get("source_dataset_uri")
        src_sha = plan_data.get("source_dataset_sha256")
        src_schema_fp = plan_data.get("source_schema_fingerprint")
        decision_src = plan_data.get("decision_source", "rule_fallback")
        fallback_reason = plan_data.get("fallback_reason")
        planner_ver = plan_data.get("planner_version", "preprocessing-planner-v1")

        if not src_uri or not src_sha:
            raise PreprocessingPlanPublishError("Plan 발행 시 source_dataset_uri 및 source_dataset_sha256 provenance가 필수입니다.")
        if not src_schema_fp:
            raise PreprocessingPlanPublishError("Plan 발행 시 source_schema_fingerprint가 필수입니다.")

        canonical_version = compute_preprocessing_plan_version(dataset_id, dataset_version, plan_data)

        full_plan_data = {
            "preprocessing_plan_id": plan_id,
            "preprocessing_plan_version": canonical_version,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "source_dataset_uri": src_uri,
            "source_dataset_sha256": src_sha,
            "source_schema_fingerprint": src_schema_fp,
            "source_dataset_size_bytes": plan_data.get("source_dataset_size_bytes"),
            "decision_source": decision_src,
            "fallback_reason": fallback_reason,
            "planner_version": planner_ver,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "structure_type": plan_data.get("structure_type", "tabular_column_as_attribute"),
            "selected_columns": plan_data.get("selected_columns", []),
            "id_column": plan_data.get("id_column"),
            "time_column": plan_data.get("time_column"),
            "attribute_column": plan_data.get("attribute_column"),
            "value_column": plan_data.get("value_column"),
            "duplicate_policy": plan_data.get("duplicate_policy", "error"),
            "aggregation": plan_data.get("aggregation"),
        }

        # Validate complete plan structure and contracts before persisting
        self._validate_plan_content(full_plan_data, dataset_id, dataset_version, plan_id)

        target_plan_path = plan_dir / f"{plan_id}.json"
        if target_plan_path.exists():
            raise PreprocessingPlanPublishError(f"Plan 파일이 이미 존재합니다 (불변 파일 덮어쓰기 금지): {target_plan_path}")

        # Keep atomic staging names short. Dataset/version identifiers already make
        # this directory deep enough to exceed the legacy Windows MAX_PATH limit
        # when the complete plan UUID is repeated in the temporary filename.
        temp_plan_path = plan_dir / f".tmp_{uuid.uuid4().hex}.json"
        temp_latest_path = plan_dir / f".tmp_{uuid.uuid4().hex}.json"

        try:
            # 1. Write and validate immutable plan JSON
            with open(temp_plan_path, "w", encoding="utf-8") as f:
                json.dump(full_plan_data, f, ensure_ascii=False, indent=2)

            plan_sha256 = compute_file_sha256(temp_plan_path)

            # 2. Atomic rename plan file
            temp_plan_path.replace(target_plan_path)
            logger.info(f"[PreprocessingRepository] Atomically published immutable plan {plan_id} to {target_plan_path}")

            # 3. Write latest.json pointer
            latest_data = {
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "preprocessing_plan_id": plan_id,
                "preprocessing_plan_version": canonical_version,
                "path": f"{plan_id}.json",
                "sha256": plan_sha256,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(temp_latest_path, "w", encoding="utf-8") as f:
                json.dump(latest_data, f, ensure_ascii=False, indent=2)

            # 4. Atomic replace latest.json
            latest_pointer_path = plan_dir / "latest.json"
            temp_latest_path.replace(latest_pointer_path)
            logger.info(f"[PreprocessingRepository] Atomically updated latest pointer for {dataset_id}:{dataset_version} -> {plan_id}")

            logical_uri = self.get_logical_uri(target_plan_path)
            return PublishedPreprocessingPlan(
                preprocessing_plan_id=plan_id,
                preprocessing_plan_version=canonical_version,
                preprocessing_plan_uri=logical_uri,
                sha256=plan_sha256,
            )
        except Exception as exc:
            for p in (temp_plan_path, temp_latest_path):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            if isinstance(exc, PreprocessingPlanPublishError):
                raise
            logger.exception(f"[PreprocessingRepository] Failed to publish plan: {exc}")
            raise PreprocessingPlanPublishError(f"전처리 계획 저장에 실패했습니다: {exc}") from exc
