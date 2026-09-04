from __future__ import annotations

import importlib
import io
import json
import platform
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from model.contracts import (
    ArtifactReference,
    CandidateResult,
    ExperimentRun,
    MetricSet,
    SplitPolicy,
    ThresholdPolicy,
    canonical_checksum,
)


class ArtifactStore(Protocol):
    def put_bytes(self, relative_path: str, payload: bytes, media_type: str) -> ArtifactReference: ...

EXPERIMENT_ENGINE_VERSION = "predictive-experiment-runner-v1"
REQUIRED_ALGORITHMS = ("dummy_prior", "logistic_regression", "random_forest")
OPTIONAL_ALGORITHMS = ("lightgbm", "xgboost")


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    excluded_embargo_rows: int
    boundaries: dict[str, Any]


def dependency_capabilities() -> dict[str, dict[str, Any]]:
    capabilities: dict[str, dict[str, Any]] = {
        "dummy_prior": {"status": "ready", "version": sklearn.__version__},
        "logistic_regression": {"status": "ready", "version": sklearn.__version__},
        "random_forest": {"status": "ready", "version": sklearn.__version__},
    }
    for algorithm, module_name in (("lightgbm", "lightgbm"), ("xgboost", "xgboost")):
        try:
            module = importlib.import_module(module_name)
            capabilities[algorithm] = {
                "status": "ready",
                "version": getattr(module, "__version__", "unknown"),
            }
        except ImportError:
            capabilities[algorithm] = {
                "status": "blocked_dependency",
                "version": None,
                "reason": f"optional dependency {module_name} is not installed",
            }
    return capabilities


def _group_chronological_split(frame: pd.DataFrame, policy: SplitPolicy) -> SplitFrames:
    if policy.group_field not in frame or policy.time_field not in frame:
        raise ValueError("Split Policy group/time field is missing from Feature Dataset")
    working = frame.copy(deep=True)
    working[policy.time_field] = pd.to_datetime(working[policy.time_field], utc=True, errors="raise")
    working["__split_order"] = np.arange(len(working))
    train_parts: list[pd.DataFrame] = []
    validation_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    excluded = 0
    boundaries: dict[str, Any] = {}
    embargo = pd.Timedelta(hours=policy.embargo_hours)
    for group_value, group in working.groupby(policy.group_field, sort=True):
        ordered = group.sort_values([policy.time_field, "__split_order"], kind="mergesort")
        size = len(ordered)
        if size < 5:
            raise ValueError(f"group {group_value} has fewer than five observations")
        train_end = max(1, min(size - 2, int(np.floor(size * policy.train_fraction))))
        validation_end = max(
            train_end + 1,
            min(size - 1, int(np.floor(size * (policy.train_fraction + policy.validation_fraction)))),
        )
        train_boundary = ordered.iloc[train_end - 1][policy.time_field]
        validation_boundary = ordered.iloc[validation_end - 1][policy.time_field]
        train = ordered.iloc[:train_end]
        validation = ordered.iloc[train_end:validation_end]
        test = ordered.iloc[validation_end:]
        if embargo > pd.Timedelta(0):
            validation_mask = validation[policy.time_field] > train_boundary + embargo
            excluded += int((~validation_mask).sum())
            validation = validation.loc[validation_mask]
            test_mask = test[policy.time_field] > validation_boundary + embargo
            excluded += int((~test_mask).sum())
            test = test.loc[test_mask]
        if train.empty or validation.empty or test.empty:
            raise ValueError(f"split or embargo left group {group_value} without all three partitions")
        train_parts.append(train)
        validation_parts.append(validation)
        test_parts.append(test)
        boundaries[str(group_value)] = {
            "train_end": train_boundary.isoformat(),
            "validation_end": validation_boundary.isoformat(),
            "train_count": len(train),
            "validation_count": len(validation),
            "test_count": len(test),
        }
    return SplitFrames(
        train=pd.concat(train_parts, ignore_index=True).drop(columns="__split_order"),
        validation=pd.concat(validation_parts, ignore_index=True).drop(columns="__split_order"),
        test=pd.concat(test_parts, ignore_index=True).drop(columns="__split_order"),
        excluded_embargo_rows=excluded,
        boundaries=boundaries,
    )


