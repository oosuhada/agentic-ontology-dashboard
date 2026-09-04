"""Canonical V3.1 compressor temporal training for immutable Model Artifacts.

The implementation intentionally mirrors the *ideas* in gen_data's legacy
sanity benchmark without importing that repository at runtime.  gen_data stays
the source producer; Generator owns feature engineering, labels, evaluation and
the promoted model contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_SEED = 42
TRAINING_VERSION = "compressor-temporal-v3"
FEATURE_SCHEMA_VERSION = "compressor-temporal-v2"
FEATURE_ENGINEERING_KIND = "compressor-temporal-v2"
SENSORS = [
    "voltage_raw",
    "rotation_raw",
    "pressure_raw",
    "vibration_raw",
    "relative_vibration_z",
]
TEMPORAL_SUFFIXES = [
    "current",
    "6h_mean",
    "6h_std",
    "6h_max_abs",
    "6h_change",
    "1h_change",
    "abs_current",
    "6h_abs_mean",
]
FEATURE_COLUMNS = [f"{sensor}_{suffix}" for sensor in SENSORS for suffix in TEMPORAL_SUFFIXES]


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


@dataclass(frozen=True)
class TrainingResult:
    model: Pipeline
    selected_model: str
    feature_schema: dict[str, Any]
    training_config: dict[str, Any]
    metrics: dict[str, Any]
    threshold_curve: list[dict[str, Any]]
    feature_table_rows: int
    positive_labels: int
    negative_labels: int


def _future_label(timestamps: np.ndarray, event_times: np.ndarray, horizon_hours: int) -> np.ndarray:
    if len(event_times) == 0:
        return np.zeros(len(timestamps), dtype=np.int8)
    horizon_ns = int(pd.Timedelta(hours=horizon_hours).value)
    indices = np.searchsorted(event_times, timestamps, side="right")
    labels = np.zeros(len(timestamps), dtype=np.int8)
    valid = indices < len(event_times)
    labels[valid] = (event_times[indices[valid]] <= timestamps[valid] + horizon_ns).astype(np.int8)
    return labels


def build_temporal_feature_table(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
    *,
    horizon_hours: int = 24,
) -> tuple[pd.DataFrame, dict[str, dict[str, dict[str, float]]], dict[str, Any]]:
    required_observation = {"observed_at", "asset_id", "site_id", "operating_state", *SENSORS}
    missing_observation = sorted(required_observation - set(observations.columns))
    if missing_observation:
        raise ValueError(f"compressor observations missing columns: {missing_observation}")
    required_failure = {"asset_id", "failure_occurred_at"}
    missing_failure = sorted(required_failure - set(failures.columns))
    if missing_failure:
        raise ValueError(f"compressor failure truth missing columns: {missing_failure}")

    obs = observations.copy()
    obs["asset_id"] = obs["asset_id"].astype(str)
    obs["observed_at"] = pd.to_datetime(obs["observed_at"], utc=True, errors="raise")
    truth = failures.copy()
    truth["asset_id"] = truth["asset_id"].astype(str)
    truth["failure_occurred_at"] = pd.to_datetime(truth["failure_occurred_at"], utc=True, errors="raise")
    truth_times = {
        str(asset_id): group["failure_occurred_at"]
        .sort_values()
        .to_numpy(dtype="datetime64[ns]")
        .astype("int64")
        for asset_id, group in truth.groupby("asset_id", sort=True)
    }

    frames: list[pd.DataFrame] = []
    baseline_stats: dict[str, dict[str, dict[str, float]]] = {}
    cadence_minutes: list[float] = []
    for asset_id, group in obs.groupby("asset_id", sort=True):
        group = group.sort_values("observed_at", kind="mergesort").reset_index(drop=True)
        diffs = group["observed_at"].diff().dropna().dt.total_seconds().div(60.0)
        if not diffs.empty:
            cadence_minutes.append(float(diffs.median()))

        raw = group[SENSORS].apply(pd.to_numeric, errors="raise").astype(float)
        baseline_end = group["observed_at"].iloc[0] + pd.Timedelta(days=7)
        baseline_mask = (group["observed_at"] < baseline_end) & (group["operating_state"] == "running")
        if int(baseline_mask.sum()) < 36:
            raise ValueError(f"asset {asset_id} has insufficient running baseline rows")
        baseline_mean = raw.loc[baseline_mask].mean()
        baseline_std = raw.loc[baseline_mask].std().replace(0.0, 1.0).fillna(1.0)
        baseline_stats[str(asset_id)] = {
            sensor: {"mean": float(baseline_mean[sensor]), "std": float(baseline_std[sensor])}
            for sensor in SENSORS
        }
        numeric = (raw - baseline_mean) / baseline_std

        features = pd.DataFrame(index=group.index)
        for sensor in SENSORS:
            series = numeric[sensor]
            features[f"{sensor}_current"] = series
            features[f"{sensor}_6h_mean"] = series.rolling(36, min_periods=12).mean()
            features[f"{sensor}_6h_std"] = series.rolling(36, min_periods=12).std()
            features[f"{sensor}_6h_max_abs"] = series.abs().rolling(36, min_periods=12).max()
            features[f"{sensor}_6h_change"] = (series - series.shift(35)) / 6.0
            features[f"{sensor}_1h_change"] = series - series.shift(6)
            features[f"{sensor}_abs_current"] = series.abs()
            features[f"{sensor}_6h_abs_mean"] = series.abs().rolling(36, min_periods=12).mean()

        # Reduce highly duplicated pre-failure labels while retaining an hourly
        # operational cadence after a complete six-hour temporal warm-up.
        selected = np.arange(36, len(group), 6)
        sample = features.iloc[selected].copy()
        sample["asset_id"] = str(asset_id)
        sample["site_id"] = group.iloc[selected]["site_id"].astype(str).to_numpy()
        sample["observed_at"] = group.iloc[selected]["observed_at"].to_numpy()
        sample["operating_state"] = group.iloc[selected]["operating_state"].to_numpy()
        timestamps = sample["observed_at"].to_numpy(dtype="datetime64[ns]").astype("int64")
        event_times = truth_times.get(str(asset_id), np.asarray([], dtype=np.int64))
        sample["label"] = _future_label(timestamps, event_times, horizon_hours)

        # Rows after the dataset's known truth horizon are not confirmed
        # negatives.  Maintenance/non-running rows are not valid pre-failure
        # operating examples either.
        censor_cutoff = group["observed_at"].iloc[-1] - pd.Timedelta(hours=horizon_hours)
        sample = sample[
            (sample["observed_at"] >= baseline_end)
            & (sample["observed_at"] <= censor_cutoff)
            & (sample["operating_state"] == "running")
        ]
        sample = sample.dropna(subset=FEATURE_COLUMNS)
        frames.append(sample)

    if not frames:
        raise ValueError("compressor temporal feature table is empty")
    frame = pd.concat(frames, ignore_index=True)
    if frame["label"].nunique() < 2:
        raise ValueError("compressor temporal labels contain fewer than two classes")
    cadence = float(np.median(cadence_minutes)) if cadence_minutes else 10.0
    metadata = {
        "horizon_hours": horizon_hours,
        "expected_cadence_minutes": cadence,
        "baseline_days": 7,
        "rolling_rows": 36,
        "rolling_min_periods": 12,
        "sample_stride_rows": 6,
        "baseline_calibration_only": True,
        "history_state_policy": "rolling_history_may_include_non_running_rows_current_sample_must_be_running",
        "right_censoring": True,
        "maintenance_rows_excluded": True,
    }
    return frame, baseline_stats, metadata


def _split_chronologically(frame: pd.DataFrame) -> SplitFrames:
    train_parts: list[pd.DataFrame] = []
    validation_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _asset_id, group in frame.groupby("asset_id", sort=True):
        ordered = group.sort_values("observed_at", kind="mergesort")
        size = len(ordered)
        train_end = max(1, min(size - 2, int(size * 0.70)))
        validation_end = max(train_end + 1, min(size - 1, int(size * 0.85)))
        train_parts.append(ordered.iloc[:train_end])
        validation_parts.append(ordered.iloc[train_end:validation_end])
        test_parts.append(ordered.iloc[validation_end:])
    split = SplitFrames(
        train=pd.concat(train_parts, ignore_index=True),
        validation=pd.concat(validation_parts, ignore_index=True),
        test=pd.concat(test_parts, ignore_index=True),
    )
    for name, part in (("train", split.train), ("validation", split.validation), ("test", split.test)):
        if part["label"].nunique() < 2:
            raise ValueError(f"time-ordered {name} split contains fewer than two classes")
    return split


def _candidate(algorithm: str, *, n_jobs: int) -> Pipeline:
    if algorithm == "logistic_regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=1500,
                        class_weight="balanced",
                        C=0.5,
                        random_state=RANDOM_SEED,
                    ),
                ),
            ]
        )
    if algorithm == "random_forest":
        return Pipeline(
            [
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=2,
                        class_weight="balanced_subsample",
                        n_jobs=n_jobs,
                        random_state=RANDOM_SEED,
                    ),
                )
            ]
        )
    raise ValueError(f"unsupported compressor candidate: {algorithm}")


def _metric_set(y_true: pd.Series | np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=int)
    probability = np.asarray(probabilities, dtype=float)
    prediction = (probability >= threshold).astype(int)
    matrix = confusion_matrix(y, prediction, labels=[0, 1]).astype(int).tolist()
    top_count = max(1, int(np.ceil(len(y) * 0.05)))
    top_indices = np.argpartition(probability, -top_count)[-top_count:]
    positive = int(y.sum())
    prevalence = float(y.mean()) if len(y) else 0.0
    precision = float(precision_score(y, prediction, zero_division=0))
    return {
        "sample_count": int(len(y)),
        "positive_count": positive,
        "prevalence": prevalence,
        "roc_auc": float(roc_auc_score(y, probability)) if len(np.unique(y)) == 2 else None,
        "average_precision": float(average_precision_score(y, probability)) if positive else 0.0,
        "precision": precision,
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "confusion_matrix": matrix,
        "top_5pct_recall": float(y[top_indices].sum() / max(1, positive)),
        "alert_rate": float(prediction.mean()) if len(prediction) else 0.0,
        "precision_lift_over_prevalence": float(precision / prevalence) if prevalence > 0 else None,
        "threshold": float(threshold),
    }


def _select_threshold(
    y_true: pd.Series,
    probabilities: np.ndarray,
    *,
    minimum_recall: float,
) -> tuple[float, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    thresholds = sorted(set(np.linspace(0.01, 0.99, 99).tolist() + np.quantile(probabilities, np.linspace(0.02, 0.98, 49)).tolist()))
    for threshold in thresholds:
        metrics = _metric_set(y_true, probabilities, float(threshold))
        rows.append(
            {
                "threshold": float(threshold),
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "confusion_matrix": metrics["confusion_matrix"],
            }
        )
    feasible = [row for row in rows if float(row["recall"]) >= minimum_recall]
    if feasible:
        selected = max(feasible, key=lambda row: (float(row["f1"]), float(row["precision"]), float(row["threshold"])))
    else:
        selected = max(rows, key=lambda row: (float(row["recall"]), float(row["f1"])))
    return float(selected["threshold"]), rows


def _leave_one_site_out(
    frame: pd.DataFrame,
    algorithm: str,
    *,
    n_jobs: int,
    threshold: float,
) -> dict[str, Any]:
    sites = sorted(frame["site_id"].astype(str).unique())
    if len(sites) < 2:
        raise ValueError("regression sanity evaluation requires at least two sites")
    y = frame["label"].to_numpy(dtype=int)
    predictions = np.zeros(len(frame), dtype=float)
    fold_metrics: dict[str, Any] = {}
    site_values = frame["site_id"].astype(str).to_numpy()
    for site in sites:
        test_mask = site_values == site
        train_mask = ~test_mask
        model = _candidate(algorithm, n_jobs=n_jobs)
        model.fit(frame.loc[train_mask, FEATURE_COLUMNS], frame.loc[train_mask, "label"].astype(int))
        fold_probability = model.predict_proba(frame.loc[test_mask, FEATURE_COLUMNS])[:, 1]
        predictions[test_mask] = fold_probability
        fold_metrics[site] = _metric_set(frame.loc[test_mask, "label"], fold_probability, threshold)
    result = _metric_set(y, predictions, threshold)
    result["protocol"] = "leave_one_site_out"
    result["folds"] = fold_metrics
    return result


def train_compressor_model(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
    *,
    n_jobs: int = 2,
    horizon_hours: int = 24,
    minimum_recall: float = 0.30,
) -> TrainingResult:
    frame, baseline_stats, feature_metadata = build_temporal_feature_table(
        observations,
        failures,
        horizon_hours=horizon_hours,
    )
    split = _split_chronologically(frame)
    candidate_names = ("logistic_regression", "random_forest")
    candidate_validation: dict[str, Any] = {}
    candidate_sanity: dict[str, Any] = {}
    fitted: dict[str, Pipeline] = {}
    validation_probabilities: dict[str, np.ndarray] = {}

    for algorithm in candidate_names:
        model = _candidate(algorithm, n_jobs=n_jobs)
        model.fit(split.train[FEATURE_COLUMNS], split.train["label"].astype(int))
        probability = model.predict_proba(split.validation[FEATURE_COLUMNS])[:, 1]
        candidate_validation[algorithm] = _metric_set(split.validation["label"], probability, 0.5)
        fitted[algorithm] = model
        validation_probabilities[algorithm] = probability

    prevalence = float(frame["label"].mean())
    for algorithm in candidate_names:
        candidate_sanity[algorithm] = _leave_one_site_out(
            frame,
            algorithm,
            n_jobs=n_jobs,
            threshold=0.5,
        )

    eligible = [
        algorithm
        for algorithm in candidate_names
        if float(candidate_sanity[algorithm]["average_precision"]) > prevalence
    ] or list(candidate_names)
    selected_model = max(
        eligible,
        key=lambda algorithm: (
            float(candidate_validation[algorithm]["average_precision"]),
            float(candidate_sanity[algorithm]["average_precision"]),
        ),
    )
    threshold, threshold_curve = _select_threshold(
        split.validation["label"],
        validation_probabilities[selected_model],
        minimum_recall=minimum_recall,
    )
    deployment_test_probability = fitted[selected_model].predict_proba(split.test[FEATURE_COLUMNS])[:, 1]
    deployment_test = _metric_set(split.test["label"], deployment_test_probability, threshold)
    regression_sanity = _leave_one_site_out(
        frame,
        selected_model,
        n_jobs=n_jobs,
        threshold=threshold,
    )

    final_model = _candidate(selected_model, n_jobs=n_jobs)
    final_model.fit(frame[FEATURE_COLUMNS], frame["label"].astype(int))
    positive = int(frame["label"].sum())
    feature_schema = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "features": FEATURE_COLUMNS,
        "target": "failure_within_24h",
        "prediction_task": "binary_failure_within_horizon",
        "observation_family": "compressor",
        "feature_engineering": {
            "kind": FEATURE_ENGINEERING_KIND,
            "base_sensors": SENSORS,
            **feature_metadata,
            "runtime_context": {
                "asset_baseline": "artifact_embedded_per_asset_first_7d_running",
                "recent_history_rows_required": 35,
                "history_order": "strictly_ascending_before_current_observation",
                "new_asset_policy": "calibrate_baseline_before_inference",
            },
            "baseline_stats": baseline_stats,
        },
    }
    training_config = {
        "training_version": TRAINING_VERSION,
        "selected_model": selected_model,
        "candidate_models": list(candidate_names),
        "random_seed": RANDOM_SEED,
        "n_jobs": n_jobs,
        "label_horizon_hours": horizon_hours,
        "deployment_split": "per_asset_chronological_70_15_15",
        "regression_sanity_split": "leave_one_site_out",
        "threshold_selection": "validation_max_f1_with_minimum_recall_constraint",
        "minimum_recall": minimum_recall,
        "selected_threshold": threshold,
        "test_used_for_selection": False,
    }
    metrics = {
        "feature_table": {
            "rows": int(len(frame)),
            "positive_labels": positive,
            "negative_labels": int(len(frame) - positive),
            "prevalence": prevalence,
            "feature_count": len(FEATURE_COLUMNS),
        },
        "candidate_validation_metrics_at_0_5": candidate_validation,
        "candidate_regression_sanity_at_0_5": candidate_sanity,
        "selected_model": selected_model,
        "selected_threshold": threshold,
        "threshold_selection_methodology": (
            "validation max F1 subject to recall >= minimum_recall; "
            "deployment test untouched during threshold selection"
        ),
        "regression_sanity": regression_sanity,
        "deployment_realism_test": deployment_test,
        "reference_context": {
            "canonical_v3_1_compressor_reference_pr_auc": 0.222111,
            "canonical_v3_1_compressor_reference_roc_auc": 0.734353,
            "canonical_v3_1_compressor_reference_top_5pct_recall": 0.283333,
            "reference_is_regression_sanity_not_production_guarantee": True,
        },
    }
    return TrainingResult(
        model=final_model,
        selected_model=selected_model,
        feature_schema=feature_schema,
        training_config=training_config,
        metrics=metrics,
        threshold_curve=threshold_curve,
        feature_table_rows=int(len(frame)),
        positive_labels=positive,
        negative_labels=int(len(frame) - positive),
    )
