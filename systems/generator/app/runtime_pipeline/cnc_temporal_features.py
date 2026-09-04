"""Runtime implementation of the Canonical V3.1 CNC temporal feature contract."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


SUPPORTED_KIND = "cnc-temporal-v1"


def derive_cnc_temporal_feature_rows(
    frame: pd.DataFrame,
    *,
    feature_schema: dict[str, Any],
    id_column: str,
    time_column: str,
) -> tuple[np.ndarray, list[str], list[tuple[str, str]]]:
    """Return one inference-ready feature row per asset, using its latest history."""
    engineering = feature_schema.get("feature_engineering") or {}
    if engineering.get("kind") != SUPPORTED_KIND:
        raise ValueError(f"unsupported CNC feature engineering kind: {engineering.get('kind')!r}")

    sensors = list(engineering.get("base_sensors") or [])
    if not sensors:
        raise ValueError("CNC feature schema has no base sensors")

    expected_features: list[str] = []
    for item in feature_schema.get("features") or []:
        if isinstance(item, str):
            expected_features.append(item)
        elif isinstance(item, dict):
            name = item.get("feature_name") or item.get("name")
            if name:
                expected_features.append(str(name))
    if not expected_features:
        raise ValueError("CNC feature schema has no declared features")

    runtime_context = engineering.get("runtime_context") or {}
    prior_required = int(runtime_context.get("recent_history_rows_required", 35))
    total_required = prior_required + 1
    if total_required != 36:
        raise ValueError(
            "cnc-temporal-v1 requires exactly 35 prior observations plus the current observation"
        )
    baseline_stats = engineering.get("baseline_stats") or {}
    expected_cadence = float(engineering.get("expected_cadence_minutes") or 10.0)

    rows: list[list[float]] = []
    metadata: list[tuple[str, str]] = []
    for raw_asset_id, group in frame.groupby(id_column, sort=False):
        if len(group) < total_required:
            continue
        asset_id = str(raw_asset_id)
        asset_baseline = baseline_stats.get(asset_id)
        if not isinstance(asset_baseline, dict):
            raise ValueError(f"CNC asset {asset_id} has no calibrated baseline in Model Artifact")

        recent_frame = group.iloc[-total_required:].copy()
        timestamps = pd.to_datetime(recent_frame[time_column], utc=True, errors="raise")
        if not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
            raise ValueError("CNC runtime history timestamps must be strictly increasing")
        cadence = timestamps.diff().dropna().dt.total_seconds().div(60.0)
        if not cadence.empty and float((cadence - expected_cadence).abs().max()) > max(
            1.0, expected_cadence * 0.25
        ):
            raise ValueError(
                f"CNC runtime history cadence is incompatible with {expected_cadence:g}-minute contract"
            )

        normalized = pd.DataFrame(index=recent_frame.index)
        for sensor in sensors:
            if sensor not in recent_frame:
                raise ValueError(f"CNC runtime observation missing sensor: {sensor}")
            stats = asset_baseline.get(sensor) or {}
            mean = float(stats.get("mean"))
            std = float(stats.get("std"))
            if not np.isfinite(mean) or not np.isfinite(std) or std <= 0:
                raise ValueError(f"CNC baseline for {asset_id}/{sensor} is invalid")
            values = pd.to_numeric(recent_frame[sensor], errors="raise").astype(float)
            normalized[sensor] = (values - mean) / std

        calculated: dict[str, float] = {}
        for sensor in sensors:
            series = normalized[sensor]
            current = float(series.iloc[-1])
            recent = series.iloc[-36:]
            calculated[f"{sensor}_current"] = current
            calculated[f"{sensor}_6h_mean"] = float(recent.mean())
            calculated[f"{sensor}_6h_std"] = float(recent.std())
            calculated[f"{sensor}_6h_max_abs"] = float(recent.abs().max())
            calculated[f"{sensor}_6h_change"] = float((current - float(series.iloc[-36])) / 6.0)
            calculated[f"{sensor}_1h_change"] = float(current - float(series.iloc[-7]))
            calculated[f"{sensor}_abs_current"] = float(abs(current))
            calculated[f"{sensor}_6h_abs_mean"] = float(recent.abs().mean())

        missing = [name for name in expected_features if name not in calculated]
        if missing:
            raise ValueError(f"CNC runtime feature implementation missing schema features: {missing}")
        feature_row = [float(calculated[name]) for name in expected_features]
        if not np.isfinite(np.asarray(feature_row, dtype=np.float64)).all():
            raise ValueError("CNC runtime features contain NaN or Inf")
        rows.append(feature_row)
        metadata.append((asset_id, timestamps.iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ")))

    return np.asarray(rows, dtype=np.float64), expected_features, metadata
