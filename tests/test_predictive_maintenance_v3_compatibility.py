from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    DatasetBundleManifestV2,
    PredictiveMaintenanceCanonicalV2Adapter,
    compute_bundle_checksum,
)
from predictive_maintenance_v3_helpers import (
    create_small_v3_package,
    refresh_v3_contracts,
)


ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = ROOT.parent / "predictive_maintenance_canonical_v2"
V3_ROOT = ROOT.parent / "predictive_maintenance_canonical_v3.1"
V2_CHECKSUM = "ac12fdc33f1e03b46447687e689566fd2b66f5d30bb253fbe82309770313594b"
ROW_COUNT_KEYS = {
    "asset_master": "assets",
    "asset_relation": "relations",
    "compressor_sensor_observation": "compressor_observations",
    "cnc_sensor_observation": "cnc_observations",
    "cnc_production_cycle": "production_cycles",
    "maintenance_event": "maintenance_events",
    "prediction_timeline": "prediction_timeline_rows",
    "result_artifact": "result_artifact_rows",
}


def build(root: Path) -> DatasetBundleManifestV2:
    return PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        root,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        manifest_id="predictive-maintenance-canonical-v2",
    )


def rebuild(manifest: DatasetBundleManifestV2, files) -> DatasetBundleManifestV2:
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


def test_v2_checksum_is_stable_and_v3_is_a_new_version() -> None:
    v2 = build(V2_ROOT)
    v3 = build(V3_ROOT)

    assert v2.bundle_checksum_sha256 == V2_CHECKSUM
    assert v2.source_contract.is_v3 is False
    assert len(v2.files) == 9
    assert v3.source_contract.is_v3 is True
    assert v3.bundle_checksum_sha256 != V2_CHECKSUM
    assert {item.role for item in v3.files} == {
        "asset_master",
        "asset_relation",
        "compressor_sensor_observation",
        "cnc_sensor_observation",
        "cnc_production_cycle",
        "maintenance_event",
        "prediction_snapshot",
        "prediction_factor",
        "prediction_timeline",
        "result_artifact",
    }
    assert [item.role for item in v3.governance_artifacts] == [
        "package_validation",
        "agent_example_evaluation",
    ]
    package_validation = v3.governance_artifacts[0]
    rendered = json.dumps(package_validation.summary, ensure_ascii=False)
    assert "event_condition_details" not in rendered
    assert "condition_variant" not in rendered
    assert package_validation.summary["tool_wear_continuity"] == {
        "tolerance_minutes": 1.0,
        "reset_value_max_minutes": 5.0,
        "running_reset_count": 0,
        "maximum_allowed": 0,
        "tool_replacement_event_count": 731,
        "aligned_reset_transition_count": 731,
        "reset_without_matching_maintenance_count": 0,
        "replacement_without_reset_count": 0,
        "pass": True,
    }
    assert v3.governance_artifacts[1].summary["maintenance_evidence_accuracy"] == 1.0


def test_real_v3_bundle_validates_with_result_artifact_parity() -> None:
    manifest = build(V3_ROOT)
    result = BundleFileAdapter(allowed_roots=[V3_ROOT]).validate(manifest)
    actual = {item.role: item.source_record_count for item in result.roles}
    package_counts = manifest.governance_artifacts[0].summary["row_counts"]

    assert result.status == "completed"
    for role, package_key in ROW_COUNT_KEYS.items():
        assert actual[role] == package_counts[package_key]
    assert actual["prediction_snapshot"] == 100
    assert actual["prediction_factor"] == 300
    assert result.source_record_count == sum(actual.values())
    assert result.issues == []


def test_v3_source_contract_is_version_aware_but_still_strict() -> None:
    manifest = build(V3_ROOT)
    payload = manifest.model_dump(mode="python", by_alias=True)
    payload["source_contract"]["unknown_contract_flag"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DatasetBundleManifestV2.model_validate(payload)

    payload = manifest.model_dump(mode="python", by_alias=True)
    payload["source_contract"]["asset_variability_policy"] = None
    with pytest.raises(ValidationError, match="must be declared together"):
        DatasetBundleManifestV2.model_validate(payload)


def test_v3_requires_result_artifact_role(tmp_path: Path) -> None:
    root = create_small_v3_package(tmp_path)
    manifest = build(root)
    without_result = [item for item in manifest.files if item.role != "result_artifact"]
    result = BundleFileAdapter(allowed_roots=[root]).validate(rebuild(manifest, without_result))

    assert result.status == "failed"
    assert any(item.code == "missing_required_role" for item in result.issues)


def test_v3_rejects_result_checksum_and_prediction_binding(tmp_path: Path) -> None:
    root = create_small_v3_package(tmp_path)
    manifest = build(root)
    result_file = next(item for item in manifest.files if item.role == "result_artifact")
    changed = result_file.model_copy(update={"checksum_sha256": "f" * 64})
    files = [changed if item.role == "result_artifact" else item for item in manifest.files]
    checksum_result = BundleFileAdapter(allowed_roots=[root]).validate(rebuild(manifest, files))
    assert checksum_result.status == "failed"
    assert any(item.code == "checksum_mismatch" for item in checksum_result.issues)

    result_path = root / "canonical" / "model_outputs" / "result_artifact.jsonl"
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["provenance"]["prediction_id"] = "UNKNOWN#2026-08-01T01:00:00+09:00"
    result_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    refresh_v3_contracts(root)
    binding_manifest = build(root)
    binding_result = BundleFileAdapter(allowed_roots=[root]).validate(binding_manifest)
    assert binding_result.status == "failed"
    assert any(item.code == "result_artifact_prediction_mismatch" for item in binding_result.issues)


def test_v3_1_rejects_failed_tool_wear_and_maintenance_evidence_gates(
    tmp_path: Path,
) -> None:
    root = create_small_v3_package(tmp_path)
    validation_path = root / "canonical" / "validation" / "package_validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["tool_wear_continuity"]["running_reset_count"] = 1
    validation_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="tool-wear continuity gate failed"):
        build(root)

    root = create_small_v3_package(tmp_path / "agent")
    agent_path = root / "canonical" / "validation" / "agent_claims_example_evaluation.json"
    agent = json.loads(agent_path.read_text(encoding="utf-8"))
    agent["maintenance_evidence_accuracy"] = 0.0
    agent_path.write_text(json.dumps(agent, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="agent evidence gate failed"):
        build(root)
