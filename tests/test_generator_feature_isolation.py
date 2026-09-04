"""
test_generator_feature_isolation.py

담당 기능:
- systems/generator/feature/feature_builder.py의 설비별 시계열 계산 격리(Groupby), 명시적 시간 정렬 및 독립 윈도우 초기화 검증 테스트 모듈.

입력:
- 복수 설비(ASSET_A, ASSET_B)가 섞인 텔레메트리 데이터프레임
- 셔플된 행 순서의 데이터프레임

출력:
- pytest 아서션 성공 여부

의존 모듈:
- pytest, pandas, numpy
- systems.generator.feature.feature_builder: build_features
- systems.generator.ontology_mapping.mapping_cache: MappingStore, ColumnMapping
- systems.generator.feature.feature_catalog: load_catalog

설계 원칙과의 연결:
- docs/architecture.md의 '설비 단위 시간격리 및 결정론적 피처 연산' 원칙을 검증한다.
"""

import os
import json
import pytest
import pandas as pd
import numpy as np
from pandas.testing import assert_frame_equal
from systems.generator.feature.feature_builder import build_features
from systems.generator.ontology_mapping.mapping_cache import MappingStore, MappingRecord
from systems.generator.feature.feature_catalog import load_catalog


class DummyMappingStore:
    """테스트용 Mock MappingStore."""
    def get_mapping(self, col: str):
        if col in ("voltage", "voltage_raw", "Voltage"):
            return MappingRecord(source_field=col, target_ontology="Voltage", source="llm_agent", confidence=1.0, status="confirmed")
        if col in ("rotation", "rotation_raw", "Rotation"):
            return MappingRecord(source_field=col, target_ontology="Rotation", source="llm_agent", confidence=1.0, status="confirmed")
        return None


@pytest.fixture
def dummy_store():
    return DummyMappingStore()


@pytest.fixture
def catalog():
    return load_catalog()


def test_multi_asset_feature_isolation(dummy_store, catalog):
    """테스트 1: 설비 2개가 섞인 DataFrame 입력 시 설비 경계에서 diff/shift/rolling 값이 오염되지 않음."""
    dates_a = pd.date_range("2026-01-01", periods=5, freq="1h")
    dates_b = pd.date_range("2026-01-01", periods=5, freq="1h")

    df_a = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 5,
        "observed_at": dates_a,
        "voltage": [10.0, 20.0, 30.0, 40.0, 50.0]
    })
    df_b = pd.DataFrame({
        "asset_id": ["ASSET_B"] * 5,
        "observed_at": dates_b,
        "voltage": [100.0, 200.0, 300.0, 400.0, 500.0]
    })

    # 설비 A와 B를 하나의 DataFrame으로 병합
    mixed_df = pd.concat([df_a, df_b], ignore_index=True)
    plan = {"id_column": "asset_id", "time_column": "observed_at"}

    res = build_features(mixed_df, dummy_store, catalog, plan=plan)

    # ASSET_B의 첫 행(voltage=100.0)에서의 Voltage_rolling_mean 검증
    asset_b_res = res[res["asset_id"] == "ASSET_B"].reset_index(drop=True)

    # dropna()로 인해 std가 NaN인 ASSET_B의 첫 행이 제거되고, 2번째 행(100.0, 200.0)부터 보존됨
    # 오염 누설 시 rolling_mean은 (30 + 40 + 50 + 100 + 200) / 5 = 84.0이 되나,
    # 설비 격리에 의해 ASSET_B 2번째 행의 rolling_mean은 (100 + 200) / 2 = 150.0이어야 함
    asset_b_mean = asset_b_res["voltage__Voltage__rolling_mean__window_5"].iloc[0]
    assert asset_b_mean == 150.0, f"Expected ASSET_B rolling_mean to be 150.0 within ASSET_B stream, but got {asset_b_mean}"


