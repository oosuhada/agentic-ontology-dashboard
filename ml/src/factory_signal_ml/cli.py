from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import audit_fixture, fixture_paths, load_fixture
from .dataset import audit_ai4i
from .evidence import build_evidence_package
from .training import train_and_evaluate


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_audit_dataset(args: argparse.Namespace) -> int:
    _print(audit_ai4i(args.csv).to_dict())
    return 0


def command_validate_fixtures(args: argparse.Namespace) -> int:
    rows = []
    failed = False
    for path in fixture_paths(Path(args.root)):
        fixture = load_fixture(path)
        issues = [issue.to_dict() for issue in audit_fixture(fixture)]
        expected_invalid = fixture["scenario_id"] == "GS-007"
        passed = bool(issues) if expected_invalid else not issues
        failed = failed or not passed
        rows.append(
            {
                "path": str(path),
                "scenario_id": fixture["scenario_id"],
                "quality_issue_count": len(issues),
                "expected_invalid": expected_invalid,
                "pass": passed,
            }
        )
    _print({"fixtures": rows, "pass": not failed})
    return 1 if failed else 0


def command_train(args: argparse.Namespace) -> int:
    metadata = train_and_evaluate(
        args.csv,
        args.output,
        minimum_recall=args.minimum_recall,
        false_negative_cost=args.false_negative_cost,
        false_positive_cost=args.false_positive_cost,
    )
    _print(metadata)
    return 0


def command_evidence(args: argparse.Namespace) -> int:
    fixture = load_fixture(args.fixture)
    _print(build_evidence_package(fixture))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory-signal-ml")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit-dataset")
    audit.add_argument("csv")
    audit.set_defaults(func=command_audit_dataset)

    fixtures = sub.add_parser("validate-fixtures")
    fixtures.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    fixtures.set_defaults(func=command_validate_fixtures)

    train = sub.add_parser("train")
    train.add_argument("csv")
    train.add_argument("--output", default="ml/artifacts")
    train.add_argument("--minimum-recall", type=float, default=0.80)
    train.add_argument("--false-negative-cost", type=float, default=10.0)
    train.add_argument("--false-positive-cost", type=float, default=1.0)
    train.set_defaults(func=command_train)

    evidence = sub.add_parser("evidence")
    evidence.add_argument("fixture")
    evidence.set_defaults(func=command_evidence)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
