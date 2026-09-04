from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from systems.backend.app.diagnosis.contracts import load_fixture
from systems.backend.app.diagnosis.evidence import FixtureContextProvider, build_product_result_artifact
from systems.backend.app.diagnosis.evidence_baseline import build_history_baseline_window
from systems.backend.app.diagnosis.evidence_enrichment import (
    build_ranked_factor_evidence,
    validate_evidence_payload_invariants,
)
from systems.backend.app.diagnosis.predictor import FactorScore, HeuristicPredictor, Prediction
from systems.backend.app.diagnosis.recommendation_policy import (
    RecommendationPolicyInput,
    evaluate_recommendation_policy,
)

ROOT = Path(__file__).resolve().parents[1]


class MissingContextProvider:
    provider_name = "missing"

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any] | None:
        return None


class BrokenContextProvider:
    provider_name = "broken"

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any] | None:
        raise ValueError("provider contract violation")


def unresolved_basis_refs(evidence_payload: dict[str, Any]) -> set[str]:
    source_field_ids = {field["field_id"] for field in evidence_payload["source_fields"]}
    basis_refs: set[str] = set()
    for hypothesis in evidence_payload["component_hypotheses"]:
        basis_refs.update(hypothesis["basis"])
    for action in evidence_payload["recommended_actions"]:
        basis_refs.update(action["basis"])
    return basis_refs - source_field_ids


def semantic_reference_payload() -> dict[str, Any]:
    return json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "product_result_evidence_projection"
            / "semantic_regression"
            / "pdm-operations-semantic-reference-critical.json"
        ).read_text(encoding="utf-8")
    )


def test_product_result_artifact_includes_producer_evidence_payload_without_default_maintenance_context() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    payload = artifact["evidence_payload"]

    assert set(payload) == {
        "sensor_evidence",
        "component_hypotheses",
        "status_flags",
        "recommended_actions",
        "source_fields",
        "evidence_gaps",
    }
    assert artifact["provenance"]["evidence_payload_reference"] == {
        "source": "product_result_artifact",
        "reference": artifact["artifact_id"],
        "generated_by": "systems.backend.app.diagnosis.evidence_enrichment",
    }
    tool_wear = payload["sensor_evidence"]["sensors"]["tool_wear_min"]
    assert tool_wear["current"] == 230.0
    assert tool_wear["window_mean"] == 213.666667
    assert tool_wear["z_score"] == 2.352075
    assert tool_wear["basis"]["baseline_n"] == 3
    assert tool_wear["basis"]["baseline_reference"] == "fixture.history"
    assert payload["sensor_evidence"]["window_rows"] == 3
    assert [factor["feature"] for factor in artifact["ranked_factor_evidence"]] == [
        factor.feature for factor in HeuristicPredictor().predict(fixture).factors[:5]
    ]
    assert artifact["ranked_factor_evidence"][0]["normal_range"] == "0–180"
    assert artifact["ranked_factor_evidence"][0]["value"] == 230.0
    assert "maintenance_context" not in payload
    assert any(gap["field"] == "evidence_payload.maintenance_context" for gap in payload["evidence_gaps"])
    assert unresolved_basis_refs(payload) == set()


def test_product_result_artifact_uses_maintenance_context_only_when_provider_is_explicit() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")

    artifact = build_product_result_artifact(
        fixture,
        predictor=HeuristicPredictor(),
        context_provider=FixtureContextProvider(),
    )
    payload = artifact["evidence_payload"]

    assert payload["maintenance_context"]["provider"] == "fixture"
    assert not any(gap["field"] == "evidence_payload.maintenance_context" for gap in payload["evidence_gaps"])


def test_evidence_payload_preserves_pdm_operations_reference_semantics_without_copying_values() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    semantic_reference = semantic_reference_payload()

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    payload = artifact["evidence_payload"]

    assert set(payload["sensor_evidence"]) == set(semantic_reference["sensor_evidence"])
    assert set(next(iter(payload["sensor_evidence"]["sensors"].values()))["basis"]) == set(
        next(iter(semantic_reference["sensor_evidence"]["sensors"].values()))["basis"]
    )
    assert payload["component_hypotheses"][0]["association"] == semantic_reference["component_hypotheses"][0][
        "association"
    ]
    assert set(payload["recommended_actions"][0]) == set(semantic_reference["recommended_actions"][0])
    assert payload["source_fields"][0]["field_id"].startswith("factor.1.")
    assert any(field["field_id"].startswith("sensor_evidence.sensors.") for field in payload["source_fields"])


