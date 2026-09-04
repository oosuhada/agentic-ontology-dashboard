"""
feature_label_service.py

담당 기능:
- 추출된 피처 데이터프레임과 고장 이력 데이터프레임을 조인하여 머신러닝 지도학습 라벨(label 0/1)을 생성하는 모듈.
- canonicalize_timestamp_series를 통해 시간 컬럼을 표준형(datetime64[ns])으로 정규화한 후, failure metadata에서 anchor(failure_point)와 exclusion_end(period_end/maintenance_end)를 분리해 단일 공식 positive = [anchor-horizon, anchor)으로 라벨링한다. anchor~exclusion_end 구간(active failure)은 label=0이 아니라 행 자체를 제거한다.
- degradation_start(period_start)는 failure metadata에서 라벨 계산에 사용하지 않으며 결과 DataFrame에 새로 추가하지 않는다. 다만 features_df에 이미 degradation_start 계열 컬럼이 존재하는 경우 이 함수는 그 컬럼을 1차로 제거(drop)한다 — 최종 target leakage 방어는 이 함수 및 PR #22의 Feature Schema allowlist 양쪽에서 이루어진다.

입력:
- features_df(pd.DataFrame): 피처 데이터프레임
- failures_df(pd.DataFrame): 고장 데이터프레임
- failure_meta(dict, optional): Stage 0 고장 데이터셋 메타데이터
- prediction_horizon_hours(int): 예측 호라이즌시간 (기본값 24시간)
- plan(dict, optional): ExtractionPlan 정보 (id_column, time_column 등)

출력:
- df(pd.DataFrame): label 컬럼이 추가되고 1차 누수 컬럼이 정제된 데이터프레임

의존 모듈:
- pandas, numpy
- systems.generator.common.timestamp_canonicalizer.canonicalize_timestamp_series

예외/경계 상황:
- id/time 컬럼 자체를 찾지 못한 경우 label을 전부 0으로 채우고 경고 로그를 남긴다.
- anchor_col(failure_point)을 metadata에서 찾지 못한 경우 라벨링을 수행하지 않고 (전체 label=0) 경고 로그를 남긴다.
- 개별 고장 이벤트의 anchor 값이 결측(NaT)이면 해당 이벤트만 건너뛴다.

설계 원칙과의 연결:
- docs/architecture.md 및 contracts/schemas/product-result-artifact.schema.json의 'prediction_task: binary_failure_within_horizon' 계약을 준수한다.
"""

import logging
import pandas as pd
import numpy as np
from systems.generator.common.timestamp_canonicalizer import canonicalize_timestamp_series

logger = logging.getLogger(__name__)


def build_labels(
    features_df: pd.DataFrame,
    failures_df: pd.DataFrame,
    failure_meta: dict | None = None,
    prediction_horizon_hours: int = 24,
    plan: dict | None = None,
) -> pd.DataFrame:
    """
    features_df와 failures_df를 매칭하여 prediction_horizon 기반 label(0/1) 컬럼을 생성하고,
    active failure 구간(다운타임) 행을 제거(drop)하며, features_df에 존재하는 degradation_start 누수 컬럼을 1차 제거한다.

    Positive 구간 공식:
        positive = [failure_point - prediction_horizon, failure_point)

    Active Failure 제거 구간:
        [failure_point, exclusion_end] (exclusion_end: period_end 또는 maintenance_end)
    """
    df = features_df.copy()
    f_df = failures_df.copy()

    # 0. Remove pre-existing degradation_start leakage columns if present in features_df
    time_cols_meta = (failure_meta or {}).get("time_columns", [])
    degradation_cols = [c["name"] for c in time_cols_meta if c.get("semantic") == "period_start"]
    leaked_cols = [c for c in degradation_cols if c in df.columns]
    if leaked_cols:
        logger.warning(f"[LabelBuilder] Removing leaked degradation_start columns from features_df: {leaked_cols}")
        df = df.drop(columns=leaked_cols)

    id_col = None
    if plan and isinstance(plan, dict):
        id_col = plan.get("id_column")
    if not id_col or id_col not in df.columns:
        id_col = "asset_id" if "asset_id" in df.columns else ("machineID" if "machineID" in df.columns else None)

    time_col = None
    if plan and isinstance(plan, dict):
        time_col = plan.get("time_column")
    if not time_col or time_col not in df.columns:
        time_col = "observed_at" if "observed_at" in df.columns else ("datetime" if "datetime" in df.columns else None)

    fail_id_col = None
    if plan and isinstance(plan, dict):
        fail_id_col = plan.get("id_column")
    if not fail_id_col or fail_id_col not in f_df.columns:
        fail_id_col = "asset_id" if "asset_id" in f_df.columns else ("machineID" if "machineID" in f_df.columns else None)

    if time_col and time_col in df.columns:
        df[time_col] = canonicalize_timestamp_series(df[time_col], col_name=time_col)

    df["label"] = 0

    if not (id_col and fail_id_col and time_col):
        logger.warning("[LabelBuilder] id/time 컬럼을 찾지 못해 label을 전부 0으로 채웁니다.")
        return df

    # anchor_col (failure_point) 및 exclusion_end_col (period_end / maintenance_end) 탐지
    anchor_col = next((c["name"] for c in time_cols_meta if c.get("semantic") == "failure_point"), None)
    if not anchor_col:
        anchor_col = "observed_at" if "observed_at" in f_df.columns else ("datetime" if "datetime" in f_df.columns else None)

    exclusion_end_col = next((c["name"] for c in time_cols_meta if c.get("semantic") in ("period_end", "maintenance_end")), None)

    if not anchor_col or anchor_col not in f_df.columns:
        logger.warning("[LabelBuilder] anchor_col(failure_point)를 찾지 못해 고장 이벤트를 라벨링에서 제외합니다.")
        return df

    f_df[anchor_col] = canonicalize_timestamp_series(f_df[anchor_col], col_name=anchor_col)
    if exclusion_end_col and exclusion_end_col in f_df.columns:
        f_df[exclusion_end_col] = canonicalize_timestamp_series(f_df[exclusion_end_col], col_name=exclusion_end_col)

    horizon_delta = pd.Timedelta(hours=prediction_horizon_hours)
    rows_to_drop_mask = pd.Series(False, index=df.index)

    for _, row in f_df.iterrows():
        if pd.isna(row[anchor_col]):
            continue

        f_time = row[anchor_col]
        h_start = f_time - horizon_delta

        # 1. Positive Labeling: [f_time - horizon, f_time)
        pos_mask = (
            (df[id_col] == row[fail_id_col]) &
            (df[time_col] >= h_start) &
            (df[time_col] < f_time)
        )
        df.loc[pos_mask, "label"] = 1

        # 2. Active Failure Exclusion: [f_time, exclusion_end] 또는 [f_time, f_time]
        if exclusion_end_col and exclusion_end_col in row and pd.notna(row[exclusion_end_col]):
            ex_end = row[exclusion_end_col]
            ex_mask = (
                (df[id_col] == row[fail_id_col]) &
                (df[time_col] >= f_time) &
                (df[time_col] <= ex_end)
            )
        else:
            ex_mask = (
                (df[id_col] == row[fail_id_col]) &
                (df[time_col] == f_time)
            )
        rows_to_drop_mask |= ex_mask

    # Active Failure 구간 행 제거 (Drop)
    df = df[~rows_to_drop_mask].reset_index(drop=True)

    pos_count = (df["label"] == 1).sum()
    logger.info(f"[LabelBuilder] 라벨링 완료. 최종 {len(df)}행 중 positive: {pos_count}행")
    return df
