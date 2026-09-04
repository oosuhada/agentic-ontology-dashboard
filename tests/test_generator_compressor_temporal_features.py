from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from systems.generator.app.runtime_pipeline.compressor_temporal_features import (
    derive_compressor_temporal_feature_rows,
)


SENSORS = [
    "voltage_raw",
    "rotation_raw",
    "pressure_raw",
    "vibration_raw",
    "relative_vibration_z",
]
SUFFIXES = [
    "current",
    "6h_mean",
    "6h_std",
    "6h_max_abs",
    "6h_change",
    "1h_change",
    "abs_current",
    "6h_abs_mean",
]


def schema() -> dict:
    return {
        "schema_version": "compressor-temporal-v2",
        "features": [
            f"{sensor}_{suffix}" for sensor in SENSORS for suffix in SUFFIXES
        ],
        "feature_engineering": {
            "kind": "compressor-temporal-v2",
            "base_sensors": SENSORS,
            "expected_cadence_minutes": 10,
            "runtime_context": {"recent_history_rows_required": 35},
            "baseline_stats": {
                "CMP-01": {
                    sensor: {"mean": 100.0, "std": 10.0}
                    for sensor in SENSORS
                }
            },
        },
    }


def observations(*, broken_cadence: bool = False) -> pd.DataFrame:
    timestamps = list(pd.date_range("2026-09-01T00:00:00Z", periods=36, freq="10min"))
    if broken_cadence:
        timestamps[-1] += pd.Timedelta(minutes=5)
    rows = []
    for index, observed_at in enumerate(timestamps):
        rows.append(
            {
                "asset_id": "CMP-01",
                "observed_at": observed_at.isoformat(),
                **{sensor: 100.0 + index for sensor in SENSORS},
            }
        )
    return pd.DataFrame(rows)


def test_compressor_runtime_features_match_declared_order() -> None:
    features, columns, metadata = derive_compressor_temporal_feature_rows(
        observations(),
        feature_schema=schema(),
        id_column="asset_id",
        time_column="observed_at",
    )

    assert columns == schema()["features"]
    assert features.shape == (1, 40)
    assert np.isfinite(features).all()
    assert metadata == [("CMP-01", "2026-09-01T05:50:00Z")]


def test_compressor_runtime_features_reject_broken_cadence() -> None:
    with pytest.raises(ValueError, match="cadence"):
        derive_compressor_temporal_feature_rows(
            observations(broken_cadence=True),
            feature_schema=schema(),
            id_column="asset_id",
            time_column="observed_at",
        )
