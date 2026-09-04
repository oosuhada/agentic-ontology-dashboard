"""Service for extracting label-free 2D float64 Runtime Features for inference."""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.feature.feature_schema_provider import (
    FeatureItem,
    FeatureSchemaProvider,
    FeatureSchemaSpec,
)
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineAssetIdColumnMissingError,
    PipelineAssetIdMissingError,
    PipelineAssetIdValueMissingError,
    PipelineFeatureMetadataAlignmentError,
    PipelineFeatureSchemaMismatchError,
    PipelineHistoryInsufficientError,
    PipelineModelFeatureMissingValueHandlingNotImplementedError,
    PipelineRuntimeFeatureFailedError,
    PipelineSensorValueMissingError,
    PipelineTimestampInvalidError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    RuntimeFeatureRowMetadata,
)
from systems.generator.app.runtime_pipeline.cnc_temporal_features import (
    SUPPORTED_KIND as CNC_TEMPORAL_KIND,
    derive_cnc_temporal_feature_rows,
)
from systems.generator.app.runtime_pipeline.compressor_temporal_features import (
    SUPPORTED_KIND as COMPRESSOR_TEMPORAL_KIND,
    derive_compressor_temporal_feature_rows,
)

logger = logging.getLogger(__name__)


@dataclass
class RuntimeFeatureBundle:
    """In-memory bundle returned from computation before atomic persistence."""
    features: np.ndarray
    feature_columns: list[str]
    row_metadata: list[RuntimeFeatureRowMetadata]
    runtime_feature_version: str
    feature_schema_version: str
    dataset_id: str
    dataset_version: str
    asset_history_status: dict[str, dict[str, Any]] = field(default_factory=dict)


