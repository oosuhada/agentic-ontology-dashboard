from __future__ import annotations

import hashlib
import json
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

    model_dir = root / "canonical" / "model_outputs"
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
    model["result_artifact"] = {
        "schema_version": "result-artifact-v1.0",
        "row_count": len(artifacts),
        "prediction_task": "binary_failure_within_horizon",
        "predicted_failure_type_semantics": "generic binary risk class",
    }
    model["output_sha256"]["result_artifact.jsonl"] = _sha256(result_path)
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return root


def refresh_v3_contracts(root: Path) -> None:
    refresh_contracts(root)
    model_path = root / "canonical" / "model_outputs" / "model_contract.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    result_path = root / "canonical" / "model_outputs" / "result_artifact.jsonl"
    model["output_sha256"]["result_artifact.jsonl"] = _sha256(result_path)
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
