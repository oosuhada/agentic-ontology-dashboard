from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.dataset.ingestion import (
    BundleFileAdapter,
    DatasetBundleFile,
    DatasetBundleManifestV2,
    PredictiveMaintenanceCanonicalV2Adapter,
    compute_bundle_checksum,
    default_adapter_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_PACKAGE_ROOT = ROOT.parent / "predictive_maintenance_canonical_v2"
EXPECTED_REAL_COUNTS = {
    "asset_master": 100,
    "asset_relation": 80,
    "compressor_sensor_observation": 86_400,
    "cnc_sensor_observation": 345_600,
    "cnc_production_cycle": 170_860,
    "maintenance_event": 795,
    "prediction_snapshot": 100,
    "prediction_factor": 300,
    "prediction_timeline": 68_211,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def refresh_contracts(package_root: Path) -> None:
    dataset_dir = package_root / "canonical" / "dataset"
    model_dir = package_root / "canonical" / "model_outputs"
    canonical_names = [
        "asset_master.csv",
        "asset_relation.csv",
        "compressor_sensor_observation.csv",
        "cnc_sensor_observation.csv",
        "cnc_production_cycle.csv",
        "maintenance_event.csv",
    ]
    output_names = [
        "prediction_snapshot.jsonl",
        "prediction_factor.jsonl",
        "prediction_timeline.jsonl",
    ]
    manifest_path = dataset_dir / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["canonical_outputs"] = {
        name: sha256(dataset_dir / name) for name in canonical_names
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    model_path = model_dir / "model_contract.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["canonical_input_sha256"] = manifest["canonical_outputs"]
    model["output_sha256"] = {name: sha256(model_dir / name) for name in output_names}
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")


def create_small_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "predictive_maintenance_canonical_v2"
    dataset_dir = package_root / "canonical" / "dataset"
    model_dir = package_root / "canonical" / "model_outputs"
    observed_at = "2026-08-01T01:00:00+09:00"

    write_csv(
        dataset_dir / "asset_master.csv",
        [
            {
                "asset_id": "CMP-001",
                "asset_type": "compressor",
                "site_id": "S01",
                "cell_id": "S01-L01",
            },
            {
                "asset_id": "CNC-001",
                "asset_type": "cnc",
                "site_id": "S01",
                "cell_id": "S01-L01",
            },
        ],
    )
    write_csv(
        dataset_dir / "asset_relation.csv",
        [
            {
                "from_asset_id": "CMP-001",
                "relation_type": "SUPPLIES_AIR_TO",
                "to_asset_id": "CNC-001",
            }
        ],
    )
    write_csv(
        dataset_dir / "compressor_sensor_observation.csv",
        [
            {
                "observed_at": observed_at,
                "asset_id": "CMP-001",
                "site_id": "S01",
                "cell_id": "S01-L01",
                "is_operating": 1,
                "operating_state": "running",
                "voltage_raw": 220.0,
                "rotation_raw": 1500.0,
                "pressure_raw": 7.0,
                "vibration_raw": 0.2,
                "relative_vibration_z": 0.1,
                "relative_vibration_zone": "normal",
                "generator_version": "canonical-independent-v1.0",
            }
        ],
    )
    write_csv(
        dataset_dir / "cnc_sensor_observation.csv",
        [
            {
                "observed_at": observed_at,
                "asset_id": "CNC-001",
                "site_id": "S01",
                "cell_id": "S01-L01",
                "is_operating": 1,
                "operating_state": "running",
                "product_type": "H",
                "air_temperature_k": 300.0,
                "process_temperature_k": 310.0,
                "rotational_speed_rpm": 1200,
                "torque_nm": 40.0,
                "tool_wear_min": 10.0,
                "generator_version": "canonical-independent-v1.0",
            }
        ],
    )
    write_csv(
        dataset_dir / "cnc_production_cycle.csv",
        [
            {
                "product_id": "PRD-001",
                "cnc_asset_id": "CNC-001",
                "cycle_started_at": "2026-08-01T00:30:00+09:00",
                "cycle_completed_at": observed_at,
                "product_type": "H",
                "cutting_minutes": 20,
                "tool_wear_increment_min": 1.0,
            }
        ],
    )
    write_csv(
        dataset_dir / "maintenance_event.csv",
        [
            {
                "maintenance_id": "MNT-001",
                "asset_id": "CNC-001",
                "maintenance_type": "planned_tool_change",
                "started_at": "2026-08-01T02:00:00+09:00",
                "completed_at": "2026-08-01T03:00:00+09:00",
                "tool_replaced": 1,
                "source_event_id": "",
            }
        ],
    )
    snapshots = [
        {
            "prediction_id": f"CMP-001#{observed_at}",
            "asset_id": "CMP-001",
            "asset_type": "compressor",
            "observed_at": observed_at,
            "prediction_horizon_hours": 24,
            "failure_probability": 0.2,
            "predicted_failure_type": "none",
            "confidence": 0.8,
            "status": "normal",
            "model_version": "test-v1",
            "feature_scope": "independent",
        },
        {
            "prediction_id": f"CNC-001#{observed_at}",
            "asset_id": "CNC-001",
            "asset_type": "cnc",
            "observed_at": observed_at,
            "prediction_horizon_hours": 24,
            "failure_probability": 0.3,
            "predicted_failure_type": "none",
            "confidence": 0.7,
            "status": "normal",
            "model_version": "test-v1",
            "feature_scope": "independent",
        },
    ]
    write_jsonl(model_dir / "prediction_snapshot.jsonl", snapshots)
    write_jsonl(
        model_dir / "prediction_factor.jsonl",
        [
            {
                "prediction_id": row["prediction_id"],
                "rank": 1,
                "feature": "feature-a",
                "feature_value": 1.0,
                "signed_contribution": 0.2,
                "absolute_contribution": 0.2,
                "direction": "positive",
                "explanation_method": "linear",
                "source_type": "derived_model_output",
            }
            for row in snapshots
        ],
    )
    write_jsonl(
        model_dir / "prediction_timeline.jsonl",
        [
            {
                "prediction_id": row["prediction_id"],
                "asset_id": row["asset_id"],
                "asset_type": row["asset_type"],
                "observed_at": row["observed_at"],
                "prediction_horizon_hours": 24,
                "failure_probability": row["failure_probability"],
                "status": row["status"],
                "top_factors": ["feature-a"],
                "model_version": "test-v1",
                "feature_scope": "independent",
                "source_type": "derived_replay_prediction",
            }
            for row in snapshots
        ],
    )
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": "canonical-independent-v1.0",
                "created_at": "2026-08-04T14:30:01+09:00",
                "start_at": "2026-08-01T00:00:00+09:00",
                "end_at": "2026-08-31T00:00:00+09:00",
                "days": 30,
                "seed": 42,
                "rate_profile": "balanced_demo",
                "observation_interval_minutes": 10,
                "source_contract": {
                    "compressor_and_cnc_independent": True,
                    "topology_relation_is_not_causal_truth": True,
                    "upstream_features_in_source": False,
                    "synthetic_effect_columns_in_source": False,
                    "prediction_outputs_in_source": False,
                    "evaluation_truth_separate": True,
                },
                "canonical_outputs": {},
                "evaluation_truth_outputs": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model_contract.json").write_text(
        json.dumps(
            {
                "model_version": "test-v1",
                "dataset_version": "canonical-independent-v1.0",
                "canonical_input_sha256": {},
                "outputs_are_not_source_data": True,
                "output_sha256": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    refresh_contracts(package_root)
    return package_root


def build_manifest(package_root: Path) -> DatasetBundleManifestV2:
    return PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        package_root,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        manifest_id="pm-test-bundle",
    )


def validate(package_root: Path, manifest: DatasetBundleManifestV2):
    return BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)


def rebuild_manifest_with_files(
    manifest: DatasetBundleManifestV2,
    files: list[DatasetBundleFile],
) -> DatasetBundleManifestV2:
    payload = manifest.model_dump(mode="python", by_alias=True)
    payload["files"] = [item.model_dump(mode="python", by_alias=True) for item in files]
    payload["bundle_checksum_sha256"] = compute_bundle_checksum(
        dataset_version=manifest.dataset_version,
        schema_version=manifest.schema_version,
        generation=manifest.generation,
        source_contract=manifest.source_contract,
        files=files,
    )
    return DatasetBundleManifestV2.model_validate(payload)


def rewrite_csv_value(path: Path, field: str, value: str) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    rows[0][field] = value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rewrite_jsonl_value(path: Path, field: str, value: str) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0][field] = value
    write_jsonl(path, rows)


def test_bundle_adapter_is_registered() -> None:
    registry = default_adapter_registry()
    assert registry.get_bundle("predictive-maintenance-canonical-v2").code == (
        "predictive-maintenance-canonical-v2"
    )


def test_small_bundle_validates_without_materializing_rows(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    result = validate(package_root, build_manifest(package_root))

    assert result.status == "completed"
    assert result.source_record_count == 13
    assert result.accepted_record_count == 13
    assert result.quarantined_record_count == 0
    assert result.materialized_record_count == 0
    assert result.metrics["source_rows_materialized_in_memory"] == 0
    assert "accepted_records" not in result.model_dump(mode="json")


def test_required_file_missing_fails_entire_bundle(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    (package_root / "canonical" / "dataset" / "asset_relation.csv").unlink()

    result = validate(package_root, manifest)

    assert result.status == "failed"
    assert result.accepted_record_count == 0
    assert any(issue.code == "file_access_failed" for issue in result.issues)


def test_required_role_missing_fails_entire_bundle(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    files = [item for item in manifest.files if item.role != "prediction_factor"]

    result = validate(package_root, rebuild_manifest_with_files(manifest, files))

    assert result.status == "failed"
    assert any(issue.code == "missing_required_role" for issue in result.issues)


def test_checksum_mismatch_fails_entire_bundle(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    path = package_root / "canonical" / "dataset" / "asset_master.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = validate(package_root, manifest)

    assert result.status == "failed"
    assert result.accepted_record_count == 0
    assert any(issue.code == "checksum_mismatch" for issue in result.issues)


def test_unknown_relation_asset_is_quarantined_and_bundle_fails(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    path = package_root / "canonical" / "dataset" / "asset_relation.csv"
    rewrite_csv_value(path, "to_asset_id", "CNC-UNKNOWN")
    refresh_contracts(package_root)

    result = validate(package_root, build_manifest(package_root))

    assert result.status == "failed"
    assert result.accepted_record_count == 0
    assert result.quarantined_record_count == 1
    assert any(issue.code == "unknown_relation_asset" for issue in result.issues)


def test_unknown_observation_asset_is_quarantined_and_bundle_fails(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    path = package_root / "canonical" / "dataset" / "cnc_sensor_observation.csv"
    rewrite_csv_value(path, "asset_id", "CNC-UNKNOWN")
    refresh_contracts(package_root)

    result = validate(package_root, build_manifest(package_root))

    assert result.status == "failed"
    assert result.quarantined_record_count == 1
    assert any(issue.code == "unknown_observation_asset" for issue in result.issues)


def test_unknown_factor_prediction_id_is_quarantined_and_bundle_fails(
    tmp_path: Path,
) -> None:
    package_root = create_small_package(tmp_path)
    path = package_root / "canonical" / "model_outputs" / "prediction_factor.jsonl"
    rewrite_jsonl_value(path, "prediction_id", "UNKNOWN#2026-08-01T01:00:00+09:00")
    refresh_contracts(package_root)

    result = validate(package_root, build_manifest(package_root))

    assert result.status == "failed"
    assert result.quarantined_record_count == 1
    assert any(issue.code == "unknown_factor_prediction_id" for issue in result.issues)


def test_duplicate_timeline_identity_is_quarantined_and_bundle_fails(
    tmp_path: Path,
) -> None:
    package_root = create_small_package(tmp_path)
    path = package_root / "canonical" / "model_outputs" / "prediction_timeline.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    write_jsonl(path, [*rows, rows[0]])
    refresh_contracts(package_root)

    result = validate(package_root, build_manifest(package_root))

    assert result.status == "failed"
    assert result.quarantined_record_count == 1
    assert any(
        issue.code == "duplicate_timeline_prediction_id" for issue in result.issues
    )


def test_evaluation_truth_cannot_be_added_to_runtime_bundle(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    truth = package_root / "canonical" / "evaluation_truth" / "failure_schedule.csv"
    write_csv(truth, [{"event_id": "EVT-001"}])

    with pytest.raises(ValidationError, match="evaluation_truth"):
        DatasetBundleFile(
            role="truth_artifact",
            uri=truth.resolve().as_uri(),
            format="csv",
            media_type="text/csv",
            checksum_sha256=sha256(truth),
            size_bytes=truth.stat().st_size,
            schema={"schema_version": "truth-v1", "required_fields": ["event_id"]},
        )


def test_same_bundle_revalidation_is_idempotent(tmp_path: Path) -> None:
    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    adapter = BundleFileAdapter(allowed_roots=[package_root])

    first = adapter.validate(manifest)
    second = adapter.validate(manifest)

    assert first.status == second.status == "completed"
    assert first.ingestion_run_id == second.ingestion_run_id
    assert first.idempotency_key == second.idempotency_key
    assert first.validation_checksum_sha256 == second.validation_checksum_sha256


@pytest.mark.skipif(not REAL_PACKAGE_ROOT.is_dir(), reason="canonical v2 package is not mounted")
def test_current_real_bundle_matches_package_contracts_and_row_counts() -> None:
    manifest = PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        REAL_PACKAGE_ROOT,
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
    )
    result = BundleFileAdapter(allowed_roots=[REAL_PACKAGE_ROOT]).validate(manifest)
    source_manifest = json.loads(
        (REAL_PACKAGE_ROOT / "canonical" / "dataset" / "dataset_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    model_contract = json.loads(
        (REAL_PACKAGE_ROOT / "canonical" / "model_outputs" / "model_contract.json").read_text(
            encoding="utf-8"
        )
    )
    expected_checksums = {
        **{
            Path(name).stem: checksum
            for name, checksum in source_manifest["canonical_outputs"].items()
        },
        **{
            Path(name).stem: checksum
            for name, checksum in model_contract["output_sha256"].items()
            if name.startswith("prediction_")
        },
    }

    assert result.status == "completed"
    assert result.source_record_count == sum(EXPECTED_REAL_COUNTS.values()) == 672_446
    assert {role.role: role.source_record_count for role in result.roles} == (
        EXPECTED_REAL_COUNTS
    )
    assert all(role.checksum_valid and role.schema_valid for role in result.roles)
    assert {
        role.role: role.expected_checksum_sha256 for role in result.roles
    } == expected_checksums
    assert result.quarantined_record_count == 0
    assert result.materialized_record_count == 0
