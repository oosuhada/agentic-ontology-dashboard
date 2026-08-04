#!/usr/bin/env python3
"""Verify the governed Adaptive Modeling release boundary.

The verifier records local pass/fail separately from external production
capabilities. Missing credentials or endpoints are reported as ``blocked``;
they are never converted into a successful production release claim.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


Status = Literal["pass", "blocked", "fail"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    evidence: Any
    action: str | None = None


PHASE_FILES = [
    f"phase-{number:02d}-{slug}.md"
    for number, slug in (
        (9, "contract-foundation"),
        (10, "dataset-intake"),
        (11, "ontology-mapping-approval"),
        (12, "feature-recipe-registry"),
        (13, "experiment-evaluation"),
        (14, "model-registry-promotion"),
        (15, "ml-validator-workbench"),
        (16, "governance-release"),
    )
]

REQUIRED_FILES = [
    "api/migrations/postgresql/0016_adaptive_modeling_foundation.sql",
    "api/migrations/postgresql/0017_adaptive_model_registry.sql",
    "api/migrations/sqlite/0011_adaptive_modeling_foundation.sql",
    "api/migrations/sqlite/0012_adaptive_model_registry.sql",
    "api/ontology_dashboard/adapters/governed_tabular.py",
    "api/ontology_dashboard/modeling/artifacts.py",
    "api/ontology_dashboard/modeling/experiments.py",
    "api/ontology_dashboard/modeling/features.py",
    "api/ontology_dashboard/modeling/intake.py",
    "api/ontology_dashboard/modeling/mapping.py",
    "api/ontology_dashboard/modeling/models.py",
    "api/ontology_dashboard/modeling/registry.py",
    "api/ontology_dashboard/modeling/repository.py",
    "api/ontology_dashboard/modeling/schema.py",
    "api/ontology_dashboard/modeling/service.py",
    "api/ontology_dashboard/routers/modeling.py",
    "schemas/adaptive-modeling.schema.json",
    "scripts/generate_adaptive_modeling_schema.py",
    "scripts/run_modeling_experiment_worker.py",
    "tests/test_adaptive_modeling_contracts.py",
    "tests/test_dataset_intake.py",
    "tests/test_ontology_mapping_workflow.py",
    "tests/test_feature_recipe_registry.py",
    "tests/test_modeling_experiment_runner.py",
    "tests/test_model_registry_and_explanations.py",
    "tests/test_adaptive_modeling_e2e.py",
    "web/src/features/modeling/MLValidatorWorkbench.tsx",
    "web/src/features/modeling/modelingApi.ts",
    "web/e2e/adaptive-modeling-validator.spec.ts",
    "web/e2e/adaptive-modeling-validator.manifest.ts",
]

TARGETED_TESTS = [
    "tests/test_adaptive_modeling_contracts.py",
    "tests/test_dataset_intake.py",
    "tests/test_ontology_mapping_workflow.py",
    "tests/test_feature_recipe_registry.py",
    "tests/test_modeling_experiment_runner.py",
    "tests/test_model_registry_and_explanations.py",
    "tests/test_adaptive_modeling_e2e.py",
    "tests/test_adapter_layer.py",
    "tests/test_predictive_maintenance_postgresql.py::test_postgresql_adaptive_modeling_repository_jsonb_idempotency_and_rls",
]


def required_file(name: str, path: Path) -> Check:
    return Check(
        name=name,
        status="pass" if path.is_file() else "fail",
        evidence=str(path),
    )


def run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 600,
) -> Check:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, "fail", {"command": command, "error": str(exc)})
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return Check(
        name=name,
        status="pass" if completed.returncode == 0 else "fail",
        evidence={
            "command": command,
            "returncode": completed.returncode,
            "output_tail": output[-6000:],
        },
    )


def schema_parity_check(root: Path) -> Check:
    sys.path.insert(0, str(root / "api"))
    try:
        from ontology_dashboard.modeling.schema import adaptive_modeling_schema

        checked_in = json.loads(
            (root / "schemas/adaptive-modeling.schema.json").read_text(
                encoding="utf-8"
            )
        )
        generated = adaptive_modeling_schema()
        return Check(
            "adaptive.schema.typed_parity",
            "pass" if checked_in == generated else "fail",
            {
                "checked_in_matches_typed_contract": checked_in == generated,
                "contract_count": len(generated.get("anyOf", [])),
            },
        )
    except Exception as exc:  # noqa: BLE001 - release report requires exact failure
        return Check("adaptive.schema.typed_parity", "fail", str(exc))
    finally:
        if sys.path and sys.path[0] == str(root / "api"):
            sys.path.pop(0)


def optional_dependency_checks() -> list[Check]:
    checks: list[Check] = []
    for module in ("lightgbm", "xgboost", "shap"):
        available = importlib.util.find_spec(module) is not None
        checks.append(
            Check(
                name=f"adaptive.optional_dependency.{module}",
                status="pass" if available else "blocked",
                evidence={"installed": available},
                action=(
                    None
                    if available
                    else f"Install the governed optional dependency before activating {module}-dependent models."
                ),
            )
        )
    return checks


def production_capability_checks() -> list[Check]:
    requirements = {
        "postgresql_url": "ONTOLOGY_DASHBOARD_DATABASE_URL",
        "modeling_artifact_root": "ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT",
        "project3_url": "ONTOLOGY_DASHBOARD_PROJECT3_URL",
        "neo4j_uri": "ONTOLOGY_DASHBOARD_NEO4J_URI",
    }
    checks: list[Check] = []
    for name, variable in requirements.items():
        configured = bool(os.getenv(variable, "").strip())
        checks.append(
            Check(
                name=f"production.{name}",
                status="pass" if configured else "blocked",
                evidence={"environment_variable": variable, "configured": configured},
                action=None if configured else f"Configure {variable} in the production runtime.",
            )
        )
    return checks


def semantic_guards(root: Path) -> list[Check]:
    models = (root / "api/ontology_dashboard/modeling/models.py").read_text(
        encoding="utf-8"
    )
    service = (root / "api/ontology_dashboard/modeling/service.py").read_text(
        encoding="utf-8"
    )
    feature = (root / "api/ontology_dashboard/modeling/features.py").read_text(
        encoding="utf-8"
    )
    registry = (root / "api/ontology_dashboard/modeling/registry.py").read_text(
        encoding="utf-8"
    )
    return [
        Check(
            "adaptive.semantic.binary_prediction",
            "pass"
            if "binary_failure_within_horizon" in models
            and "failure_risk" in models
            and "no_significant_risk" in models
            and "failure_risk" in registry
            and "no_significant_risk" in registry
            else "fail",
            "binary task and labels remain explicit",
        ),
        Check(
            "adaptive.semantic.no_work_order_side_effect",
            "pass" if '"work_order_created": False' in service else "fail",
            "recommended action is stored as policy advice only",
        ),
        Check(
            "adaptive.semantic.evaluator_truth_forbidden",
            "pass"
            if "evaluation_truth" in feature and "hidden_truth" in feature
            else "fail",
            "feature and promotion gates explicitly reject evaluator-only truth",
        ),
        Check(
            "adaptive.semantic.noncausal_explanation",
            "pass"
            if 'causal_proof: Literal[False] = False' in models
            and "causal_proof=False" in registry
            else "fail",
            "local contribution is not represented as causal proof",
        ),
    ]


def canonical_check(
    root: Path,
    package_root: Path | None,
    project3_root: Path | None,
) -> Check:
    if package_root is None:
        return Check(
            "canonical.v3_1.invariance",
            "blocked",
            "package root was not supplied",
            "Provide --canonical-package-root for immutable V3.1 verification.",
        )
    command = [
        str(root / ".venv/bin/python"),
        "scripts/verify_predictive_maintenance_v3_1_release.py",
        "--root",
        ".",
        "--package-root",
        str(package_root),
        "--run-package-validator",
    ]
    if project3_root is not None:
        command.extend(["--project3-root", str(project3_root)])
    return run_command("canonical.v3_1.invariance", command, cwd=root, timeout=600)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    checks: list[Check] = []
    prompt_root = (
        root
        / "docs/60-development-prompts/predictive-maintenance-adaptive-modeling"
    )
    checks.extend(
        required_file(f"adaptive.prompt.{name}", prompt_root / name)
        for name in PHASE_FILES
    )
    checks.extend(
        required_file(f"adaptive.file.{name}", root / name)
        for name in REQUIRED_FILES
    )
    checks.append(schema_parity_check(root))
    checks.extend(semantic_guards(root))
    checks.extend(optional_dependency_checks())
    checks.extend(production_capability_checks())

    if args.run_tests:
        python = str(root / ".venv/bin/python")
        checks.append(
            run_command(
                "adaptive.tests.targeted",
                [python, "-m", "pytest", "-q", *TARGETED_TESTS],
                cwd=root,
                timeout=900,
            )
        )
        checks.append(
            run_command(
                "adaptive.frontend.component",
                [
                    "npm",
                    "--prefix",
                    "web",
                    "test",
                    "--",
                    "src/features/modeling/MLValidatorWorkbench.test.tsx",
                ],
                cwd=root,
            )
        )
        checks.append(
            run_command(
                "adaptive.frontend.typecheck",
                ["npm", "--prefix", "web", "run", "lint"],
                cwd=root,
            )
        )
        checks.append(
            run_command(
                "adaptive.frontend.build",
                ["npm", "--prefix", "web", "run", "build"],
                cwd=root,
            )
        )
        checks.append(
            run_command(
                "adaptive.frontend.playwright",
                [
                    "npx",
                    "playwright",
                    "test",
                    "e2e/adaptive-modeling-validator.spec.ts",
                ],
                cwd=root / "web",
                timeout=900,
            )
        )

    checks.append(
        canonical_check(root, args.canonical_package_root, args.project3_root)
    )
    passed = sum(item.status == "pass" for item in checks)
    blocked = sum(item.status == "blocked" for item in checks)
    failed = sum(item.status == "fail" for item in checks)
    return {
        "schema_version": "adaptive-modeling-release-verification-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": [asdict(item) for item in checks],
        "summary": {
            "passed": passed,
            "blocked": blocked,
            "failed": failed,
            "local_release_pass": failed == 0,
            "strict_release_pass": failed == 0 and blocked == 0,
        },
        "truth_detail_exposed": False,
        "offline_metrics_represent_operational_outcomes": False,
        "recommended_action_implies_execution": False,
        "local_contribution_implies_causality": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--canonical-package-root", type=Path)
    parser.add_argument("--project3-root", type=Path)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    summary = report["summary"]
    if summary["failed"]:
        return 1
    if args.strict and summary["blocked"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