def split_feature_frame(frame: pd.DataFrame, policy: SplitPolicy) -> SplitFrames:
    if policy.mode == "benchmark_random":
        raise ValueError("benchmark_random split is not allowed for promoted operational experiments")
    if policy.mode == "group_holdout":
        groups = sorted(frame[policy.group_field].dropna().astype(str).unique())
        if len(groups) < 3:
            raise ValueError("group_holdout requires at least three groups")
        train_end = max(1, int(len(groups) * policy.train_fraction))
        validation_end = max(train_end + 1, int(len(groups) * (policy.train_fraction + policy.validation_fraction)))
        train_groups = set(groups[:train_end])
        validation_groups = set(groups[train_end:validation_end])
        test_groups = set(groups[validation_end:])
        return SplitFrames(
            train=frame[frame[policy.group_field].astype(str).isin(train_groups)].copy(),
            validation=frame[frame[policy.group_field].astype(str).isin(validation_groups)].copy(),
            test=frame[frame[policy.group_field].astype(str).isin(test_groups)].copy(),
            excluded_embargo_rows=0,
            boundaries={
                "train_groups": sorted(train_groups),
                "validation_groups": sorted(validation_groups),
                "test_groups": sorted(test_groups),
            },
        )
    return _group_chronological_split(frame, policy)


def _preprocessor(frame: pd.DataFrame, feature_columns: list[str], *, scale: bool) -> ColumnTransformer:
    categorical = [
        column
        for column in feature_columns
        if not pd.api.types.is_numeric_dtype(frame[column])
    ]
    numeric = [column for column in feature_columns if column not in categorical]
    numeric_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("numeric", Pipeline(numeric_steps), numeric))
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            )
        )
    if not transformers:
        raise ValueError("Feature Dataset does not contain usable feature columns")
    return ColumnTransformer(transformers=transformers, remainder="drop")


def build_candidate(
    algorithm: str,
    *,
    frame: pd.DataFrame,
    feature_columns: list[str],
    random_seed: int,
) -> Pipeline:
    if algorithm == "dummy_prior":
        estimator: Any = DummyClassifier(strategy="prior", random_state=random_seed)
        scale = False
    elif algorithm == "logistic_regression":
        estimator = LogisticRegression(
            class_weight="balanced",
            max_iter=3000,
            random_state=random_seed,
        )
        scale = True
    elif algorithm == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=250,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=random_seed,
        )
        scale = False
    elif algorithm == "lightgbm":
        module = importlib.import_module("lightgbm")
        estimator = module.LGBMClassifier(
            n_estimators=250,
            class_weight="balanced",
            random_state=random_seed,
            verbosity=-1,
        )
        scale = False
    elif algorithm == "xgboost":
        module = importlib.import_module("xgboost")
        estimator = module.XGBClassifier(
            n_estimators=250,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=random_seed,
            n_jobs=-1,
        )
        scale = False
    else:
        raise ValueError(f"unknown algorithm: {algorithm}")
    return Pipeline(
        [
            ("preprocess", _preprocessor(frame, feature_columns, scale=scale)),
            ("classifier", estimator),
        ]
    )


def metric_set(y_true: pd.Series, probabilities: np.ndarray, threshold: float) -> MetricSet:
    y = np.asarray(y_true, dtype=int)
    probability = np.asarray(probabilities, dtype=float)
    prediction = (probability >= threshold).astype(int)
    positive_count = int(y.sum())
    sample_count = len(y)
    both_classes = len(np.unique(y)) == 2
    return MetricSet(
        average_precision=float(average_precision_score(y, probability)) if positive_count else 0.0,
        roc_auc=float(roc_auc_score(y, probability)) if both_classes else None,
        precision=float(precision_score(y, prediction, zero_division=0)),
        recall=float(recall_score(y, prediction, zero_division=0)),
        f1=float(f1_score(y, prediction, zero_division=0)),
        brier_score=float(brier_score_loss(y, probability)),
        positive_prediction_rate=float(prediction.mean()) if sample_count else 0.0,
        confusion_matrix=confusion_matrix(y, prediction, labels=[0, 1]).astype(int).tolist(),
        sample_count=sample_count,
        positive_count=positive_count,
        positive_rate=float(positive_count / sample_count) if sample_count else 0.0,
        unavailable_reason=None if both_classes else "only_one_target_class_present",
    )


