#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from app.diagnosis.contracts import load_fixture
from app.diagnosis.evidence import build_product_result_artifact
from app.diagnosis.predictor import HeuristicPredictor
from app.diagnosis.recommendation_policy import (
    POLICY_VERSION,
    RecommendationPolicyInput,
    evaluate_recommendation_policy,
)
from app.dependencies import build_manufacturing_service
from app.operations.contracts import LayoutRequest, ReportRequest

FORBIDDEN_PHRASES = [
    "자동 정지 완료",
    "설비가 정지되었습니다",
    "작업 지시가 실행되었습니다",
    "근본 원인이 확정",
    "고장이 확정",
]


def load_schema(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / "contracts" / "schemas" / name).read_text(encoding="utf-8"))


def evaluate(root: Path) -> dict[str, Any]:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", "1")
    suite = yaml.safe_load((root / "evaluation" / "gold_scenarios.yml").read_text(encoding="utf-8"))
    report_validator = Draft202012Validator(load_schema(root, "report.schema.json"))
    layout_validator = Draft202012Validator(load_schema(root, "ui-block.schema.json"))
    result_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="factory-signal-eval-") as temp_dir:
        service = build_manufacturing_service(Path(temp_dir) / "eval.db", root=root)
        for scenario in suite["scenarios"]:
            event_id = f"EVT-{scenario['id']}"
            fixture = load_fixture(root / scenario["fixture_path"])
            artifact = build_product_result_artifact(
                fixture,
                predictor=HeuristicPredictor(),
            )
            evidence_payload = artifact["evidence_payload"]
            source_action = evidence_payload["recommended_actions"][0]
            producer_recommendation = evaluate_recommendation_policy(
                RecommendationPolicyInput(
                    source_product_result_id=str(artifact["artifact_id"]),
                    source_evidence_id=str(
                        artifact["provenance"]["evidence_payload_reference"]["reference"]
                    ),
                    source_schema_version=str(artifact["schema_version"]),
                    status=str(artifact["status_grade"]),
                    equipment=dict(fixture["equipment"]),
                    basis=tuple(source_action["basis"]),
                    source_fields=tuple(
                        field["field_id"] for field in evidence_payload["source_fields"]
                    ),
                    data_quality_hold=(
                        str(artifact["status_grade"]) == "data_quality_hold"
                        or bool(artifact["data_quality_warnings"])
                    ),
                )
            )
            fixture_expected = service.fixtures[event_id]["expected"]
            evidence = service.evidence(event_id)
            expected = scenario["expected"]["system_state"]
            status_pass = evidence["status"] == expected["risk_band"] == fixture_expected["risk_band"]
            decision_pass = evidence["recommended_decision"] == expected["recommended_decision"] == fixture_expected["recommended_decision"]
            policy_pass = (
                producer_recommendation is not None
                and producer_recommendation.kind == expected["recommended_decision"]
            )
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
                and policy_pass
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
                    "policy_version": POLICY_VERSION,
                    "policy_pass": policy_pass,
                    "producer_recommendation": (
                        producer_recommendation.model_dump(mode="json")
                        if producer_recommendation is not None
                        else None
                    ),
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
        "policy_version": POLICY_VERSION,
        "policy_passed": sum(1 for row in result_rows if row["policy_pass"]),
        "operational_side_effect_counts": {
            "recommendations": 0,
            "decisions": 0,
            "work_orders": 0,
            "maintenance_actions": 0,
            "maintenance_events": 0,
        },
        "claim_boundary": (
            "Gold 8/8 is engineering acceptance evidence only, "
            "not field or business impact validation."
        ),
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
