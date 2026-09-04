from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_predictive_maintenance_v3_1_release.py"
SPEC = importlib.util.spec_from_file_location("pm_v3_release", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_equal_check_fails_on_contract_mismatch() -> None:
    check = module.equal_check("model", "wrong", module.MODEL_VERSION)
    assert check.status == "fail"
    assert check.evidence["expected"] == module.MODEL_VERSION


def test_project3_missing_is_blocked_not_passed() -> None:
    checks = module.project3_checks(None)
    assert len(checks) == 1
    assert checks[0].status == "blocked"


def test_package_only_release_checks_skip_project_scope(monkeypatch, tmp_path: Path) -> None:
    package_check = module.Check("package.ok", "pass", "package evidence")
    project_check = module.Check("project.missing", "fail", "missing prompt")
    project3_check = module.Check("project3.missing", "blocked", "missing repo")
    monkeypatch.setattr(module, "safe_package_checks", lambda _root: [package_check])
    monkeypatch.setattr(module, "project_checks", lambda _root: [project_check])
    monkeypatch.setattr(module, "project3_checks", lambda _root: [project3_check])

    checks = module.release_checks(
        tmp_path / "project",
        tmp_path / "package",
        None,
        package_only=True,
    )

    assert checks == [package_check]


def test_full_release_checks_include_project_scope(monkeypatch, tmp_path: Path) -> None:
    package_check = module.Check("package.ok", "pass", "package evidence")
    project_check = module.Check("project.missing", "fail", "missing prompt")
    project3_check = module.Check("project3.missing", "blocked", "missing repo")
    monkeypatch.setattr(module, "safe_package_checks", lambda _root: [package_check])
    monkeypatch.setattr(module, "project_checks", lambda _root: [project_check])
    monkeypatch.setattr(module, "project3_checks", lambda _root: [project3_check])

    checks = module.release_checks(
        tmp_path / "project",
        tmp_path / "package",
        None,
        package_only=False,
    )

    assert checks == [package_check, project_check, project3_check]


def test_package_checks_publish_safe_aggregate_contract(tmp_path: Path) -> None:
    root = tmp_path / "package"
    archive = root / "dist/predictive_maintenance_canonical_v3.1.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"release")
    write_json(
        root / "canonical/dataset/dataset_manifest.json",
        {"dataset_version": module.SOURCE_VERSION},
    )
    write_json(
        root / "canonical/model_outputs/model_contract.json",
        {
            "model_version": module.MODEL_VERSION,
            "dataset_version": module.SOURCE_VERSION,
            "result_artifact": {
                "schema_version": module.RESULT_SCHEMA_VERSION,
                "prediction_task": module.PREDICTION_TASK,
            },
        },
    )
    result_artifact = root / "canonical/model_outputs/result_artifact.jsonl"
    result_artifact.write_text("{}\n", encoding="utf-8")
    write_json(
        root / "canonical/validation/package_validation.json",
        {
            "valid": True,
            "row_counts": module.EXPECTED_ROW_COUNTS,
            "tool_wear_continuity": {
                "pass": True,
                "running_reset_count": 0,
                "tool_replacement_event_count": 731,
                "aligned_reset_transition_count": 731,
                "reset_without_matching_maintenance_count": 0,
                "replacement_without_reset_count": 0,
            },
            "ai4i_physics": {"pass": True, "event_condition_details": ["private"]},
        },
    )
    write_json(
        root / "canonical/validation/agent_claims_example_evaluation.json",
        {
            "positive_upstream_accuracy": 1.0,
            "negative_rejection_accuracy": 1.0,
            "false_upstream_claim_rate": 0.0,
            "maintenance_evidence_accuracy": 1.0,
        },
    )
    write_json(
        root / "experiments/connected_air_supply/experiment_manifest.json",
        {
            "positive_upstream_case_count": 16,
            "negative_control_case_count": 4,
            "hidden_truth_is_evaluator_only": True,
            "canonical_dataset_mutated": False,
        },
    )
    checksum = module.sha256(archive)
    (root / "dist/predictive_maintenance_canonical_v3.1.zip.sha256").write_text(
        f"{checksum}  {archive.name}\n",
        encoding="utf-8",
    )

    checks = module.safe_package_checks(root)
    assert checks
    assert all(check.status == "pass" for check in checks)
    rendered = json.dumps([module.asdict(check) for check in checks]).lower()
    assert "event_condition_details" not in rendered