def test_row_order_independence(dummy_store, catalog):
    """테스트 2: 입력 행 순서를 섞어도 (내부 정렬 후) 동일한 피처 결과가 나옴."""
    dates = pd.date_range("2026-01-01", periods=10, freq="1h")
    df_orig = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 5 + ["ASSET_B"] * 5,
        "observed_at": list(dates[:5]) + list(dates[:5]),
        "voltage": [10.0, 20.0, 30.0, 40.0, 50.0, 100.0, 110.0, 120.0, 130.0, 140.0]
    })

    plan = {"id_column": "asset_id", "time_column": "observed_at"}

    res_orig = build_features(df_orig, dummy_store, catalog, plan=plan)

    # 무작위 셔플
    df_shuffled = df_orig.sample(frac=1, random_state=42).reset_index(drop=True)
    res_shuffled = build_features(df_shuffled, dummy_store, catalog, plan=plan)

    assert_frame_equal(
        res_orig.reset_index(drop=True),
        res_shuffled.reset_index(drop=True),
        check_dtype=False
    )


def test_independent_window_initialization(dummy_store, catalog):
    """테스트 3: 설비별 rolling window가 서로 독립적으로 초기화됨."""
    dates = pd.date_range("2026-01-01", periods=5, freq="1h")
    df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 5 + ["ASSET_B"] * 5,
        "observed_at": list(dates) + list(dates),
        "voltage": [10.0, 10.0, 10.0, 10.0, 10.0, 50.0, 50.0, 50.0, 50.0, 50.0]
    })
    plan = {"id_column": "asset_id", "time_column": "observed_at"}

    res = build_features(df, dummy_store, catalog, plan=plan)

    # ASSET_A rolling_mean은 항상 10.0, ASSET_B rolling_mean은 항상 50.0이어야 함
    mean_a = res[res["asset_id"] == "ASSET_A"]["voltage__Voltage__rolling_mean__window_5"]
    mean_b = res[res["asset_id"] == "ASSET_B"]["voltage__Voltage__rolling_mean__window_5"]

    assert (mean_a == 10.0).all(), f"ASSET_A rolling mean contaminated: {mean_a.tolist()}"
    assert (mean_b == 50.0).all(), f"ASSET_B rolling mean contaminated: {mean_b.tolist()}"


def test_horizon_labeling_lead_window():
    """테스트 4: 단일 고장 시점 기반 prediction_horizon_hours(24h) 사전 라벨링 매칭 및 active failure drop 검증."""
    from systems.generator.feature.feature_label_service import build_labels

    dates = pd.date_range("2026-01-01 00:00:00", periods=48, freq="1h")
    features_df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 48,
        "observed_at": dates,
        "voltage": [10.0] * 48
    })

    failures_df = pd.DataFrame({
        "asset_id": ["ASSET_A"],
        "observed_at": [pd.Timestamp("2026-01-02 12:00:00")]
    })

    labeled_df = build_labels(features_df, failures_df, prediction_horizon_hours=24)

    pos_mask = labeled_df["label"] == 1
    pos_times = labeled_df.loc[pos_mask, "observed_at"]

    # [2026-01-01 12:00:00, 2026-01-02 12:00:00) 24개 시간 관측 포인트가 positive
    assert len(pos_times) == 24, f"Expected 24 hourly points in [f_time-24h, f_time), got {len(pos_times)}"
    assert pos_times.min() == pd.Timestamp("2026-01-01 12:00:00")
    assert pos_times.max() == pd.Timestamp("2026-01-02 11:00:00")
    # 고장 당해 시점(2026-01-02 12:00:00)은 active failure 구간으로 drop되었는지 확인
    assert pd.Timestamp("2026-01-02 12:00:00") not in labeled_df["observed_at"].values


