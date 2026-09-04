from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ..feature.dataset import audit_ai4i, canonicalize, load_ai4i

RANDOM_SEED = 42
NUMERIC_FEATURES = [
    "air_temperature_k",
    "process_temperature_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
    "temperature_difference_k",
    "mechanical_power_w",
    "overstrain_index",
]
CATEGORICAL_FEATURES = ["product_type"]
ALL_FEATURES = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]


def _training_n_jobs() -> int:
    """Bound tree-model parallelism for shared production hosts.

    The previous ``n_jobs=-1`` default consumed every host CPU. The Generator is
    a batch workload and shares the Mac mini with databases and unrelated
    services, so production defaults to two workers while remaining explicitly
    configurable for CI/developer machines.
    """

    raw = os.getenv("GENERATOR_TRAINING_N_JOBS", "2").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("GENERATOR_TRAINING_N_JOBS must be an integer") from exc
    if value == 0 or value < -1:
        raise ValueError("GENERATOR_TRAINING_N_JOBS must be -1 or a positive integer")
    return value


@dataclass(frozen=True)
class MetricSet:
    average_precision: float
    precision: float
    recall: float
    f1: float
    confusion_matrix: list[list[int]]


@dataclass(frozen=True)
class ThresholdChoice:
    recall_constrained: float
    recall_target: float
    cost_minimizing: float
    false_negative_cost: float
    false_positive_cost: float


def _preprocessor(*, scale: bool) -> ColumnTransformer:
    numeric_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer(
        transformers=[
            ("numeric", Pipeline(numeric_steps), NUMERIC_FEATURES),
            (
                "category",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def build_candidates() -> dict[str, Pipeline]:
    return {
        "dummy": Pipeline(
            [
                ("preprocess", _preprocessor(scale=False)),
                ("classifier", DummyClassifier(strategy="prior", random_state=RANDOM_SEED)),
            ]
        ),
        "logistic_regression": Pipeline(
            [
                ("preprocess", _preprocessor(scale=True)),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=3000,
                        random_state=RANDOM_SEED,
                    ),
                ),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("preprocess", _preprocessor(scale=False)),
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=2,
                        class_weight="balanced_subsample",
                        n_jobs=_training_n_jobs(),
                        random_state=RANDOM_SEED,
                    ),
                ),
            ]
        ),
    }


def metrics_at_threshold(y_true: pd.Series | np.ndarray, probabilities: np.ndarray, threshold: float) -> MetricSet:
    predictions = (probabilities >= threshold).astype(int)
    matrix = confusion_matrix(y_true, predictions, labels=[0, 1]).astype(int).tolist()
    return MetricSet(
        average_precision=float(average_precision_score(y_true, probabilities)),
        precision=float(precision_score(y_true, predictions, zero_division=0)),
        recall=float(recall_score(y_true, predictions, zero_division=0)),
        f1=float(f1_score(y_true, predictions, zero_division=0)),
        confusion_matrix=matrix,
    )


def select_thresholds(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    minimum_recall: float = 0.80,
    false_negative_cost: float = 10.0,
    false_positive_cost: float = 1.0,
) -> tuple[ThresholdChoice, list[dict[str, float]]]:
    rows: list[dict[str, float]] = []
    for threshold in np.linspace(0.01, 0.99, 99):
        metric = metrics_at_threshold(y_true, probabilities, float(threshold))
        tn, fp = metric.confusion_matrix[0]
        fn, tp = metric.confusion_matrix[1]
        cost = fp * false_positive_cost + fn * false_negative_cost
        rows.append(
            {
                "threshold": float(round(threshold, 4)),
                "precision": metric.precision,
                "recall": metric.recall,
                "f1": metric.f1,
                "false_positives": float(fp),
                "false_negatives": float(fn),
                "true_positives": float(tp),
                "true_negatives": float(tn),
                "expected_cost": float(cost),
            }
        )

    feasible = [row for row in rows if row["recall"] >= minimum_recall]
    if feasible:
        constrained = max(feasible, key=lambda row: (row["precision"], row["f1"], row["threshold"]))
    else:
        constrained = max(rows, key=lambda row: (row["recall"], row["f1"]))
    cost_choice = min(rows, key=lambda row: (row["expected_cost"], -row["recall"]))
    return (
        ThresholdChoice(
            recall_constrained=constrained["threshold"],
            recall_target=minimum_recall,
            cost_minimizing=cost_choice["threshold"],
            false_negative_cost=false_negative_cost,
            false_positive_cost=false_positive_cost,
        ),
        rows,
    )


def train_and_evaluate(
    csv_path: str | Path,
    output_dir: str | Path,
    *,
    minimum_recall: float = 0.80,
    false_negative_cost: float = 10.0,
    false_positive_cost: float = 1.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit = audit_ai4i(csv_path)
    canonical = canonicalize(load_ai4i(csv_path))
    x = canonical[ALL_FEATURES]
    y = canonical["machine_failure"].astype(int)

    x_train_validation, x_test, y_train_validation, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        stratify=y,
        random_state=RANDOM_SEED,
    )
    x_train, x_validation, y_train, y_validation = train_test_split(
        x_train_validation,
        y_train_validation,
        test_size=0.25,
        stratify=y_train_validation,
        random_state=RANDOM_SEED,
    )

    candidates = build_candidates()
    validation_metrics: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Pipeline] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(x_train, y_train)
        probabilities = pipeline.predict_proba(x_validation)[:, 1]
        validation_metrics[name] = asdict(metrics_at_threshold(y_validation, probabilities, 0.5))
        fitted[name] = pipeline

    eligible = [name for name in candidates if name != "dummy"]
    selected_name = max(eligible, key=lambda name: validation_metrics[name]["average_precision"])
    selected_validation_probabilities = fitted[selected_name].predict_proba(x_validation)[:, 1]
    threshold_choice, threshold_curve = select_thresholds(
        y_validation,
        selected_validation_probabilities,
        minimum_recall=minimum_recall,
        false_negative_cost=false_negative_cost,
        false_positive_cost=false_positive_cost,
    )

    selected_pipeline = build_candidates()[selected_name]
    selected_pipeline.fit(x_train_validation, y_train_validation)
    test_probabilities = selected_pipeline.predict_proba(x_test)[:, 1]
    test_metrics = asdict(
        metrics_at_threshold(y_test, test_probabilities, threshold_choice.recall_constrained)
    )
    dummy_test_probabilities = fitted["dummy"].predict_proba(x_test)[:, 1]
    dummy_test_metrics = asdict(metrics_at_threshold(y_test, dummy_test_probabilities, 0.5))

    model_version = f"ai4i-{selected_name}-v1"
    metadata = {
        "schema_version": "1.0",
        "model_version": model_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "dataset": audit.to_dict(),
        "features": ALL_FEATURES,
        "target": "machine_failure",
        "candidate_validation_metrics": validation_metrics,
        "selected_model": selected_name,
        "threshold_choice": asdict(threshold_choice),
        "test_metrics": test_metrics,
        "dummy_test_metrics": dummy_test_metrics,
        "split": {"train": 0.60, "validation": 0.20, "test": 0.20},
        "limitations": [
            "AI4I is synthetic and observations are treated as independent.",
            "Failure-mode labels are excluded from model inputs.",
            "Operational deployment requires customer-specific validation.",
        ],
    }

    joblib.dump(selected_pipeline, output / "model.joblib")
    (output / "model_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "threshold_curve.json").write_text(json.dumps(threshold_curve, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
