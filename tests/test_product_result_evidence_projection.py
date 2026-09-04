from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.diagnosis.evidence_projection import (
    EVENT_EVIDENCE_CONTRACT_TYPE,
    EVENT_EVIDENCE_SCHEMA_VERSION,
    event_evidence_projection_to_legacy_evidence,
    product_result_artifact_to_event_evidence_projection,
)
from app.diagnosis.evidence_enrichment import validate_evidence_payload_invariants

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "product_result_evidence_projection"


def load_projection_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def assert_absent_hidden_truth(payload: object) -> None:
    if isinstance(payload, dict):
        assert "evaluation_truth" not in payload
        assert "hidden_truth" not in payload
        for value in payload.values():
            assert_absent_hidden_truth(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_absent_hidden_truth(value)


def enriched_critical_artifact() -> dict:
    return load_projection_fixture("producer-enriched-critical-artifact.json")


def test_product_result_artifact_to_event_evidence_projection_matches_expected_reference_slice() -> None:
    expected = load_projection_fixture("expected-event-evidence-projection-critical.json")
    projection = product_result_artifact_to_event_evidence_projection(enriched_critical_artifact())

    assert projection["schema_version"] == expected["schema_version"] == EVENT_EVIDENCE_SCHEMA_VERSION
    assert projection["contract_type"] == expected["contract_type"] == EVENT_EVIDENCE_CONTRACT_TYPE
    assert projection["event_id"] == expected["event_id"]
    assert projection["evidence_id"] == f"EVD-{projection['event_id']}"
    assert projection["subject"] == expected["subject"]
    assert projection["artifact_reference"]["evidence_payload_reference"] == expected["artifact_reference"][
        "evidence_payload_reference"
    ]
    assert projection["assessment"]["status"] == expected["assessment"]["status"]
    assert projection["assessment"]["recommended_decision"] == expected["assessment"]["recommended_decision"]
    assert projection["assessment"]["operational_decision_kind"] == expected["assessment"][
        "operational_decision_kind"
    ]
    assert projection["assessment"]["threshold"] == expected["assessment"]["threshold"]
    assert projection["assessment"]["top_factors"] == expected["assessment"]["top_factors"]
    assert projection["report_projection"]["display_labels"]["confidence_label"] == "high"
    assert projection["report_projection"]["sensor_cards"][0]["z_score"] == -2.9
    assert projection["report_projection"]["sensor_cards"][0]["basis"]["baseline_n"] == 240
    assert projection["report_projection"]["inspection_targets"][0]["component_id"] == "rotating_assembly"
    assert_absent_hidden_truth(projection)
    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "event-evidence-projection.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(Draft202012Validator(schema).iter_errors(projection)) == []


def test_enriched_artifact_fixture_keeps_evidence_payload_to_producer_candidate_fields() -> None:
    payload_keys = set(enriched_critical_artifact()["evidence_payload"])

    assert payload_keys == {
        "sensor_evidence",
        "component_hypotheses",
        "status_flags",
        "maintenance_context",
        "recommended_actions",
        "source_fields",
        "evidence_gaps",
    }


def test_projection_rejects_mutated_or_missing_source_flag() -> None:
    artifact = enriched_critical_artifact()

    mutated = json.loads(json.dumps(artifact))
    mutated["provenance"]["canonical_source_mutated"] = True
    with pytest.raises(ValueError, match="canonical_source_mutated must be false"):
        product_result_artifact_to_event_evidence_projection(mutated)

    missing = json.loads(json.dumps(artifact))
    del missing["provenance"]["canonical_source_mutated"]
    with pytest.raises(ValueError, match="canonical_source_mutated must be false"):
        product_result_artifact_to_event_evidence_projection(missing)


def test_projection_requires_enriched_evidence_payload() -> None:
    artifact = enriched_critical_artifact()
    del artifact["evidence_payload"]

    with pytest.raises(ValueError, match="evidence_payload is required"):
        product_result_artifact_to_event_evidence_projection(artifact)


def test_projection_does_not_create_evidence_trace_when_payload_has_none() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["source_fields"] = []

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["report_projection"]["evidence_trace"] == []
    assert projection["assessment"]["top_factors"][0]["feature"] == "rotation_raw"


def test_payload_fields_do_not_override_artifact_judgement_or_subject() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["top_factors"] = [{"feature": "payload_should_not_win"}]
    artifact["evidence_payload"]["equipment"] = {
        "equipment_id": "PAYLOAD-ASSET",
        "display_name": "payload display label",
    }

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["assessment"]["top_factors"] == artifact["top_factors"]
    assert projection["artifact_reference"]["top_factor_count"] == len(artifact["top_factors"])
    assert "ranked_factor_evidence" not in projection["artifact_reference"]
    assert projection["subject"] == {
        "equipment_id": "CMP-S03-L03-01",
        "display_name": "CMP-S03-L03-01",
        "asset_type": "compressor",
    }


def test_legacy_projection_rejects_unmapped_product_result_factors() -> None:
    projection = product_result_artifact_to_event_evidence_projection(enriched_critical_artifact())

    with pytest.raises(ValueError, match="producer-normalized top_factors"):
        event_evidence_projection_to_legacy_evidence(projection)


def test_legacy_projection_uses_ranked_factor_evidence_for_current_schema() -> None:
    artifact = enriched_critical_artifact()
    projection = product_result_artifact_to_event_evidence_projection(artifact)

    legacy = event_evidence_projection_to_legacy_evidence(
        projection,
        ranked_factor_evidence=artifact["ranked_factor_evidence"],
    )

    schema = json.loads((ROOT / "contracts" / "schemas" / "evidence-package.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(legacy)) == []
    assert legacy["schema_version"] == "1.0"
    assert legacy["evidence_id"] == projection["evidence_id"]
    assert legacy["event_id"] == projection["event_id"]
    assert legacy["status"] == projection["assessment"]["status"]
    assert legacy["recommended_decision"] == projection["assessment"]["recommended_decision"]
    assert legacy["threshold"] == projection["assessment"]["threshold"]
    assert legacy["top_factors"] == artifact["ranked_factor_evidence"]
    assert legacy["top_factors"][0]["normal_range"] == "baseline z-score -2.0..2.0"
    assert legacy["lineage"]["product_result_artifact"]["artifact_id"] == projection["artifact_reference"]["artifact_id"]
    assert_absent_hidden_truth(legacy)


def test_projection_display_confidence_prefers_canonical_label_over_numeric_value() -> None:
    artifact = enriched_critical_artifact()
    artifact["confidence"] = 0.84
    artifact["confidence_label"] = "medium"

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["assessment"]["confidence"] == "medium"
    assert projection["report_projection"]["display_labels"]["confidence_label"] == "medium"


def test_operational_decision_is_null_without_producer_recommendation() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["recommended_actions"] = []
    artifact["recommended_action"] = {
        "action": "immediate_inspection_and_stop_review",
        "priority": "urgent",
    }
    artifact["status_grade"] = "critical"

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["assessment"]["operational_decision_kind"] is None


def test_operational_decision_does_not_reinterpret_producer_kind() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["recommended_actions"][0]["kind"] = "opaque_producer_kind"

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["report_projection"]["recommended_actions"][0]["kind"] == (
        "opaque_producer_kind"
    )
    assert projection["assessment"]["operational_decision_kind"] == "review_shutdown"


def test_non_operational_producer_action_is_report_only() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["recommended_actions"][0]["action_id"] = (
        "inspect_rotating_assembly"
    )

    projection = product_result_artifact_to_event_evidence_projection(artifact)

    assert projection["assessment"]["operational_decision_kind"] is None
    assert projection["report_projection"]["recommended_actions"][0]["action_id"] == (
        "inspect_rotating_assembly"
    )


def test_product_result_contract_rejects_multiple_operational_recommendations() -> None:
    artifact = enriched_critical_artifact()
    artifact["evidence_payload"]["recommended_actions"].append(
        dict(artifact["evidence_payload"]["recommended_actions"][0])
    )

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "product-result-artifact.schema.json").read_text(
            encoding="utf-8"
        )
    )
    errors = list(Draft202012Validator(schema).iter_errors(artifact))

    assert any(error.validator == "maxItems" for error in errors)
    with pytest.raises(ValueError, match="at most one operational recommendation"):
        validate_evidence_payload_invariants(artifact["evidence_payload"])
