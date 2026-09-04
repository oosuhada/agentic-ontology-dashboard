"""Canonical V3.1 CNC temporal training for immutable Model Artifacts.

This module implements the same source/label semantics as the legacy gen_data
regression benchmark without importing gen_data at runtime.  The release model
is selected on a per-asset chronological validation split; leave-one-site-out
metrics remain a separate regression-sanity view.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .compressor_training import (
    RANDOM_SEED,
    SplitFrames,
    TrainingResult,
    _future_label,
    _metric_set,
    _select_threshold,
)


TRAINING_VERSION = "cnc-temporal-v3-operational-selection"
FEATURE_SCHEMA_VERSION = "cnc-temporal-v1"
FEATURE_ENGINEERING_KIND = "cnc-temporal-v1"
SENSORS = [
    "air_temperature_k",
    "process_temperature_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
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


def build_temporal_feature_table(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
    *,
    horizon_hours: int = 24,
) -> tuple[pd.DataFrame, dict[str, dict[str, dict[str, float]]], dict[str, Any]]:
    required_observation = {"observed_at", "asset_id", "site_id", "operating_state", *SENSORS}
    missing_observation = sorted(required_observation - set(observations.columns))
    if missing_observation:
        raise ValueError(f"CNC observations missing columns: {missing_observation}")
    required_failure = {"asset_id", "failure_occurred_at"}
    missing_failure = sorted(required_failure - set(failures.columns))
    if missing_failure:
        raise ValueError(f"CNC failure truth missing columns: {missing_failure}")

    obs = observations.copy()
    obs["asset_id"] = obs["asset_id"].astype(str)
    obs["observed_at"] = pd.to_datetime(obs["observed_at"], utc=True, errors="raise")
    truth = failures.copy()
    truth["asset_id"] = truth["asset_id"].astype(str)
    truth["failure_occurred_at"] = pd.to_datetime(
        truth["failure_occurred_at"], utc=True, errors="raise"
    )
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
        baseline_mask = (group["observed_at"] < baseline_end) & (
            group["operating_state"] == "running"
        )
        if int(baseline_mask.sum()) < 36:
            raise ValueError(f"asset {asset_id} has insufficient running baseline rows")
        baseline_mean = raw.loc[baseline_mask].mean()
        baseline_std = raw.loc[baseline_mask].std().replace(0.0, 1.0).fillna(1.0)
        baseline_stats[str(asset_id)] = {
            sensor: {"mean": float(baseline_mean[sensor]), "std": float(baseline_std[sensor])}
            for sensor in SENSORS
        }
        normalized = (raw - baseline_mean) / baseline_std

        features = pd.DataFrame(index=group.index)
        for sensor in SENSORS:
            series = normalized[sensor]
            features[f"{sensor}_current"] = series
            features[f"{sensor}_6h_mean"] = series.rolling(36, min_periods=12).mean()
            features[f"{sensor}_6h_std"] = series.rolling(36, min_periods=12).std()
            features[f"{sensor}_6h_max_abs"] = series.abs().rolling(36, min_periods=12).max()
            features[f"{sensor}_6h_change"] = (series - series.shift(35)) / 6.0
            features[f"{sensor}_1h_change"] = series - series.shift(6)
            features[f"{sensor}_abs_current"] = series.abs()
            features[f"{sensor}_6h_abs_mean"] = series.abs().rolling(36, min_periods=12).mean()

        selected = np.arange(36, len(group), 6)
        sample = features.iloc[selected].copy()
        sample["asset_id"] = str(asset_id)
        sample["site_id"] = group.iloc[selected]["site_id"].astype(str).to_numpy()
        sample["observed_at"] = group.iloc[selected]["observed_at"].to_numpy()
        sample["operating_state"] = group.iloc[selected]["operating_state"].to_numpy()
        timestamps = sample["observed_at"].to_numpy(dtype="datetime64[ns]").astype("int64")
        event_times = truth_times.get(str(asset_id), np.asarray([], dtype=np.int64))
        sample["label"] = _future_label(timestamps, event_times, horizon_hours)
        censor_cutoff = group["observed_at"].iloc[-1] - pd.Timedelta(hours=horizon_hours)
        sample = sample[
            (sample["observed_at"] >= baseline_end)
            & (sample["observed_at"] <= censor_cutoff)
            & (sample["operating_state"] == "running")
        ]
        sample = sample.dropna(subset=FEATURE_COLUMNS)
        frames.append(sample)

    if not frames:
        raise ValueError("CNC temporal feature table is empty")
    frame = pd.concat(frames, ignore_index=True)
    if frame["label"].nunique() < 2:
        raise ValueError("CNC temporal labels contain fewer than two classes")
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
            raise ValueError(f"time-ordered CNC {name} split contains fewer than two classes")
    return split


def _candidate(algorithm: str, *, n_jobs: int) -> Pipeline:
    if algorithm == "logistic_regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=2000,
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
                        n_estimators=360,
                        min_samples_leaf=2,
                        class_weight="balanced_subsample",
                        max_features="sqrt",
                        n_jobs=n_jobs,
                        random_state=RANDOM_SEED,
                    ),
                )
            ]
        )
    if algorithm == "extra_trees":
        return Pipeline(
            [
                (
                    "classifier",
                    ExtraTreesClassifier(
                        n_estimators=360,
                        min_samples_leaf=2,
                        class_weight="balanced",
                        max_features="sqrt",
                        n_jobs=n_jobs,
                        random_state=RANDOM_SEED,
                    ),
                )
            ]
        )
    if algorithm == "lightgbm":
        from lightgbm import LGBMClassifier

        return Pipeline(
            [
                (
                    "classifier",
                    LGBMClassifier(
                        n_estimators=360,
                        learning_rate=0.05,
                        num_leaves=31,
                        class_weight="balanced",
                        subsample=0.9,
                        colsample_bytree=0.9,
                        n_jobs=n_jobs,
                        random_state=RANDOM_SEED,
                        verbosity=-1,
                    ),
                )
            ]
        )
    if algorithm == "xgboost":
        from xgboost import XGBClassifier

        return Pipeline(
            [
                (
                    "classifier",
                    XGBClassifier(
                        n_estimators=360,
                        max_depth=6,
                        learning_rate=0.05,
                        subsample=0.9,
                        colsample_bytree=0.9,
                        tree_method="hist",
                        eval_metric="logloss",
                        n_jobs=n_jobs,
                        random_state=RANDOM_SEED,
                    ),
                )
            ]
        )
    raise ValueError(f"unsupported CNC candidate: {algorithm}")


def _leave_one_site_out(
    frame: pd.DataFrame,
    algorithm: str,
    *,
    n_jobs: int,
    threshold: float,
) -> dict[str, Any]:
    sites = sorted(frame["site_id"].astype(str).unique())
    if len(sites) < 2:
        raise ValueError("CNC regression sanity evaluation requires at least two sites")
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


def train_cnc_model(
    observations: pd.DataFrame,
    failures: pd.DataFrame,
    *,
    n_jobs: int = 2,
    horizon_hours: int = 24,
    minimum_recall: float = 0.50,
) -> TrainingResult:
    frame, baseline_stats, feature_metadata = build_temporal_feature_table(
        observations,
        failures,
        horizon_hours=horizon_hours,
    )
    split = _split_chronologically(frame)
    candidate_names = (
        "logistic_regression",
        "random_forest",
        "extra_trees",
        "lightgbm",
        "xgboost",
    )
    candidate_validation: dict[str, Any] = {}
    candidate_sanity: dict[str, Any] = {}
    candidate_operating_points: dict[str, Any] = {}
    candidate_thresholds: dict[str, float] = {}
    candidate_threshold_curves: dict[str, list[dict[str, Any]]] = {}
    fitted: dict[str, Pipeline] = {}
    validation_probabilities: dict[str, np.ndarray] = {}

    for algorithm in candidate_names:
        model = _candidate(algorithm, n_jobs=n_jobs)
        model.fit(split.train[FEATURE_COLUMNS], split.train["label"].astype(int))
        probability = model.predict_proba(split.validation[FEATURE_COLUMNS])[:, 1]
        candidate_validation[algorithm] = _metric_set(split.validation["label"], probability, 0.5)
        fitted[algorithm] = model
        validation_probabilities[algorithm] = probability
        candidate_threshold, candidate_curve = _select_threshold(
            split.validation["label"],
            probability,
            minimum_recall=minimum_recall,
        )
        candidate_thresholds[algorithm] = candidate_threshold
        candidate_threshold_curves[algorithm] = candidate_curve
        candidate_operating_points[algorithm] = _metric_set(
            split.validation["label"],
            probability,
            candidate_threshold,
        )

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
        and float(candidate_operating_points[algorithm]["recall"]) >= minimum_recall
    ] or list(candidate_names)
    selected_model = max(
        eligible,
        key=lambda algorithm: (
            float(candidate_operating_points[algorithm]["f1"]),
            float(candidate_operating_points[algorithm]["precision"]),
            float(candidate_validation[algorithm]["average_precision"]),
            float(candidate_sanity[algorithm]["average_precision"]),
        ),
    )
    threshold = candidate_thresholds[selected_model]
    threshold_curve = candidate_threshold_curves[selected_model]
    deployment_probability = fitted[selected_model].predict_proba(split.test[FEATURE_COLUMNS])[:, 1]
    deployment_test = _metric_set(split.test["label"], deployment_probability, threshold)
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
        "observation_family": "cnc",
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
        "candidate_selection": "validation_operating_point_max_f1_then_precision_under_minimum_recall",
        "threshold_selection": "per_candidate_validation_max_f1_with_minimum_recall_constraint",
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
        "candidate_validation_operating_points": candidate_operating_points,
        "candidate_regression_sanity_at_0_5": candidate_sanity,
        "selected_model": selected_model,
        "selected_threshold": threshold,
        "threshold_selection_methodology": (
            "each candidate selects validation max F1 subject to recall >= minimum_recall; "
            "candidate selection then maximizes validation operating-point F1/precision; "
            "deployment test untouched during threshold selection"
        ),
        "regression_sanity": regression_sanity,
        "deployment_realism_test": deployment_test,
        "reference_context": {
            "canonical_v3_1_cnc_reference_pr_auc": 0.529580,
            "canonical_v3_1_cnc_reference_roc_auc": 0.813453,
            "canonical_v3_1_cnc_reference_top_5pct_recall": 0.598323,
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
