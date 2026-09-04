from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "product_result_evidence_projection"
EVIDENCE_PAYLOAD_KEYS = {
    "sensor_evidence",
    "component_hypotheses",
    "status_flags",
    "maintenance_context",
    "recommended_actions",
    "source_fields",
    "evidence_gaps",
}
FORBIDDEN_PAYLOAD_KEYS = {
    "event_id",
    "scenario_id",
    "equipment",
    "observation",
    "history",
    "detected_interval",
    "generated_at",
    "threshold",
    "model",
    "top_factors",
    "data_quality_warnings",
    "lineage",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def product_result_artifact_schema() -> dict:
    return load_json(ROOT / "contracts" / "schemas" / "product-result-artifact.schema.json")


def producer_enriched_artifact() -> dict:
    return load_json(PROJECTION_FIXTURE_ROOT / "producer-enriched-critical-artifact.json")


def schema_errors(payload: dict) -> list:
    return list(Draft202012Validator(product_result_artifact_schema()).iter_errors(payload))


def unresolved_basis_refs(evidence_payload: dict) -> set[str]:
    source_field_ids = {field["field_id"] for field in evidence_payload["source_fields"]}
    basis_refs: set[str] = set()

    for hypothesis in evidence_payload["component_hypotheses"]:
        basis_refs.update(hypothesis["basis"])
    for action in evidence_payload["recommended_actions"]:
        basis_refs.update(action["basis"])

    return basis_refs - source_field_ids


def test_product_result_artifact_schema_accepts_existing_v1_artifact_without_evidence_payload() -> None:
    artifact = producer_enriched_artifact()
    artifact.pop("evidence_payload")
    artifact["provenance"].pop("evidence_payload_reference")

    assert schema_errors(artifact) == []


def test_product_result_artifact_schema_accepts_optional_evidence_payload_contract() -> None:
    artifact = producer_enriched_artifact()

    assert set(artifact["evidence_payload"]) == EVIDENCE_PAYLOAD_KEYS
    assert schema_errors(artifact) == []


def test_product_result_artifact_schema_allows_explicit_recommendation_absence() -> None:
    artifact = producer_enriched_artifact()
    artifact["recommended_action"] = None
    artifact["evidence_payload"]["recommended_actions"] = []
    artifact["evidence_payload"]["evidence_gaps"].append(
        {
            "gap_id": "gap.recommended_actions.unavailable",
            "field": "evidence_payload.recommended_actions",
            "reason": "insufficient_context",
            "required_source": "recommendation_policy_input",
            "owner_domain": "diagnosis",
            "display_policy": "show_limitation",
        }
    )

    assert schema_errors(artifact) == []


def test_product_result_artifact_schema_rejects_recommendation_presence_mismatch() -> None:
    missing_root = producer_enriched_artifact()
    missing_root.pop("recommended_action")

    stale_root = producer_enriched_artifact()
    stale_root["evidence_payload"]["recommended_actions"] = []

    assert any(
        "recommended_action" in error.message for error in schema_errors(missing_root)
    )
    assert any(
        "None" in error.message or "null" in error.message
        for error in schema_errors(stale_root)
    )


def test_product_result_artifact_schema_rejects_payload_without_evidence_reference() -> None:
    artifact = producer_enriched_artifact()
    artifact["provenance"].pop("evidence_payload_reference")

    errors = schema_errors(artifact)

    assert any("'evidence_payload_reference' is a required property" in error.message for error in errors)


def test_product_result_artifact_schema_rejects_evidence_reference_without_payload() -> None:
    artifact = producer_enriched_artifact()
    artifact.pop("evidence_payload")

    errors = schema_errors(artifact)

    assert any("'evidence_payload' is a required property" in error.message for error in errors)


def test_product_result_artifact_schema_allows_missing_maintenance_context_with_gap() -> None:
    artifact = producer_enriched_artifact()
    artifact["evidence_payload"].pop("maintenance_context")
    artifact["evidence_payload"]["evidence_gaps"].append(
        {
            "gap_id": "gap.maintenance_context.unavailable",
            "field": "evidence_payload.maintenance_context",
            "reason": "missing_source",
            "required_source": "maintenance_context_provider",
            "owner_domain": "maintenance",
            "display_policy": "show_as_unavailable",
        }
    )

    assert schema_errors(artifact) == []


def test_product_result_artifact_schema_allows_null_maintenance_context_with_gap() -> None:
    artifact = producer_enriched_artifact()
    artifact["evidence_payload"]["maintenance_context"] = None
    artifact["evidence_payload"]["evidence_gaps"].append(
        {
            "gap_id": "gap.maintenance_context.null",
            "field": "evidence_payload.maintenance_context",
            "reason": "missing_source",
            "required_source": "maintenance_context_provider",
            "owner_domain": "maintenance",
            "display_policy": "show_as_unavailable",
        }
    )

    assert schema_errors(artifact) == []


def test_product_result_artifact_status_flags_are_fixed_contract_flags() -> None:
    artifact = producer_enriched_artifact()
    artifact["evidence_payload"]["status_flags"]["made_up_flag"] = True

    errors = schema_errors(artifact)

    assert any("Additional properties are not allowed" in error.message for error in errors)


def test_product_result_artifact_schema_rejects_dashboard_fixture_fields_inside_evidence_payload() -> None:
    artifact = producer_enriched_artifact()
    artifact["evidence_payload"]["event_id"] = "EVT-SHOULD-NOT-BE-HERE"

    errors = schema_errors(artifact)

    assert any("Additional properties are not allowed" in error.message for error in errors)


def test_product_result_artifact_evidence_payload_contract_documents_forbidden_keys() -> None:
    artifact = producer_enriched_artifact()

    assert set(artifact["evidence_payload"]).isdisjoint(FORBIDDEN_PAYLOAD_KEYS)


def test_product_result_artifact_basis_refs_resolve_to_source_fields() -> None:
    artifact = producer_enriched_artifact()

    assert unresolved_basis_refs(artifact["evidence_payload"]) == set()


def test_product_result_artifact_basis_refs_detect_unmapped_source_field_ids() -> None:
    artifact = producer_enriched_artifact()
    artifact["evidence_payload"]["recommended_actions"][0]["basis"].append("factor.999.nonexistent")

    assert unresolved_basis_refs(artifact["evidence_payload"]) == {"factor.999.nonexistent"}


def test_product_result_artifact_schema_keeps_event_identity_out_of_root_contract() -> None:
    properties = product_result_artifact_schema()["properties"]

    assert "event_id" not in properties
    assert "scenario_id" not in properties
    assert "equipment" not in properties
    assert "observation" not in properties
    assert "history" not in properties
    assert "detected_interval" not in properties
    assert "lineage" not in properties


def test_product_result_artifact_schema_allows_threshold_and_generated_at_as_optional_root_fields() -> None:
    properties = product_result_artifact_schema()["properties"]

    assert properties["threshold"]["type"] == ["number", "null"]
    assert properties["generated_at"]["type"] == "string"


def test_product_result_artifact_evidence_reference_targets_diagnosis_enrichment_helper() -> None:
    artifact = producer_enriched_artifact()

    assert artifact["provenance"]["evidence_payload_reference"] == {
        "source": "product_result_artifact",
        "reference": "producer-enriched-critical",
        "generated_by": "systems.backend.app.diagnosis.evidence_enrichment",
    }
