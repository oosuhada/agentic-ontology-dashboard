from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from systems.backend.app.diagnosis.compressor_runtime_features import derive_compressor_temporal_features
from systems.generator.model.compressor_training import (
    FEATURE_COLUMNS,
    FEATURE_ENGINEERING_KIND,
    FEATURE_SCHEMA_VERSION,
    SENSORS,
    build_temporal_feature_table,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamps = pd.date_range("2026-08-01T00:00:00Z", periods=10 * 24 * 6, freq="10min")
    phase = np.arange(len(timestamps), dtype=float)
    observations = pd.DataFrame(
        {
            "observed_at": timestamps,
            "asset_id": "CMP-TEST-01",
            "site_id": "SITE-A",
            "operating_state": "running",
            "voltage_raw": 170.0 + np.sin(phase / 20.0),
            "rotation_raw": 450.0 + np.cos(phase / 15.0) * 3.0,
            "pressure_raw": 100.0 + np.sin(phase / 25.0) * 2.0,
            "vibration_raw": 40.0 + np.cos(phase / 10.0),
            "relative_vibration_z": np.sin(phase / 18.0),
        }
    )
    failures = pd.DataFrame(
        {
            "asset_id": ["CMP-TEST-01"],
            "failure_occurred_at": [pd.Timestamp("2026-08-09T12:00:00Z")],
        }
    )
    return observations, failures


def test_backend_reproduces_generator_temporal_features() -> None:
    observations, failures = _frames()
    feature_table, baseline_stats, metadata = build_temporal_feature_table(observations, failures)
    target = feature_table.iloc[20]
    timestamp = pd.Timestamp(target["observed_at"])
    row_index = int(observations.index[observations["observed_at"] == timestamp][0])
    assert row_index >= 35

    history_rows = observations.iloc[row_index - 35 : row_index]
    current_row = observations.iloc[row_index]

    def runtime_observation(row: pd.Series) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(row["observed_at"]).isoformat(),
            **{sensor: float(row[sensor]) for sensor in SENSORS},
        }

    schema = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "features": FEATURE_COLUMNS,
        "feature_engineering": {
            "kind": FEATURE_ENGINEERING_KIND,
            "base_sensors": SENSORS,
            **metadata,
            "runtime_context": {"recent_history_rows_required": 35},
            "baseline_stats": baseline_stats,
        },
    }
    fixture = {
        "equipment": {"equipment_id": "CMP-TEST-01"},
        "history": [runtime_observation(row) for _, row in history_rows.iterrows()],
        "observation": runtime_observation(current_row),
    }

    runtime = derive_compressor_temporal_features(fixture, schema)
    for feature in FEATURE_COLUMNS:
        assert runtime[feature] == pytest.approx(float(target[feature]), rel=1e-10, abs=1e-10)


def test_right_censor_and_failure_window_semantics() -> None:
    observations, failures = _frames()
    feature_table, _baseline_stats, _metadata = build_temporal_feature_table(observations, failures)
    failure_at = pd.Timestamp("2026-08-09T12:00:00Z")
    positives = feature_table[feature_table["label"] == 1]
    assert not positives.empty
    assert positives["observed_at"].min() >= failure_at - pd.Timedelta(hours=24)
    assert positives["observed_at"].max() < failure_at
    assert feature_table["observed_at"].max() <= observations["observed_at"].max() - pd.Timedelta(hours=24)


def test_first_seven_days_are_calibration_only() -> None:
    observations, failures = _frames()
    feature_table, _baseline_stats, metadata = build_temporal_feature_table(observations, failures)
    baseline_end = observations["observed_at"].min() + pd.Timedelta(days=7)

    assert metadata["baseline_calibration_only"] is True
    assert feature_table["observed_at"].min() >= baseline_end