def test_anchor_missing_and_exclusion_drop():
    """테스트 5: anchor(failure_point) 부재 시 대체 금지 및 active failure 구간(maintenance_end) drop 검증."""
    from systems.generator.feature.feature_label_service import build_labels

    dates = pd.date_range("2026-01-01 00:00:00", periods=48, freq="1h")
    features_df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 48,
        "observed_at": dates,
        "voltage": [10.0] * 48
    })

    # failure_point(anchor)는 있고 maintenance_end(exclusion_end)가 존재하는 메타데이터 케이스
    failures_df = pd.DataFrame({
        "asset_id": ["ASSET_A"],
        "fail_time": [pd.Timestamp("2026-01-02 12:00:00")],
        "maint_end": [pd.Timestamp("2026-01-02 18:00:00")]
    })
    meta = {
        "time_columns": [
            {"name": "fail_time", "semantic": "failure_point"},
            {"name": "maint_end", "semantic": "maintenance_end"}
        ]
    }

    labeled_df = build_labels(features_df, failures_df, failure_meta=meta, prediction_horizon_hours=24)

    # 12:00 ~ 18:00 다운타임 구간 (7개 관측 행)이 label=0이 아닌 행 제거(drop)되었는지 확인
    excluded_times = pd.date_range("2026-01-02 12:00:00", "2026-01-02 18:00:00", freq="1h")
    for t in excluded_times:
        assert t not in labeled_df["observed_at"].values, f"Expected {t} to be dropped from labeled_df"

    # anchor 부재 케이스 (maintenance_end만 존재)
    bad_failures_df = pd.DataFrame({
        "asset_id": ["ASSET_A"],
        "maint_end": [pd.Timestamp("2026-01-02 18:00:00")]
    })
    bad_meta = {
        "time_columns": [
            {"name": "maint_end", "semantic": "maintenance_end"}
        ]
    }
    bad_labeled_df = build_labels(features_df, bad_failures_df, failure_meta=bad_meta, prediction_horizon_hours=24)
    # anchor 부재 시 maintenance_end를 anchor로 쓰지 않으므로 positive가 발생하지 않음
    assert (bad_labeled_df["label"] == 0).all()


def test_degradation_start_target_leakage_protection():
    """테스트 6: degradation_start(period_start)가 positive 구간을 clip하지 않고 label df 컬럼에서 제외됨을 검증."""
    from systems.generator.feature.feature_label_service import build_labels

    dates = pd.date_range("2026-01-01 00:00:00", periods=48, freq="1h")
    features_df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 48,
        "observed_at": dates,
        "voltage": [10.0] * 48
    })

    # period_start가 horizon 24시간보다 늦은 2026-01-02 06:00:00 에 나타난 케이스
    failures_df = pd.DataFrame({
        "asset_id": ["ASSET_A"],
        "start_time": [pd.Timestamp("2026-01-02 06:00:00")],
        "fail_time": [pd.Timestamp("2026-01-02 12:00:00")]
    })
    meta = {
        "time_columns": [
            {"name": "start_time", "semantic": "period_start"},
            {"name": "fail_time", "semantic": "failure_point"}
        ]
    }

    labeled_df = build_labels(features_df, failures_df, failure_meta=meta, prediction_horizon_hours=24)

    pos_mask = labeled_df["label"] == 1
    pos_times = labeled_df.loc[pos_mask, "observed_at"]

    # degradation_start로 clip되지 않고 24시간 전체 [2026-01-01 12:00:00, 2026-01-02 12:00:00)가 positive 임을 검증
    assert len(pos_times) == 24
    assert pos_times.min() == pd.Timestamp("2026-01-01 12:00:00")
    # Target Leakage 방지: start_time, fail_time이 labeled_df 컬럼에 들어가지 않음
    assert "start_time" not in labeled_df.columns
    assert "fail_time" not in labeled_df.columns


