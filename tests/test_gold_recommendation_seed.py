from __future__ import annotations

import json
from pathlib import Path

from scripts.seed_gold_recommendations import seed_gold_recommendations

ROOT = Path(__file__).resolve().parents[1]


def test_gold_seed_writes_evaluation_fixture_store_without_operational_side_effects(tmp_path: Path) -> None:
    output = tmp_path / "recommendation-policy-v1.json"

    first = seed_gold_recommendations(ROOT, output=output)
    second = seed_gold_recommendations(ROOT, output=output)

    assert first["fixture_count"] == 8
    assert first["inserted"] == 8
    assert second["inserted"] == 0
    assert second["replayed"] == 8
    assert len(second["fixture_recommendations"]) == 8
    assert set(second["operational_side_effect_counts"].values()) == {0}
    assert "engineering acceptance evidence only" in second["claim_boundary"]
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["fixture_checksum_sha256"]
    assert stored["evaluator"] == {
        "name": "seed_gold_recommendations.py",
        "version": "recommendation-policy-gold-seed-v1",
    }
    assert stored["schema_versions"]["source_schema_version"] == "result-artifact-v1.0"
    assert stored["writer_strategy_boundary"] == {
        "fixture_store": "evaluation_demo_fixture",
        "operational_materialization": "runtime_generated_only",
        "imported_precomputed": "preserve_result_and_recommendation_detail_unavailable",
    }
    assert "field or business impact validation" in stored["validation_scope"]["not_verified"]
    assert all(row["store"] == "evaluation_demo_fixture" for row in stored["fixture_recommendations"])
    assert all(row["do_not_operationalize"] is True for row in stored["fixture_recommendations"])


def test_gold_seed_policy_v2_re_evaluation_is_separate_evaluation_artifact(tmp_path: Path) -> None:
    v1 = seed_gold_recommendations(ROOT, output=tmp_path / "policy-v1.json")
    v2 = seed_gold_recommendations(
        ROOT,
        output=tmp_path / "policy-v2.json",
        policy_version="recommendation-policy-v2",
    )

    assert v1["policy_version"] == "recommendation-policy-v1"
    assert v2["policy_version"] == "recommendation-policy-v2"
    assert len(v2["fixture_recommendations"]) == 0
    assert len(v2["fixture_non_recommendations"]) == 8
    assert set(v2["operational_side_effect_counts"].values()) == {0}


def test_gold_seed_new_artifact_revision_creates_new_source_lineage(tmp_path: Path) -> None:
    output = tmp_path / "recommendation-policy-v1.json"
    first = seed_gold_recommendations(ROOT, output=output)
    stored = json.loads(output.read_text(encoding="utf-8"))
    row = dict(stored["fixture_recommendations"][0])
    row["source_product_result_id"] = f"{row['source_product_result_id']}#revision-2"
    stored["fixture_recommendations"].append(row)
    output.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    replay = seed_gold_recommendations(ROOT, output=output)

    assert first["inserted"] == 8
    assert len(replay["fixture_recommendations"]) == 9
    assert replay["inserted"] == 0
