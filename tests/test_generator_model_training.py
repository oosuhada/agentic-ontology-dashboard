"""Tests for Generator multi-model training pipeline, feature allowlists, and Model Artifact publication."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from systems.backend.app.diagnosis.artifact_provider import LocalModelArtifactProvider
from systems.backend.app.diagnosis.contracts import load_fixture
from systems.backend.app.diagnosis.feature_executor import execute_feature_contract
from systems.backend.app.diagnosis.predictor import ArtifactPredictor
from systems.generator.model import (
    FRAMEWORK_BY_ALGORITHM,
    MODEL_SPECS,
    REGISTERED_MODELS,
    LightGBMModel,
    ModelRegistry,
    ModelScore,
    RandomForestModel,
    XGBoostModel,
    asset_time_split,
    get_model_class,
    infer_history_requirement,
    publish_model_artifact,
    validate_manifest,
)


def _make_synthetic_labeled_dataset(n_samples: int = 100) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=n_samples, freq="1h")
    assets = ["ASSET_1" if i < n_samples // 2 else "ASSET_2" for i in range(n_samples)]
    np.random.seed(42)

    return pd.DataFrame({
        "asset_id": assets,
        "observed_at": dates,
        "period_start": dates,  # metadata leakage candidate
        "vibration_mean_3h": np.random.normal(10.0, 2.0, n_samples),
        "temperature_std_6h": np.random.normal(50.0, 5.0, n_samples),
        "pressure_raw": np.random.normal(100.0, 10.0, n_samples),
        "label": np.random.choice([0, 1], size=n_samples, p=[0.8, 0.2]),
    })


def _make_runtime_compatible_labeled_dataset(n_samples: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=n_samples, freq="1h")
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "asset_id": ["M-001"] * n_samples,
        "observed_at": dates,
        "air_temperature_k": rng.normal(298.2, 0.8, n_samples),
        "process_temperature_k": rng.normal(308.7, 1.0, n_samples),
        "rotational_speed_rpm": rng.normal(1510.0, 120.0, n_samples),
        "torque_nm": rng.normal(41.0, 7.0, n_samples),
        "tool_wear_min": np.linspace(20.0, 220.0, n_samples),
        "label": np.asarray([0] * (n_samples - 16) + [1] * 16, dtype=int),
    })


def test_model_package_import_contract():
    """Test 1: systems.generator.model imports without prediction package reverse dependency and has REGISTERED_MODELS."""
    import systems.generator.model as model_pkg

    assert hasattr(model_pkg, "train_all")
    assert hasattr(model_pkg, "publish_model_artifact")
    assert hasattr(model_pkg, "REGISTERED_MODELS")
    assert len(model_pkg.REGISTERED_MODELS) == 3
    assert "systems.generator.prediction" not in sys.modules


def test_model_specs_and_framework_mapping():
    """Test 2: get_model_class dynamically loads algorithm classes and verifies framework mapping."""
    assert set(REGISTERED_MODELS.keys()) == {"lightgbm", "xgboost", "random_forest"}
    assert FRAMEWORK_BY_ALGORITHM["lightgbm"] == "lightgbm"
    assert FRAMEWORK_BY_ALGORITHM["xgboost"] == "xgboost"
    assert FRAMEWORK_BY_ALGORITHM["random_forest"] == "scikit-learn"

    rf_cls = get_model_class("random_forest")
    assert rf_cls is RandomForestModel
    assert rf_cls.framework == "scikit-learn"

    lgb_cls = get_model_class("lightgbm")
    assert lgb_cls is LightGBMModel

    xgb_cls = get_model_class("xgboost")
    assert xgb_cls is XGBoostModel

    with pytest.raises(ValueError, match="Unknown model algorithm"):
        get_model_class("unknown_algo")


def test_asset_time_split_prevents_future_leakage():
    """Test 3: asset_time_split sorts each asset chronologically and separates past/future."""
    df = _make_synthetic_labeled_dataset(60)

    # Shuffle input rows to test order independence
    shuffled_df = df.sample(frac=1.0, random_state=123).reset_index(drop=True)

    train_df, val_df, test_df = asset_time_split(shuffled_df, id_col="asset_id", time_col="observed_at", test_size=0.2, val_size=0.2)

    assert len(train_df) + len(val_df) + len(test_df) == len(df)

    for asset_name in ("ASSET_1", "ASSET_2"):
        t_asset = train_df[train_df["asset_id"] == asset_name]
        v_asset = val_df[val_df["asset_id"] == asset_name]
        te_asset = test_df[test_df["asset_id"] == asset_name]

        if not t_asset.empty and not v_asset.empty:
            assert t_asset["observed_at"].max() <= v_asset["observed_at"].min()
        if not v_asset.empty and not te_asset.empty:
            assert v_asset["observed_at"].max() <= te_asset["observed_at"].min()


def test_explicit_feature_schema_allowlist_excludes_metadata():
    """Test 4: Only declared feature allowlist columns are used in model training."""
    df = _make_synthetic_labeled_dataset(60)
    rf_cls = get_model_class("random_forest")
    model = rf_cls()

    declared_features = ["vibration_mean_3h", "temperature_std_6h", "pressure_raw"]
    model.train(df, feature_names=declared_features, target_col="label", id_col="asset_id", time_col="observed_at")

    assert model.feature_cols == declared_features
    assert "asset_id" not in model.feature_cols
    assert "observed_at" not in model.feature_cols
    assert "period_start" not in model.feature_cols
    assert "label" not in model.feature_cols


def test_models_train_predict_proba_and_explain(tmp_path):
    """Test 5: LightGBM, XGBoost, and RandomForest train, predict ModelScore, and predict probabilities."""
    df = _make_synthetic_labeled_dataset(60)
    features = ["vibration_mean_3h", "temperature_std_6h", "pressure_raw"]

    for algo_name in ("random_forest", "lightgbm", "xgboost"):
        cls = get_model_class(algo_name)
        model = cls()
        model.train(df, feature_names=features, target_col="label")

        # Probability prediction test
        probs = model.predict_proba(df[features])
        assert probs.ndim == 2
        assert probs.shape == (len(df), 2)
        assert np.all((probs >= 0.0) & (probs <= 1.0))

        # ModelScore predict & explain test
        score = model.predict(df[features])
        assert isinstance(score, ModelScore)
        assert 0.0 <= score.probability <= 1.0
        assert score.predicted_class in (0, 1)
        assert set(score.feature_importance.keys()) == set(features)

        # Save and load round-trip
        save_file = str(tmp_path / f"{algo_name}.joblib")
        model.save(save_file)

        loaded_model = cls()
        loaded_model.load(save_file)
        assert loaded_model.feature_cols == features

        loaded_probs = loaded_model.predict_proba(df[features])
        assert np.allclose(probs, loaded_probs)


def test_missing_feature_column_raises_error():
    """Test 6: Missing declared feature column in inference DataFrame raises a clear ValueError."""
    df = _make_synthetic_labeled_dataset(40)
    features = ["vibration_mean_3h", "temperature_std_6h", "pressure_raw"]

    rf_cls = get_model_class("random_forest")
    model = rf_cls()
    model.train(df, feature_names=features, target_col="label")

    incomplete_df = df[["vibration_mean_3h", "temperature_std_6h"]]
    with pytest.raises(ValueError, match="missing required features"):
        model.predict_proba(incomplete_df)


def test_history_requirement_is_inferred_from_cadence_and_feature_window():
    telemetry = pd.DataFrame(
        {
            "asset_id": ["M-001"] * 12,
            "observed_at": pd.date_range("2026-08-01T00:00:00Z", periods=12, freq="10min"),
        }
    )
    requirement = infer_history_requirement(
        telemetry,
        feature_names=[
            "rotational_speed_rpm__RotationalSpeed__moving_average__window_10",
            "tool_wear_min__ToolWear__gradient__default",
            "tool_wear_min__ToolWear__lag__periods_1",
        ],
        id_col="asset_id",
        time_col="observed_at",
    )

    assert requirement["expected_sampling_interval_seconds"] == 600
    assert requirement["minimum_history_rows"] == 10
    assert requirement["maximum_lookback_hours"] == 2
    assert requirement["missing_history_policy"] == "fail"


def test_backend_feature_executor_matches_generator_temporal_semantics():
    history = []
    for index in range(10):
        history.append(
            {
                "timestamp": f"2026-08-01T00:{index * 10:02d}:00+09:00" if index < 6 else f"2026-08-01T01:{(index - 6) * 10:02d}:00+09:00",
                "air_temperature_k": 298.0 + index,
                "process_temperature_k": 308.0 + index * 2,
                "rotational_speed_rpm": 1500.0 + index * 10,
                "torque_nm": 40.0 + index,
                "tool_wear_min": 20.0 + index * 3,
            }
        )
    fixture = {
        "history": history,
        "observation": dict(history[-1]),
    }
    feature_names = [
        "air_temperature_k__AirTemperature__rolling_mean__window_5",
        "air_temperature_k__AirTemperature__rolling_std__window_5",
        "process_temperature_k__ProcessTemperature__gradient__default",
        "rotational_speed_rpm__RotationalSpeed__moving_average__window_10",
        "tool_wear_min__ToolWear__lag__periods_1",
        "tool_wear_min__ToolWear__gradient__default",
    ]
    values = execute_feature_contract(
        fixture,
        feature_names=feature_names,
        direct_values=fixture["observation"],
        history_requirement={
            "order_by": "observed_at",
            "minimum_history_rows": 10,
            "maximum_lookback_hours": 2,
        },
        executor_version="pdm-feature-executor-v1",
    )

    air = pd.Series([row["air_temperature_k"] for row in history], dtype=float)
    process = pd.Series([row["process_temperature_k"] for row in history], dtype=float)
    rpm = pd.Series([row["rotational_speed_rpm"] for row in history], dtype=float)
    wear = pd.Series([row["tool_wear_min"] for row in history], dtype=float)
    assert values[feature_names[0]] == pytest.approx(float(air.rolling(5, min_periods=1).mean().iloc[-1]))
    assert values[feature_names[1]] == pytest.approx(float(air.rolling(5, min_periods=1).std().iloc[-1]))
    assert values[feature_names[2]] == pytest.approx(float(process.diff().iloc[-1]))
    assert values[feature_names[3]] == pytest.approx(float(rpm.rolling(10, min_periods=1).mean().iloc[-1]))
    assert values[feature_names[4]] == pytest.approx(float(wear.shift(1).iloc[-1]))
    assert values[feature_names[5]] == pytest.approx(float(wear.diff().iloc[-1]))


def test_temporal_model_artifact_runs_through_backend_predictor(tmp_path):
    feature_names = [
        "air_temperature_k__AirTemperature__rolling_mean__window_5",
        "process_temperature_k__ProcessTemperature__gradient__default",
        "rotational_speed_rpm__RotationalSpeed__moving_average__window_10",
        "tool_wear_min__ToolWear__lag__periods_1",
    ]
    rng = np.random.default_rng(7)
    training = pd.DataFrame(
        {
            feature_names[0]: rng.normal(300.0, 1.0, 80),
            feature_names[1]: rng.normal(0.0, 0.5, 80),
            feature_names[2]: rng.normal(1500.0, 100.0, 80),
            feature_names[3]: np.linspace(10.0, 210.0, 80),
            "label": np.asarray([0] * 64 + [1] * 16, dtype=int),
        }
    )
    model = RandomForestModel()
    model.train(training, feature_names=feature_names, target_col="label")
    model_file = tmp_path / "temporal.joblib"
    model.save(model_file)

    destination = publish_model_artifact(
        artifact_uri=tmp_path / "artifacts",
        model_id="temporal-rf",
        model_version="v1",
        dataset_version="temporal-test-v1",
        feature_schema_version="pdm-feature-v1",
        model_file=model_file,
        feature_schema={
            "schema_version": "pdm-feature-v1",
            "features": feature_names,
            "target": "label",
            "prediction_task": "binary_failure_within_horizon",
            "feature_executor_version": "pdm-feature-executor-v1",
            "partition_by": "asset_id",
            "order_by": "observed_at",
        },
        training_config={"algorithm": "random_forest", "framework": "scikit-learn"},
        metrics={},
        history_requirement={
            "history_requirement_version": "pdm-history-v1",
            "partition_by": "asset_id",
            "order_by": "observed_at",
            "expected_sampling_interval_seconds": 600,
            "minimum_history_rows": 10,
            "maximum_lookback_hours": 2,
            "missing_history_policy": "fail",
        },
        provenance={"test": True},
        compatibility={
            "runtime": "app.diagnosis",
            "feature_executor_version": "pdm-feature-executor-v1",
            "prediction_task": "binary_failure_within_horizon",
        },
    )

    fixture = load_fixture("data/fixtures/GS-001-normal-stable.json")
    start = pd.Timestamp("2026-08-01T00:00:00+09:00")
    history = []
    for index in range(10):
        history.append(
            {
                "timestamp": (start + pd.Timedelta(minutes=10 * index)).isoformat(),
                "product_type": "M",
                "air_temperature_k": 298.0 + index * 0.1,
                "process_temperature_k": 308.0 + index * 0.2,
                "rotational_speed_rpm": 1500.0 + index * 5.0,
                "torque_nm": 40.0 + index * 0.3,
                "tool_wear_min": 20.0 + index,
            }
        )
    fixture["history"] = history
    fixture["observation"] = dict(history[-1])

    prediction = ArtifactPredictor(destination).predict(fixture)

    assert prediction.probability is not None
    assert 0.0 <= prediction.probability <= 1.0


@pytest.mark.parametrize("algo_name", ["random_forest", "lightgbm", "xgboost"])
def test_canonical_model_artifact_publish_and_backend_roundtrip(tmp_path, algo_name):
    """Test 7: every published estimator survives the real Backend ArtifactPredictor path."""
    df = _make_runtime_compatible_labeled_dataset()
    features = [
        "air_temperature_k",
        "process_temperature_k",
        "rotational_speed_rpm",
        "torque_nm",
        "tool_wear_min",
    ]

    model_cls = get_model_class(algo_name)
    model = model_cls()
    model.train(df, feature_names=features, target_col="label")

    model_file = tmp_path / f"{algo_name}.joblib"
    model.save(model_file)

    artifact_root = tmp_path / "artifacts"
    artifact_uri = f"file://{artifact_root.resolve()}"
    model_id = f"pdm-cnc-tool-wear-{algo_name}"
    model_version = "v1"

    dest = publish_model_artifact(
        artifact_uri=artifact_uri,
        model_id=model_id,
        model_version=model_version,
        dataset_version="ds-v1",
        feature_schema_version="pdm-feature-v1",
        model_file=model_file,
        feature_schema={
            "schema_version": "pdm-feature-v1",
            "features": features,
            "target": "label",
            "prediction_task": "binary_failure_within_horizon",
        },
        training_config={
            "algorithm": algo_name,
            "framework": FRAMEWORK_BY_ALGORITHM[algo_name],
            "feature_count": len(features),
            "split_strategy": "asset_time_split",
            "target_name": "label",
            "random_seed": 42,
        },
        metrics={"validation_metrics": {"precision": 0.85, "recall": 0.80}},
        provenance={"training": {"run_id": "run-test-01", "publisher": "systems/generator"}},
        compatibility={
            "runtime": "app.diagnosis",
            "feature_executor_version": "pdm-feature-executor-v1",
            "prediction_task": "binary_failure_within_horizon",
        },
    )

    assert dest.exists()
    for filename in (
        "manifest.json",
        "model.joblib",
        "feature_schema.json",
        "label_schema.json",
        "history_requirement.json",
        "metrics.json",
    ):
        assert (dest / filename).exists()

    provider = LocalModelArtifactProvider(f"file://{dest.resolve()}")
    loaded = provider.load()
    assert loaded.manifest["model_id"] == model_id
    assert loaded.manifest["model_version"] == model_version
    assert loaded.feature_schema["features"] == features
    direct_probs = loaded.model.predict_proba(df[features].iloc[:2])
    assert direct_probs.shape == (2, 2)

    fixture = load_fixture("data/fixtures/GS-001-normal-stable.json")
    prediction = ArtifactPredictor(f"file://{dest.resolve()}").predict(fixture)
    assert prediction.probability is not None
    assert 0.0 <= prediction.probability <= 1.0

    with pytest.raises(FileExistsError, match="Model Artifact already published"):
        publish_model_artifact(
            artifact_uri=artifact_uri,
            model_id=model_id,
            model_version=model_version,
            dataset_version="ds-v1",
            feature_schema_version="pdm-feature-v1",
            model_file=model_file,
            feature_schema={"schema_version": "pdm-feature-v1", "features": features},
            training_config={"algorithm": algo_name},
            metrics={},
            provenance={},
            compatibility={},
        )
