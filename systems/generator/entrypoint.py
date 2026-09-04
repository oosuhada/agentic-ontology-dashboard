"""Standalone Generator batch entrypoint.

This module deliberately exposes a batch CLI rather than a permanently busy API
server. It exercises the PR #21 extraction/mapping/feature/label path and keeps
the final Generator/Backend boundary at the immutable Model Artifact publisher.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from systems.generator.extraction.extraction_profiler import load_family_registry
from systems.generator.extraction.extraction_service import get_last_plans, load_all_sources
from systems.generator.feature.feature_builder import build_features, save_features_npy
from systems.generator.feature.feature_catalog import load_catalog
from systems.generator.feature.feature_label_service import build_labels
from systems.generator.generator_config import PATHS
from systems.generator.model.cnc_training import (
    FEATURE_SCHEMA_VERSION as CNC_FEATURE_SCHEMA_VERSION,
    TRAINING_VERSION as CNC_TRAINING_VERSION,
    train_cnc_model,
)
from systems.generator.model.compressor_training import (
    FEATURE_SCHEMA_VERSION,
    TRAINING_VERSION,
    train_compressor_model,
)
from systems.generator.model.model_registry import publish_model_artifact
from systems.generator.model.legacy_v31_training import (
    CLASS_WEIGHT as LEGACY_CLASS_WEIGHT,
    FAMILY_SENSORS as LEGACY_FAMILY_SENSORS,
    MAX_ITER as LEGACY_MAX_ITER,
    MODEL_VERSION as LEGACY_MODEL_VERSION,
    RANDOM_SEED as LEGACY_RANDOM_SEED,
    REFERENCE_PROBABILITY_TOLERANCE as LEGACY_PROBABILITY_TOLERANCE,
    REGULARIZATION_C as LEGACY_REGULARIZATION_C,
    reconstruct_legacy_v31_model,
)
from systems.generator.ontology_mapping.mapping_agent import map_all_sources
from systems.generator.ontology_mapping.mapping_cache import get_mapping_store

logger = logging.getLogger(__name__)

def _metadata_for(source_key: str, registry: dict[str, Any]) -> dict[str, Any]:
    filename = next((name for name in registry if Path(name).stem == source_key), None)
    return registry.get(filename, {}) if filename else {}


def _effective_plan(
    source_key: str,
    plans: dict[str, Any],
    metadata: dict[str, Any],
    frame: pd.DataFrame,
) -> dict[str, Any]:
    """Fill LLM-fallback plan gaps from Stage-0 metadata/canonical columns."""

    plan = dict(plans.get(source_key) or {})
    id_candidates = [metadata.get("id_col"), "asset_id", "machineID", "equipment_id", "device_id"]
    time_candidates = [metadata.get("time_col"), "observed_at", "datetime", "timestamp", "time"]
    if not plan.get("id_column") or plan.get("id_column") not in frame.columns:
        plan["id_column"] = next((column for column in id_candidates if column and column in frame.columns), None)
    if not plan.get("time_column") or plan.get("time_column") not in frame.columns:
        plan["time_column"] = next((column for column in time_candidates if column and column in frame.columns), None)
    return plan


def _select_pipeline_pair(sources: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    registry = load_family_registry()
    telemetry = [key for key in sources if _metadata_for(key, registry).get("role") == "telemetry_sensor"]
    failures = [
        key
        for key in sources
        if _metadata_for(key, registry).get("role") in {"failure_event", "evaluation_truth"}
    ]
    for telemetry_key in telemetry:
        telemetry_meta = _metadata_for(telemetry_key, registry)
        telemetry_ids = set(telemetry_meta.get("id_columns") or [])
        for failure_key in failures:
            failure_meta = _metadata_for(failure_key, registry)
            if telemetry_ids.intersection(failure_meta.get("id_columns") or []):
                return telemetry_key, failure_key, telemetry_meta, failure_meta
    raise ValueError(
        "no telemetry/failure pair with a shared asset identifier was found; "
        "stage-0 source_family_registry.json contains the authoritative roles"
    )


def run_feature_label_pipeline(*, force_reanalyze: bool = False) -> dict[str, Any]:
    sources = load_all_sources(str(PATHS.data_dir), force_reanalyze=force_reanalyze)
    store = map_all_sources(sources, get_mapping_store())
    telemetry_key, failure_key, telemetry_meta, failure_meta = _select_pipeline_pair(sources)
    plans = get_last_plans()
    plan = _effective_plan(telemetry_key, plans, telemetry_meta, sources[telemetry_key])
    features = build_features(sources[telemetry_key], store, load_catalog(), plan=plan)
    labeled = build_labels(
        features,
        sources[failure_key],
        failure_meta=failure_meta,
        plan=plan,
    )
    output_dir = PATHS.data_preprocessed / "features"
    save_features_npy(features, str(output_dir), telemetry_key, plan=plan)
    labeled_path = PATHS.data_preprocessed / f"{telemetry_key}_labeled.csv"
    labeled.to_csv(labeled_path, index=False)
    positive = int(labeled["label"].sum()) if "label" in labeled else 0
    return {
        "source_files": len(sources),
        "telemetry_source": telemetry_key,
        "failure_source": failure_key,
        "input_rows": int(len(sources[telemetry_key])),
        "feature_rows": int(len(features)),
        "feature_count": max(0, int(len(features.columns) - 2)),
        "labeled_rows": int(len(labeled)),
        "positive_labels": positive,
        "negative_labels": int(len(labeled) - positive),
        "asset_count": int(features[plan["id_column"]].nunique()) if plan.get("id_column") in features else 1,
        "labeled_output": str(labeled_path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _training_n_jobs() -> int:
    value = int(os.getenv("GENERATOR_TRAINING_N_JOBS", "2"))
    if value == 0 or value < -1:
        raise ValueError("GENERATOR_TRAINING_N_JOBS must be -1 or a positive integer")
    return value


def publish_training_artifact(*, force_reanalyze: bool = False) -> Path:
    """Train a runtime-compatible compressor model and publish it immutably.

    The source remains the gen_data file contract. Training labels use the same
    failure-horizon semantics as the Generator feature/label stage, while the
    published feature schema is intentionally limited to fields the Backend
    runtime observation contract can provide.
    """

    artifact_uri = os.getenv("MODEL_ARTIFACT_URI", "").strip()
    if not artifact_uri:
        raise RuntimeError("MODEL_ARTIFACT_URI is required for Generator publication")

    observation_path = Path(
        os.getenv(
            "COMPRESSOR_OBSERVATION_URI",
            str(PATHS.data_dir / "compressor_sensor_observation.csv"),
        )
    ).expanduser().resolve()
    configured_truth = os.getenv("COMPRESSOR_FAILURE_TRUTH_URI", "").strip()
    truth_candidates = [
        Path(configured_truth).expanduser().resolve() if configured_truth else None,
        (PATHS.data_dir / "compressor_failure_truth.csv").resolve(),
        (
            PATHS.data_dir.parent
            / "evaluation_truth"
            / "compressor_failure_truth.csv"
        ).resolve(),
    ]
    failure_path = next((path for path in truth_candidates if path and path.is_file()), None)
    if not observation_path.is_file():
        raise ValueError(
            f"compressor observation source does not exist: {observation_path}"
        )
    if failure_path is None:
        raise ValueError(
            "compressor failure truth source does not exist; set "
            "COMPRESSOR_FAILURE_TRUTH_URI or provide "
            "../evaluation_truth/compressor_failure_truth.csv relative to DATA_DIR"
        )

    observations = pd.read_csv(observation_path)
    failures = pd.read_csv(failure_path)

    training = train_compressor_model(
        observations,
        failures,
        n_jobs=_training_n_jobs(),
        horizon_hours=24,
        minimum_recall=0.30,
    )

    source_sha = _sha256(observation_path)
    dataset_version = f"gen-data-v3.1-sha256-{source_sha[:12]}"
    algorithm_slug = training.selected_model.replace("_", "-")
    model_version = f"compressor-{algorithm_slug}-v3-{source_sha[:12]}"
    destination = Path(str(artifact_uri).removeprefix("file://")).expanduser().resolve() / "compressor-failure-risk" / model_version
    if destination.exists():
        return destination

    with tempfile.TemporaryDirectory(prefix="compressor-model-") as work:
        model_file = Path(work) / "model.joblib"
        import joblib

        joblib.dump(training.model, model_file)
        threshold_curve_file = Path(work) / "threshold_curve.json"
        threshold_curve_file.write_text(
            json.dumps(training.threshold_curve, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        label_schema = {
            "label_schema_version": "compressor-failure-within-horizon-v1",
            "target": "failure_within_24h",
            "prediction_task": "binary_failure_within_horizon",
            "prediction_horizon_hours": 24,
            "positive_semantics": "next failure strictly after observation and within 24 hours",
            "post_failure_rows_positive": False,
            "right_censoring": "exclude final 24h of each asset observation horizon",
            "maintenance_rows_excluded": True,
            "truth_usage": "label creation and offline evaluation only",
        }
        runtime_context = dict(
            (training.feature_schema.get("feature_engineering") or {}).get("runtime_context") or {}
        )
        prior_observations = int(runtime_context.get("recent_history_rows_required", 35))
        history_requirement = {
            "history_requirement_version": "compressor-history-requirement-v1",
            "feature_executor_version": FEATURE_SCHEMA_VERSION,
            "observation_family": "compressor",
            "current_observation_required": True,
            "prior_observations_required": prior_observations,
            "minimum_history_rows": prior_observations + 1,
            "required_columns": list(
                (training.feature_schema.get("feature_engineering") or {}).get("base_sensors") or []
            ),
            "missing_history_policy": "fail_closed",
            "expected_cadence_minutes": float(
                (training.feature_schema.get("feature_engineering") or {}).get(
                    "expected_cadence_minutes", 10.0
                )
            ),
            "ordering": runtime_context.get(
                "history_order", "strictly_ascending_before_current_observation"
            ),
            "new_asset_policy": runtime_context.get(
                "new_asset_policy", "calibrate_baseline_before_inference"
            ),
        }
        return publish_model_artifact(
            artifact_uri=artifact_uri,
            model_id="compressor-failure-risk",
            model_version=model_version,
            dataset_version=dataset_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            model_file=model_file,
            feature_schema=training.feature_schema,
            training_config=training.training_config,
            metrics=training.metrics,
            provenance={
                "source_repository": "Biz-CollabCraft/gen_data",
                "source_contract": "Canonical V3.1 file/artifact",
                "source_file": observation_path.name,
                "source_file_sha256": source_sha,
                "failure_truth_file": failure_path.name,
                "failure_truth_file_sha256": _sha256(failure_path),
                "producer": "ontology_dashboard/systems/generator",
                "training_implementation": TRAINING_VERSION,
            },
            compatibility={
                "runtime": "ontology_dashboard.systems.backend.diagnosis",
                "prediction_task": "binary_failure_within_horizon",
                "observation_family": "compressor",
                "python": ">=3.11",
            },
            label_schema=label_schema,
            history_requirement=history_requirement,
            extra_files={"threshold_curve": threshold_curve_file},
        )


def publish_cnc_training_artifact(*, force_reanalyze: bool = False) -> Path:
    """Train the 80-asset Canonical V3.1 CNC family and publish immutably."""

    artifact_uri = os.getenv("MODEL_ARTIFACT_URI", "").strip()
    if not artifact_uri:
        raise RuntimeError("MODEL_ARTIFACT_URI is required for Generator publication")

    observation_path = Path(
        os.getenv("CNC_OBSERVATION_URI", str(PATHS.data_dir / "cnc_sensor_observation.csv"))
    ).expanduser().resolve()
    configured_truth = os.getenv("CNC_FAILURE_TRUTH_URI", "").strip()
    truth_candidates = [
        Path(configured_truth).expanduser().resolve() if configured_truth else None,
        (PATHS.data_dir / "cnc_failure_truth.csv").resolve(),
        (PATHS.data_dir.parent / "evaluation_truth" / "cnc_failure_truth.csv").resolve(),
    ]
    failure_path = next((path for path in truth_candidates if path and path.is_file()), None)
    if not observation_path.is_file():
        raise ValueError(f"CNC observation source does not exist: {observation_path}")
    if failure_path is None:
        raise ValueError(
            "CNC failure truth source does not exist; set CNC_FAILURE_TRUTH_URI or provide "
            "../evaluation_truth/cnc_failure_truth.csv relative to DATA_DIR"
        )

    observations = pd.read_csv(observation_path)
    failures = pd.read_csv(failure_path)

    training = train_cnc_model(
        observations,
        failures,
        n_jobs=_training_n_jobs(),
        horizon_hours=24,
        minimum_recall=0.50,
    )
    source_sha = _sha256(observation_path)
    dataset_version = f"gen-data-v3.1-sha256-{source_sha[:12]}"
    algorithm_slug = training.selected_model.replace("_", "-")
    model_version = f"cnc-{algorithm_slug}-v3-{source_sha[:12]}"
    destination = (
        Path(str(artifact_uri).removeprefix("file://")).expanduser().resolve()
        / "cnc-failure-risk"
        / model_version
    )
    if destination.exists():
        return destination

    with tempfile.TemporaryDirectory(prefix="cnc-model-") as work:
        model_file = Path(work) / "model.joblib"
        import joblib

        joblib.dump(training.model, model_file)
        threshold_curve_file = Path(work) / "threshold_curve.json"
        threshold_curve_file.write_text(
            json.dumps(training.threshold_curve, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        label_schema = {
            "label_schema_version": "cnc-failure-within-horizon-v1",
            "target": "failure_within_24h",
            "prediction_task": "binary_failure_within_horizon",
            "prediction_horizon_hours": 24,
            "positive_semantics": "next failure strictly after observation and within 24 hours",
            "post_failure_rows_positive": False,
            "right_censoring": "exclude final 24h of each asset observation horizon",
            "maintenance_rows_excluded": True,
            "truth_usage": "label creation and offline evaluation only",
        }
        runtime_context = dict(
            (training.feature_schema.get("feature_engineering") or {}).get("runtime_context") or {}
        )
        prior_observations = int(runtime_context.get("recent_history_rows_required", 35))
        history_requirement = {
            "history_requirement_version": "cnc-history-requirement-v1",
            "feature_executor_version": CNC_FEATURE_SCHEMA_VERSION,
            "observation_family": "cnc",
            "current_observation_required": True,
            "prior_observations_required": prior_observations,
            "minimum_history_rows": prior_observations + 1,
            "required_columns": list(
                (training.feature_schema.get("feature_engineering") or {}).get("base_sensors") or []
            ),
            "missing_history_policy": "fail_closed",
            "expected_cadence_minutes": float(
                (training.feature_schema.get("feature_engineering") or {}).get(
                    "expected_cadence_minutes", 10.0
                )
            ),
            "ordering": runtime_context.get(
                "history_order", "strictly_ascending_before_current_observation"
            ),
            "new_asset_policy": runtime_context.get(
                "new_asset_policy", "calibrate_baseline_before_inference"
            ),
        }
        return publish_model_artifact(
            artifact_uri=artifact_uri,
            model_id="cnc-failure-risk",
            model_version=model_version,
            dataset_version=dataset_version,
            feature_schema_version=CNC_FEATURE_SCHEMA_VERSION,
            model_file=model_file,
            feature_schema=training.feature_schema,
            training_config=training.training_config,
            metrics=training.metrics,
            provenance={
                "source_repository": "Biz-CollabCraft/gen_data",
                "source_contract": "Canonical V3.1 file/artifact",
                "source_file": observation_path.name,
                "source_file_sha256": source_sha,
                "failure_truth_file": failure_path.name,
                "failure_truth_file_sha256": _sha256(failure_path),
                "producer": "ontology_dashboard/systems/generator",
                "training_implementation": CNC_TRAINING_VERSION,
            },
            compatibility={
                "runtime": "ontology_dashboard.systems.backend.diagnosis",
                "prediction_task": "binary_failure_within_horizon",
                "observation_family": "cnc",
                "python": ">=3.11",
            },
            label_schema=label_schema,
            history_requirement=history_requirement,
            extra_files={"threshold_curve": threshold_curve_file},
        )


def publish_legacy_v31_artifacts() -> dict[str, Path]:
    """Reconstruct and publish the frozen Canonical V3.1 runtime models.

    Publication is allowed only when the immutable source/truth checksums match
    the legacy model contract and the reconstructed latest probabilities match
    the checked-in reference snapshots.
    """

    artifact_uri = os.getenv("MODEL_ARTIFACT_URI", "").strip()
    if not artifact_uri:
        raise RuntimeError("MODEL_ARTIFACT_URI is required for Generator publication")

    data_dir = PATHS.data_dir.resolve()
    truth_dir = data_dir.parent / "evaluation_truth"
    output_dir = data_dir.parent / "model_outputs"
    contract_path = output_dir / "model_contract.json"
    metrics_path = output_dir / "model_metrics.json"
    snapshot_path = output_dir / "prediction_snapshot.jsonl"
    for required_path in (contract_path, metrics_path, snapshot_path):
        if not required_path.is_file():
            raise ValueError(f"Canonical V3.1 reconstruction input is missing: {required_path}")

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("model_version") != LEGACY_MODEL_VERSION:
        raise ValueError(
            "Canonical model contract does not describe "
            f"{LEGACY_MODEL_VERSION}: {contract.get('model_version')!r}"
        )
    if contract.get("dataset_version") != "canonical-ai4i-physics-v3.1":
        raise ValueError("Canonical model contract dataset version is not V3.1")
    expected_outputs = contract.get("output_sha256") or {}
    for reference_path in (metrics_path, snapshot_path):
        if _sha256(reference_path) != expected_outputs.get(reference_path.name):
            raise ValueError(
                f"Canonical V3.1 reference output checksum mismatch: {reference_path}"
            )
    reference_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    specifications = {
        "compressor": {
            "model_id": "compressor-failure-risk",
            "feature_kind": "compressor-temporal-v2",
            "feature_schema_version": "compressor-independent-logreg-v3.1-features-v1",
            "history_requirement_version": "compressor-independent-logreg-v3.1-history-v1",
        },
        "cnc": {
            "model_id": "cnc-failure-risk",
            "feature_kind": "cnc-temporal-v1",
            "feature_schema_version": "cnc-independent-logreg-v3.1-features-v1",
            "history_requirement_version": "cnc-independent-logreg-v3.1-history-v1",
        },
    }
    published: dict[str, Path] = {}
    artifact_root = Path(str(artifact_uri).removeprefix("file://")).expanduser().resolve()

    for family, specification in specifications.items():
        observation_path = data_dir / f"{family}_sensor_observation.csv"
        truth_path = truth_dir / f"{family}_failure_truth.csv"
        expected_observation_sha = (contract.get("canonical_input_sha256") or {}).get(
            observation_path.name
        )
        expected_truth_sha = (contract.get("evaluation_truth_input_sha256") or {}).get(
            truth_path.name
        )
        if not observation_path.is_file() or _sha256(observation_path) != expected_observation_sha:
            raise ValueError(f"Canonical V3.1 observation checksum mismatch: {observation_path}")
        if not truth_path.is_file() or _sha256(truth_path) != expected_truth_sha:
            raise ValueError(f"Canonical V3.1 failure truth checksum mismatch: {truth_path}")

        destination = artifact_root / str(specification["model_id"]) / LEGACY_MODEL_VERSION
        if destination.exists():
            manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            provenance = manifest.get("provenance") or {}
            if (
                manifest.get("model_version") != LEGACY_MODEL_VERSION
                or provenance.get("canonical_model_contract_sha256") != _sha256(contract_path)
                or provenance.get("reference_snapshot_sha256") != _sha256(snapshot_path)
            ):
                raise ValueError(
                    f"Existing {LEGACY_MODEL_VERSION} artifact does not match the frozen "
                    f"Canonical V3.1 reconstruction contract: {destination}"
                )
            published[family] = destination
            continue

        reconstruction = reconstruct_legacy_v31_model(
            family=family,
            observation_path=observation_path,
            truth_path=truth_path,
            reference_snapshot_path=snapshot_path,
        )
        feature_schema_version = str(specification["feature_schema_version"])
        feature_schema = {
            "schema_version": feature_schema_version,
            "feature_schema_version": feature_schema_version,
            "features": reconstruction.feature_columns,
            "target": "failure_within_24h",
            "prediction_task": "binary_failure_within_horizon",
            "observation_family": family,
            "feature_engineering": {
                "kind": specification["feature_kind"],
                "base_sensors": LEGACY_FAMILY_SENSORS[family],
                "expected_cadence_minutes": 10.0,
                "rolling_rows": 36,
                "rolling_min_periods": 12,
                "sample_stride_rows": 6,
                "baseline_days": 7,
                "runtime_context": {
                    "asset_baseline": "artifact_embedded_per_asset_first_7d_running",
                    "recent_history_rows_required": 35,
                    "history_order": "strictly_ascending_before_current_observation",
                    "new_asset_policy": "calibrate_baseline_before_inference",
                },
                "baseline_stats": reconstruction.baseline_stats,
            },
        }
        training_config = {
            "training_config_version": "independent-logreg-v3.1-frozen-reconstruction-v1",
            "training_version": "independent-logreg-v3.1",
            "selected_model": "logistic_regression",
            "random_seed": LEGACY_RANDOM_SEED,
            "max_iter": LEGACY_MAX_ITER,
            "class_weight": LEGACY_CLASS_WEIGHT,
            "regularization_c": LEGACY_REGULARIZATION_C,
            # V3.1 used 0.5 for the binary failure/no-failure label.  The
            # lower operational severity boundaries are Backend policy, not a
            # replacement binary classifier threshold.
            "selected_threshold": 0.50,
            "severity_thresholds": {
                "attention": 0.20,
                "warning": 0.45,
                "critical": 0.75,
            },
            "label_horizon_hours": 24,
            "reconstruction_policy": (
                "fit frozen recipe only; publish iff latest predictions reproduce "
                "the immutable Canonical V3.1 snapshots"
            ),
        }
        family_metrics = dict(reference_metrics[family])
        family_metrics["runtime_reconstruction"] = {
            "feature_table_rows": reconstruction.rows,
            "positive_rows": reconstruction.positive_rows,
            "reference_prediction_count": reconstruction.reference_prediction_count,
            "max_abs_probability_error": reconstruction.max_reference_probability_error,
            "probability_tolerance": LEGACY_PROBABILITY_TOLERANCE,
            "verified": True,
        }
        history_requirement = {
            "history_requirement_version": specification["history_requirement_version"],
            "feature_executor_version": feature_schema_version,
            "observation_family": family,
            "current_observation_required": True,
            "prior_observations_required": 35,
            "minimum_history_rows": 36,
            "required_columns": LEGACY_FAMILY_SENSORS[family],
            "missing_history_policy": "fail_closed",
            "expected_cadence_minutes": 10.0,
            "ordering": "strictly_ascending_before_current_observation",
            "new_asset_policy": "calibrate_baseline_before_inference",
        }
        label_schema = {
            "label_schema_version": f"{family}-failure-within-horizon-v3.1",
            "target": "failure_within_24h",
            "prediction_task": "binary_failure_within_horizon",
            "prediction_horizon_hours": 24,
            "positive_semantics": "next failure strictly after observation and within 24 hours",
            "post_failure_rows_positive": False,
            "right_censoring": "exclude final 24h of each asset observation horizon",
            "maintenance_rows_excluded": True,
            "truth_usage": "label creation and reconstruction verification only",
        }

        with tempfile.TemporaryDirectory(prefix=f"{family}-legacy-v31-") as work:
            model_file = Path(work) / "model.joblib"
            import joblib

            joblib.dump(reconstruction.model, model_file)
            published[family] = publish_model_artifact(
                artifact_uri=artifact_uri,
                model_id=str(specification["model_id"]),
                model_version=LEGACY_MODEL_VERSION,
                dataset_version=str(contract["dataset_version"]),
                feature_schema_version=feature_schema_version,
                model_file=model_file,
                feature_schema=feature_schema,
                training_config=training_config,
                metrics=family_metrics,
                provenance={
                    "source_repository": "Biz-CollabCraft/gen_data",
                    "source_contract": "Canonical V3.1 file/artifact",
                    "source_package_root": "gen_data/canonical",
                    "source_file": observation_path.name,
                    "source_file_sha256": expected_observation_sha,
                    "failure_truth_file": truth_path.name,
                    "failure_truth_file_sha256": expected_truth_sha,
                    "canonical_model_contract_sha256": _sha256(contract_path),
                    "reference_snapshot_sha256": _sha256(snapshot_path),
                    "producer": "ontology_dashboard/systems/generator",
                    "reconstruction": "deterministic_from_frozen_v3.1_recipe",
                },
                compatibility={
                    "runtime": "ontology_dashboard.systems.generator.runtime_pipeline",
                    "prediction_task": "binary_failure_within_horizon",
                    "observation_family": family,
                    "python": ">=3.11",
                },
                label_schema=label_schema,
                history_requirement=history_requirement,
                extra_files={"legacy_model_contract": contract_path},
            )
    return published


def update_current_alias(artifact_path: Path) -> Path:
    alias = artifact_path.parent / "current"
    temporary = artifact_path.parent / ".current.tmp"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(artifact_path.name)
    os.replace(temporary, alias)
    return alias


def assert_promotion_sanity(artifact_path: Path) -> None:
    """Refuse to promote an artifact that cannot detect known positives.

    Publication remains immutable even when a candidate misses the gate, which
    preserves debugging evidence without moving the Backend's ``current`` alias.
    """

    metrics = json.loads((artifact_path / "metrics.json").read_text(encoding="utf-8"))
    feature_table = metrics.get("feature_table") or {}
    sanity = metrics.get("regression_sanity") or {}
    deployment = metrics.get("deployment_realism_test") or {}
    prevalence = float(feature_table.get("prevalence") or 0.0)
    average_precision = float(sanity.get("average_precision") or 0.0)
    if average_precision <= prevalence:
        raise RuntimeError(
            "Model Artifact promotion blocked: regression sanity average precision "
            f"{average_precision:.6f} is not above prevalence {prevalence:.6f}"
        )
    if average_precision < 0.15:
        raise RuntimeError(
            "Model Artifact promotion blocked: regression sanity average precision "
            f"{average_precision:.6f} is below the project sanity floor 0.150000"
        )
    if float(sanity.get("recall") or 0.0) <= 0.0:
        raise RuntimeError("Model Artifact promotion blocked: regression sanity recall is zero")
    if float(deployment.get("recall") or 0.0) <= 0.0:
        raise RuntimeError("Model Artifact promotion blocked: deployment realism recall is zero")
    deployment_precision = float(deployment.get("precision") or 0.0)
    deployment_prevalence = float(deployment.get("prevalence") or 0.0)
    if deployment_precision <= deployment_prevalence:
        raise RuntimeError(
            "Model Artifact promotion blocked: deployment alert precision does not exceed base prevalence "
            f"({deployment_precision:.6f} <= {deployment_prevalence:.6f})"
        )
    manifest = json.loads((artifact_path / "manifest.json").read_text(encoding="utf-8"))
    family = str((manifest.get("compatibility") or {}).get("observation_family") or "")
    if family == "compressor":
        deployment_ap = float(deployment.get("average_precision") or 0.0)
        deployment_recall = float(deployment.get("recall") or 0.0)
        precision_lift = float(deployment.get("precision_lift_over_prevalence") or 0.0)
        if deployment_ap < 0.15:
            raise RuntimeError(
                "Compressor Model Artifact promotion blocked: deployment average precision "
                f"{deployment_ap:.6f} is below the 0.150000 release floor"
            )
        if deployment_precision < 0.05:
            raise RuntimeError(
                "Compressor Model Artifact promotion blocked: deployment alert precision "
                f"{deployment_precision:.6f} is below the 0.050000 release floor"
            )
        if deployment_recall < 0.30:
            raise RuntimeError(
                "Compressor Model Artifact promotion blocked: deployment recall "
                f"{deployment_recall:.6f} is below the 0.300000 release floor"
            )
        if precision_lift < 5.0:
            raise RuntimeError(
                "Compressor Model Artifact promotion blocked: precision lift "
                f"{precision_lift:.6f} is below the 5.000000 release floor"
            )
    if family == "cnc":
        if deployment_precision < 0.50:
            raise RuntimeError(
                "CNC Model Artifact promotion blocked: deployment alert precision "
                f"{deployment_precision:.6f} is below the 0.500000 release floor"
            )
        if float(deployment.get("recall") or 0.0) < 0.30:
            raise RuntimeError(
                "CNC Model Artifact promotion blocked: deployment recall is below the 0.300000 release floor"
            )


def llm_smoke() -> dict[str, Any]:
    from systems.generator.generator_llm_client import ExtractionStructureResponse, call_llm, validate_or_transform_pydantic

    raw = call_llm(
        'Return only JSON: {"structure_type":"tabular_column_as_attribute","reason":"runtime smoke"}',
        system="Return the requested JSON only.",
    )
    parsed = validate_or_transform_pydantic(raw, ExtractionStructureResponse)
    if parsed is None:
        raise RuntimeError("OpenAI response failed Pydantic parsing")
    return {"status": "ok", "structure_type": parsed.structure_type}


def main() -> int:
    parser = argparse.ArgumentParser(description="ontology_dashboard standalone Generator")
    parser.add_argument(
        "command",
        choices=(
            "run",
            "feature-label",
            "train-publish",
            "train-publish-cnc",
            "train-publish-all",
            "reconstruct-publish-v3-1",
            "llm-smoke",
        ),
        nargs="?",
        default="run",
    )
    parser.add_argument("--force-reanalyze", action="store_true")
    parser.add_argument(
        "--promote-current",
        action="store_true",
        help="after metric sanity gates pass, atomically move the current alias to the published artifact",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

    result: dict[str, Any] = {}
    promotion_failures: list[str] = []
    if args.command in {"run", "feature-label"}:
        result["pipeline"] = run_feature_label_pipeline(force_reanalyze=args.force_reanalyze)
    if args.command in {"run", "train-publish", "train-publish-all"}:
        artifact = publish_training_artifact(force_reanalyze=args.force_reanalyze)
        manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
        result["artifact"] = {
            "path": str(artifact),
            "model_version": manifest["model_version"],
            "dataset_version": manifest["dataset_version"],
            "artifact_files": len(manifest["artifact_files"]),
            "promoted_current": False,
        }
        if args.promote_current:
            try:
                assert_promotion_sanity(artifact)
                current = update_current_alias(artifact)
                result["artifact"]["current_uri"] = str(current)
                result["artifact"]["promoted_current"] = True
            except RuntimeError as exc:
                result["artifact"]["promotion_error"] = str(exc)
                promotion_failures.append(f"compressor: {exc}")
    if args.command in {"run", "train-publish-cnc", "train-publish-all"}:
        cnc_artifact = publish_cnc_training_artifact(force_reanalyze=args.force_reanalyze)
        cnc_manifest = json.loads((cnc_artifact / "manifest.json").read_text(encoding="utf-8"))
        result["cnc_artifact"] = {
            "path": str(cnc_artifact),
            "model_version": cnc_manifest["model_version"],
            "dataset_version": cnc_manifest["dataset_version"],
            "artifact_files": len(cnc_manifest["artifact_files"]),
            "promoted_current": False,
        }
        if args.promote_current:
            try:
                assert_promotion_sanity(cnc_artifact)
                cnc_current = update_current_alias(cnc_artifact)
                result["cnc_artifact"]["current_uri"] = str(cnc_current)
                result["cnc_artifact"]["promoted_current"] = True
            except RuntimeError as exc:
                result["cnc_artifact"]["promotion_error"] = str(exc)
                promotion_failures.append(f"cnc: {exc}")
    if args.command == "reconstruct-publish-v3-1":
        legacy_artifacts = publish_legacy_v31_artifacts()
        result["legacy_v3_1_artifacts"] = {
            family: {
                "path": str(path),
                "model_version": LEGACY_MODEL_VERSION,
            }
            for family, path in sorted(legacy_artifacts.items())
        }
    if args.command == "llm-smoke":
        result["llm"] = llm_smoke()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if promotion_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