def threshold_curve(
    y_true: pd.Series,
    probabilities: np.ndarray,
    *,
    recall_target: float,
    false_negative_cost: float,
    false_positive_cost: float,
) -> tuple[ThresholdPolicy, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for threshold in np.linspace(0.01, 0.99, 99):
        metrics = metric_set(y_true, probabilities, float(threshold))
        assert metrics.confusion_matrix is not None
        tn, fp = metrics.confusion_matrix[0]
        fn, tp = metrics.confusion_matrix[1]
        rows.append(
            {
                "threshold": float(round(threshold, 4)),
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1": metrics.f1,
                "false_positives": fp,
                "false_negatives": fn,
                "true_positives": tp,
                "true_negatives": tn,
                "expected_cost": fp * false_positive_cost + fn * false_negative_cost,
            }
        )
    feasible = [row for row in rows if float(row["recall"] or 0) >= recall_target]
    recall_choice = max(
        feasible or rows,
        key=lambda row: (
            float(row["precision"] or 0) if feasible else float(row["recall"] or 0),
            float(row["f1"] or 0),
            float(row["threshold"]),
        ),
    )
    cost_choice = min(
        rows,
        key=lambda row: (float(row["expected_cost"]), -float(row["recall"] or 0)),
    )
    policy_payload = {
        "recall_target": recall_target,
        "recall_constrained_threshold": recall_choice["threshold"],
        "cost_minimizing_threshold": cost_choice["threshold"],
        "false_negative_cost": false_negative_cost,
        "false_positive_cost": false_positive_cost,
    }
    return (
        ThresholdPolicy(
            threshold_policy_id=f"threshold-{canonical_checksum(policy_payload)[:24]}",
            version=1,
            selected_operational_threshold=float(recall_choice["threshold"]),
            validation_only_selection=True,
            **policy_payload,
        ),
        rows,
    )


def calibration_rows(y_true: pd.Series, probabilities: np.ndarray) -> list[dict[str, float]]:
    y = np.asarray(y_true, dtype=int)
    if len(np.unique(y)) < 2:
        return []
    fraction, mean = calibration_curve(y, probabilities, n_bins=10, strategy="quantile")
    return [
        {"mean_predicted_probability": float(x), "observed_positive_rate": float(y_value)}
        for x, y_value in zip(mean, fraction, strict=True)
    ]


def evaluation_curves(
    y_true: pd.Series,
    probabilities: np.ndarray,
) -> dict[str, list[dict[str, float]]]:
    y = pd.to_numeric(y_true, errors="coerce").fillna(0).astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return {"precision_recall": [], "roc": []}
    precision, recall, pr_thresholds = precision_recall_curve(y, probabilities)
    precision_recall_rows = [
        {
            "recall": float(recall[index]),
            "precision": float(precision[index]),
            "threshold": float(pr_thresholds[index]) if index < len(pr_thresholds) else 1.0,
        }
        for index in range(len(precision))
    ]
    false_positive_rate, true_positive_rate, roc_thresholds = roc_curve(y, probabilities)
    roc_rows = [
        {
            "false_positive_rate": float(false_positive_rate[index]),
            "true_positive_rate": float(true_positive_rate[index]),
            "threshold": float(roc_thresholds[index]) if np.isfinite(roc_thresholds[index]) else 1.0,
        }
        for index in range(len(false_positive_rate))
    ]
    return {"precision_recall": precision_recall_rows, "roc": roc_rows}


def slice_metrics(
    frame: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
    *,
    label_column: str,
    group_field: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    working = frame.reset_index(drop=True).copy()
    working["__probability"] = probabilities
    for group_value, group in working.groupby(group_field, sort=True):
        if len(group) < 5:
            rows.append(
                {
                    "slice_field": group_field,
                    "slice_value": str(group_value),
                    "available": False,
                    "reason": "fewer_than_five_rows",
                }
            )
            continue
        metrics = metric_set(group[label_column], group["__probability"].to_numpy(), threshold)
        rows.append(
            {
                "slice_field": group_field,
                "slice_value": str(group_value),
                "available": True,
                "metrics": metrics.model_dump(mode="json"),
            }
        )
    return rows


def runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def _joblib_reference(
    store: ArtifactStore,
    *,
    experiment_id: str,
    candidate_id: str,
    model: Any,
) -> ArtifactReference:
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return store.put_bytes(
        f"experiments/{experiment_id}/models/{candidate_id}.joblib",
        buffer.getvalue(),
        "application/octet-stream",
    )


def run_experiment(
    experiment: ExperimentRun,
    *,
    feature_frame: pd.DataFrame,
    algorithms: list[str],
    artifact_store: ArtifactStore,
    recall_target: float,
    false_negative_cost: float,
    false_positive_cost: float,
    progress_callback: Callable[[float, list[CandidateResult]], None] | None = None,
) -> tuple[ExperimentRun, ThresholdPolicy, dict[str, Any]]:
    if "label" not in feature_frame:
        raise ValueError("Feature Dataset does not contain label")
    split = split_feature_frame(feature_frame, experiment.split_policy)
    feature_columns = [column for column in feature_frame if column.startswith("feature__")]
    if not feature_columns:
        raise ValueError("Feature Dataset does not contain materialized feature columns")
    capabilities = dependency_capabilities()
    candidates: list[CandidateResult] = []
    fitted: dict[str, Pipeline] = {}
    validation_probabilities: dict[str, np.ndarray] = {}
    total = max(1, len(algorithms))
    for index, algorithm in enumerate(algorithms, start=1):
        candidate_id = f"candidate-{algorithm}-{uuid.uuid5(uuid.NAMESPACE_URL, experiment.experiment_id + ':' + algorithm)}"
        capability = capabilities.get(algorithm, {"status": "blocked_dependency", "reason": "unregistered algorithm"})
        if capability["status"] != "ready":
            candidates.append(
                CandidateResult(
                    candidate_id=candidate_id,
                    algorithm=algorithm,
                    status="blocked_dependency",
                    dependency_version=capability.get("version"),
                    error_reason=capability.get("reason"),
                )
            )
        else:
            try:
                pipeline = build_candidate(
                    algorithm,
                    frame=split.train,
                    feature_columns=feature_columns,
                    random_seed=experiment.random_seed,
                )
                pipeline.fit(split.train[feature_columns], split.train["label"].astype(int))
                probabilities = pipeline.predict_proba(split.validation[feature_columns])[:, 1]
                metrics = metric_set(split.validation["label"], probabilities, 0.5)
                artifact = _joblib_reference(
                    artifact_store,
                    experiment_id=experiment.experiment_id,
                    candidate_id=candidate_id,
                    model=pipeline,
                )
                candidates.append(
                    CandidateResult(
                        candidate_id=candidate_id,
                        algorithm=algorithm,
                        status="succeeded",
                        dependency_version=capability.get("version"),
                        validation_metrics=metrics,
                        artifact=artifact,
                    )
                )
                fitted[candidate_id] = pipeline
                validation_probabilities[candidate_id] = probabilities
            except Exception as exc:
                candidates.append(
                    CandidateResult(
                        candidate_id=candidate_id,
                        algorithm=algorithm,
                        status="failed",
                        dependency_version=capability.get("version"),
                        error_reason=f"{type(exc).__name__}: {exc}",
                    )
                )
        if progress_callback:
            progress_callback(index / total * 0.8, candidates)

    successful = [
        item
        for item in candidates
        if item.status == "succeeded"
        and item.algorithm != "dummy_prior"
        and item.validation_metrics is not None
    ]
    if not successful:
        raise ValueError("no non-baseline candidate completed successfully")
    selected = max(
        successful,
        key=lambda item: (
            float(item.validation_metrics.average_precision or -1),
            float(item.validation_metrics.recall or -1),
        ),
    )
    selected_probabilities = validation_probabilities[selected.candidate_id]
    threshold_policy, curve = threshold_curve(
        split.validation["label"],
        selected_probabilities,
        recall_target=recall_target,
        false_negative_cost=false_negative_cost,
        false_positive_cost=false_positive_cost,
    )
    selected_model = fitted[selected.candidate_id]
    test_probabilities = selected_model.predict_proba(split.test[feature_columns])[:, 1]
    test_metrics = metric_set(
        split.test["label"],
        test_probabilities,
        threshold_policy.selected_operational_threshold,
    )
    updated_candidates: list[CandidateResult] = []
    for item in candidates:
        if item.candidate_id == selected.candidate_id:
            updated_candidates.append(
                item.model_copy(
                    update={
                        "selected": True,
                        "selection_rationale": "highest validation Average Precision among non-baseline candidates",
                        "held_out_test_metrics": test_metrics,
                    }
                )
            )
        else:
            updated_candidates.append(item)

    curves = evaluation_curves(split.validation["label"], selected_probabilities)
    report = {
        "schema_version": "experiment-report-v1",
        "engine_version": EXPERIMENT_ENGINE_VERSION,
        "experiment_id": experiment.experiment_id,
        "lineage": {
            "dataset_version_id": experiment.dataset_version_id,
            "mapping_set_id": experiment.mapping_set_id,
            "recipe_set_id": experiment.recipe_set_id,
            "feature_dataset_version_id": experiment.feature_dataset_version_id,
            "label_policy_id": experiment.label_policy_id,
        },
        "split": {
            "policy": experiment.split_policy.model_dump(mode="json"),
            "boundaries": split.boundaries,
            "excluded_embargo_rows": split.excluded_embargo_rows,
            "counts": {
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
            },
        },
        "candidate_results": [item.model_dump(mode="json") for item in updated_candidates],
        "selected_candidate_id": selected.candidate_id,
        "threshold_policy": threshold_policy.model_dump(mode="json"),
        "threshold_curve": curve,
        "precision_recall_curve": curves["precision_recall"],
        "roc_curve": curves["roc"],
        "calibration": calibration_rows(split.validation["label"], selected_probabilities),
        "slice_metrics": slice_metrics(
            split.validation,
            selected_probabilities,
            threshold_policy.selected_operational_threshold,
            label_column="label",
            group_field=experiment.split_policy.group_field,
        ),
        "runtime_versions": runtime_versions(),
        "test_used_for_selection": False,
        "validation_used_for_selection": True,
        "limitations": [
            "Operational validity depends on customer-specific validation.",
            "Threshold costs are explicit policy inputs, not measured business costs.",
        ],
    }
    report_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    report_artifact = artifact_store.put_bytes(
        f"experiments/{experiment.experiment_id}/report.json",
        report_bytes,
        "application/json",
    )
    threshold_bytes = json.dumps(
        {"policy": threshold_policy.model_dump(mode="json"), "curve": curve},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    threshold_artifact = artifact_store.put_bytes(
        f"experiments/{experiment.experiment_id}/threshold-policy.json",
        threshold_bytes,
        "application/json",
    )
    threshold_policy = threshold_policy.model_copy(update={"artifact": threshold_artifact})
    completed = experiment.model_copy(
        update={
            "status": "succeeded",
            "progress": 1.0,
            "candidates": updated_candidates,
            "selected_candidate_id": selected.candidate_id,
            "threshold_policy_id": threshold_policy.threshold_policy_id,
            "artifact": report_artifact,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    if progress_callback:
        progress_callback(1.0, updated_candidates)
    return completed, threshold_policy, report


__all__ = [
    "EXPERIMENT_ENGINE_VERSION",
    "OPTIONAL_ALGORITHMS",
    "REQUIRED_ALGORITHMS",
    "SplitFrames",
    "build_candidate",
    "calibration_rows",
    "dependency_capabilities",
    "evaluation_curves",
    "metric_set",
    "run_experiment",
    "runtime_versions",
    "slice_metrics",
    "split_feature_frame",
    "threshold_curve",
]