class RuntimeFeatureService:
    """Extracts label-free numeric feature matrices matching Model Artifact recipe contracts."""

    def __init__(
        self,
        schema_provider: Optional[FeatureSchemaProvider] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.schema_provider = schema_provider or FeatureSchemaProvider()
        if cache_dir is None:
            self.cache_dir = PATHS.runtime_feature_root
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_id_and_time_columns(
        self,
        df: pd.DataFrame,
        id_column: Optional[str] = None,
        time_column: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Identify asset ID and timestamp columns with fail-closed missing ID check."""
        target_id_col = id_column
        if not target_id_col:
            candidates = [c for c in ("asset_id", "Product ID", "UDI", "equipment_id", "machine_id") if c in df.columns]
            if candidates:
                target_id_col = candidates[0]
            else:
                raise PipelineAssetIdColumnMissingError(
                    "데이터셋에 설비 식별자(asset_id) 컬럼이 누락되었습니다. 임의의 default_asset 대체는 금지됩니다.",
                    details=[{"available_columns": list(df.columns)}],
                    retryable=False,
                )

        if not target_id_col or target_id_col not in df.columns:
            raise PipelineAssetIdColumnMissingError(
                f"데이터셋에 설비 식별자 컬럼 '{target_id_col}'이 존재하지 않습니다.",
                details=[{"id_column": target_id_col, "available_columns": list(df.columns)}],
                retryable=False,
            )

        # Strict validation: reject any null, nan, empty string, whitespace, "null", "none"
        raw_id_series = df[target_id_col]
        invalid_mask = (
            raw_id_series.isna()
            | raw_id_series.astype(str).str.strip().str.lower().isin(["", "null", "none", "nan"])
        )
        if invalid_mask.any():
            invalid_indices = [int(i) for i in df.index[invalid_mask]]
            raise PipelineAssetIdValueMissingError(
                f"설비 식별자 컬럼 '{target_id_col}'에 누락/무효 값(None, 빈문자열, null, none)이 {len(invalid_indices)}건 존재합니다.",
                details=[{
                    "id_column": target_id_col,
                    "invalid_row_count": len(invalid_indices),
                    "sample_row_indexes": invalid_indices[:10],
                }],
                retryable=False,
            )

        target_time_col = time_column
        if not target_time_col:
            for candidate in ("timestamp", "observed_at", "time", "date", "datetime"):
                if candidate in df.columns:
                    target_time_col = candidate
                    break

        return target_id_col, target_time_col

    def _calculate_feature_series_for_asset(
        self,
        asset_id: str,
        series: pd.Series,
        item: FeatureItem,
        time_series: Optional[pd.Series] = None,
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
        feature_schema_version: Optional[str] = None,
    ) -> pd.Series:
        """Compute single feature series within an isolated asset group with fail-closed missing value checks."""
        # Raw sensor value missing check
        if series.isna().any():
            missing_indices = [int(i) for i in series.index[series.isna()]]
            missing_timestamps = (
                list(time_series.loc[missing_indices].astype(str)) if time_series is not None else []
            )
            raise PipelineSensorValueMissingError(
                f"원본 센서 필드 '{item.source_field}'에 결측치(NaN/null)가 {len(missing_indices)}건 발생했습니다.",
                details=[{
                    "asset_id": str(asset_id),
                    "source_field": item.source_field,
                    "missing_count": len(missing_indices),
                    "missing_row_indices": missing_indices[:10],
                    "missing_timestamps": missing_timestamps[:10],
                }],
                retryable=False,
            )

        numeric_series = pd.to_numeric(series, errors="coerce")
        if numeric_series.isna().any():
            missing_indices = [int(i) for i in numeric_series.index[numeric_series.isna()]]
            raise PipelineSensorValueMissingError(
                f"원본 센서 필드 '{item.source_field}'에 숫자로 변환할 수 없는 유효하지 않은 값이 포함되어 있습니다.",
                details=[{"source_field": item.source_field, "missing_row_indices": missing_indices[:10]}],
                retryable=False,
            )

        op = item.operation
        params = item.parameters or {}
        col_name = item.feature_name
        src_col = item.source_field
        mv_policy = item.missing_value_policy

        if op == "raw":
            res = numeric_series
        elif op in ("lag", "diff"):
            periods = int(params.get("periods", 1))
            if op == "lag":
                res = numeric_series.shift(periods)
            else:
                res = numeric_series.diff(periods)
        elif "rolling" in op:
            window = int(params.get("window", 3))
            min_p = int(params.get("min_periods", 1))
            r = numeric_series.rolling(window=window, min_periods=min_p)
            if op == "rolling_mean":
                res = r.mean()
            elif op == "rolling_std":
                res = r.std()
            elif op == "rolling_max":
                res = r.max()
            elif op == "rolling_min":
                res = r.min()
            else:
                res = numeric_series
        elif op == "ewm_mean":
            span = int(params.get("span", 3))
            res = numeric_series.ewm(span=span, adjust=False).mean()
        else:
            res = numeric_series

        # Fail-closed if NaN or Inf occurs
        nan_or_inf_mask = res.isna() | np.isinf(res)
        if nan_or_inf_mask.any():
            missing_indices = [int(i) for i in res.index[nan_or_inf_mask]]
            missing_timestamps = (
                list(time_series.loc[missing_indices].astype(str)) if time_series is not None else []
            )
            raise PipelineModelFeatureMissingValueHandlingNotImplementedError(
                f"Feature '{col_name}' 계산 중 결측값/무한대(NaN/Inf)가 {len(missing_indices)}건 발생했습니다. "
                f"선언된 결측 처리 정책 '{mv_policy}'은 미구현 상태입니다.",
                details=[{
                    "model_id": model_id,
                    "model_version": model_version,
                    "feature_schema_version": feature_schema_version,
                    "feature_name": col_name,
                    "source_field": src_col,
                    "operation": op,
                    "missing_value_policy": mv_policy,
                    "asset_id": str(asset_id),
                    "missing_count": len(missing_indices),
                    "missing_row_indices": missing_indices[:10],
                    "missing_timestamps": missing_timestamps[:10],
                }],
                retryable=False,
            )

        return res.astype("float64")

    def extract_and_publish(
        self,
        *,
        preprocessed_df: pd.DataFrame,
        feature_schema_dict: dict[str, Any],
        history_requirement_dict: dict[str, Any],
        model_id: Optional[str] = None,
        model_version: Optional[str] = None,
        id_column: Optional[str] = None,
        time_column: Optional[str] = None,
        dataset_id: str = "canonical-ai4i-v1",
        dataset_version: str = "canonical-ai4i-physics-v3.1",
        run_id: Optional[str] = None,
    ) -> tuple[RuntimeFeatureBundle, ArtifactReference]:
        """Compute runtime feature matrix with equipment-isolated timeseries and publish npy artifact."""
        if preprocessed_df.empty:
            raise PipelineRuntimeFeatureFailedError("전처리된 데이터프레임이 비어 있습니다.")

        # 1. Validate asset ID and sort deterministically
        id_col, time_col = self._resolve_id_and_time_columns(preprocessed_df, id_column, time_column)

        df_sorted = preprocessed_df.copy()
        if time_col and time_col in df_sorted.columns:
            raw_ts = df_sorted[time_col]
            if raw_ts.isna().any() or raw_ts.astype(str).str.strip().isin(["", "null", "none", "nan"]).any():
                raise PipelineTimestampInvalidError(
                    f"타임스탬프 컬럼 '{time_col}'에 결측치 또는 유효하지 않은 값이 포함되어 있습니다.",
                    details=[{"time_column": time_col}],
                    retryable=False,
                )
            try:
                converted_ts = pd.to_datetime(raw_ts, utc=True)
            except Exception as exc:
                raise PipelineTimestampInvalidError(
                    f"타임스탬프 컬럼 '{time_col}' 파싱 실패: {exc}",
                    details=[{"time_column": time_col, "error": str(exc)}],
                    retryable=False,
                ) from exc

            if converted_ts.isna().any():
                raise PipelineTimestampInvalidError(
                    f"타임스탬프 변환 후 NaT가 발견되었습니다: 컬럼 '{time_col}'",
                    details=[{"time_column": time_col}],
                    retryable=False,
                )
            df_sorted[time_col] = converted_ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Check for duplicates on [asset_id, timestamp]
            dups = df_sorted.duplicated(subset=[id_col, time_col], keep=False)
            if dups.any():
                dup_rows = df_sorted[dups]
                sample_asset = str(dup_rows[id_col].iloc[0])
                sample_ts = str(dup_rows[time_col].iloc[0])
                raise PipelineTimestampInvalidError(
                    f"동일 설비 '{sample_asset}' 및 시각 '{sample_ts}'에 대한 중복 관측 행이 {dups.sum()}건 존재합니다. 계약상 중복 병합 정책이 정의되지 않아 처리를 중단합니다.",
                    details=[{"asset_id": sample_asset, "timestamp": sample_ts, "duplicate_count": int(dups.sum())}],
                    retryable=False,
                )

            df_sorted = df_sorted.sort_values(by=[id_col, time_col], kind="stable").reset_index(drop=True)
        else:
            df_sorted = df_sorted.sort_values(by=[id_col], kind="stable").reset_index(drop=True)

        # 2. Per-equipment History Requirement evaluation
        engineering = feature_schema_dict.get("feature_engineering") or {}
        min_rows = int(history_requirement_dict.get("minimum_history_rows", 1))
        if engineering.get("kind") in {
            CNC_TEMPORAL_KIND,
            COMPRESSOR_TEMPORAL_KIND,
        }:
            prior_required = int(
                (engineering.get("runtime_context") or {}).get(
                    "recent_history_rows_required", 35
                )
            )
            min_rows = max(min_rows, prior_required + 1)
        grouped_counts = df_sorted.groupby(id_col).size().to_dict()
        asset_history_status: dict[str, dict[str, Any]] = {}
        ready_count = 0

        for asset_key, count in grouped_counts.items():
            is_ready = bool(count >= min_rows)
            if is_ready:
                ready_count += 1
            asset_history_status[str(asset_key)] = {
                "ready": is_ready,
                "count": int(count),
                "minimum_history_rows": min_rows,
            }

        # If ALL equipments have insufficient history -> fail stage
        if ready_count == 0:
            raise PipelineHistoryInsufficientError(
                f"모든 설비의 관측 이력 행 수가 부족합니다 (요구치={min_rows}): {grouped_counts}",
                details=[{"minimum_history_rows": min_rows, "history_counts": grouped_counts}],
                retryable=False,
            )

        req_cols = history_requirement_dict.get("required_columns", [])
        missing_req = [c for c in req_cols if c not in df_sorted.columns]
        if missing_req:
            raise PipelineFeatureSchemaMismatchError(
                f"Model Artifact가 요구하는 필수 센서 컬럼이 누락되었습니다: {missing_req}",
                details=[{"missing_columns": missing_req}],
                retryable=False,
            )

        temporal_deriver = {
            CNC_TEMPORAL_KIND: derive_cnc_temporal_feature_rows,
            COMPRESSOR_TEMPORAL_KIND: derive_compressor_temporal_feature_rows,
        }.get(engineering.get("kind"))
        if temporal_deriver is not None:
            if not time_col:
                raise PipelineTimestampInvalidError(
                    "Temporal Runtime Feature에는 observed_at/timestamp 컬럼이 필수입니다.",
                    retryable=False,
                )
            try:
                features_matrix, feature_cols, temporal_metadata = (
                    temporal_deriver(
                        df_sorted,
                        feature_schema=feature_schema_dict,
                        id_column=id_col,
                        time_column=time_col,
                    )
                )
            except Exception as exc:
                raise PipelineRuntimeFeatureFailedError(
                    f"Temporal Runtime Feature 계산 실패: {exc}",
                    details=[{
                        "model_id": model_id,
                        "model_version": model_version,
                        "feature_schema_version": feature_schema_dict.get("schema_version")
                        or feature_schema_dict.get("feature_schema_version"),
                    }],
                    retryable=False,
                ) from exc

            row_metadata = [
                RuntimeFeatureRowMetadata(
                    row_index=index,
                    asset_id=asset_id,
                    observed_at=observed_at,
                )
                for index, (asset_id, observed_at) in enumerate(temporal_metadata)
            ]
            feat_hash = hashlib.sha256(features_matrix.tobytes()).hexdigest()[:16]
            bundle = RuntimeFeatureBundle(
                features=features_matrix,
                feature_columns=feature_cols,
                row_metadata=row_metadata,
                runtime_feature_version=f"runtime-feat-{feat_hash}",
                feature_schema_version=str(
                    feature_schema_dict.get("schema_version")
                    or feature_schema_dict.get("feature_schema_version")
                    or "unknown"
                ),
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                asset_history_status=asset_history_status,
            )
            artifact_ref = self._persist_feature_artifact(
                bundle, model_id=model_id, run_id=run_id
            )
            return bundle, artifact_ref

        # 3. Parse feature schema
        try:
            schema_spec: FeatureSchemaSpec = self.schema_provider.parse_schema_dict(feature_schema_dict)
        except Exception as exc:
            raise PipelineFeatureSchemaMismatchError(f"Feature Schema 유효성 검증 실패: {exc}") from exc

        # 4. Calculate features column by column with strict equipment isolation
        feature_cols: list[str] = []
        feature_data_dict: dict[str, np.ndarray] = {}

        for item in schema_spec.features:
            col_name = item.feature_name
            src_col = item.source_field

            if src_col not in df_sorted.columns:
                raise PipelineFeatureSchemaMismatchError(
                    f"Feature '{col_name}'의 원본 필드 '{src_col}'이 데이터셋에 없습니다.",
                    details=[{"feature_name": col_name, "source_field": src_col}],
                    retryable=False,
                )

            # Isolated per asset calculation
            res_series_list: list[pd.Series] = []
            for asset_id_val, group in df_sorted.groupby(id_col, sort=False):
                time_s = group[time_col] if time_col and time_col in group.columns else None
                computed = self._calculate_feature_series_for_asset(
                    asset_id=str(asset_id_val),
                    series=group[src_col],
                    item=item,
                    time_series=time_s,
                    model_id=model_id,
                    model_version=model_version,
                    feature_schema_version=schema_spec.schema_version,
                )
                res_series_list.append(computed)

            combined_series = pd.concat(res_series_list).sort_index()
            feature_data_dict[col_name] = combined_series.values.astype(np.float64)
            feature_cols.append(col_name)

        # 5. Assemble 2D float64 matrix
        matrix_list = [feature_data_dict[c] for c in feature_cols]
        features_matrix = np.column_stack(matrix_list).astype(np.float64)

        if np.isnan(features_matrix).any() or np.isinf(features_matrix).any():
            raise PipelineModelFeatureMissingValueHandlingNotImplementedError(
                "Feature 행렬에 결측값 또는 무한대(NaN/Inf)가 존재합니다. 조용한 0 치환은 금지됩니다.",
                details=[{
                    "model_id": model_id,
                    "model_version": model_version,
                    "feature_schema_version": schema_spec.schema_version,
                    "matrix_shape": list(features_matrix.shape),
                }],
                retryable=False,
            )

        # 6. Row metadata
        row_metadata: list[RuntimeFeatureRowMetadata] = []
        for idx in range(len(df_sorted)):
            row = df_sorted.iloc[idx]
            asset_val = str(row.get(id_col))
            ts_val = str(row.get(time_col)) if time_col else ""
            row_metadata.append(
                RuntimeFeatureRowMetadata(
                    row_index=idx,
                    asset_id=asset_val,
                    observed_at=ts_val,
                )
            )

        # Metadata alignment verification
        if features_matrix.shape[0] != len(row_metadata):
            raise PipelineFeatureMetadataAlignmentError(
                f"Feature 행렬 행 수({features_matrix.shape[0]})와 메타데이터 행 수({len(row_metadata)})가 불일치합니다.",
                details=[{"matrix_rows": features_matrix.shape[0], "metadata_rows": len(row_metadata)}],
                retryable=False,
            )

        feat_hash = hashlib.sha256(features_matrix.tobytes()).hexdigest()[:16]
        runtime_feature_version = f"runtime-feat-{feat_hash}"

        bundle = RuntimeFeatureBundle(
            features=features_matrix,
            feature_columns=feature_cols,
            row_metadata=row_metadata,
            runtime_feature_version=runtime_feature_version,
            feature_schema_version=schema_spec.schema_version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            asset_history_status=asset_history_status,
        )

        # 7. Atomic persistence
        artifact_ref = self._persist_feature_artifact(bundle, model_id=model_id, run_id=run_id)
        return bundle, artifact_ref

    def _persist_feature_artifact(
        self,
        bundle: RuntimeFeatureBundle,
        model_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> ArtifactReference:
        """Atomically persist features array as .npy file and return ArtifactReference."""
        target_dir = self.cache_dir
        if run_id:
            target_dir = self.cache_dir / run_id
            target_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"{model_id}_" if model_id else ""
        target_filename = f"{prefix}{bundle.runtime_feature_version}.npy"
        target_path = target_dir / target_filename

        tmp_path = target_dir / f".tmp_{uuid.uuid4().hex}_{target_filename}"
        with open(tmp_path, "wb") as f:
            np.save(f, bundle.features)

        sha256_hash = compute_file_sha256(tmp_path)
        size_bytes = tmp_path.stat().st_size

        if target_path.exists():
            os.replace(tmp_path, target_path)
        else:
            tmp_path.rename(target_path)

        return ArtifactReference(
            uri=str(target_path).replace("\\", "/"),
            sha256=sha256_hash,
            role="runtime_features",
            size_bytes=size_bytes,
        )

    def load_bundle_from_artifact(
        self,
        artifact_ref: ArtifactReference,
        preprocessed_df: pd.DataFrame,
        feature_schema_dict: dict[str, Any],
        id_column: Optional[str] = None,
        time_column: Optional[str] = None,
        dataset_id: str = "canonical-ai4i-v1",
        dataset_version: str = "canonical-ai4i-physics-v3.1",
    ) -> RuntimeFeatureBundle:
        """Reconstruct RuntimeFeatureBundle from a validated on-disk NPY file and preprocessed_df."""
        npy_path = Path(artifact_ref.uri)
        if not npy_path.exists() or not npy_path.is_file():
            raise PipelineRuntimeFeatureFailedError(f"Runtime Feature NPY 파일이 존재하지 않습니다: {npy_path}")

        actual_sha = compute_file_sha256(npy_path)
        if actual_sha != artifact_ref.sha256:
            raise PipelineRuntimeFeatureFailedError(
                f"Runtime Feature NPY 파일 체크섬 불일치: 기대={artifact_ref.sha256}, 실제={actual_sha}"
            )

        features_matrix = np.load(npy_path)

        id_col, time_col = self._resolve_id_and_time_columns(preprocessed_df, id_column, time_column)
        df_sorted = preprocessed_df.copy()
        if time_col and time_col in df_sorted.columns:
            converted_ts = pd.to_datetime(df_sorted[time_col], utc=True)
            df_sorted[time_col] = converted_ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            df_sorted = df_sorted.sort_values(by=[id_col, time_col], kind="stable")
        else:
            df_sorted = df_sorted.sort_values(by=[id_col], kind="stable")

        engineering = feature_schema_dict.get("feature_engineering") or {}
        temporal_deriver = {
            CNC_TEMPORAL_KIND: derive_cnc_temporal_feature_rows,
            COMPRESSOR_TEMPORAL_KIND: derive_compressor_temporal_feature_rows,
        }.get(engineering.get("kind"))
        if temporal_deriver is not None:
            if not time_col:
                raise PipelineTimestampInvalidError(
                    "Temporal Runtime Feature에는 observed_at/timestamp 컬럼이 필수입니다.",
                    retryable=False,
                )
            _, feature_cols, temporal_metadata = temporal_deriver(
                df_sorted,
                feature_schema=feature_schema_dict,
                id_column=id_col,
                time_column=time_col,
            )
            if features_matrix.shape[0] != len(temporal_metadata):
                raise PipelineFeatureMetadataAlignmentError(
                    "Temporal Feature 행렬과 최신 설비 메타데이터 행 수가 일치하지 않습니다.",
                    details=[{
                        "matrix_rows": int(features_matrix.shape[0]),
                        "metadata_rows": len(temporal_metadata),
                    }],
                    retryable=False,
                )
            row_metadata = [
                RuntimeFeatureRowMetadata(
                    row_index=index,
                    asset_id=asset_id,
                    observed_at=observed_at,
                )
                for index, (asset_id, observed_at) in enumerate(temporal_metadata)
            ]
            prior_required = int(
                (engineering.get("runtime_context") or {}).get(
                    "recent_history_rows_required", 35
                )
            )
            min_rows = prior_required + 1
            counts = df_sorted.groupby(id_col).size().to_dict()
            asset_history_status = {
                str(asset_id): {
                    "ready": bool(count >= min_rows),
                    "count": int(count),
                    "minimum_history_rows": min_rows,
                }
                for asset_id, count in counts.items()
            }
            schema_version = str(
                feature_schema_dict.get("schema_version")
                or feature_schema_dict.get("feature_schema_version")
                or "unknown"
            )
        else:
            schema_spec = self.schema_provider.parse_schema_dict(feature_schema_dict)
            feature_cols = [item.feature_name for item in schema_spec.features]

            row_metadata = []
            for idx in range(len(df_sorted)):
                row = df_sorted.iloc[idx]
                asset_val = str(row.get(id_col))
                ts_val = str(row.get(time_col)) if time_col else ""
                row_metadata.append(
                    RuntimeFeatureRowMetadata(
                        row_index=idx,
                        asset_id=asset_val,
                        observed_at=ts_val,
                    )
                )
            asset_history_status = {}
            schema_version = schema_spec.schema_version

        feat_hash = hashlib.sha256(features_matrix.tobytes()).hexdigest()[:16]
        runtime_feature_version = f"runtime-feat-{feat_hash}"

        return RuntimeFeatureBundle(
            features=features_matrix,
            feature_columns=feature_cols,
            row_metadata=row_metadata,
            runtime_feature_version=runtime_feature_version,
            feature_schema_version=schema_version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            asset_history_status=asset_history_status,
        )