def test_feature_name_format_and_collision_prevention(catalog):
    """테스트 7: 동일 ontology node에 매핑된 두 source column이 서로 다른 feature 컬럼 이름을 가짐."""
    class MultiSourceStore:
        def get_mapping(self, col: str):
            if col in ("voltage_sensor_1", "voltage_sensor_2"):
                from systems.generator.ontology_mapping.mapping_cache import MappingRecord
                return MappingRecord(source_field=col, target_ontology="Voltage", source="llm_agent", confidence=1.0, status="confirmed")
            return None

    dates = pd.date_range("2026-01-01", periods=5, freq="1h")
    df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 5,
        "observed_at": dates,
        "voltage_sensor_1": [10.0, 20.0, 30.0, 40.0, 50.0],
        "voltage_sensor_2": [100.0, 200.0, 300.0, 400.0, 500.0],
    })
    plan = {"id_column": "asset_id", "time_column": "observed_at"}
    res = build_features(df, MultiSourceStore(), catalog, plan=plan)

    expected_col_1 = "voltage_sensor_1__Voltage__rolling_mean__window_5"
    expected_col_2 = "voltage_sensor_2__Voltage__rolling_mean__window_5"

    assert expected_col_1 in res.columns, f"Expected {expected_col_1} in columns: {res.columns}"
    assert expected_col_2 in res.columns, f"Expected {expected_col_2} in columns: {res.columns}"
    assert res[expected_col_1].iloc[-1] == 30.0
    assert res[expected_col_2].iloc[-1] == 300.0


def test_environment_fail_fast_on_missing_id_column(dummy_store, catalog, monkeypatch):
    """테스트 8: id_column 식별 실패 시 single_asset 설정 및 APP_ENV에 따른 fail-fast 정책."""
    df = pd.DataFrame({
        "observed_at": pd.date_range("2026-01-01", periods=5, freq="1h"),
        "voltage": [10.0, 20.0, 30.0, 40.0, 50.0]
    })

    # 1. production 환경 -> ValueError
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="id_column could not be identified"):
        build_features(df, dummy_store, catalog)

    # 2. single_asset=False -> test/local 환경에서도 ValueError
    monkeypatch.setenv("APP_ENV", "test")
    with pytest.raises(ValueError, match="single_asset=False was explicitly set"):
        build_features(df, dummy_store, catalog, single_asset=False)

    # 3. single_asset=True -> production 환경에서도 처리 허용
    monkeypatch.setenv("APP_ENV", "production")
    res_single = build_features(df, dummy_store, catalog, single_asset=True)
    assert len(res_single) > 0

    # 4. test/local 환경 -> single_asset 미지정 시 경고 후 허용
    monkeypatch.setenv("APP_ENV", "test")
    res_test = build_features(df, dummy_store, catalog)
    assert len(res_test) > 0


def test_missing_time_column_always_fails(dummy_store, catalog):
    """테스트 9: time_column 식별 실패 시 임의 첫번째 컬럼 fallback 없이 항상 ValueError 발생."""
    df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 5,
        "voltage": [10.0, 20.0, 30.0, 40.0, 50.0]
    })

    with pytest.raises(ValueError, match="time_column could not be identified"):
        build_features(df, dummy_store, catalog, single_asset=True)


