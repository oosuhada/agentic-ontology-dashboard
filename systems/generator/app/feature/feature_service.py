"""Feature Service coordinating dataset loading, feature calculations, horizon labeling, and bundle publishing."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from systems.generator.app.feature.feature_exception import (
    FeatureAssetIdentityNotSupportedError,
    FeatureContractError,
    FeatureDatasetIntegrityError,
    FeatureInputNotFoundError,
    FeatureLabelAlignmentError,
    FeatureSchemaMismatchError,
    InsufficientTrainingDataError,
)
from systems.generator.app.feature.feature_input_resolver import (
    FeatureInputResolver,
    ResolvedFeatureInput,
)
from systems.generator.app.feature.feature_repository import (
    FeatureRepository,
    compute_feature_dataset_version,
)
from systems.generator.app.feature.feature_schema import (
    FeatureOutputsPayload,
    FeatureRequest,
    FeatureResponse,
)
from systems.generator.app.feature.feature_schema_provider import (
    FeatureItem,
    FeatureSchemaProvider,
)
from systems.generator.app.feature.label_schema_provider import (
    LabelSchemaProvider,
    LabelSchemaSpec,
)
from systems.generator.app.preprocessing.preprocessing_exception import DatasetNotFoundError
from systems.generator.app.preprocessing.preprocessing_repository import PreprocessingRepository
from systems.generator.common.timestamp_canonicalizer import canonicalize_timestamp_series
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)


class FeatureService:
    """Service handling Feature Dataset Bundle generation, deterministic alignment, and execution."""

    def __init__(
        self,
        preprocessing_repo: PreprocessingRepository | None = None,
        feature_repo: FeatureRepository | None = None,
        feature_schema_provider: FeatureSchemaProvider | None = None,
        label_schema_provider: LabelSchemaProvider | None = None,
        feature_input_resolver: FeatureInputResolver | None = None,
    ) -> None:
        self.preprocessing_repo = preprocessing_repo or PreprocessingRepository()
        self.feature_repo = feature_repo or FeatureRepository()
        self.feature_schema_provider = feature_schema_provider or FeatureSchemaProvider()
        self.label_schema_provider = label_schema_provider or LabelSchemaProvider()
        self.feature_input_resolver = feature_input_resolver or FeatureInputResolver(feature_repo=self.feature_repo)

    def _load_dataframe(self, path: Path) -> pd.DataFrame:
        """Load tabular data from CSV or JSONL."""
        try:
            if path.suffix.lower() == ".jsonl":
                return pd.read_json(path, lines=True)
            return pd.read_csv(path)
        except Exception as exc:
            raise FeatureContractError(f"데이터셋 파일 파싱 실패 ({path.name}): {exc}") from exc

    def _prepare_canonical_working_df(
        self,
        obs_df: pd.DataFrame,
        id_col: str | None,
        time_col: str | None,
        context: dict[str, Any] | None = None,
    ) -> tuple[pd.DataFrame, str, str]:
        """Normalize timestamps and perform stable sorting by asset ID and time.

        Strictly validates that Preprocessing Plan declares an id_column present in Observation Dataset
        without missing values. Fails closed with FeatureAssetIdentityNotSupportedError (501) otherwise.
        """
        ctx = context or {}
        working_df = obs_df.copy()

        # 1. Determine and normalize time column
        resolved_time_col = time_col
        if not resolved_time_col or resolved_time_col not in working_df.columns:
            for candidate in ["observed_at", "timestamp", "datetime", "date", "time"]:
                if candidate in working_df.columns:
                    resolved_time_col = candidate
                    break

        if not resolved_time_col or resolved_time_col not in working_df.columns:
            raise FeatureLabelAlignmentError(
                "호라이즌 라벨링에 필요한 Observation timestamp 컬럼이 없습니다."
            )

        working_df[resolved_time_col] = canonicalize_timestamp_series(
            working_df[resolved_time_col], col_name=resolved_time_col
        )
        if working_df[resolved_time_col].isna().any():
            raise FeatureLabelAlignmentError(
                "Observation timestamp에 정규화할 수 없는 값이 포함되어 있습니다."
            )

        # 2. Strict Asset ID Validation (Fail-Closed)
        resolved_id_col = id_col
        if not resolved_id_col or not str(resolved_id_col).strip():
            logger.warning(
                f"[FeatureService] event=feature_asset_identity_unsupported "
                f"error_code=FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED "
                f"request_id={ctx.get('request_id')} "
                f"dataset_id={ctx.get('dataset_id')} dataset_version={ctx.get('dataset_version')} "
                f"preprocessing_plan_id={ctx.get('preprocessing_plan_id')} preprocessing_plan_version={ctx.get('preprocessing_plan_version')} "
                f"declared_id_column={resolved_id_col} "
                f"failure_reason='Preprocessing Plan에 id_column이 선언되지 않았거나 비어 있습니다.'"
            )
            raise FeatureAssetIdentityNotSupportedError(
                "Observation Dataset에서 설비 ID를 식별할 수 없습니다. "
                "현재 Feature 파이프라인은 Preprocessing Plan에 의해 명시된 asset ID가 필요하며, "
                "ID가 없는 단일 설비 데이터의 자동 ID 생성 기능은 아직 지원하지 않습니다.",
                details=[{
                    "required_contract": "preprocessing_plan.id_column",
                    "unsupported_case": "observation_without_asset_id",
                    "required_follow_up": "single-asset identity resolution 기능 구현",
                    "declared_id_column": resolved_id_col,
                    "failure_reason": "Preprocessing Plan에 id_column이 선언되지 않았거나 비어 있습니다.",
                }],
            )

        if resolved_id_col not in working_df.columns:
            logger.warning(
                f"[FeatureService] event=feature_asset_identity_unsupported "
                f"error_code=FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED "
                f"request_id={ctx.get('request_id')} "
                f"dataset_id={ctx.get('dataset_id')} dataset_version={ctx.get('dataset_version')} "
                f"preprocessing_plan_id={ctx.get('preprocessing_plan_id')} preprocessing_plan_version={ctx.get('preprocessing_plan_version')} "
                f"declared_id_column={resolved_id_col} "
                f"failure_reason='선언된 id_column이 Observation Dataset에 존재하지 않습니다.'"
            )
            raise FeatureAssetIdentityNotSupportedError(
                "Observation Dataset에서 설비 ID를 식별할 수 없습니다. "
                "현재 Feature 파이프라인은 Preprocessing Plan에 의해 명시된 asset ID가 필요하며, "
                "ID가 없는 단일 설비 데이터의 자동 ID 생성 기능은 아직 지원하지 않습니다.",
                details=[{
                    "required_contract": "preprocessing_plan.id_column",
                    "unsupported_case": "observation_without_asset_id",
                    "required_follow_up": "single-asset identity resolution 기능 구현",
                    "declared_id_column": resolved_id_col,
                    "available_columns": list(working_df.columns),
                    "failure_reason": f"선언된 id_column '{resolved_id_col}'이 Observation Dataset에 존재하지 않습니다.",
                }],
            )

        # 3. Validate ID values
        id_series = working_df[resolved_id_col]
        if id_series.isna().any():
            logger.warning(
                f"[FeatureService] event=feature_asset_identity_unsupported "
                f"error_code=FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED "
                f"request_id={ctx.get('request_id')} "
                f"dataset_id={ctx.get('dataset_id')} dataset_version={ctx.get('dataset_version')} "
                f"preprocessing_plan_id={ctx.get('preprocessing_plan_id')} preprocessing_plan_version={ctx.get('preprocessing_plan_version')} "
                f"declared_id_column={resolved_id_col} "
                f"failure_reason='id_column에 결측치(null/NaN)가 포함되어 있습니다.'"
            )
            raise FeatureAssetIdentityNotSupportedError(
                "Observation Dataset에서 설비 ID를 식별할 수 없습니다. "
                "현재 Feature 파이프라인은 Preprocessing Plan에 의해 명시된 asset ID가 필요하며, "
                "ID가 없는 단일 설비 데이터의 자동 ID 생성 기능은 아직 지원하지 않습니다.",
                details=[{
                    "required_contract": "preprocessing_plan.id_column",
                    "unsupported_case": "observation_without_asset_id",
                    "required_follow_up": "single-asset identity resolution 기능 구현",
                    "declared_id_column": resolved_id_col,
                    "failure_reason": f"id_column '{resolved_id_col}'에 결측치(null/NaN)가 포함되어 있습니다.",
                }],
            )

        normalized_ids = id_series.astype(str).str.strip()
        if normalized_ids.eq("").any():
            logger.warning(
                f"[FeatureService] event=feature_asset_identity_unsupported "
                f"error_code=FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED "
                f"request_id={ctx.get('request_id')} "
                f"dataset_id={ctx.get('dataset_id')} dataset_version={ctx.get('dataset_version')} "
                f"preprocessing_plan_id={ctx.get('preprocessing_plan_id')} preprocessing_plan_version={ctx.get('preprocessing_plan_version')} "
                f"declared_id_column={resolved_id_col} "
                f"failure_reason='id_column에 빈 문자열이 포함되어 있습니다.'"
            )
            raise FeatureAssetIdentityNotSupportedError(
                "Observation Dataset에서 설비 ID를 식별할 수 없습니다. "
                "현재 Feature 파이프라인은 Preprocessing Plan에 의해 명시된 asset ID가 필요하며, "
                "ID가 없는 단일 설비 데이터의 자동 ID 생성 기능은 아직 지원하지 않습니다.",
                details=[{
                    "required_contract": "preprocessing_plan.id_column",
                    "unsupported_case": "observation_without_asset_id",
                    "required_follow_up": "single-asset identity resolution 기능 구현",
                    "declared_id_column": resolved_id_col,
                    "failure_reason": f"id_column '{resolved_id_col}'에 빈 문자열이 포함되어 있습니다.",
                }],
            )

        working_df[resolved_id_col] = normalized_ids

        # 4. Stable sort by (asset_id, timestamp)
        working_df = working_df.sort_values(
            by=[resolved_id_col, resolved_time_col], kind="mergesort"
        ).reset_index(drop=True)

        return working_df, resolved_id_col, resolved_time_col

    def _compute_features_and_missing_masks(
        self,
        working_df: pd.DataFrame,
        feature_items: list[FeatureItem],
        id_col: str | None,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Compute feature transformations according to schema and track missing value masks."""
        computed_df = pd.DataFrame(index=working_df.index)
        missing_drop_mask = pd.Series(False, index=working_df.index)

        for item in feature_items:
            src = item.source_field
            if src not in working_df.columns:
                raise FeatureSchemaMismatchError(
                    f"Feature Schema의 source_field '{src}'가 Observation 데이터셋에 존재하지 않습니다."
                )

            op = item.operation
            params = item.parameters or {}
            mv_policy = item.missing_value_policy or "drop"

            # Execute operation without premature fillna
            if op == "raw":
                try:
                    series = working_df[src].astype(float)
                except (ValueError, TypeError) as exc:
                    raise FeatureContractError(f"Feature '{item.feature_name}'의 수치형 변환 실패: {exc}") from exc
            elif op in ("rolling_mean", "rolling_std", "rolling_max", "rolling_min"):
                window = params.get("window", 5)
                min_periods = params.get("min_periods", 1)
                if id_col and id_col in working_df.columns:
                    grouped = working_df.groupby(id_col)[src]
                    if op == "rolling_mean":
                        series = grouped.transform(lambda s: s.rolling(window, min_periods=min_periods).mean())
                    elif op == "rolling_std":
                        series = grouped.transform(lambda s: s.rolling(window, min_periods=min_periods).std())
                    elif op == "rolling_max":
                        series = grouped.transform(lambda s: s.rolling(window, min_periods=min_periods).max())
                    elif op == "rolling_min":
                        series = grouped.transform(lambda s: s.rolling(window, min_periods=min_periods).min())
                else:
                    rolling_obj = working_df[src].rolling(window, min_periods=min_periods)
                    if op == "rolling_mean":
                        series = rolling_obj.mean()
                    elif op == "rolling_std":
                        series = rolling_obj.std()
                    elif op == "rolling_max":
                        series = rolling_obj.max()
                    elif op == "rolling_min":
                        series = rolling_obj.min()
            elif op == "lag":
                periods = params.get("periods", 1)
                if id_col and id_col in working_df.columns:
                    series = working_df.groupby(id_col)[src].shift(periods)
                else:
                    series = working_df[src].shift(periods)
            elif op == "diff":
                periods = params.get("periods", 1)
                if id_col and id_col in working_df.columns:
                    series = working_df.groupby(id_col)[src].diff(periods)
                else:
                    series = working_df[src].diff(periods)
            elif op == "ewm_mean":
                span = params.get("span", 5)
                if id_col and id_col in working_df.columns:
                    series = working_df.groupby(id_col)[src].transform(lambda s: s.ewm(span=span).mean())
                else:
                    series = working_df[src].ewm(span=span).mean()
            else:
                raise FeatureSchemaMismatchError(f"지원하지 않는 Feature 연산(operation)입니다: '{op}'")

            # Enforce missing value policy directly on computed series
            if mv_policy == "drop":
                nan_mask = series.isna()
                missing_drop_mask |= nan_mask
            elif mv_policy == "fill_zero":
                series = series.fillna(0.0)
            elif mv_policy == "ffill":
                # Forward-fill computed series within asset boundaries without reverting to raw source
                if id_col and id_col in working_df.columns:
                    series = series.groupby(working_df[id_col], sort=False).ffill()
                else:
                    series = series.ffill()
                series = series.fillna(0.0)
            elif mv_policy == "error":
                if series.isna().any():
                    raise FeatureDatasetIntegrityError(
                        f"Feature '{item.feature_name}'에 결측값(NaN)이 존재합니다 (missing_value_policy='error')."
                    )
            else:
                raise FeatureSchemaMismatchError(
                    f"지원하지 않는 missing_value_policy입니다: '{mv_policy}'. (허용: drop, fill_zero, ffill, error)"
                )

            computed_df[item.feature_name] = series.astype(float)

        return computed_df, missing_drop_mask

    def _generate_labels_and_exclusion_mask(
        self,
        working_df: pd.DataFrame,
        fail_df: pd.DataFrame,
        label_schema: LabelSchemaSpec,
        id_col: str | None,
        time_col: str | None,
        failure_source_mode: str = "external_dataset",
    ) -> tuple[pd.Series, pd.Series]:
        """Generate binary labels using [anchor - horizon, anchor) and mark [anchor, exclusion_end] active failures."""
        if not time_col or time_col not in working_df.columns:
            raise FeatureLabelAlignmentError(
                "호라이즌 라벨링에 필요한 Observation timestamp 컬럼이 없습니다."
            )

        labels_series = pd.Series(0, index=working_df.index, dtype=np.int64)
        active_failure_drop_mask = pd.Series(False, index=working_df.index)

        horizon_delta = pd.Timedelta(hours=label_schema.prediction_horizon_hours)

        # 1. External Failure Dataset mode
        if failure_source_mode == "external_dataset":
            if fail_df.empty:
                raise InsufficientTrainingDataError(
                    "외부 Failure Dataset에 유효한 failure event가 없습니다."
                )

            f_df = fail_df.copy()

            # Filter only active failure event rows if an indicator column exists
            failure_indicator_col = None
            for cand in ["Machine failure", "failure", "is_failure", "is_failed", "target"]:
                if cand in f_df.columns:
                    failure_indicator_col = cand
                    break

            if failure_indicator_col:
                f_df = f_df[f_df[failure_indicator_col] > 0]

            if f_df.empty:
                raise InsufficientTrainingDataError(
                    "외부 Failure Dataset에 활성 failure event가 없습니다."
                )

            # Remove degradation_start leakage columns
            for deg_col in ["degradation_start", "degradation_started_at", "period_start"]:
                if deg_col in f_df.columns:
                    f_df = f_df.drop(columns=[deg_col])

            # Strict anchor column check
            anchor_col = label_schema.anchor
            if anchor_col not in f_df.columns:
                raise FeatureSchemaMismatchError(
                    f"Label Schema가 선언한 anchor 컬럼 '{label_schema.anchor}'이 Failure 데이터셋에 없습니다."
                )

            f_df[anchor_col] = canonicalize_timestamp_series(f_df[anchor_col], col_name=anchor_col)
            if f_df[anchor_col].isna().any():
                raise FeatureContractError("Failure 데이터셋의 anchor 타임스탬프에 유효하지 않은 값(NaT)이 포함되어 있습니다.")

            # Strict exclusion_end column check
            ex_end_col = label_schema.exclusion_end
            if ex_end_col:
                if ex_end_col not in f_df.columns:
                    raise FeatureSchemaMismatchError(
                        f"Label Schema가 선언한 exclusion_end 컬럼 '{label_schema.exclusion_end}'이 Failure 데이터셋에 없습니다."
                    )
                f_df[ex_end_col] = canonicalize_timestamp_series(f_df[ex_end_col], col_name=ex_end_col)
                if f_df[ex_end_col].isna().any():
                    raise FeatureContractError("Failure 데이터셋의 exclusion_end 타임스탬프에 유효하지 않은 값(NaT)이 포함되어 있습니다.")

                # Validate exclusion_end >= anchor
                invalid_intervals = f_df[f_df[ex_end_col] < f_df[anchor_col]]
                if not invalid_intervals.empty:
                    first_bad = invalid_intervals.iloc[0]
                    raise FeatureContractError(
                        f"Failure 이벤트의 exclusion_end('{first_bad[ex_end_col]}')가 anchor('{first_bad[anchor_col]}')보다 앞섭니다."
                    )

            # Strict Asset ID check
            if id_col and id_col in working_df.columns:
                fail_id_col = None
                for cand in [id_col, "asset_id", "machineID", "Product ID", "product_id", "UDI", "udi"]:
                    if cand in f_df.columns:
                        fail_id_col = cand
                        break

                if fail_id_col is None:
                    raise FeatureLabelAlignmentError(
                        "다중 설비 Observation에 대응할 Failure asset ID 컬럼이 Failure 데이터셋에 없습니다."
                    )

                observation_assets = set(working_df[id_col].dropna().astype(str))

                for _, row in f_df.iterrows():
                    raw_fail_asset = row.get(fail_id_col)
                    if pd.isna(raw_fail_asset) or str(raw_fail_asset).strip() == "":
                        raise FeatureLabelAlignmentError("Failure 데이터셋의 이벤트 행에 asset ID 값이 누락되었습니다.")

                    fail_asset_str = str(raw_fail_asset)
                    if fail_asset_str not in observation_assets:
                        raise FeatureLabelAlignmentError(
                            f"Failure event의 asset '{fail_asset_str}'이 Observation Dataset에 존재하지 않습니다."
                        )

                    f_time = row[anchor_col]
                    h_start = f_time - horizon_delta
                    asset_mask = (working_df[id_col].astype(str) == fail_asset_str)

                    pos_mask = asset_mask & (working_df[time_col] >= h_start) & (working_df[time_col] < f_time)
                    labels_series.loc[pos_mask] = 1

                    if ex_end_col:
                        ex_end = row[ex_end_col]
                        ex_mask = asset_mask & (working_df[time_col] >= f_time) & (working_df[time_col] <= ex_end)
                    else:
                        ex_mask = asset_mask & (working_df[time_col] == f_time)
                    active_failure_drop_mask |= ex_mask
            else:
                # Single asset dataset
                for _, row in f_df.iterrows():
                    f_time = row[anchor_col]
                    h_start = f_time - horizon_delta
                    asset_mask = pd.Series(True, index=working_df.index)

                    pos_mask = asset_mask & (working_df[time_col] >= h_start) & (working_df[time_col] < f_time)
                    labels_series.loc[pos_mask] = 1

                    if ex_end_col:
                        ex_end = row[ex_end_col]
                        ex_mask = asset_mask & (working_df[time_col] >= f_time) & (working_df[time_col] <= ex_end)
                    else:
                        ex_mask = asset_mask & (working_df[time_col] == f_time)
                    active_failure_drop_mask |= ex_mask

            return labels_series, active_failure_drop_mask

        # 2. Embedded Observation mode
        elif failure_source_mode == "embedded_observation":
            failure_indicator_col = None
            for cand in ["Machine failure", "failure", "is_failure", "target"]:
                if cand in working_df.columns:
                    failure_indicator_col = cand
                    break

            if failure_indicator_col is None:
                raise FeatureContractError(
                    "embedded_observation 모드이지만 Observation 데이터셋에 유효한 failure indicator 컬럼이 없습니다."
                )

            fail_indices = working_df.index[working_df[failure_indicator_col] > 0].tolist()
            if not fail_indices:
                raise InsufficientTrainingDataError(
                    "내장 failure indicator에 활성 failure event가 0건입니다."
                )

            for f_idx in fail_indices:
                f_time = working_df[time_col].iloc[f_idx]
                if pd.isna(f_time):
                    raise FeatureLabelAlignmentError(
                        "내장 failure event의 timestamp가 유효하지 않습니다."
                    )

                h_start = f_time - horizon_delta

                if id_col and id_col in working_df.columns:
                    target_asset = str(working_df[id_col].iloc[f_idx])
                    asset_mask = (working_df[id_col].astype(str) == target_asset)
                else:
                    asset_mask = pd.Series(True, index=working_df.index)

                pos_mask = asset_mask & (working_df[time_col] >= h_start) & (working_df[time_col] < f_time)
                labels_series.loc[pos_mask] = 1

                ex_mask = asset_mask & (working_df[time_col] == f_time)
                active_failure_drop_mask |= ex_mask

            return labels_series, active_failure_drop_mask

        else:
            raise FeatureContractError(f"지원하지 않는 failure_source_mode입니다: '{failure_source_mode}'")

    def execute_feature(self, request: FeatureRequest, request_id: str | None = None) -> FeatureResponse:
        """Execute Feature Dataset generation pipeline and publish immutable bundle."""
        active_req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        run_id = f"feat-{uuid.uuid4().hex[:8]}"

        logger.info(
            f"[FeatureService] Starting Feature run {run_id} for dataset={request.dataset_id}:{request.dataset_version}, "
            f"plan={request.preprocessing_plan_id}:{request.preprocessing_plan_version}, "
            f"mode={request.failure_source_mode}"
        )

        # 1. Load Preprocessing Plan via Repository
        try:
            plan = self.preprocessing_repo.load_plan(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                preprocessing_plan_id=request.preprocessing_plan_id,
            )
        except DatasetNotFoundError as exc:
            raise FeatureInputNotFoundError(f"Preprocessing Plan을 찾을 수 없습니다: {exc}") from exc
        except Exception as exc:
            if "DatasetContractError" in type(exc).__name__:
                raise FeatureContractError(f"Preprocessing Plan 로드 실패: {exc}") from exc
            raise

        # Validate matching Plan IDs and versions
        if plan.get("preprocessing_plan_id") != request.preprocessing_plan_id:
            raise FeatureContractError(
                f"로드된 Plan ID ('{plan.get('preprocessing_plan_id')}')가 "
                f"요청 ID ('{request.preprocessing_plan_id}')와 일치하지 않습니다."
            )
        if plan.get("preprocessing_plan_version") != request.preprocessing_plan_version:
            raise FeatureContractError(
                f"로드된 Plan 버전 ('{plan.get('preprocessing_plan_version')}')가 "
                f"요청 버전 ('{request.preprocessing_plan_version}')와 일치하지 않습니다."
            )

        plan_dir = self.preprocessing_repo.get_dataset_plan_dir(request.dataset_id, request.dataset_version)
        plan_filename = f"{request.preprocessing_plan_id}.json" if not request.preprocessing_plan_id.endswith(".json") else request.preprocessing_plan_id
        plan_file = plan_dir / plan_filename
        plan_sha256 = compute_file_sha256(plan_file)
        plan_uri = self.feature_repo.get_logical_uri(plan_file)

        # 2. Strictly Resolve and validate Versioned Observation Dataset
        resolved_obs = self.feature_input_resolver.resolve_dataset(
            dataset_type="observation",
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
        )

        # Cross-validate Plan provenance against resolved Observation dataset
        plan_ds_id = plan.get("dataset_id")
        plan_ds_ver = plan.get("dataset_version")
        plan_src_sha256 = plan.get("source_dataset_sha256")

        if plan_ds_id != resolved_obs.dataset_id:
            raise FeatureContractError(
                f"Preprocessing Plan의 dataset_id('{plan_ds_id}')가 "
                f"Observation Dataset ID('{resolved_obs.dataset_id}')와 일치하지 않습니다."
            )
        if plan_ds_ver != resolved_obs.dataset_version:
            raise FeatureContractError(
                f"Preprocessing Plan의 dataset_version('{plan_ds_ver}')이 "
                f"Observation Dataset 버전('{resolved_obs.dataset_version}')과 일치하지 않습니다."
            )
        if plan_src_sha256 and plan_src_sha256.lower() != resolved_obs.payload_sha256.lower():
            raise FeatureContractError(
                f"Preprocessing Plan의 source_dataset_sha256('{plan_src_sha256}')과 "
                f"실제 Observation payload SHA-256('{resolved_obs.payload_sha256}')이 일치하지 않습니다."
            )

        obs_df = self._load_dataframe(resolved_obs.payload_path)
        if obs_df.empty:
            raise InsufficientTrainingDataError("Observation 데이터셋이 비어 있습니다 (0행).")

        # 3. Handle Failure Dataset according to failure_source_mode
        resolved_fail: ResolvedFeatureInput | None = None
        if request.failure_source_mode == "external_dataset":
            if not request.failure_dataset_id or not request.failure_dataset_version:
                raise FeatureContractError("external_dataset 모드에서는 failure_dataset_id 및 failure_dataset_version이 필수입니다.")
            resolved_fail = self.feature_input_resolver.resolve_dataset(
                dataset_type="failure",
                dataset_id=request.failure_dataset_id,
                dataset_version=request.failure_dataset_version,
            )
            fail_df = self._load_dataframe(resolved_fail.payload_path)
        elif request.failure_source_mode == "embedded_observation":
            resolved_fail = None
            fail_df = pd.DataFrame()
        else:
            raise FeatureContractError(f"지원하지 않는 failure_source_mode입니다: '{request.failure_source_mode}'")

        # 4. Resolve Feature Schema & Label Schema from files
        feature_schema = self.feature_schema_provider.get_feature_schema(
            schema_version=request.feature_schema_version,
        )
        feature_schema_sha256 = feature_schema.compute_checksum()
        feature_schema_uri = self.feature_repo.get_logical_uri(feature_schema.schema_file_path) if feature_schema.schema_file_path else f"schemas/features/{request.feature_schema_version}.json"

        label_schema = self.label_schema_provider.get_label_schema(
            schema_version=request.label_schema_version,
            requested_horizon_hours=request.prediction_horizon_hours,
        )
        label_schema_sha256 = label_schema.compute_checksum()
        label_schema_uri = self.feature_repo.get_logical_uri(label_schema.schema_file_path) if label_schema.schema_file_path else f"schemas/labels/{request.label_schema_version}.json"

        # 5. Prepare Canonical Working DataFrame & Validate Asset Identity / Timestamps
        plan_id_col = plan.get("id_column")
        plan_time_col = plan.get("time_column")
        context = {
            "dataset_id": request.dataset_id,
            "dataset_version": request.dataset_version,
            "preprocessing_plan_id": request.preprocessing_plan_id,
            "preprocessing_plan_version": request.preprocessing_plan_version,
            "request_id": active_req_id,
        }
        working_df, id_col, time_col = self._prepare_canonical_working_df(
            obs_df=obs_df,
            id_col=plan_id_col,
            time_col=plan_time_col,
            context=context,
        )

        # 6. Build Canonical Deterministic Fingerprint
        fingerprint = {
            "observation_dataset_id": resolved_obs.dataset_id,
            "observation_dataset_version": resolved_obs.dataset_version,
            "observation_manifest_sha256": resolved_obs.manifest_sha256,
            "observation_payload_sha256": resolved_obs.payload_sha256,
            "failure_source_mode": request.failure_source_mode,
            "failure_dataset_id": resolved_fail.dataset_id if resolved_fail else None,
            "failure_dataset_version": resolved_fail.dataset_version if resolved_fail else None,
            "failure_manifest_sha256": resolved_fail.manifest_sha256 if resolved_fail else None,
            "failure_payload_sha256": resolved_fail.payload_sha256 if resolved_fail else None,
            "preprocessing_plan_id": request.preprocessing_plan_id,
            "preprocessing_plan_version": request.preprocessing_plan_version,
            "preprocessing_plan_sha256": plan_sha256,
            "feature_schema_version": request.feature_schema_version,
            "feature_schema_sha256": feature_schema_sha256,
            "label_schema_version": request.label_schema_version,
            "label_schema_sha256": label_schema_sha256,
            "prediction_horizon_hours": request.prediction_horizon_hours,
            "feature_engine_version": "1.0",
        }
        feature_dataset_version = compute_feature_dataset_version(fingerprint)

        # 7. Check existing bundle reuse (Immutable Bundle Policy)
        existing_bundle = self.feature_repo.find_feature_bundle(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            feature_dataset_version=feature_dataset_version,
            expected_fingerprint=fingerprint,
        )
        if existing_bundle is not None:
            logger.info(f"[FeatureService] Reusing existing valid Feature Bundle {feature_dataset_version}")
            return FeatureResponse(
                request_id=active_req_id,
                run_id=run_id,
                status="succeeded",
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                failure_source_mode=request.failure_source_mode,
                failure_dataset_id=request.failure_dataset_id if request.failure_source_mode == "external_dataset" else None,
                failure_dataset_version=request.failure_dataset_version if request.failure_source_mode == "external_dataset" else None,
                preprocessing_plan_id=request.preprocessing_plan_id,
                preprocessing_plan_version=request.preprocessing_plan_version,
                feature_schema_version=request.feature_schema_version,
                label_schema_version=request.label_schema_version,
                outputs=FeatureOutputsPayload(
                    feature_dataset_version=existing_bundle.feature_dataset_version,
                    row_count=existing_bundle.row_count,
                    feature_count=existing_bundle.feature_count,
                    features_uri=existing_bundle.features_uri,
                    labels_uri=existing_bundle.labels_uri,
                    metadata_uri=existing_bundle.metadata_uri,
                ),
            )

        # 8. Compute Features & Missing Masks
        computed_features_df, missing_drop_mask = self._compute_features_and_missing_masks(
            working_df=working_df,
            feature_items=feature_schema.features,
            id_col=id_col,
        )

        # 9. Compute Labels & Active Failure Drop Mask
        labels_series, active_failure_drop_mask = self._generate_labels_and_exclusion_mask(
            working_df=working_df,
            fail_df=fail_df,
            label_schema=label_schema,
            id_col=id_col,
            time_col=time_col,
            failure_source_mode=request.failure_source_mode,
        )

        # 10. Align Surviving Rows across Features, Labels, and Row Metadata
        combined_drop_mask = missing_drop_mask | active_failure_drop_mask
        keep_mask = ~combined_drop_mask

        surviving_features_df = computed_features_df[keep_mask].copy()
        surviving_labels_series = labels_series[keep_mask].copy()
        surviving_working_df = working_df[keep_mask].copy()

        ordered_feature_names = feature_schema.feature_names
        features_matrix = surviving_features_df[ordered_feature_names].to_numpy(dtype=np.float64)
        labels_array = surviving_labels_series.to_numpy(dtype=np.int64)

        surviving_count = len(surviving_working_df)
        if features_matrix.shape[0] != surviving_count or labels_array.shape[0] != surviving_count:
            raise FeatureLabelAlignmentError("Feature matrix, Labels, row_metadata 행 정렬에 실패했습니다.")

        if surviving_count == 0:
            raise InsufficientTrainingDataError("모든 행이 제외 또는 결측치 처리되어 유효한 학습 데이터가 0행입니다.")

        # Validate label classes for official prediction task
        if label_schema.prediction_task == "binary_failure_within_horizon":
            unique_labels = set(np.unique(labels_array).tolist())
            if unique_labels != {0, 1}:
                raise InsufficientTrainingDataError(
                    "binary_failure_within_horizon 학습에는 label 0과 1이 모두 필요합니다."
                )

        # Build row metadata (strictly preserving validated canonical asset_id)
        row_metadata = []
        for idx in range(surviving_count):
            asset_val = str(surviving_working_df[id_col].iloc[idx])
            time_val = str(surviving_working_df[time_col].iloc[idx])
            row_metadata.append({"asset_id": asset_val, "timestamp": time_val})

        # 11. Build Complete Provenance Metadata
        provenance_meta = {
            "observation_dataset_id": resolved_obs.dataset_id,
            "observation_dataset_version": resolved_obs.dataset_version,
            "observation_manifest_sha256": resolved_obs.manifest_sha256,
            "observation_manifest_uri": resolved_obs.manifest_uri,
            "observation_payload_sha256": resolved_obs.payload_sha256,
            "observation_payload_uri": resolved_obs.payload_uri,
            "failure_source_mode": request.failure_source_mode,
            "failure_dataset_id": resolved_fail.dataset_id if resolved_fail else None,
            "failure_dataset_version": resolved_fail.dataset_version if resolved_fail else None,
            "failure_manifest_sha256": resolved_fail.manifest_sha256 if resolved_fail else None,
            "failure_manifest_uri": resolved_fail.manifest_uri if resolved_fail else None,
            "failure_payload_sha256": resolved_fail.payload_sha256 if resolved_fail else None,
            "failure_payload_uri": resolved_fail.payload_uri if resolved_fail else None,
            "preprocessing_plan_id": request.preprocessing_plan_id,
            "preprocessing_plan_version": request.preprocessing_plan_version,
            "preprocessing_plan_sha256": plan_sha256,
            "preprocessing_plan_uri": plan_uri,
            "feature_schema_version": request.feature_schema_version,
            "feature_schema_sha256": feature_schema_sha256,
            "feature_schema_uri": feature_schema_uri,
            "label_schema_version": request.label_schema_version,
            "label_schema_sha256": label_schema_sha256,
            "label_schema_uri": label_schema_uri,
            "prediction_horizon_hours": request.prediction_horizon_hours,
            "feature_engine_version": "1.0",
        }

        # 12. Publish Bundle Atomically
        published = self.feature_repo.publish_bundle(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            feature_dataset_version=feature_dataset_version,
            features=features_matrix,
            labels=labels_array,
            feature_columns=ordered_feature_names,
            row_metadata=row_metadata,
            fingerprint=fingerprint,
            provenance_metadata=provenance_meta,
            run_id=run_id,
        )

        return FeatureResponse(
            request_id=active_req_id,
            run_id=run_id,
            status="succeeded",
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            failure_source_mode=request.failure_source_mode,
            failure_dataset_id=request.failure_dataset_id if request.failure_source_mode == "external_dataset" else None,
            failure_dataset_version=request.failure_dataset_version if request.failure_source_mode == "external_dataset" else None,
            preprocessing_plan_id=request.preprocessing_plan_id,
            preprocessing_plan_version=request.preprocessing_plan_version,
            feature_schema_version=request.feature_schema_version,
            label_schema_version=request.label_schema_version,
            outputs=FeatureOutputsPayload(
                feature_dataset_version=published.feature_dataset_version,
                row_count=published.row_count,
                feature_count=published.feature_count,
                features_uri=published.features_uri,
                labels_uri=published.labels_uri,
                metadata_uri=published.metadata_uri,
            ),
        )