@pytest.mark.parametrize(
    ("criticality", "expected_kind"),
    [
        ("high", "review_shutdown"),
        ("medium", "request_inspection"),
        ("low", "request_inspection"),
    ],
)
def test_evidence_payload_recommended_action_is_criticality_aware_for_critical_status(
    criticality: str,
    expected_kind: str,
) -> None:
    """evidence_payload.recommended_actions must not diverge from recommendation-policy-v1.

    Regression test for a status-only _ACTION_BY_STATUS table that used to
    always report "review_shutdown" for status=critical regardless of
    equipment criticality, even though recommendation-policy-v1 only reviews
    shutdown for critical+high and asks for inspection at critical+medium/low.
    """
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-004-power-overstrain-critical.json")
    fixture["equipment"]["criticality"] = criticality

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())

    assert artifact["status_grade"] == "critical"
    action = artifact["evidence_payload"]["recommended_actions"][0]
    assert action["kind"] == expected_kind

    # Cross-check directly against the operational policy evaluator so the
    # display-facing evidence_payload can never show a different action than
    # what would actually be materialized for the same status/criticality.
    payload = artifact["evidence_payload"]
    policy_recommendation = evaluate_recommendation_policy(
        RecommendationPolicyInput(
            source_product_result_id=artifact["artifact_id"],
            source_evidence_id=artifact["provenance"]["evidence_payload_reference"]["reference"],
            source_schema_version=artifact["schema_version"],
            status=artifact["status_grade"],
            equipment=fixture["equipment"],
            basis=tuple(action["basis"]),
            source_fields=tuple(field["field_id"] for field in payload["source_fields"]),
        )
    )
    assert policy_recommendation is not None
    assert policy_recommendation.kind == expected_kind == action["kind"]


def test_evidence_payload_recommended_action_records_gap_without_criticality() -> None:
    from systems.backend.app.diagnosis.evidence_enrichment import build_product_result_evidence_payload

    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-004-power-overstrain-critical.json")
    prediction = HeuristicPredictor().predict(fixture)
    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    fixture_without_criticality = json.loads(json.dumps(fixture))
    fixture_without_criticality["equipment"].pop("criticality", None)

    payload = build_product_result_evidence_payload(artifact, fixture_without_criticality, prediction)

    assert artifact["status_grade"] == "critical"
    assert payload["recommended_actions"] == []
    assert {
        "gap_id": "gap.recommended_actions.unavailable",
        "field": "evidence_payload.recommended_actions",
        "reason": "criticality_missing_or_unresolved",
        "required_source": "recommendation_policy_input",
        "owner_domain": "diagnosis",
        "display_policy": "show_limitation",
    } in payload["evidence_gaps"]
    policy_recommendation = evaluate_recommendation_policy(
        RecommendationPolicyInput(
            source_product_result_id=artifact["artifact_id"],
            source_evidence_id=artifact["provenance"]["evidence_payload_reference"]["reference"],
            source_schema_version=artifact["schema_version"],
            status=artifact["status_grade"],
            equipment=fixture_without_criticality["equipment"],
            basis=(),
            source_fields=tuple(field["field_id"] for field in payload["source_fields"]),
        )
    )
    assert policy_recommendation is None


def test_product_result_artifact_excludes_non_numeric_observation_values_from_sensor_evidence() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    fixture["observation"]["operator_confirmed"] = True

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    sensors = artifact["evidence_payload"]["sensor_evidence"]["sensors"]

    assert "product_type" not in sensors
    assert "operator_confirmed" not in sensors
    assert "tool_wear_min" in sensors


def test_product_result_artifact_preserves_signed_contribution_direction_fallback() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-001-normal-stable.json")

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())

    assert any(factor["signed_contribution"] < 0 for factor in artifact["top_factors"])
    for factor in artifact["top_factors"]:
        if factor["signed_contribution"] < 0:
            assert factor["direction"] == "risk_down"
        assert factor["evidence_field_id"].startswith(f"factor.{factor['rank']}.")
        assert 0 <= factor["contribution"] <= 1


def test_raw_signal_factor_keeps_source_raw_unit_and_signal_label() -> None:
    prediction = Prediction(
        model_version="test-model",
        probability=0.8,
        risk_band="warning",
        recommended_decision="request_inspection",
        confidence="medium",
        predicted_failure_type="failure_risk",
        factors=[
            FactorScore(
                feature="voltage_raw",
                raw_value=170.0,
                score=0.8,
                direction="risk_up",
            )
        ],
        quality_issues=[],
        model_artifact=None,
    )

    factor = build_ranked_factor_evidence(prediction)[0]

    assert factor["unit"] == "raw"
    assert factor["display_name"] == "전압 신호"


