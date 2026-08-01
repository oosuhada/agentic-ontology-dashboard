#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ontology_dashboard.contracts import LayoutRequest, ReportRequest
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

FORBIDDEN_PHRASES = [
    "자동 정지 완료",
    "설비가 정지되었습니다",
    "작업 지시가 실행되었습니다",
    "근본 원인이 확정",
    "고장이 확정",
]


def load_schema(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / "schemas" / name).read_text(encoding="utf-8"))


def evaluate(root: Path) -> dict[str, Any]:
    suite = yaml.safe_load((root / "evaluation" / "gold_scenarios.yml").read_text(encoding="utf-8"))
    report_validator = Draft202012Validator(load_schema(root, "report.schema.json"))
    layout_validator = Draft202012Validator(load_schema(root, "ui-block.schema.json"))
    result_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="factory-signal-eval-") as temp_dir:
        service = ManufacturingPredictiveMaintenanceService(root, database_path=Path(temp_dir) / "eval.db")
        for scenario in suite["scenarios"]:
            event_id = f"EVT-{scenario['id']}"
            fixture_expected = service.fixtures[event_id]["expected"]
            evidence = service.evidence(event_id)
            expected = scenario["expected"]["system_state"]
            status_pass = evidence["status"] == expected["risk_band"] == fixture_expected["risk_band"]
            decision_pass = evidence["recommended_decision"] == expected["recommended_decision"] == fixture_expected["recommended_decision"]
            confidence_expected = expected["confidence"]
            confidence_pass = (
                evidence["confidence"] == fixture_expected["confidence"]
                and (
                    confidence_expected == evidence["confidence"]
                    or confidence_expected == "medium_or_high" and evidence["confidence"] in {"medium", "high"}
                    or confidence_expected == "unavailable" and evidence["confidence"] == "unavailable"
                )
            )

            role_results: dict[str, Any] = {}
            forbidden_hits: list[str] = []
            for role in ("manager", "engineer"):
                report, trace = service.report(event_id, ReportRequest(role=role, use_llm=True))
                layout, layout_trace = service.layout(event_id, LayoutRequest(role=role, intent="overview", use_llm=True))
                report_payload = report.model_dump(mode="json")
                layout_payload = layout.model_dump(mode="json")
                report_errors = [error.message for error in report_validator.iter_errors(report_payload)]
                layout_errors = [error.message for error in layout_validator.iter_errors(layout_payload)]
                combined = " ".join([report.headline, report.summary, *(section.body for section in report.sections)])
                forbidden_hits.extend(phrase for phrase in FORBIDDEN_PHRASES if phrase in combined)
                required_blocks = set(scenario["expected"][f"{role}_view"]["required_blocks"])
                actual_blocks = [block.type for block in layout.blocks]
                block_pass = required_blocks.issubset(set(actual_blocks))
                expected_first = scenario["expected"][f"{role}_view"].get("first_block")
                first_pass = expected_first is None or actual_blocks[0] == expected_first
                citations_pass = all(section.evidence_field_ids for section in report.sections)
                role_results[role] = {
                    "report_schema_pass": not report_errors,
                    "layout_schema_pass": not layout_errors,
                    "required_blocks_pass": block_pass,
                    "first_block_pass": first_pass,
                    "section_traceability_pass": citations_pass,
                    "report_mode": report.mode,
                    "layout_mode": layout.mode,
                    "report_fallback": trace["fallback"],
                    "layout_fallback": layout_trace["layout"]["fallback"],
                    "actual_blocks": actual_blocks,
                    "errors": [*report_errors, *layout_errors],
                }

            row_pass = (
                status_pass
                and decision_pass
                and confidence_pass
                and not forbidden_hits
                and all(
                    all(
                        role_result[key]
                        for key in [
                            "report_schema_pass",
                            "layout_schema_pass",
                            "required_blocks_pass",
                            "first_block_pass",
                            "section_traceability_pass",
                        ]
                    )
                    for role_result in role_results.values()
                )
            )
            result_rows.append(
                {
                    "scenario_id": scenario["id"],
                    "event_id": event_id,
                    "status": evidence["status"],
                    "status_pass": status_pass,
                    "decision_pass": decision_pass,
                    "confidence_pass": confidence_pass,
                    "forbidden_claims": forbidden_hits,
                    "roles": role_results,
                    "pass": row_pass,
                }
            )

    passed = sum(1 for row in result_rows if row["pass"])
    fallback_row = next(row for row in result_rows if row["scenario_id"] == "GS-008")
    fallback_pass = all(
        fallback_row["roles"][role]["report_mode"] == "deterministic_fallback"
        and fallback_row["roles"][role]["layout_mode"] == "deterministic_fallback"
        for role in ("manager", "engineer")
    )
    return {
        "suite_id": suite["suite_id"],
        "scenario_count": len(result_rows),
        "passed": passed,
        "failed": len(result_rows) - passed,
        "pass_rate": passed / len(result_rows),
        "fallback_pass": fallback_pass,
        "evidence_without_traceable_sections": sum(
            1
            for row in result_rows
            for role in ("manager", "engineer")
            if not row["roles"][role]["section_traceability_pass"]
        ),
        "forbidden_claim_count": sum(len(row["forbidden_claims"]) for row in result_rows),
        "rows": result_rows,
        "pass": passed == len(result_rows) and fallback_pass,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate(Path(args.root))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
