"""Generator-owned multi-model training pipeline and orchestration facade."""

from __future__ import annotations

import json
import logging
import os
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score

from systems.generator.common.timestamp_canonicalizer import canonicalize_timestamp_series
from systems.generator.extraction.extraction_profiler import load_family_registry
from systems.generator.extraction.extraction_service import load_all_sources
from systems.generator.feature.feature_builder import build_features, save_features_npy
from systems.generator.feature.feature_catalog import load_catalog
from systems.generator.feature.feature_label_service import build_labels
from systems.generator.generator_config import PATHS
from systems.generator.model.lightgbm import LightGBMModel
from systems.generator.model.model_registry import (
    get_next_run_version,
    publish_model_artifact,
    save_run_result,
)
from systems.generator.model.random_forest import RandomForestModel
from systems.generator.model.xgboost import XGBoostModel
from systems.generator.ontology_mapping.mapping_agent import map_all_sources
from systems.generator.ontology_mapping.mapping_cache import get_mapping_store, reload_mapping_store
from systems.generator.ontology_mapping.ontology_mapping_capability_service import detect_capabilities

logger = logging.getLogger(__name__)

REGISTERED_MODELS: dict[str, type[Any]] = {
    "lightgbm": LightGBMModel,
    "xgboost": XGBoostModel,
    "random_forest": RandomForestModel,
}

FRAMEWORK_BY_ALGORITHM: dict[str, str] = {
    "lightgbm": "lightgbm",
    "xgboost": "xgboost",
    "random_forest": "scikit-learn",
}

MODEL_SPECS = REGISTERED_MODELS


def infer_history_requirement(
    telemetry: pd.DataFrame,
    *,
    feature_names: list[str],
    id_col: str,
    time_col: str,
) -> dict[str, Any]:
    """Infer runtime history requirements from cadence and published temporal features."""

    cadence_seconds: float | None = None
    if time_col in telemetry.columns:
        work = telemetry[[c for c in (id_col, time_col) if c in telemetry.columns]].copy()
        work[time_col] = canonicalize_timestamp_series(work[time_col], col_name=time_col)
        deltas: list[float] = []
        if id_col in work.columns:
            grouped = work.sort_values([id_col, time_col]).groupby(id_col)[time_col]
            series = grouped.diff().dt.total_seconds()
        else:
            series = work.sort_values(time_col)[time_col].diff().dt.total_seconds()
        deltas = [float(value) for value in series.dropna().tolist() if float(value) > 0]
        if deltas:
            cadence_seconds = float(np.median(np.asarray(deltas, dtype=float)))

    if cadence_seconds is None or not math.isfinite(cadence_seconds) or cadence_seconds <= 0:
        raise ValueError("cannot infer positive telemetry cadence for history requirement")

    minimum_rows = 1
    for feature_name in feature_names:
        parts = str(feature_name).split("__")
        if len(parts) != 4:
            continue
        operation = parts[2]
        parameter_text = parts[3]
        parameters: dict[str, int] = {}
        if parameter_text != "default":
            pieces = parameter_text.split("_")
            if len(pieces) == 2:
                try:
                    parameters[pieces[0]] = int(pieces[1])
                except ValueError:
                    pass
        if operation in {"rolling_mean", "rolling_std", "moving_average"}:
            default_window = 5 if operation != "moving_average" else 10
            minimum_rows = max(minimum_rows, int(parameters.get("window", default_window)))
        elif operation == "ema":
            minimum_rows = max(minimum_rows, int(parameters.get("span", 10)))
        elif operation == "lag":
            minimum_rows = max(minimum_rows, int(parameters.get("periods", 1)) + 1)
        elif operation == "gradient":
            minimum_rows = max(minimum_rows, 2)

    lookback_hours = max(1, math.ceil(((minimum_rows - 1) * cadence_seconds) / 3600.0))
    return {
        "history_requirement_version": "pdm-history-v1",
        "partition_by": id_col,
        "order_by": time_col,
        "expected_sampling_interval_seconds": int(round(cadence_seconds)),
        "minimum_history_rows": minimum_rows,
        "maximum_lookback_hours": lookback_hours,
        "history_sufficiency_policy": "decision-required",
        "missing_history_policy": "fail",
        "current_observation_included_in_window": True,
    }