def test_product_result_artifact_records_gap_when_maintenance_context_is_missing() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")

    artifact = build_product_result_artifact(
        fixture,
        predictor=HeuristicPredictor(),
        context_provider=MissingContextProvider(),  # type: ignore[arg-type]
    )
    payload = artifact["evidence_payload"]

    assert "maintenance_context" not in payload
    assert {
        "gap_id": "gap.maintenance_context.unavailable",
        "field": "evidence_payload.maintenance_context",
        "reason": "missing_source",
        "required_source": "maintenance_context_provider",
        "owner_domain": "maintenance",
        "display_policy": "show_as_unavailable",
    } in payload["evidence_gaps"]


def test_product_result_artifact_propagates_context_provider_contract_errors() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")

    with pytest.raises(ValueError, match="provider contract violation"):
        build_product_result_artifact(
            fixture,
            predictor=HeuristicPredictor(),
            context_provider=BrokenContextProvider(),  # type: ignore[arg-type]
        )


def test_sensor_baseline_excludes_duplicate_current_observation_timestamp() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    fixture["history"].append(dict(fixture["observation"]))

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    tool_wear = artifact["evidence_payload"]["sensor_evidence"]["sensors"]["tool_wear_min"]

    assert tool_wear["basis"]["baseline_n"] == 3
    assert tool_wear["window_mean"] == 213.666667
    assert tool_wear["z_score"] == 2.352075


def test_history_baseline_policy_is_shared_for_dedupe_and_zero_variance() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    fixture["history"] = [
        {
            "timestamp": "2026-07-31T23:45:00+09:00",
            "product_type": "M",
            "tool_wear_min": 200,
            "torque_nm": 50,
        },
        {
            "timestamp": "2026-07-31T23:45:00+09:00",
            "product_type": "M",
            "tool_wear_min": 205,
            "torque_nm": 50,
        },
        {
            "timestamp": "2026-08-01T00:00:00+09:00",
            "product_type": "M",
            "tool_wear_min": 230,
            "torque_nm": 55,
        },
    ]

    baseline = build_history_baseline_window(fixture)

    assert baseline.stat("tool_wear_min", 230.0).n == 1
    assert baseline.stat("tool_wear_min", 230.0).mean == 205.0
    assert baseline.stat("tool_wear_min", 230.0).z_score is None
    assert baseline.stat("torque_nm", 55.0).z_score is None


def test_sensor_window_does_not_expose_placeholder_for_untimestamped_history_rows() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    fixture["history"].insert(
        0,
        {
            "product_type": "M",
            "air_temperature_k": 298.8,
            "process_temperature_k": 309.1,
            "rotational_speed_rpm": 1475,
            "torque_nm": 49.0,
            "tool_wear_min": 200,
        },
    )

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    window = artifact["evidence_payload"]["sensor_evidence"]["window"]

    assert window["start"] == "2026-07-31T23:45:00+09:00"
    assert not window["start"].startswith("history[")


def test_component_hypotheses_are_grouped_by_component_id() -> None:
    from systems.backend.app.diagnosis.evidence_enrichment import build_product_result_evidence_payload

    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    prediction = HeuristicPredictor().predict(fixture)
    artifact = {
        "status_grade": "warning",
        "top_factors": [
            {"rank": 1, "feature": "mechanical_power_w", "signed_contribution": 0.7},
            {"rank": 2, "feature": "overstrain_index", "signed_contribution": 0.5},
            {"rank": 3, "feature": "tool_wear_min", "signed_contribution": 0.4},
        ],
    }

    payload = build_product_result_evidence_payload(artifact, fixture, prediction)
    hypotheses = payload["component_hypotheses"]
    component_ids = [hypothesis["component_id"] for hypothesis in hypotheses]

    assert len(component_ids) == len(set(component_ids))
    drive_power = next(hypothesis for hypothesis in hypotheses if hypothesis["component_id"] == "drive_power")
    assert drive_power["basis"] == [
        "factor.1.mechanical_power_w",
        "factor.2.overstrain_index",
    ]


def test_product_result_artifact_records_data_quality_gaps_without_zero_filling() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-007-invalid-sensor-data.json")

    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    payload = artifact["evidence_payload"]

    assert artifact["status_grade"] == "data_quality_hold"
    assert artifact["failure_probability"] is None
    assert "air_temperature_k" not in payload["sensor_evidence"]["sensors"]
    assert any(gap["gap_id"].startswith("gap.data_quality.") for gap in payload["evidence_gaps"])