def test_extraction_service_wide_format_duplicate_checking(tmp_path):
    """테스트 10: extraction_service.py 내 extract_with_plan wide-format 중복 검사 (aggregate vs error, 비숫자 충돌)."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    csv_file = tmp_path / "wide_dup_sample.csv"
    df_dup = pd.DataFrame({
        "asset_id": ["ASSET_A", "ASSET_A", "ASSET_A"],
        "observed_at": ["2026-01-01 00:00:00", "2026-01-01 00:00:00", "2026-01-01 01:00:00"],
        "voltage": [10.0, 20.0, 30.0],
        "status": ["OK", "OK", "OK"]
    })
    df_dup.to_csv(csv_file, index=False)

    # 1. duplicate_policy="error" -> ValueError
    plan_err = {
        "structure_type": "tabular_column_as_attribute",
        "id_column": "asset_id",
        "time_column": "observed_at",
        "duplicate_policy": "error"
    }
    with pytest.raises(ValueError, match="Duplicate rows found"):
        extract_with_plan(str(csv_file), plan_err)

    # 2. duplicate_policy="aggregate", aggregation="mean" -> 성공적 집계
    plan_agg = {
        "structure_type": "tabular_column_as_attribute",
        "id_column": "asset_id",
        "time_column": "observed_at",
        "duplicate_policy": "aggregate",
        "aggregation": "mean"
    }
    res = extract_with_plan(str(csv_file), plan_agg)
    assert len(res) == 2
    assert res.loc[res["observed_at"] == "2026-01-01 00:00:00", "voltage"].values[0] == 15.0

    # 3. 비숫자 컬럼 값이 그룹 내에서 갈리는 경우 -> ValueError
    df_conflict = pd.DataFrame({
        "asset_id": ["ASSET_A", "ASSET_A"],
        "observed_at": ["2026-01-01 00:00:00", "2026-01-01 00:00:00"],
        "voltage": [10.0, 20.0],
        "status": ["OK", "FAIL"]
    })
    csv_conflict = tmp_path / "wide_conflict.csv"
    df_conflict.to_csv(csv_conflict, index=False)

    with pytest.raises(ValueError, match="Cannot deduplicate non-numeric column"):
        extract_with_plan(str(csv_conflict), plan_agg)


def test_build_labels_with_plan_wiring():
    """테스트 11: build_labels()에 plan(id_column, time_column) 배선 검증."""
    from systems.generator.feature.feature_label_service import build_labels

    dates = pd.date_range("2026-01-01 00:00:00", periods=48, freq="1h")
    features_df = pd.DataFrame({
        "custom_eq_id": ["EQ_100"] * 48,
        "custom_ts": dates,
        "voltage": [10.0] * 48
    })

    failures_df = pd.DataFrame({
        "custom_eq_id": ["EQ_100"],
        "observed_at": [pd.Timestamp("2026-01-02 12:00:00")]
    })

    plan = {"id_column": "custom_eq_id", "time_column": "custom_ts"}
    labeled_df = build_labels(features_df, failures_df, prediction_horizon_hours=24, plan=plan)

    pos_count = (labeled_df["label"] == 1).sum()
    assert pos_count == 24
    assert "custom_eq_id" in labeled_df.columns
    assert "custom_ts" in labeled_df.columns


def test_preprocessing_plan_response_literal_and_pair_validation():
    """테스트 12: PreprocessingPlanResponse duplicate_policy / aggregation Literal 및 Pair validation."""
    from pydantic import ValidationError
    from systems.generator.app.preprocessing.preprocessing_schema import PreprocessingPlanResponse

    valid_plan = PreprocessingPlanResponse(duplicate_policy="aggregate", aggregation="mean")
    assert valid_plan.duplicate_policy == "aggregate"
    assert valid_plan.aggregation == "mean"

    # invalid literal
    with pytest.raises(ValidationError):
        PreprocessingPlanResponse(duplicate_policy="invalid_policy")

    # duplicate_policy='aggregate' without aggregation -> ValidationError
    with pytest.raises(ValidationError, match="requires a non-null aggregation"):
        PreprocessingPlanResponse(duplicate_policy="aggregate", aggregation=None)

    # duplicate_policy='error' with aggregation -> ValidationError
    with pytest.raises(ValidationError, match="must not specify an aggregation"):
        PreprocessingPlanResponse(duplicate_policy="error", aggregation="mean")


def test_build_labels_removes_preexisting_leakage_columns():
    """테스트 13: build_labels()가 features_df에 이미 조인되어 들어온 period_start(degradation_start) 누수 컬럼을 1차 제거한다."""
    from systems.generator.feature.feature_label_service import build_labels

    dates = pd.date_range("2026-01-01 00:00:00", periods=48, freq="1h")
    features_df = pd.DataFrame({
        "asset_id": ["ASSET_A"] * 48,
        "observed_at": dates,
        "period_start": [pd.Timestamp("2026-01-01 12:00:00")] * 48,  # leaked column
        "voltage": [10.0] * 48
    })

    failures_df = pd.DataFrame({
        "asset_id": ["ASSET_A"],
        "observed_at": [pd.Timestamp("2026-01-02 12:00:00")]
    })

    failure_meta = {
        "time_columns": [
            {"name": "period_start", "semantic": "period_start"},
            {"name": "observed_at", "semantic": "failure_point"}
        ]
    }

    labeled_df = build_labels(features_df, failures_df, failure_meta=failure_meta, prediction_horizon_hours=24)
    assert "period_start" not in labeled_df.columns, "Leaked period_start column must be removed from labeled_df"


def test_long_format_extraction_with_explicit_roles(tmp_path):
    """테스트 14: 역할이 명시된 long-format 데이터가 정상 피벗됨."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    csv_file = tmp_path / "long_sample.csv"
    df_long = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:00:00", "2026-01-01 01:00:00", "2026-01-01 01:00:00"],
        "asset_id": ["A1", "A1", "A1", "A1"],
        "attribute": ["volt", "rot", "volt", "rot"],
        "value": [10.0, 100.0, 20.0, 200.0]
    })
    df_long.to_csv(csv_file, index=False)

    plan = {
        "structure_type": "tabular_row_as_attribute",
        "id_column": "asset_id",
        "time_column": "timestamp",
        "attribute_column": "attribute",
        "value_column": "value",
        "duplicate_policy": "error"
    }

    pivoted = extract_with_plan(str(csv_file), plan)
    assert len(pivoted) == 2
    assert "asset_id" in pivoted.columns
    assert "timestamp" in pivoted.columns
    assert "volt" in pivoted.columns
    assert "rot" in pivoted.columns
    assert pivoted.loc[pivoted["timestamp"] == pd.Timestamp("2026-01-01 00:00:00"), "volt"].values[0] == 10.0


