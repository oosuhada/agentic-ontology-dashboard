from __future__ import annotations

from pathlib import Path

from scripts.evaluate_gold import evaluate

ROOT = Path(__file__).resolve().parents[1]


def test_gold_evaluation_records_recommendation_policy_and_side_effect_boundary() -> None:
    result = evaluate(ROOT)

    assert result["policy_version"] == "recommendation-policy-v1"
    assert result["policy_passed"] == 8
    assert set(result["operational_side_effect_counts"].values()) == {0}
    assert "engineering acceptance evidence only" in result["claim_boundary"]
    assert all(row["producer_recommendation"]["source_product_result_id"] for row in result["rows"])
    assert all(row["producer_recommendation"]["source_evidence_id"] for row in result["rows"])
