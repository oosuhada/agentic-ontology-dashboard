"""Orchestration service for dataset resolution, planning, validation, and preprocessing."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional
import pandas as pd

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.common.timestamp_canonicalizer import canonicalize_timestamp_series
from systems.generator.app.preprocessing.preprocessing_profiler import build_family_registry, load_family_registry
from systems.generator.app.preprocessing.preprocessing_schema import (
    PreprocessingRequest,
    PreprocessingResponse,
    PreprocessingResultPayload,
    PreprocessingPlanResponse,
)
from systems.generator.app.preprocessing.preprocessing_exception import (
    PreprocessingError,
    DatasetNotFoundError,
    DatasetContractError,
    PreprocessingRoleError,
    PreprocessingPlanValidationError,
    PreprocessingPlanningError,
    PreprocessingPlanConflictError,
)
from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner
from systems.generator.app.preprocessing.preprocessing_repository import (
    PreprocessingRepository,
    compute_source_schema_fingerprint,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".jsonl")
_last_plans: dict[str, Any] = {}


def _is_within_allowed_root(path: Path, allowed_roots: list[Path]) -> bool:
    """Check if the resolved path is strictly within any of the allowed root directories."""
    resolved_path = path.resolve()
    for root in allowed_roots:
        try:
            resolved_path.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def preprocess_with_plan(filepath: str, plan: dict[str, Any]) -> pd.DataFrame:
    """Execute dataframe loading and transformation based on the validated preprocessing plan."""
    ext = os.path.splitext(filepath)[1].lower()
    logger.info(f"[Preprocessor] Reading file '{filepath}' (ext: {ext})...")

    if ext == ".csv":
        df = pd.read_csv(filepath)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath)
    elif ext == ".jsonl":
        df = pd.read_json(filepath, lines=True)
    else:
        raise DatasetContractError(f"지원하지 않는 파일 형식입니다: {ext}")


    if df.empty or len(df.columns) == 0:
        raise DatasetContractError("데이터셋이 비어 있거나 유효한 컬럼이 없습니다.")

    structure_type = plan.get("structure_type", "tabular_column_as_attribute")

    if structure_type == "tabular_column_as_attribute":
        selected_cols = plan.get("selected_columns")
        if selected_cols is None:
            selected_cols = list(df.columns)
        elif not isinstance(selected_cols, list) or len(selected_cols) == 0:
            raise PreprocessingPlanValidationError("Wide 구조 Plan에 selected_columns 목록이 누락되었거나 비어 있습니다.")

        # Fail-fast on any missing selected column (no arbitrary fallback!)
        missing_cols = [c for c in selected_cols if c not in df.columns]
        if missing_cols:
            raise PreprocessingPlanValidationError(
                f"선택된 컬럼 중 데이터셋에 존재하지 않는 컬럼이 있습니다: {missing_cols}",
                details=[{
                    "missing_columns": missing_cols,
                    "declared_columns": selected_cols,
                    "available_columns": list(df.columns),
                }],
            )

        # Validate declared role columns
        id_col = plan.get("id_column")
        time_col = plan.get("time_column")
        if id_col and id_col not in df.columns:
            raise PreprocessingPlanValidationError(
                f"선언된 id_column '{id_col}'가 데이터셋에 존재하지 않습니다: {list(df.columns)}"
            )
        if time_col and time_col not in df.columns:
            raise PreprocessingPlanValidationError(
                f"선언된 time_column '{time_col}'가 데이터셋에 존재하지 않습니다: {list(df.columns)}"
            )

        # Timestamp canonicalization for Wide-format
        if time_col and time_col in df.columns:
            df[time_col] = canonicalize_timestamp_series(df[time_col], col_name=time_col)
            if df[time_col].isna().any():
                raise DatasetContractError(f"컬럼 '{time_col}'의 타임스탬프 정규화 실패 또는 NaT 값이 감지되었습니다.")

        # Stable sort by [id_column, time_column] or [time_column]
        sort_cols = []
        if id_col and id_col in df.columns:
            sort_cols.append(id_col)
        if time_col and time_col in df.columns:
            sort_cols.append(time_col)

        if sort_cols:
            df = df.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)

        extracted_df = df[selected_cols].copy()

        # Duplicate checking and policy enforcement
        if sort_cols:
            has_duplicates = extracted_df.duplicated(subset=sort_cols).any()
            if has_duplicates:
                dup_policy = plan.get("duplicate_policy", "error")
                aggfunc = plan.get("aggregation")
                if dup_policy == "aggregate" and aggfunc:
                    numeric_cols = [
                        c for c in extracted_df.columns
                        if c not in sort_cols and pd.api.types.is_numeric_dtype(extracted_df[c])
                    ]
                    non_numeric_cols = [c for c in extracted_df.columns if c not in sort_cols and c not in numeric_cols]
                    for c in non_numeric_cols:
                        per_group_nunique = extracted_df.groupby(sort_cols)[c].nunique()
                        if (per_group_nunique > 1).any():
                            raise DatasetContractError(
                                f"Cannot deduplicate non-numeric column '{c}' with conflicting "
                                f"values within the same {sort_cols} group; no aggregation policy "
                                f"is defined for non-numeric conflicts"
                            )
                    agg_map = {c: aggfunc for c in numeric_cols}
                    agg_map.update({c: "first" for c in non_numeric_cols})
                    extracted_df = extracted_df.groupby(sort_cols, as_index=False).agg(agg_map)
                    extracted_df = extracted_df.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)
                else:
                    raise DatasetContractError(
                        f"Duplicate rows found for key {sort_cols} and duplicate_policy={dup_policy!r}; "
                        f"set plan.duplicate_policy='aggregate' with an aggregation function, or deduplicate the source data"
                    )

        logger.info(f"[Preprocessor] Successfully processed {len(selected_cols)} columns from '{filepath}'. Output shape: {extracted_df.shape}")
        return extracted_df

    elif structure_type == "tabular_row_as_attribute":
        logger.info(f"[Preprocessor] Performing contract-driven tabular_row_as_attribute transform for '{filepath}'...")
        id_col = plan.get("id_column")
        time_col = plan.get("time_column")
        attr_col = plan.get("attribute_column")
        val_col = plan.get("value_column")

        missing_roles = []
        if not id_col:
            missing_roles.append("id_column")
        if not attr_col:
            missing_roles.append("attribute_column")
        if not val_col:
            missing_roles.append("value_column")

        if missing_roles:
            raise PreprocessingRoleError(
                f"Long-format preprocessing for '{filepath}' failed: missing required role(s) {missing_roles}. "
                f"Specified roles: id_column={id_col!r}, attribute_column={attr_col!r}, value_column={val_col!r}, time_column={time_col!r}."
            )

        missing_cols = [c for c in [id_col, attr_col, val_col] if c not in df.columns]
        if time_col and time_col not in df.columns:
            missing_cols.append(time_col)

        if missing_cols:
            raise PreprocessingPlanValidationError(
                f"Long-format preprocessing for '{filepath}' failed: specified role columns {missing_cols} not found in DataFrame."
            )

        roles = [id_col, attr_col, val_col]
        if time_col:
            roles.append(time_col)
        if len(roles) != len(set(roles)):
            raise PreprocessingPlanValidationError(
                f"Long-format preprocessing for '{filepath}' failed: role columns must be unique and cannot overlap: {roles}."
            )

        if time_col and time_col in df.columns:
            df[time_col] = canonicalize_timestamp_series(df[time_col], col_name=time_col)
            if df[time_col].isna().any():
                raise DatasetContractError(f"Long-format time_column '{time_col}' 정규화 실패 또는 NaT 값이 감지되었습니다.")
            index_cols = [id_col, time_col]
        else:
            index_cols = [id_col]

        check_cols = index_cols + [attr_col]
        has_duplicates = df.duplicated(subset=check_cols).any()

        dup_policy = plan.get("duplicate_policy", "error")
        aggfunc = plan.get("aggregation")

        if has_duplicates:
            if dup_policy == "aggregate" and aggfunc:
                logger.info(f"[Preprocessor] Duplicate entries found in long-format '{filepath}'. Aggregating using '{aggfunc}'...")
                pivoted = df.pivot_table(index=index_cols, columns=attr_col, values=val_col, aggfunc=aggfunc).reset_index()
                return pivoted
            else:
                raise DatasetContractError(
                    f"Long-format dataset '{filepath}' contains duplicate observation entries for keys {check_cols} "
                    f"without an explicit aggregation policy (duplicate_policy='{dup_policy}')."
                )

        pivoted = df.pivot(index=index_cols, columns=attr_col, values=val_col).reset_index()
        pivoted.columns.name = None
        logger.info(f"[Preprocessor] Successfully pivoted long-format dataset '{filepath}'. Output shape: {pivoted.shape}")
        return pivoted

    else:
        raise PreprocessingPlanValidationError(f"지원하지 않는 structure_type입니다: '{structure_type}'")


extract_with_plan = preprocess_with_plan


def load_all_sources(data_dir: str, force_reanalyze: bool = False) -> dict[str, pd.DataFrame]:
    """Legacy helper: profile, plan, and load all files in data_dir."""
    global _last_plans
    if not os.path.exists(data_dir):
        raise ValueError(f"Directory missing: {data_dir}")

    build_family_registry(data_dir)
    planner = PreprocessingPlanner()
    sources = {}
    plans = {}
    for filename in sorted(os.listdir(data_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext in SUPPORTED_EXTENSIONS:
            filepath = os.path.join(data_dir, filename)
            key = os.path.splitext(filename)[0]
            plan = planner.build_plan(filepath, force_reanalyze=force_reanalyze)
            df = preprocess_with_plan(filepath, plan)
            sources[key] = df
            plans[key] = plan

    _last_plans = plans
    return sources


def get_last_plans() -> dict[str, Any]:
    return _last_plans


class PreprocessingService:
    """Orchestrates preprocessing requests end-to-end."""

    def __init__(
        self,
        planner: Optional[PreprocessingPlanner] = None,
        repository: Optional[PreprocessingRepository] = None,
    ) -> None:
        self.planner = planner or PreprocessingPlanner()
        self.repository = repository or PreprocessingRepository()

    def preprocess_with_plan(self, filepath: str, plan: dict[str, Any]) -> pd.DataFrame:
        """Execute dataframe loading and transformation based on the validated preprocessing plan."""
        return preprocess_with_plan(filepath, plan)

    def _resolve_dataset_path(self, request: PreprocessingRequest) -> Path:
        """Resolve dataset_id / dataset_version / source_uri to a concrete readable file path."""
        allowed_roots = [PATHS.data_dir.resolve(), PATHS.data_preprocessed.resolve()]

        # 1. Direct source_uri if provided
        if request.source_uri:
            raw_uri = str(request.source_uri).strip()
            p = Path(raw_uri)
            # Security checks: relative path only, no directory traversal
            if p.is_absolute() or ".." in p.parts:
                raise DatasetContractError(
                    "source_uri는 허용된 데이터 루트(data_dir, data_preprocessed) 내 상대경로 파일이어야 하며 절대경로/상위경로(..)는 허용되지 않습니다."
                )

            found_path: Optional[Path] = None
            for base in allowed_roots:
                candidate = (base / raw_uri).resolve()
                if _is_within_allowed_root(candidate, allowed_roots) and candidate.is_file():
                    found_path = candidate
                    break

            if not found_path:
                repo_root = PATHS.models_store.parent.resolve()
                repo_candidate = (repo_root / raw_uri).resolve()
                if _is_within_allowed_root(repo_candidate, allowed_roots) and repo_candidate.is_file():
                    found_path = repo_candidate

            if found_path:
                return found_path

            # Check if file exists outside allowed roots (e.g. repository root files)
            repo_root = PATHS.models_store.parent.resolve()
            outside_candidate = (repo_root / raw_uri).resolve()
            if outside_candidate.is_file():
                raise DatasetContractError(
                    f"source_uri '{request.source_uri}'는 허용된 데이터 루트 외부의 파일입니다. 데이터 루트 내부 상대경로만 허용됩니다."
                )

            raise DatasetNotFoundError(
                f"지정한 source_uri 파일을 허용된 데이터 루트에서 찾을 수 없습니다: '{request.source_uri}'"
            )

        # 2. Lookup by dataset_id and dataset_version
        id_path = Path(str(request.dataset_id).strip())
        ver_path = Path(str(request.dataset_version).strip())
        if id_path.is_absolute() or ".." in id_path.parts or ver_path.is_absolute() or ".." in ver_path.parts:
            raise DatasetContractError(
                "dataset_id 및 dataset_version에 절대경로나 상위경로(..)는 허용되지 않습니다."
            )

        candidates = [
            PATHS.data_dir / "observations" / request.dataset_id / request.dataset_version / "observations.jsonl",
            PATHS.data_dir / "observations" / request.dataset_id / request.dataset_version,
            PATHS.data_dir / "observations" / request.dataset_id,
            PATHS.data_dir / request.dataset_id / request.dataset_version / "observations.jsonl",
            PATHS.data_dir / request.dataset_id / request.dataset_version,
            PATHS.data_dir / request.dataset_id / f"{request.dataset_version}.csv",
            PATHS.data_dir / f"{request.dataset_id}_{request.dataset_version}.csv",
            PATHS.data_dir / f"{request.dataset_id}.csv",
            PATHS.data_dir / request.dataset_id / "input.csv",
            PATHS.data_preprocessed / request.dataset_id / f"{request.dataset_version}.csv",
            PATHS.data_preprocessed / f"{request.dataset_id}.csv",
            PATHS.data_preprocessed / request.dataset_id / "input.csv",
            PATHS.data_dir / request.dataset_id,
            PATHS.data_preprocessed / request.dataset_id,
        ]

        for cand in candidates:
            resolved_cand = cand.resolve()
            if not _is_within_allowed_root(resolved_cand, allowed_roots):
                continue

            if resolved_cand.is_file():
                return resolved_cand
            if resolved_cand.is_dir():
                for child in sorted(resolved_cand.iterdir()):
                    resolved_child = child.resolve()
                    if _is_within_allowed_root(resolved_child, allowed_roots):
                        if resolved_child.is_file() and resolved_child.suffix.lower() in SUPPORTED_EXTENSIONS:
                            return resolved_child

        raise DatasetNotFoundError(
            f"데이터셋을 찾을 수 없습니다: dataset_id='{request.dataset_id}', "
            f"version='{request.dataset_version}'"
        )

    def validate_plan(self, df_preview: pd.DataFrame, plan: dict[str, Any]) -> None:
        """Validate preprocessing plan against actual dataframe preview."""
        cols = list(df_preview.columns)
        st_type = plan.get("structure_type", "tabular_column_as_attribute")

        if st_type == "tabular_row_as_attribute":
            id_col = plan.get("id_column")
            attr_col = plan.get("attribute_column")
            val_col = plan.get("value_column")
            time_col = plan.get("time_column")

            if not id_col or not attr_col or not val_col:
                raise PreprocessingRoleError(
                    "Long-format preprocessing requires explicit id_column, attribute_column, and value_column."
                )

            roles = [id_col, attr_col, val_col]
            if time_col:
                roles.append(time_col)

            if len(roles) != len(set(roles)):
                raise PreprocessingPlanValidationError(
                    f"Long-format role columns must be unique and cannot overlap: {roles}"
                )

            missing = [r for r in roles if r not in cols]
            if missing:
                raise PreprocessingPlanValidationError(
                    f"Declared role columns {missing} not found in dataset columns: {cols}"
                )

        elif st_type == "tabular_column_as_attribute":
            selected = plan.get("selected_columns")
            if not selected:
                raise PreprocessingPlanValidationError("Wide 구조 Plan에 selected_columns 목록이 누락되었습니다.")

            missing_cols = [c for c in selected if c not in cols]
            if missing_cols:
                raise PreprocessingPlanValidationError(
                    f"선택된 컬럼 중 데이터셋에 존재하지 않는 컬럼이 있습니다: {missing_cols}",
                    details=[{
                        "missing_columns": missing_cols,
                        "declared_columns": selected,
                        "available_columns": cols,
                    }],
                )

            id_col = plan.get("id_column")
            time_col = plan.get("time_column")
            if id_col and id_col not in cols:
                raise PreprocessingPlanValidationError(
                    f"선언된 id_column '{id_col}'가 데이터셋에 존재하지 않습니다: {cols}"
                )
            if time_col and time_col not in cols:
                raise PreprocessingPlanValidationError(
                    f"선언된 time_column '{time_col}'가 데이터셋에 존재하지 않습니다: {cols}"
                )
        else:
            raise PreprocessingPlanValidationError(f"지원하지 않는 structure_type입니다: '{st_type}'")

    def run_preprocessing(self, request: PreprocessingRequest, request_id: Optional[str] = None) -> PreprocessingResponse:
        """Execute full preprocessing workflow and return structured PreprocessingResponse."""
        req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        run_id = f"preprocessing-{uuid.uuid4().hex[:12]}"

        # 1. Resolve dataset path and compute provenance
        dataset_path = self._resolve_dataset_path(request)
        dataset_sha256 = compute_file_sha256(dataset_path)
        dataset_uri = self.repository.get_logical_uri(dataset_path)
        dataset_size = dataset_path.stat().st_size
        logger.info(f"[PreprocessingService] Resolved dataset: '{dataset_path.name}' (sha256={dataset_sha256[:8]}...) for {request.dataset_id}")

        # 2. Read full dataset for source schema fingerprint and preview
        ext = dataset_path.suffix.lower()
        if ext == ".csv":
            df_full = pd.read_csv(dataset_path)
        elif ext in (".xlsx", ".xls"):
            df_full = pd.read_excel(dataset_path)
        elif ext == ".jsonl":
            df_full = pd.read_json(dataset_path, lines=True)
        else:
            raise DatasetContractError(f"지원하지 않는 파일 형식입니다: {ext}")

        if df_full.empty or len(df_full.columns) == 0:
            raise DatasetContractError("데이터셋이 비어 있거나 컬럼이 존재하지 않습니다.")

        source_schema_fp = compute_source_schema_fingerprint(df_full)
        df_preview = df_full.head(5)

        # 3. Check existing plan reuse (if force_reanalyze=False)
        existing_plan = None
        if not request.force_reanalyze:
            existing_plan = self.repository.find_latest_plan(request.dataset_id, request.dataset_version)
            if existing_plan:
                # 3.1. Verify Dataset SHA-256 and Source Schema Fingerprint match
                existing_sha = existing_plan.get("source_dataset_sha256")
                existing_schema_fp = existing_plan.get("source_schema_fingerprint")

                content_changed = existing_sha != dataset_sha256
                schema_changed = existing_schema_fp != source_schema_fp

                if content_changed or schema_changed:
                    logger.warning(
                        f"[PreprocessingService] Existing plan conflict for {request.dataset_id}:{request.dataset_version} "
                        f"(content_changed={content_changed}, schema_changed={schema_changed})"
                    )
                    raise PreprocessingPlanConflictError(
                        f"데이터셋 내용 또는 구조(Schema Fingerprint)가 변경되었습니다. force_reanalyze=True로 새 계획을 발행하십시오.",
                        details=[{
                            "content_changed": content_changed,
                            "schema_changed": schema_changed,
                            "existing_sha256": existing_sha,
                            "current_sha256": dataset_sha256,
                            "existing_schema_fingerprint": existing_schema_fp,
                            "current_schema_fingerprint": source_schema_fp,
                        }],
                    )

                # 3.2. Verify duplicate policy match
                plan_dup_policy = existing_plan.get("duplicate_policy")
                plan_agg = existing_plan.get("aggregation")
                if request.duplicate_policy != plan_dup_policy or request.aggregation != plan_agg:
                    logger.warning(
                        f"[PreprocessingService] Requested duplicate policy mismatch for {request.dataset_id}:{request.dataset_version} "
                        f"(req={request.duplicate_policy}:{request.aggregation}, plan={plan_dup_policy}:{plan_agg})"
                    )
                    raise PreprocessingPlanConflictError(
                        f"요청된 중복 처리 정책이 기존 Plan의 정책과 일치하지 않습니다.",
                        details=[{
                            "requested_duplicate_policy": request.duplicate_policy,
                            "requested_aggregation": request.aggregation,
                            "plan_duplicate_policy": plan_dup_policy,
                            "plan_aggregation": plan_agg,
                        }],
                    )

                # 3.3. Verify plan validity against preview and execute full dataset transform
                self.validate_plan(df_preview, existing_plan)
                try:
                    preprocess_with_plan(str(dataset_path), existing_plan)
                except PreprocessingError:
                    raise
                except Exception as exc:
                    logger.warning(f"[PreprocessingService] Existing plan execution failed on current dataset: {exc}")
                    raise PreprocessingPlanConflictError(
                        f"기존 계획을 현재 데이터셋에 적용할 수 없습니다: {exc}",
                        details=[{"stage": "execution", "error": str(exc)}],
                    ) from exc

                logger.info(f"[PreprocessingService] Reusing existing validated plan for {request.dataset_id}:{request.dataset_version}")
                plan_id = existing_plan["preprocessing_plan_id"]
                plan_version = existing_plan["preprocessing_plan_version"]
                plan_path = self.repository.get_dataset_plan_dir(request.dataset_id, request.dataset_version) / f"{plan_id}.json"
                plan_uri = self.repository.get_logical_uri(plan_path)
                plan_sha256 = compute_file_sha256(plan_path)

                return PreprocessingResponse(
                    request_id=req_id,
                    run_id=run_id,
                    status="succeeded",
                    dataset_id=request.dataset_id,
                    dataset_version=request.dataset_version,
                    preprocessing_plan_id=plan_id,
                    preprocessing_plan_version=plan_version,
                    result=PreprocessingResultPayload(
                        structure_type=existing_plan.get("structure_type", "tabular_column_as_attribute"),
                        id_column=existing_plan.get("id_column"),
                        time_column=existing_plan.get("time_column"),
                        attribute_column=existing_plan.get("attribute_column"),
                        value_column=existing_plan.get("value_column"),
                        duplicate_policy=existing_plan.get("duplicate_policy", request.duplicate_policy),
                        aggregation=existing_plan.get("aggregation", request.aggregation),
                        preprocessing_plan_uri=plan_uri,
                        preprocessing_plan_sha256=plan_sha256,
                    ),
                )

        # 4. Generate new Preprocessing Plan
        logger.info(f"[PreprocessingService] Generating new preprocessing plan for {request.dataset_id}:{request.dataset_version}")
        plan = self.planner.build_plan(
            str(dataset_path),
            force_reanalyze=request.force_reanalyze,
            duplicate_policy=request.duplicate_policy,
            aggregation=request.aggregation,
        )

        # Attach dataset provenance and schema fingerprint
        plan["source_dataset_uri"] = dataset_uri
        plan["source_dataset_sha256"] = dataset_sha256
        plan["source_schema_fingerprint"] = source_schema_fp
        plan["source_dataset_size_bytes"] = dataset_size

        # 5. Validate plan
        self.validate_plan(df_preview, plan)

        # 6. Execute full dataset preprocessing with plan to verify full transform success BEFORE publishing
        try:
            preprocess_with_plan(str(dataset_path), plan)
        except PreprocessingError:
            raise
        except Exception as exc:
            logger.warning(f"[PreprocessingService] Preprocessing execution failed with plan: {exc}")
            raise PreprocessingPlanningError(
                f"전처리 계획 적용 실행에 실패했습니다: {exc}",
                details=[{"stage": "execution", "error": str(exc)}],
            ) from exc

        # 7. Atomically persist immutable plan and update latest pointer
        published = self.repository.publish_plan(
            request.dataset_id,
            request.dataset_version,
            plan,
        )
        plan_id = published.preprocessing_plan_id
        plan_version = published.preprocessing_plan_version
        plan_uri = published.preprocessing_plan_uri
        plan_sha256 = published.sha256

        return PreprocessingResponse(
            request_id=req_id,
            run_id=run_id,
            status="succeeded",
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            preprocessing_plan_id=plan_id,
            preprocessing_plan_version=plan_version,
            result=PreprocessingResultPayload(
                structure_type=plan.get("structure_type", "tabular_column_as_attribute"),
                id_column=plan.get("id_column"),
                time_column=plan.get("time_column"),
                attribute_column=plan.get("attribute_column"),
                value_column=plan.get("value_column"),
                duplicate_policy=plan.get("duplicate_policy", request.duplicate_policy),
                aggregation=plan.get("aggregation", request.aggregation),
                preprocessing_plan_uri=plan_uri,
                preprocessing_plan_sha256=plan_sha256,
            ),
        )


ExtractionService = PreprocessingService