def test_evidence_payload_invariant_rejects_unmapped_basis_refs() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    artifact["evidence_payload"]["recommended_actions"][0]["basis"].append("factor.999.missing")

    with pytest.raises(ValueError, match="basis refs are not in source_fields"):
        validate_evidence_payload_invariants(artifact["evidence_payload"])


def test_evidence_payload_invariant_rejects_null_maintenance_context_without_gap() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    artifact["evidence_payload"]["maintenance_context"] = None
    artifact["evidence_payload"]["evidence_gaps"] = [
        gap
        for gap in artifact["evidence_payload"]["evidence_gaps"]
        if gap["field"] != "evidence_payload.maintenance_context"
    ]

    with pytest.raises(ValueError, match="missing maintenance_context gap"):
        validate_evidence_payload_invariants(artifact["evidence_payload"])


def test_evidence_payload_records_gap_when_top_factors_are_unavailable() -> None:
    from systems.backend.app.diagnosis.evidence_enrichment import build_product_result_evidence_payload

    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    prediction = HeuristicPredictor().predict(fixture)
    artifact = {
        "status_grade": "warning",
        "top_factors": [],
    }

    payload = build_product_result_evidence_payload(artifact, fixture, prediction)

    assert payload["component_hypotheses"] == []
    assert payload["recommended_actions"] == []
    assert {
        "gap_id": "gap.top_factors.unavailable",
        "field": "top_factors",
        "reason": "insufficient_context",
        "required_source": "observation_history",
        "owner_domain": "diagnosis",
        "display_policy": "show_limitation",
    } in payload["evidence_gaps"]
    assert any(gap["field"] == "evidence_payload.recommended_actions" for gap in payload["evidence_gaps"])
    validate_evidence_payload_invariants(payload)


def test_evidence_payload_invariant_rejects_missing_top_factor_gap() -> None:
    from systems.backend.app.diagnosis.evidence_enrichment import build_product_result_evidence_payload

    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    payload = build_product_result_evidence_payload(
        {
            "status_grade": "warning",
            "top_factors": [],
        },
        fixture,
        HeuristicPredictor().predict(fixture),
    )
    payload["evidence_gaps"] = [
        gap
        for gap in payload["evidence_gaps"]
        if gap["field"] != "top_factors"
    ]

    with pytest.raises(ValueError, match="missing top_factors gap"):
        validate_evidence_payload_invariants(payload)


def test_evidence_payload_does_not_overwrite_official_judgement_fields() -> None:
    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    before = {
        key: json.loads(json.dumps(artifact[key]))
        for key in (
            "status_grade",
            "failure_probability",
            "confidence",
            "predicted_failure_type",
            "top_factors",
            "recommended_action",
        )
    }

    artifact["evidence_payload"]["top_factors"] = [{"feature": "payload_should_not_win"}]
    artifact["evidence_payload"]["recommended_action"] = {"action": "payload_should_not_win"}

    assert {
        key: artifact[key]
        for key in (
            "status_grade",
            "failure_probability",
            "confidence",
            "predicted_failure_type",
            "top_factors",
            "recommended_action",
        )
    } == before


def test_evidence_payload_builder_enriches_top_factor_basis_when_called_directly() -> None:
    from systems.backend.app.diagnosis.evidence_enrichment import build_product_result_evidence_payload

    fixture = load_fixture(ROOT / "data" / "fixtures" / "GS-002-tool-wear-warning.json")
    artifact = build_product_result_artifact(fixture, predictor=HeuristicPredictor())
    for factor in artifact["top_factors"]:
        factor.pop("evidence_field_id")

    payload = build_product_result_evidence_payload(
        artifact,
        fixture,
        HeuristicPredictor().predict(fixture),
    )

    assert unresolved_basis_refs(payload) == set()
    assert all(factor.get("evidence_field_id") for factor in artifact["top_factors"])


def test_ranked_factor_evidence_preserves_null_raw_values() -> None:
    prediction = Prediction(
        risk_band="warning",
        probability=0.7,
        confidence="medium",
        predicted_failure_type="tool_wear",
        recommended_decision="inspect_within_current_shift",
        factors=[
            FactorScore(
                feature="tool_wear_min",
                raw_value=None,  # type: ignore[arg-type]
                score=1.0,
                direction="risk_up",
            )
        ],
        quality_issues=[],
        model_version="test",
        model_artifact=None,
    )

    ranked = build_ranked_factor_evidence(prediction)

    assert ranked[0]["value"] is None