def test_long_format_extraction_missing_roles_fails(tmp_path):
    """테스트 15: 역할 정보가 누락된 long-format plan이 위치 기반 추측 없이 명시적 실패(ValueError)."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    csv_file = tmp_path / "long_incomplete.csv"
    df_long = pd.DataFrame({
        "c0": ["A1", "A1"],
        "c1": ["volt", "rot"],
        "c2": [10.0, 100.0]
    })
    df_long.to_csv(csv_file, index=False)

    incomplete_plan = {
        "structure_type": "tabular_row_as_attribute",
        "duplicate_policy": "error"
    }

    with pytest.raises(ValueError, match="missing required role"):
        extract_with_plan(str(csv_file), incomplete_plan)


def test_long_format_extraction_nonexistent_column_fails(tmp_path):
    """테스트 16: plan이 DataFrame에 없는 컬럼을 가리키면 ValueError 발생."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    csv_file = tmp_path / "long_sample2.csv"
    df_long = pd.DataFrame({
        "asset_id": ["A1"],
        "attribute": ["volt"],
        "value": [10.0]
    })
    df_long.to_csv(csv_file, index=False)

    bad_plan = {
        "structure_type": "tabular_row_as_attribute",
        "id_column": "non_existent_id",
        "attribute_column": "attribute",
        "value_column": "value",
        "duplicate_policy": "error"
    }

    with pytest.raises(ValueError, match="not found in DataFrame"):
        extract_with_plan(str(csv_file), bad_plan)


