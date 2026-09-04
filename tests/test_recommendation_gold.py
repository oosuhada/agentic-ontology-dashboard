from __future__ import annotations

from pathlib import Path

import yaml

from app.diagnosis.contracts import load_fixture
from app.diagnosis.evidence import build_product_result_artifact
from app.diagnosis.predictor import HeuristicPredictor
from app.diagnosis.recommendation_policy import RecommendationPolicyInput, evaluate_recommendation_policy

ROOT = Path(__file__).resolve().parents[1]


def test_gold_v1_policy_outputs_match_expected_decisions() -> None:
    suite = yaml.safe_load((ROOT / "evaluation" / "gold_scenarios.yml").read_text(encoding="utf-8"))

    assert len(suite["scenarios"]) == 8
    for scenario in suite["scenarios"]:
        fixture = load_fixture(ROOT / scenario["fixture_path"])
        artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
        payload = artifact["evidence_payload"]
        action = payload["recommended_actions"][0]
        recommendation = evaluate_recommendation_policy(
            RecommendationPolicyInput(
                source_product_result_id=artifact["artifact_id"],
                source_evidence_id=artifact["provenance"]["evidence_payload_reference"]["reference"],
                source_schema_version=artifact["schema_version"],
                status=artifact["status_grade"],
                equipment=fixture["equipment"],
                basis=tuple(action["basis"]),
                source_fields=tuple(field["field_id"] for field in payload["source_fields"]),
                data_quality_hold=artifact["status_grade"] == "data_quality_hold"
                or bool(artifact["data_quality_warnings"]),
            )
        )

        assert recommendation is not None
        assert recommendation.kind == scenario["expected"]["system_state"]["recommended_decision"]
