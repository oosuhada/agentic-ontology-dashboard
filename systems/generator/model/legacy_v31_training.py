"""Deterministic reconstruction of the Canonical V3.1 logistic models.

The original ``independent-logreg-v3.1`` binaries were not retained.  This
module reconstructs their fitted parameters from the immutable Canonical V3.1
inputs and refuses publication unless the reconstructed latest predictions
match the checked-in reference snapshots.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


MODEL_VERSION = "independent-logreg-v3.1"
RANDOM_SEED = 42
MAX_ITER = 1500
CLASS_WEIGHT = "balanced"
REGULARIZATION_C = 0.5
PREDICTION_HORIZON_HOURS = 24
REFERENCE_PROBABILITY_TOLERANCE = 5e-7

FAMILY_SENSORS = {
    "compressor": [
        "voltage_raw",
        "rotation_raw",
        "pressure_raw",
        "vibration_raw",
        "relative_vibration_z",
    ],
    "cnc": [
        "air_temperature_k",
        "process_temperature_k",
        "rotational_speed_rpm",
        "torque_nm",
        "tool_wear_min",
    ],
}

@dataclass(frozen=True)
class LegacyV31Reconstruction:
    family: str
    model: Pipeline
    feature_columns: list[str]
    baseline_stats: dict[str, dict[str, dict[str, float]]]
    rows: int
    positive_rows: int
    max_reference_probability_error: float
    reference_prediction_count: int


def _load_truth(path: Path) -> dict[str, np.ndarray]:
    frame = pd.read_csv(path, parse_dates=["failure_occurred_at"])
    return {
        str(asset_id): (
            group["failure_occurred_at"]
            .sort_values()
            .to_numpy(dtype="datetime64[ns]")
            .astype("int64")
        )
        for asset_id, group in frame.groupby("asset_id")
    }


def _future_label(
    timestamps: np.ndarray,
    event_times: np.ndarray,
    horizon_hours: int,
) -> np.ndarray:
    if len(event_times) == 0:
        return np.zeros(len(timestamps), dtype=np.int8)
    horizon_ns = int(timedelta(hours=horizon_hours).total_seconds() * 1_000_000_000)
    indices = np.searchsorted(event_times, timestamps, side="right")
    labels = np.zeros(len(timestamps), dtype=np.int8)
    valid = indices < len(event_times)
    labels[valid] = (
        event_times[indices[valid]] <= timestamps[valid] + horizon_ns
    ).astype(np.int8)
    return labels


def _build_feature_table(
    observation_path: Path,
    truth_path: Path,
    sensors: list[str],
    horizon_hours: int,
) -> tuple[
    pd.DataFrame,
    list[str],
    dict[str, dict[str, dict[str, float]]],
]:
    frame = pd.read_csv(observation_path, parse_dates=["observed_at"])
    truth = _load_truth(truth_path)
    frames: list[pd.DataFrame] = []
    feature_columns: list[str] = []
    baseline_stats: dict[str, dict[str, dict[str, float]]] = {}

    for asset_id, group in frame.groupby("asset_id", sort=True):
        group = group.sort_values("observed_at").reset_index(drop=True)
        raw_numeric = group[sensors].astype(float)
        baseline_end = group["observed_at"].iloc[0] + pd.Timedelta(days=7)
        baseline_mask = (group["observed_at"] < baseline_end) & (
            group["operating_state"] == "running"
        )
        baseline_mean = raw_numeric.loc[baseline_mask].mean()
        baseline_std = raw_numeric.loc[baseline_mask].std().replace(0.0, 1.0).fillna(1.0)
        baseline_stats[str(asset_id)] = {
            sensor: {
                "mean": float(baseline_mean[sensor]),
                "std": float(baseline_std[sensor]),
            }
            for sensor in sensors
        }
        numeric = (raw_numeric - baseline_mean) / baseline_std
        features = pd.DataFrame(index=group.index)
        for sensor in sensors:
            series = numeric[sensor]
            features[f"{sensor}_current"] = series
            features[f"{sensor}_6h_mean"] = series.rolling(36, min_periods=12).mean()
            features[f"{sensor}_6h_std"] = series.rolling(36, min_periods=12).std()
            features[f"{sensor}_6h_max_abs"] = series.abs().rolling(36, min_periods=12).max()
            features[f"{sensor}_6h_change"] = (series - series.shift(35)) / 6.0
            features[f"{sensor}_1h_change"] = series - series.shift(6)
            features[f"{sensor}_abs_current"] = series.abs()
            features[f"{sensor}_6h_abs_mean"] = series.abs().rolling(36, min_periods=12).mean()
        if not feature_columns:
            feature_columns = list(features.columns)

        selected = np.arange(36, len(group), 6)
        sample = features.iloc[selected].copy()
        sample["asset_id"] = str(asset_id)
        sample["site_id"] = group.iloc[selected]["site_id"].to_numpy()
        sample["observed_at"] = group.iloc[selected]["observed_at"].to_numpy()
        sample["operating_state"] = group.iloc[selected]["operating_state"].to_numpy()
        timestamps = sample["observed_at"].to_numpy(dtype="datetime64[ns]").astype("int64")
        event_times = truth.get(str(asset_id), np.asarray([], dtype=np.int64))
        sample["label"] = _future_label(timestamps, event_times, horizon_hours)
        censor_cutoff = group["observed_at"].iloc[-1] - pd.Timedelta(hours=horizon_hours)
        sample = sample[
            (sample["observed_at"] <= censor_cutoff)
            & (sample["operating_state"] == "running")
        ]
        frames.append(sample.dropna(subset=feature_columns))

    if not frames:
        raise ValueError(f"no legacy V3.1 feature rows generated from {observation_path}")
    return pd.concat(frames, ignore_index=True), feature_columns, baseline_stats


def _load_reference_snapshots(path: Path, family: str) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            if payload.get("asset_type") == family:
                snapshots[str(payload["asset_id"])] = payload
    if not snapshots:
        raise ValueError(f"no {family} reference snapshots found in {path}")
    return snapshots


def reconstruct_legacy_v31_model(
    *,
    family: str,
    observation_path: Path,
    truth_path: Path,
    reference_snapshot_path: Path,
    probability_tolerance: float = REFERENCE_PROBABILITY_TOLERANCE,
) -> LegacyV31Reconstruction:
    """Fit the frozen V3.1 recipe and prove it reproduces stored predictions."""
    if family not in FAMILY_SENSORS:
        raise ValueError(f"unsupported legacy V3.1 family: {family}")
    feature_frame, feature_columns, baseline_stats = _build_feature_table(
        observation_path,
        truth_path,
        FAMILY_SENSORS[family],
        PREDICTION_HORIZON_HOURS,
    )
    scaler = StandardScaler()
    transformed = scaler.fit_transform(feature_frame[feature_columns].to_numpy(dtype=float))
    classifier = LogisticRegression(
        max_iter=MAX_ITER,
        class_weight=CLASS_WEIGHT,
        C=REGULARIZATION_C,
        random_state=RANDOM_SEED,
    )
    classifier.fit(transformed, feature_frame["label"].to_numpy(dtype=int))
    model = Pipeline([("scaler", scaler), ("classifier", classifier)])

    latest = (
        feature_frame.sort_values("observed_at")
        .groupby("asset_id", as_index=False)
        .tail(1)
        .sort_values("asset_id")
    )
    actual = model.predict_proba(latest[feature_columns].to_numpy(dtype=float))[:, 1]
    expected = _load_reference_snapshots(reference_snapshot_path, family)
    if len(actual) != len(expected):
        raise ValueError(
            f"legacy V3.1 {family} reference count mismatch: "
            f"reconstructed={len(actual)}, expected={len(expected)}"
        )

    errors: list[float] = []
    for index, (_, row) in enumerate(latest.iterrows()):
        asset_id = str(row["asset_id"])
        if asset_id not in expected:
            raise ValueError(f"legacy V3.1 reference missing asset: {asset_id}")
        # Reference outputs are intentionally stored at six decimal places.
        errors.append(
            abs(
                round(float(actual[index]), 6)
                - float(expected[asset_id]["failure_probability"])
            )
        )
    max_error = max(errors, default=0.0)
    if max_error > probability_tolerance:
        raise ValueError(
            f"legacy V3.1 {family} reconstruction does not reproduce the canonical "
            f"reference probabilities: max_abs_error={max_error:.12g}, "
            f"tolerance={probability_tolerance:.12g}"
        )

    return LegacyV31Reconstruction(
        family=family,
        model=model,
        feature_columns=feature_columns,
        baseline_stats=baseline_stats,
        rows=int(len(feature_frame)),
        positive_rows=int(feature_frame["label"].sum()),
        max_reference_probability_error=max_error,
        reference_prediction_count=len(expected),
    )
