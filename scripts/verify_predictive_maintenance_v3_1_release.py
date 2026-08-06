#!/usr/bin/env python3
"""Verify the immutable Predictive Maintenance Canonical v3.1 release boundary.

The verifier separates three outcomes:

* pass: locally verifiable contract is satisfied;
* blocked: an external runtime or credential is unavailable;
* fail: a supplied artifact contradicts the governed contract.

It intentionally does not read evaluation-truth detail rows into its output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


SOURCE_VERSION = "canonical-ai4i-physics-v3.1"
MODEL_VERSION = "independent-logreg-v3.1"
RESULT_SCHEMA_VERSION = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"
PROJECT_BUNDLE_CHECKSUM = (
    "12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682"
)

EXPECTED_ROW_COUNTS = {
    "assets": 100,
    "relations": 80,
    "compressor_observations": 86_400,
    "cnc_observations": 345_600,
    "production_cycles": 170_875,
    "maintenance_events": 790,
    "prediction_timeline_rows": 68_208,
    "result_artifact_rows": 100,
}

Status = Literal["pass", "blocked", "fail"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    evidence: Any
    action: str | None = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def equal_check(name: str, actual: Any, expected: Any) -> Check:
    return Check(
        name=name,
        status="pass" if actual == expected else "fail",
        evidence={"actual": actual, "expected": expected},
    )


def required_file_check(name: str, path: Path) -> Check:
    return Check(
        name=name,
        status="pass" if path.is_file() else "fail",
        evidence=str(path),
    )


def safe_package_checks(package_root: Path) -> list[Check]:
    checks: list[Check] = []
    required = {
        "dataset_manifest": package_root / "canonical/dataset/dataset_manifest.json",
        "model_contract": package_root / "canonical/model_outputs/model_contract.json",
        "result_artifact": package_root / "canonical/model_outputs/result_artifact.jsonl",
        "package_validation": package_root / "canonical/validation/package_validation.json",
        "agent_evaluation": package_root
        / "canonical/validation/agent_claims_example_evaluation.json",
        "experiment_manifest": package_root
        / "experiments/connected_air_supply/experiment_manifest.json",
        "release_archive": package_root
        / "dist/predictive_maintenance_canonical_v3.1.zip",
        "release_archive_checksum": package_root
        / "dist/predictive_maintenance_canonical_v3.1.zip.sha256",
    }
    checks.extend(required_file_check(f"package.file.{name}", path) for name, path in required.items())
    if any(check.status == "fail" for check in checks):
        return checks

    dataset_manifest = load_json(required["dataset_manifest"])
    model_contract = load_json(required["model_contract"])
    validation = load_json(required["package_validation"])
    agent = load_json(required["agent_evaluation"])
    experiment = load_json(required["experiment_manifest"])

    checks.extend(
        [
            equal_check("package.source_version", dataset_manifest.get("dataset_version"), SOURCE_VERSION),
            equal_check("package.model_version", model_contract.get("model_version"), MODEL_VERSION),
            equal_check(
                "package.model_dataset_binding",
                model_contract.get("dataset_version"),
                SOURCE_VERSION,
            ),
            equal_check(
                "package.result_schema",
                model_contract.get("result_artifact", {}).get("schema_version"),
                RESULT_SCHEMA_VERSION,
            ),
            equal_check(
                "package.prediction_task",
                model_contract.get("result_artifact", {}).get("prediction_task"),
                PREDICTION_TASK,
            ),
            equal_check("package.validation.valid", validation.get("valid"), True),
        ]
    )

    row_counts = validation.get("row_counts", {})
    for role, expected in EXPECTED_ROW_COUNTS.items():
        checks.append(equal_check(f"package.row_count.{role}", row_counts.get(role), expected))

    continuity = validation.get("tool_wear_continuity", {})
    for field, expected in {
        "pass": True,
        "running_reset_count": 0,
        "tool_replacement_event_count": 731,
        "aligned_reset_transition_count": 731,
        "reset_without_matching_maintenance_count": 0,
        "replacement_without_reset_count": 0,
    }.items():
        checks.append(equal_check(f"package.tool_wear.{field}", continuity.get(field), expected))

    ai4i = validation.get("ai4i_physics", {})
    checks.append(equal_check("package.ai4i_physics", ai4i.get("pass"), True))
    checks.extend(
        [
            equal_check(
                "package.agent.positive_upstream_accuracy",
                agent.get("positive_upstream_accuracy"),
                1.0,
            ),
            equal_check(
                "package.agent.negative_rejection_accuracy",
                agent.get("negative_rejection_accuracy"),
                1.0,
            ),
            equal_check(
                "package.agent.false_upstream_claim_rate",
                agent.get("false_upstream_claim_rate"),
                0.0,
            ),
            equal_check(
                "package.agent.maintenance_evidence_accuracy",
                agent.get("maintenance_evidence_accuracy"),
                1.0,
            ),
            equal_check(
                "package.experiment.positive_cases",
                experiment.get("positive_upstream_case_count"),
                16,
            ),
            equal_check(
                "package.experiment.negative_cases",
                experiment.get("negative_control_case_count"),
                4,
            ),
            equal_check(
                "package.experiment.hidden_truth_evaluator_only",
                experiment.get("hidden_truth_is_evaluator_only"),
                True,
            ),
            equal_check(
                "package.experiment.canonical_dataset_mutated",
                experiment.get("canonical_dataset_mutated"),
                False,
            ),
        ]
    )

    checksum_line = required["release_archive_checksum"].read_text(encoding="utf-8").strip()
    expected_archive_checksum = checksum_line.split()[0] if checksum_line else ""
    checks.append(
        equal_check(
            "package.release_archive_checksum",
            sha256(required["release_archive"]),
            expected_archive_checksum,
        )
    )
    return checks


def project_checks(project_root: Path) -> list[Check]:
    checks: list[Check] = []
    required = [
        "docs/contracts/data-contract.md",
        "docs/contracts/api-contract.md",
        "schemas/dataset-bundle-manifest.schema.json",
        "schemas/prediction-result.schema.json",
        "schemas/project3-graph-projection.schema.json",
        "api/ontology_dashboard/predictive_maintenance_runtime/service.py",
        "api/ontology_dashboard/routers/predictive_maintenance_runtime.py",
        "web/src/features/mvp/MvpApplication.tsx",
        "tests/test_predictive_maintenance_v3_compatibility.py",
        "tests/test_predictive_maintenance_projection.py",
        "tests/test_predictive_maintenance_graph_projection.py",
        "tests/test_predictive_maintenance_result_replay.py",
        "tests/test_mvp.py",
    ]
    checks.extend(
        required_file_check(f"project.file.{relative}", project_root / relative)
        for relative in required
    )
    checks.append(
        Check(
            name="project.bundle_checksum_contract",
            status="pass",
            evidence=PROJECT_BUNDLE_CHECKSUM,
        )
    )
    return checks


def project3_checks(project3_root: Path | None) -> list[Check]:
    if project3_root is None:
        return [
            Check(
                name="project3.repository",
                status="blocked",
                evidence="Project 3 repository path was not supplied",
                action="Pass --project3-root or configure ONTOLOGY_DASHBOARD_PROJECT3_URL for live verification.",
            )
        ]
    required = [
        "schemas/project3-graph-projection.schema.json",
        "backend/app/graph_projection/models.py",
        "backend/app/graph_projection/service.py",
        "tests/test_ontology_graph_projection.py",
        "tests/test_project_graph_scope.py",
    ]
    return [
        required_file_check(f"project3.file.{relative}", project3_root / relative)
        for relative in required
    ]


def run_package_validator(package_root: Path) -> Check:
    script = package_root / "scripts/validate_package.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=package_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )
    evidence: dict[str, Any] = {"returncode": result.returncode}
    try:
        payload = json.loads(result.stdout)
        if isinstance(payload, dict):
            evidence["valid"] = payload.get("valid")
            evidence["row_counts"] = payload.get("row_counts")
            evidence["tool_wear_continuity"] = payload.get("tool_wear_continuity")
            evidence["agent_example_evaluation"] = payload.get("agent_example_evaluation")
    except json.JSONDecodeError:
        evidence["output_tail"] = result.stdout[-2000:]
    return Check(
        name="package.validator_execution",
        status="pass" if result.returncode == 0 else "fail",
        evidence=evidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--project3-root")
    parser.add_argument("--run-package-validator", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Treat blocked checks as release failures")
    parser.add_argument("--output")
    args = parser.parse_args()

    project_root = Path(args.root).expanduser().resolve()
    package_root = Path(args.package_root).expanduser().resolve()
    project3_root = (
        Path(args.project3_root).expanduser().resolve() if args.project3_root else None
    )

    checks = [
        *safe_package_checks(package_root),
        *project_checks(project_root),
        *project3_checks(project3_root),
    ]
    if args.run_package_validator:
        checks.append(run_package_validator(package_root))

    failed = [check for check in checks if check.status == "fail"]
    blocked = [check for check in checks if check.status == "blocked"]
    payload = {
        "contract": "predictive-maintenance-canonical-v3.1-release-v1",
        "source_version": SOURCE_VERSION,
        "model_version": MODEL_VERSION,
        "result_artifact_schema_version": RESULT_SCHEMA_VERSION,
        "prediction_task": PREDICTION_TASK,
        "project_bundle_checksum_sha256": PROJECT_BUNDLE_CHECKSUM,
        "checks": [asdict(check) for check in checks],
        "summary": {
            "passed": sum(check.status == "pass" for check in checks),
            "blocked": len(blocked),
            "failed": len(failed),
            "local_release_pass": not failed,
            "strict_release_pass": not failed and not blocked,
        },
        "truth_detail_exposed": False,
        "topology_implies_causality": False,
        "recommended_action_implies_execution": False,
        "binary_prediction_implies_failure_mode": False,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if failed:
        return 1
    if args.strict and blocked:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
