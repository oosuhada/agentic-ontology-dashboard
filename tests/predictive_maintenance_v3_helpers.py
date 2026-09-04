from __future__ import annotations

import hashlib
import json
import csv
from pathlib import Path

from test_predictive_maintenance_bundle_adapter import (
    create_small_package,
    refresh_contracts,
    write_jsonl,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_small_v3_package(tmp_path: Path) -> Path:
    root = create_small_package(tmp_path)
    dataset_path = root / "canonical" / "dataset" / "dataset_manifest.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset["dataset_version"] = "canonical-ai4i-physics-v3.1"
    dataset["source_contract"].update(
        {
            "cnc_ai4i_physical_relations": True,
            "failure_modes_satisfy_sensor_conditions": True,
            "asset_variability_policy": "small_offsets_plus_time_varying_physical_process",
        }
    )
    dataset["ai4i_contract"] = {
        "power_formula": "torque_nm * rotational_speed_rpm * 2*pi/60",
        "power_failure_watts": {"below": 3500.0, "above": 9000.0},
        "heat_dissipation_failure": {"temperature_gap_below_k": 8.6, "rpm_below": 1380.0},
        "tool_wear_failure_minutes": {"min": 200.0, "max": 240.0},
        "overstrain_thresholds": {"L": 11000.0, "M": 12000.0, "H": 13000.0},
    }
    dataset_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    for filename in (
        "compressor_sensor_observation.csv",
        "cnc_sensor_observation.csv",
    ):
        path = root / "canonical" / "dataset" / filename
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        for row in rows:
            row["generator_version"] = dataset["dataset_version"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    model_dir = root / "canonical" / "model_outputs"
    for filename in ("prediction_snapshot.jsonl", "prediction_timeline.jsonl"):
        path = model_dir / filename
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for row in rows:
            row["model_version"] = "independent-logreg-v3.1"
        write_jsonl(path, rows)
    snapshots = [
        json.loads(line)
        for line in (model_dir / "prediction_snapshot.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    action_policy = {
        "critical": {"action": "immediate_inspection_and_stop_review", "priority": "urgent"},
        "warning": {"action": "inspect_within_current_shift", "priority": "high"},
        "attention": {"action": "schedule_targeted_diagnostic_check", "priority": "medium"},
        "normal": {"action": "continue_monitoring", "priority": "routine"},
    }
    artifacts = []
    for snapshot in snapshots:
        prediction_id = str(snapshot["prediction_id"])
        status = str(snapshot["status"])
        artifacts.append(
            {
                "artifact_id": f"RESULT#{prediction_id}",
                "artifact_type": "predictive_maintenance_result",
                "schema_version": "result-artifact-v1.0",
                "asset_id": snapshot["asset_id"],
                "asset_type": snapshot["asset_type"],
                "observed_at": snapshot["observed_at"],
                "prediction_horizon_hours": snapshot["prediction_horizon_hours"],
                "prediction_task": "binary_failure_within_horizon",
                "failure_probability": snapshot["failure_probability"],
                "predicted_failure_type": (
                    "failure_risk"
                    if float(snapshot["failure_probability"]) >= 0.5
                    else "no_significant_risk"
                ),
                "status_grade": status,
                "confidence": snapshot["confidence"],
                "top_factors": [
                    {
                        "rank": rank,
                        "feature": f"feature-{rank}",
                        "feature_value": float(rank),
                        "signed_contribution": 0.1 * rank,
                        "direction": "risk_up",
                        "explanation_method": "linear_logit_contribution",
                    }
                    for rank in (1, 2, 3)
                ],
                "recommended_action": action_policy[status],
                "provenance": {
                    "dataset_version": dataset["dataset_version"],
                    "model_version": snapshot["model_version"],
                    "prediction_id": prediction_id,
                    "source_type": "derived_result_artifact",
                    "canonical_source_mutated": False,
                },
            }
        )
    result_path = model_dir / "result_artifact.jsonl"
    write_jsonl(result_path, artifacts)
    refresh_contracts(root)
    model_path = model_dir / "model_contract.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["model_version"] = "independent-logreg-v3.1"
    model["dataset_version"] = dataset["dataset_version"]
    model["result_artifact"] = {
        "schema_version": "result-artifact-v1.0",
        "row_count": len(artifacts),
        "prediction_task": "binary_failure_within_horizon",
        "predicted_failure_type_semantics": "generic binary risk class",
    }
    model["output_sha256"]["result_artifact.jsonl"] = _sha256(result_path)
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")

    validation_dir = root / "canonical" / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    package_validation = {
        "valid": True,
        "canonical_source_separation": "pass",
        "canonical_checksum_integrity": "pass",
        "truth_separation": "pass",
        "topology_integrity": "pass",
        "observation_key_integrity": "pass",
        "failure_maintenance_coverage": "pass",
        "experiment_isolation": "pass",
        "hidden_truth_not_public": "pass",
        "negative_control_benchmark": "pass",
        "agent_positive_negative_evaluator": "pass",
        "model_contract": "pass",
        "model_dataset_binding": "pass",
        "row_counts": {
            "assets": 100,
            "relations": 80,
            "compressor_observations": 86_400,
            "cnc_observations": 345_600,
            "production_cycles": 170_875,
            "maintenance_events": 790,
            "prediction_timeline_rows": 68_208,
            "result_artifact_rows": 100,
        },
        "tool_wear_continuity": {
            "tolerance_minutes": 1.0,
            "reset_value_max_minutes": 5.0,
            "running_reset_count": 0,
            "maximum_allowed": 0,
            "tool_replacement_event_count": 731,
            "aligned_reset_transition_count": 731,
            "reset_without_matching_maintenance_count": 0,
            "replacement_without_reset_count": 0,
            "pass": True,
        },
        "ai4i_physics": {
            "air_process_correlation": {"value": 0.92, "minimum": 0.8, "pass": True},
            "rpm_torque_correlation": {"value": -0.84, "maximum": -0.6, "pass": True},
            "process_temperature_ordering": {
                "process_below_air_rows": 0,
                "fraction": 0.0,
                "maximum_fraction": 0.0,
                "pass": True,
            },
            "sensor_distribution": {},
            "pass": True,
        },
    }
    (validation_dir / "package_validation.json").write_text(
        json.dumps(package_validation, indent=2),
        encoding="utf-8",
    )
    agent_evaluation = {
        "positive_upstream_accuracy": 1.0,
        "negative_rejection_accuracy": 1.0,
        "false_upstream_claim_rate": 0.0,
        "maintenance_evidence_claims": 1,
        "maintenance_evidence_accuracy": 1.0,
    }
    (validation_dir / "agent_claims_example_evaluation.json").write_text(
        json.dumps(agent_evaluation, indent=2),
        encoding="utf-8",
    )
    return root


def refresh_v3_contracts(root: Path) -> None:
    refresh_contracts(root)
    model_path = root / "canonical" / "model_outputs" / "model_contract.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    result_path = root / "canonical" / "model_outputs" / "result_artifact.jsonl"
    model["output_sha256"]["result_artifact.jsonl"] = _sha256(result_path)
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
