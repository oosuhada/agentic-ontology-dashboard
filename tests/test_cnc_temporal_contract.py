from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from systems.backend.app.diagnosis.cnc_runtime_features import derive_cnc_temporal_features
from systems.generator.model.cnc_training import (
    FEATURE_COLUMNS,
    FEATURE_ENGINEERING_KIND,
    FEATURE_SCHEMA_VERSION,
    SENSORS,
    build_temporal_feature_table,
)
from systems.generator.app.runtime_pipeline.cnc_temporal_features import (
    derive_cnc_temporal_feature_rows,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamps = pd.date_range("2026-08-01T00:00:00Z", periods=10 * 24 * 6, freq="10min")
    phase = np.arange(len(timestamps), dtype=float)
    observations = pd.DataFrame(
        {
            "observed_at": timestamps,
            "asset_id": "CNC-TEST-01",
            "site_id": "SITE-A",
            "operating_state": "running",
            "air_temperature_k": 301.0 + np.sin(phase / 20.0),
            "process_temperature_k": 309.0 + np.cos(phase / 18.0),
            "rotational_speed_rpm": 1450.0 + np.sin(phase / 12.0) * 40.0,
            "torque_nm": 48.0 + np.cos(phase / 15.0) * 4.0,
            "tool_wear_min": 20.0 + phase * 0.02,
        }
    )
    failures = pd.DataFrame(
        {
            "asset_id": ["CNC-TEST-01"],
            "failure_occurred_at": [pd.Timestamp("2026-08-09T12:00:00Z")],
        }
    )
    return observations, failures


def test_backend_reproduces_generator_cnc_temporal_features() -> None:
    observations, failures = _frames()
    feature_table, baseline_stats, metadata = build_temporal_feature_table(observations, failures)
    target = feature_table.iloc[20]
    timestamp = pd.Timestamp(target["observed_at"])
    row_index = int(observations.index[observations["observed_at"] == timestamp][0])
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
        "equipment": {"equipment_id": "CNC-TEST-01"},
        "history": [runtime_observation(row) for _, row in history_rows.iterrows()],
        "observation": runtime_observation(current_row),
    }

    runtime = derive_cnc_temporal_features(fixture, schema)
    runtime_frame = pd.DataFrame(
        [
            {
                "asset_id": "CNC-TEST-01",
                "observed_at": item["timestamp"],
                **{sensor: item[sensor] for sensor in SENSORS},
            }
            for item in [*fixture["history"], fixture["observation"]]
        ]
    )
    generator_matrix, generator_columns, generator_metadata = (
        derive_cnc_temporal_feature_rows(
            runtime_frame,
            feature_schema=schema,
            id_column="asset_id",
            time_column="observed_at",
        )
    )
    assert generator_columns == FEATURE_COLUMNS
    assert generator_metadata == [
        ("CNC-TEST-01", timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"))
    ]
    for feature in FEATURE_COLUMNS:
        assert runtime[feature] == pytest.approx(float(target[feature]), rel=1e-10, abs=1e-10)
        feature_index = FEATURE_COLUMNS.index(feature)
        assert generator_matrix[0, feature_index] == pytest.approx(
            float(target[feature]), rel=1e-10, abs=1e-10
        )


def test_cnc_right_censor_and_failure_window_semantics() -> None:
    observations, failures = _frames()
    feature_table, _baseline_stats, _metadata = build_temporal_feature_table(observations, failures)
    failure_at = pd.Timestamp("2026-08-09T12:00:00Z")
    positives = feature_table[feature_table["label"] == 1]
    assert not positives.empty
    assert positives["observed_at"].min() >= failure_at - pd.Timedelta(hours=24)
    assert positives["observed_at"].max() < failure_at
    assert feature_table["observed_at"].max() <= observations["observed_at"].max() - pd.Timedelta(hours=24)


def test_cnc_first_seven_days_are_calibration_only() -> None:
    observations, failures = _frames()
    feature_table, _baseline_stats, metadata = build_temporal_feature_table(observations, failures)
    baseline_end = observations["observed_at"].min() + pd.Timedelta(days=7)

    assert metadata["baseline_calibration_only"] is True
    assert feature_table["observed_at"].min() >= baseline_end