def get_model_class(name: str) -> type[Any]:
    """Return the model class for a given algorithm name."""
    if name not in REGISTERED_MODELS:
        raise ValueError(f"Unknown model algorithm '{name}'. Available: {list(REGISTERED_MODELS.keys())}")
    return REGISTERED_MODELS[name]


def asset_time_split(
    df: pd.DataFrame,
    id_col: str | None = None,
    time_col: str | None = None,
    test_size: float = 0.20,
    val_size: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Perform chronological asset-time split preventing future observations from leaking into past training data."""
    if df.empty:
        raise ValueError("Cannot split empty DataFrame.")

    resolved_time_col = time_col
    if not resolved_time_col or resolved_time_col not in df.columns:
        for candidate in ("observed_at", "datetime", "timestamp", "time", "date"):
            if candidate in df.columns:
                resolved_time_col = candidate
                break

    resolved_id_col = id_col
    if not resolved_id_col or resolved_id_col not in df.columns:
        for candidate in ("asset_id", "machineID", "equipment_id", "device_id"):
            if candidate in df.columns:
                resolved_id_col = candidate
                break

    work_df = df.copy()
    if resolved_time_col and resolved_time_col in work_df.columns:
        work_df[resolved_time_col] = canonicalize_timestamp_series(work_df[resolved_time_col], col_name=resolved_time_col)

    train_chunks: list[pd.DataFrame] = []
    val_chunks: list[pd.DataFrame] = []
    test_chunks: list[pd.DataFrame] = []

    if resolved_id_col and resolved_id_col in work_df.columns:
        asset_groups = work_df.groupby(resolved_id_col, group_keys=False)
    else:
        asset_groups = [("all", work_df)]

    for _, asset_df in asset_groups:
        if resolved_time_col and resolved_time_col in asset_df.columns:
            sorted_asset_df = asset_df.sort_values(by=resolved_time_col).reset_index(drop=True)
        else:
            sorted_asset_df = asset_df.reset_index(drop=True)

        n = len(sorted_asset_df)
        if n < 3:
            train_chunks.append(sorted_asset_df)
            continue

        n_test = max(1, int(round(n * test_size)))
        n_val = max(1, int(round(n * val_size)))
        if n - n_test - n_val < 1:
            n_train = max(1, n - 2)
            n_val = 1
            n_test = max(1, n - n_train - n_val)
        else:
            n_train = n - n_val - n_test

        train_chunks.append(sorted_asset_df.iloc[:n_train])
        val_chunks.append(sorted_asset_df.iloc[n_train : n_train + n_val])
        test_chunks.append(sorted_asset_df.iloc[n_train + n_val :])

    train_df = pd.concat(train_chunks, ignore_index=True) if train_chunks else work_df.iloc[0:0]
    val_df = pd.concat(val_chunks, ignore_index=True) if val_chunks else work_df.iloc[0:0]
    test_df = pd.concat(test_chunks, ignore_index=True) if test_chunks else work_df.iloc[0:0]

    return train_df, val_df, test_df


def _calculate_metrics(y_true: pd.Series | np.ndarray, probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    y_arr = np.asarray(y_true).astype(int)
    prob_pos = probabilities[:, 1] if probabilities.ndim == 2 else probabilities
    preds = (prob_pos >= threshold).astype(int)

    matrix = confusion_matrix(y_arr, preds, labels=[0, 1]).astype(int).tolist()
    ap = float(average_precision_score(y_arr, prob_pos)) if len(np.unique(y_arr)) > 1 else 0.0
    prec = float(precision_score(y_arr, preds, zero_division=0))
    rec = float(recall_score(y_arr, preds, zero_division=0))
    f1 = float(f1_score(y_arr, preds, zero_division=0))

    return {
        "metrics_schema_version": "pdm-metrics-v1",
        "average_precision": ap,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "threshold": float(threshold),
        "confusion_matrix": matrix,
    }


def _select_training_pair(sources: dict[str, pd.DataFrame]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """Select compatible telemetry and failure event source files based on Stage 0 metadata."""
    registry = load_family_registry()

    telemetry_candidates: list[tuple[str, dict[str, Any]]] = []
    failure_candidates: list[tuple[str, dict[str, Any]]] = []

    for key in sources.keys():
        matched_filename = next((f for f in registry if os.path.splitext(f)[0] == key), None)
        meta = registry.get(matched_filename, {}) if matched_filename else {}
        role = meta.get("role")
        if role == "telemetry_sensor":
            telemetry_candidates.append((key, meta))
        elif role == "failure_event":
            failure_candidates.append((key, meta))

    for t_key, t_meta in telemetry_candidates:
        t_id_cols = set(t_meta.get("id_columns", []))
        for f_key, f_meta in failure_candidates:
            f_id_cols = set(f_meta.get("id_columns", []))
            if t_id_cols and f_id_cols and (t_id_cols & f_id_cols):
                return t_key, f_key, t_meta, f_meta

    if telemetry_candidates and failure_candidates:
        t_key, t_meta = telemetry_candidates[0]
        f_key, f_meta = failure_candidates[0]
        return t_key, f_key, t_meta, f_meta

    keys = list(sources.keys())
    t_key = next((k for k in keys if "telemetry" in k.lower() or "sensor" in k.lower()), keys[0])
    f_key = next((k for k in keys if "failure" in k.lower() or "maint" in k.lower() or k != t_key), keys[0])
    return t_key, f_key, {}, {}


def train_all(
    data_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    artifact_uri: str | Path | None = None,
    prediction_target: str = "pdm-cnc-tool-wear",
    force_reanalyze: bool = False,
) -> dict[str, Any]:
    """Execute end-to-end multi-model training pipeline and publish immutable Model Artifacts."""
    target_data_dir = str(Path(data_dir).resolve()) if data_dir else str(PATHS.data_dir)
    target_store_dir = Path(store_dir).resolve() if store_dir else PATHS.models_store
    target_artifact_uri = artifact_uri or os.environ.get("MODEL_ARTIFACT_URI") or str(target_store_dir / "artifacts")

    logger.info("========================================")
    logger.info(f"🚀 RUNNING MULTI-MODEL TRAINING PIPELINE: data_dir='{target_data_dir}', force_reanalyze={force_reanalyze}")
    logger.info("========================================")

    logger.info(">>> STEP 1: PARSE & EXTRACT SOURCES")
    sources = load_all_sources(target_data_dir, force_reanalyze=force_reanalyze)

    logger.info(">>> STEP 2: ONTOLOGY MAPPING")
    store = get_mapping_store()
    map_all_sources(sources, store)
    reload_mapping_store()

    logger.info(">>> STEP 3: CAPABILITY DETECTION")
    try:
        capabilities = detect_capabilities(store)
    except Exception as e:
        logger.warning(f"[TrainAll] Capability detection warning: {e}")
        capabilities = {}

    logger.info(">>> STEP 4: STAGE 0 METADATA PAIR SELECTION & FEATURE EXTRACTION")
    telemetry_key, failures_key, telemetry_meta, failure_meta = _select_training_pair(sources)
    family_id = telemetry_meta.get("family_id", "unknown")
    id_col = telemetry_meta.get("id_col") or "asset_id"
    time_col = telemetry_meta.get("time_col") or "observed_at"

    plan = {"id_column": id_col, "time_column": time_col}

    catalog = load_catalog()
    features = build_features(sources[telemetry_key], store, catalog, plan=plan)

    try:
        save_features_npy(
            features,
            str(PATHS.data_preprocessed / "features"),
            telemetry_key,
            id_column=id_col,
            time_column=time_col,
        )
    except Exception as e:
        logger.warning(f"[TrainAll] Feature NPY debug cache save warning: {e}")

    logger.info(">>> STEP 5: LABELING (with failure metadata semantics and plan)")
    labeled = build_labels(features, sources[failures_key], failure_meta=failure_meta, plan=plan)
    train_positive_rate = float(labeled["label"].mean()) if "label" in labeled.columns else 0.0
    logger.info(f"Labeled dataset shape: {labeled.shape}, positive rate: {train_positive_rate:.4f}")

    # STEP 6: Determine explicit Feature Schema allowlist
    exclude = set(filter(None, [
        "datetime", "observed_at", "machineID", "asset_id", "label",
        "period_start", "anchor", "failure_point", "exclusion_end", "degradation_start",
        id_col, time_col
    ]))
    feature_names = [c for c in labeled.columns if c not in exclude and pd.api.types.is_numeric_dtype(labeled[c])]

    if not feature_names:
        raise ValueError(f"No numeric feature columns found in labeled dataset for training. Columns: {list(labeled.columns)}")

    logger.info(f"Declared Feature Schema allowlist ({len(feature_names)} features): {feature_names}")

    # STEP 7: Chronological asset-time data split
    train_df, val_df, test_df = asset_time_split(labeled, id_col=id_col, time_col=time_col)
    logger.info(f"Dataset split completed: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # STEP 8: Train models and publish individual immutable Model Artifacts
    run_version = get_next_run_version(store_dir=target_store_dir)
    run_id = f"run-v{run_version}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    results: dict[str, Any] = {}
    failed_models: dict[str, str] = {}
    published_artifacts: dict[str, str] = {}

    for name, cls in REGISTERED_MODELS.items():
        try:
            logger.info(f"Training model algorithm: {name} (run v{run_version})")
            model = cls()
            model.train(
                train_df,
                feature_names=feature_names,
                target_col="label",
                id_col=id_col,
                time_col=time_col,
            )

            val_probs = model.predict_proba(val_df) if not val_df.empty else np.zeros((0, 2))
            val_metrics = _calculate_metrics(val_df["label"], val_probs) if not val_df.empty else {}

            test_probs = model.predict_proba(test_df) if not test_df.empty else np.zeros((0, 2))
            test_metrics = _calculate_metrics(test_df["label"], test_probs) if not test_df.empty else {}

            model_dir = target_store_dir / name
            model_dir.mkdir(parents=True, exist_ok=True)
            model_path = model_dir / f"model_v{run_version}.joblib"
            model.save(str(model_path))

            model_id = f"{prediction_target}-{name}"
            model_version = f"v{run_version}"
            dataset_version = f"ds-{telemetry_key}-v{run_version}"
            feature_schema_version = "pdm-feature-v1"
            framework = FRAMEWORK_BY_ALGORITHM.get(name, getattr(model, "framework", name))

            history_requirement = infer_history_requirement(
                sources[telemetry_key],
                feature_names=feature_names,
                id_col=id_col,
                time_col=time_col,
            )

            label_schema = {
                "label_schema_version": "pdm-label-v1",
                "target": "label",
                "prediction_task": "binary_failure_within_horizon",
                "prediction_horizon_hours": 24,
            }

            prediction_contract = {
                "prediction_task": "binary_failure_within_horizon",
                "prediction_horizon_hours": 24,
                "probability_output": "positive_class_probability",
                "positive_class": 1,
            }

            model_runtime = {
                "format": "joblib",
                "framework": framework,
                "framework_api": "sklearn",
                "entry_role": "model",
                "output_type": "positive_class_probability",
            }

            training_config = {
                "algorithm": name,
                "framework": framework,
                "target_name": "label",
                "feature_count": len(feature_names),
                "split_strategy": "asset_time_split",
                "random_seed": 42,
            }

            metrics = {
                "metrics_schema_version": "pdm-metrics-v1",
                "validation_metrics": val_metrics,
                "test_metrics": test_metrics,
                "train_positive_rate": train_positive_rate,
            }

            artifact_path = publish_model_artifact(
                artifact_uri=target_artifact_uri,
                model_id=model_id,
                model_version=model_version,
                dataset_version=dataset_version,
                feature_schema_version=feature_schema_version,
                model_file=model_path,
                feature_schema={
                    "schema_version": feature_schema_version,
                    "features": feature_names,
                    "target": "label",
                    "prediction_task": "binary_failure_within_horizon",
                    "feature_executor_version": "pdm-feature-executor-v1",
                    "partition_by": id_col,
                    "order_by": time_col,
                },
                training_config=training_config,
                metrics=metrics,
                label_schema=label_schema,
                history_requirement=history_requirement,
                prediction_contract=prediction_contract,
                model_runtime=model_runtime,
                provenance={
                    "training": {
                        "run_id": run_id,
                        "publisher": "systems/generator",
                        "source_telemetry_key": telemetry_key,
                        "source_failures_key": failures_key,
                    }
                },
                compatibility={
                    "runtime": "app.diagnosis",
                    "feature_executor_version": "pdm-feature-executor-v1",
                    "prediction_task": "binary_failure_within_horizon",
                    "python": ">=3.11",
                },
            )

            published_artifacts[name] = str(artifact_path)
            results[name] = {
                "model_id": model_id,
                "model_version": model_version,
                "local_path": str(model_path),
                "artifact_uri": str(artifact_path),
                "train_positive_rate": train_positive_rate,
                "validation_metrics": val_metrics,
                "test_metrics": test_metrics,
            }
            logger.info(f"Successfully trained and published {name} to {artifact_path}")
        except Exception as e:
            logger.error(f"[TrainAll] Model '{name}' failed (other models continue): {e}")
            failed_models[name] = str(e)
            results[name] = None

    if all(v is None for v in results.values()):
        raise ValueError(f"All model training attempts failed: {failed_models}")

    # STEP 9: Record secondary run registry metadata
    run_artifacts_dir = target_store_dir / "runs" / f"v{run_version}"
    run_artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_artifacts_meta = {
        "run_id": run_id,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_cols": feature_names,
        "family_id": family_id,
        "source_telemetry_key": telemetry_key,
        "source_failures_key": failures_key,
        "published_artifacts": published_artifacts,
    }
    with open(run_artifacts_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(run_artifacts_meta, f, ensure_ascii=False, indent=2)

    save_run_result(run_version, results, run_artifacts_meta, store_dir=target_store_dir)

    summary = {
        "run_version": run_version,
        "run_id": run_id,
        "trained_at": run_artifacts_meta["trained_at"],
        "models": {k: v for k, v in results.items() if v is not None},
        "failed_models": failed_models if failed_models else None,
        "published_artifacts": published_artifacts,
    }

    logger.info("========================================")
    logger.info("✅ MULTI-MODEL TRAINING PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("========================================")

    return {
        "capabilities": capabilities,
        "mappings": {
            k: {
                "source_field": v.source_field,
                "target_ontology": v.target_ontology,
                "source": v.source,
                "confidence": v.confidence,
                "status": v.status,
            }
            for k, v in store.get_all().items()
        },
        "registry": summary,
    }


def run_parsing_only(data_dir: str | Path | None = None, force_reanalyze: bool = False) -> dict[str, Any]:
    """Test data extraction, file profiling, and ontology mapping without model training."""
    target_data_dir = str(Path(data_dir).resolve()) if data_dir else str(PATHS.data_dir)
    logger.info(f"🔍 Running parsing test only: data_dir='{target_data_dir}', force_reanalyze={force_reanalyze}")

    sources = load_all_sources(target_data_dir, force_reanalyze=force_reanalyze)

    store = get_mapping_store()
    map_all_sources(sources, store)
    reload_mapping_store()

    family_registry = load_family_registry()

    file_summaries = []
    for key, df in sources.items():
        matched_filename = next((f for f in family_registry if os.path.splitext(f)[0] == key), None)
        meta = family_registry.get(matched_filename, {}) if matched_filename else {}
        file_summaries.append({
            "filename": matched_filename or key,
            "shape": list(df.shape),
            "columns": list(df.columns),
            "role": meta.get("role", "unknown"),
            "confidence": meta.get("confidence"),
            "status": meta.get("status"),
            "id_columns": meta.get("id_columns", []),
            "time_columns": meta.get("time_columns", []),
        })

    return {
        "parsed_files": file_summaries,
        "mappings": {
            k: {
                "source_field": v.source_field,
                "target_ontology": v.target_ontology,
                "source": v.source,
                "confidence": v.confidence,
                "status": v.status,
            }
            for k, v in store.get_all().items()
        },
    }


class ModelTraining:
    """Facade for offline training/evaluation owned by the generator system."""

    @staticmethod
    def train_and_evaluate(*args, **kwargs):
        from .training_impl import train_and_evaluate as implementation

        return implementation(*args, **kwargs)

    @staticmethod
    def train_all(*args, **kwargs):
        return train_all(*args, **kwargs)


def train_and_evaluate(*args, **kwargs):
    from .training_impl import train_and_evaluate as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name in {"ALL_FEATURES", "BASE_FEATURES", "DERIVED_FEATURES"}:
        from . import training_impl

        return getattr(training_impl, name)
    raise AttributeError(name)
