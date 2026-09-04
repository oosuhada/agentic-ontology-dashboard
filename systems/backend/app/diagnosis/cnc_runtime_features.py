"""Reproduce the Generator CNC temporal feature contract at inference."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


SUPPORTED_KIND = "cnc-temporal-v1"


def _asset_id(fixture: dict[str, Any]) -> str:
    equipment = fixture.get("equipment") or {}
    observation = fixture.get("observation") or {}
    value = (
        equipment.get("equipment_id")
        or equipment.get("asset_id")
        or observation.get("asset_id")
        or fixture.get("asset_id")
    )
    if value is None or not str(value).strip():
        raise ValueError("CNC runtime context has no asset identifier")
    return str(value)


def derive_cnc_temporal_features(
    fixture: dict[str, Any],
    feature_schema: dict[str, Any],
) -> dict[str, float]:
    engineering = feature_schema.get("feature_engineering") or {}
    if engineering.get("kind") != SUPPORTED_KIND:
        raise ValueError(f"unsupported CNC feature engineering kind: {engineering.get('kind')!r}")

    sensors = list(engineering.get("base_sensors") or [])
    if not sensors:
        raise ValueError("CNC feature schema has no base sensors")
    expected_features = list(feature_schema.get("features") or [])
    baseline_stats = engineering.get("baseline_stats") or {}
    asset_id = _asset_id(fixture)
    asset_baseline = baseline_stats.get(asset_id)
    if not isinstance(asset_baseline, dict):
        raise ValueError(f"CNC asset {asset_id} has no calibrated baseline in Model Artifact")

    recent_required = int(
        (engineering.get("runtime_context") or {}).get("recent_history_rows_required", 35)
    )
    history = list(fixture.get("history") or [])
    current = dict(fixture.get("observation") or {})
    if len(history) < recent_required:
        raise ValueError(
            f"CNC temporal inference requires at least {recent_required} prior observations; "
            f"received {len(history)}"
        )
    rows = [dict(item) for item in history[-recent_required:]] + [current]
    frame = pd.DataFrame(rows)
    if "timestamp" not in frame:
        raise ValueError("CNC runtime observations require timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if not frame["timestamp"].is_monotonic_increasing or frame["timestamp"].duplicated().any():
        raise ValueError("CNC runtime history timestamps must be strictly increasing")

    expected_cadence = float(engineering.get("expected_cadence_minutes") or 10.0)
    cadence = frame["timestamp"].diff().dropna().dt.total_seconds().div(60.0)
    if not cadence.empty and float((cadence - expected_cadence).abs().max()) > max(
        1.0, expected_cadence * 0.25
    ):
        raise ValueError(
            f"CNC runtime history cadence is incompatible with {expected_cadence:g}-minute contract"
        )

    normalized = pd.DataFrame(index=frame.index)
    for sensor in sensors:
        if sensor not in frame:
            raise ValueError(f"CNC runtime observation missing sensor: {sensor}")
        stats = asset_baseline.get(sensor) or {}
        mean = float(stats.get("mean"))
        std = float(stats.get("std"))
        if not np.isfinite(mean) or not np.isfinite(std) or std <= 0:
            raise ValueError(f"CNC baseline for {asset_id}/{sensor} is invalid")
        values = pd.to_numeric(frame[sensor], errors="raise").astype(float)
        normalized[sensor] = (values - mean) / std

    features: dict[str, float] = {}
    for sensor in sensors:
        series = normalized[sensor]
        current_value = float(series.iloc[-1])
        recent = series.iloc[-36:]
        features[f"{sensor}_current"] = current_value
        features[f"{sensor}_6h_mean"] = float(recent.mean())
        features[f"{sensor}_6h_std"] = float(recent.std())
        features[f"{sensor}_6h_max_abs"] = float(recent.abs().max())
        features[f"{sensor}_6h_change"] = float((current_value - float(series.iloc[-36])) / 6.0)
        features[f"{sensor}_1h_change"] = float(current_value - float(series.iloc[-7]))
        features[f"{sensor}_abs_current"] = float(abs(current_value))
        features[f"{sensor}_6h_abs_mean"] = float(recent.abs().mean())

    missing = [feature for feature in expected_features if feature not in features]
    if missing:
        raise ValueError(f"CNC runtime feature implementation missing schema features: {missing}")
    invalid = [feature for feature in expected_features if not np.isfinite(float(features[feature]))]
    if invalid:
        raise ValueError(f"CNC runtime features are non-finite: {invalid}")
    return {feature: float(features[feature]) for feature in expected_features}