def test_long_format_extraction_overlapping_roles_fails(tmp_path):
    """테스트 17: 동일 컬럼이 여러 역할에 지정되면 거부됨."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    csv_file = tmp_path / "long_sample3.csv"
    df_long = pd.DataFrame({
        "col_a": ["A1"],
        "col_b": [10.0]
    })
    df_long.to_csv(csv_file, index=False)

    overlap_plan = {
        "structure_type": "tabular_row_as_attribute",
        "id_column": "col_a",
        "attribute_column": "col_a",
        "value_column": "col_b",
        "duplicate_policy": "error"
    }

    with pytest.raises(ValueError, match="must be unique and cannot overlap"):
        extract_with_plan(str(csv_file), overlap_plan)


def test_long_format_extraction_column_order_independence(tmp_path):
    """테스트 18: 입력 컬럼 순서를 섞어도 명시적 역할 계약에 따라 동일한 피벗 결과 생성."""
    from systems.generator.extraction.extraction_service import extract_with_plan

    df_order1 = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:00:00"],
        "asset_id": ["A1", "A1"],
        "attribute": ["volt", "rot"],
        "value": [10.0, 100.0]
    })
    df_order2 = pd.DataFrame({
        "value": [10.0, 100.0],
        "attribute": ["volt", "rot"],
        "asset_id": ["A1", "A1"],
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:00:00"]
    })

    file1 = tmp_path / "order1.csv"
    file2 = tmp_path / "order2.csv"
    df_order1.to_csv(file1, index=False)
    df_order2.to_csv(file2, index=False)

    plan = {
        "structure_type": "tabular_row_as_attribute",
        "id_column": "asset_id",
        "time_column": "timestamp",
        "attribute_column": "attribute",
        "value_column": "value",
        "duplicate_policy": "error"
    }

    res1 = extract_with_plan(str(file1), plan)
    res2 = extract_with_plan(str(file2), plan)

    assert_frame_equal(res1, res2)


def test_save_load_features_npy_custom_meta_columns_roundtrip(tmp_path):
    """테스트 19: 사용자 정의 ID/time 컬럼(equipment_id, event_time)의 NPY 저장 및 복원 round-trip 검증."""
    from systems.generator.feature.feature_builder import save_features_npy, load_features_npy

    df = pd.DataFrame({
        "equipment_id": ["EQ_01", "EQ_01", "EQ_02", "EQ_02"],
        "event_time": pd.date_range("2026-01-01", periods=4, freq="1h"),
        "voltage_feat": [10.5, 11.0, 20.5, 21.0],
        "rotation_feat": [100.0, 105.0, 200.0, 205.0]
    })

    out_dir = str(tmp_path / "npy_custom")
    save_features_npy(
        df,
        out_dir,
        "custom_test",
        id_column="equipment_id",
        time_column="event_time"
    )

    # 1. X.npy 검증: feature_cols (2개)만 포함되고 equipment_id, event_time은 제외됨
    X = np.load(f"{out_dir}/custom_test_X.npy", allow_pickle=False)
    assert X.shape == (4, 2)
    assert np.allclose(X[:, 0], [10.5, 11.0, 20.5, 21.0])

    # 2. columns.json 메타데이터 검증
    import json
    with open(f"{out_dir}/custom_test_columns.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["feature_columns"] == ["voltage_feat", "rotation_feat"]
    assert meta["id_column"] == "equipment_id"
    assert meta["time_column"] == "event_time"

    # 3. load_features_npy 복원 검증: 원래 컬럼명(equipment_id, event_time) 복원
    loaded_df = load_features_npy(out_dir, "custom_test")
    assert list(loaded_df.columns) == ["voltage_feat", "rotation_feat", "equipment_id", "event_time"]
    assert loaded_df["equipment_id"].tolist() == ["EQ_01", "EQ_01", "EQ_02", "EQ_02"]
    assert (loaded_df["event_time"] == df["event_time"]).all()


def test_save_load_features_npy_legacy_format_compatibility(tmp_path):
    """테스트 20: 레거시 리스트 형식 _columns.json 캐시 하위 호환성 복원 검증."""
    from systems.generator.feature.feature_builder import load_features_npy

    out_dir = str(tmp_path / "npy_legacy")
    os.makedirs(out_dir, exist_ok=True)

    X = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    np.save(f"{out_dir}/legacy_X.npy", X, allow_pickle=False)
    np.save(f"{out_dir}/legacy_machineID.npy", np.array(["M1", "M2"]), allow_pickle=True)
    np.save(f"{out_dir}/legacy_datetime.npy", pd.to_datetime(["2026-01-01", "2026-01-02"]).to_numpy(dtype="datetime64[ns]"), allow_pickle=False)

    import json
    with open(f"{out_dir}/legacy_columns.json", "w", encoding="utf-8") as f:
        json.dump(["f1", "f2"], f)

    loaded_df = load_features_npy(out_dir, "legacy")
    assert "f1" in loaded_df.columns
    assert "f2" in loaded_df.columns
    assert "machineID" in loaded_df.columns
    assert "datetime" in loaded_df.columns
    assert loaded_df["machineID"].tolist() == ["M1", "M2"]
