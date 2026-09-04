from __future__ import annotations

import pytest

from app.diagnosis.recommendation_policy import (
    POLICY_VERSION,
    RecommendationPolicyError,
    RecommendationPolicyInput,
    evaluate_recommendation_policy,
)


def _input(status: str, criticality: str | None = "medium", **updates) -> RecommendationPolicyInput:
    payload = {
        "source_product_result_id": "RESULT#M-001#2026-08-01T00:00:00+09:00",
        "source_evidence_id": "EVD#M-001#2026-08-01T00:00:00+09:00",
        "source_schema_version": "result-artifact-v1.0",
        "status": status,
        "equipment": {} if criticality is None else {"criticality": criticality},
        "basis": ("factor.1.tool_wear_min",),
        "source_fields": ("factor.1.tool_wear_min", "sensor_evidence.sensors.tool_wear_min"),
    }
    payload.update(updates)
    return RecommendationPolicyInput(**payload)


@pytest.mark.parametrize(
    ("status", "criticality", "expected"),
    [
        ("normal", "medium", "continue_monitoring"),
        ("warning", "high", "request_inspection"),
        ("warning", "medium", "request_inspection"),
        ("critical", "high", "review_shutdown"),
        ("critical", "medium", "request_inspection"),
    ],
)
def test_recommendation_policy_v1_maps_status_and_explicit_criticality(
    status: str,
    criticality: str,
    expected: str,
) -> None:
    recommendation = evaluate_recommendation_policy(_input(status, criticality))

    assert recommendation is not None
    assert recommendation.source_policy_version == POLICY_VERSION
    assert recommendation.kind == expected
    assert recommendation.source_product_result_id.startswith("RESULT#")
    assert recommendation.source_evidence_id.startswith("EVD#")
    assert recommendation.source_schema_version == "result-artifact-v1.0"
    assert recommendation.basis == ("factor.1.tool_wear_min",)
    assert recommendation.requires_human_approval is True


def test_data_quality_hold_fails_closed_before_criticality() -> None:
    recommendation = evaluate_recommendation_policy(
        _input(
            "warning",
            "high",
            data_quality_hold=True,
            basis=(),
            source_fields=(),
        )
    )

    assert recommendation is not None
    assert recommendation.kind == "hold_for_data_check"
    assert recommendation.basis == ("policy.data_quality_hold",)


@pytest.mark.parametrize(
    "updates",
    [
        {"source_product_result_id": ""},
        {"source_evidence_id": ""},
        {"source_schema_version": ""},
    ],
)
def test_recommendation_policy_rejects_missing_source_identity(updates: dict) -> None:
    with pytest.raises(RecommendationPolicyError, match="missing recommendation source identity"):
        evaluate_recommendation_policy(_input("warning", **updates))


@pytest.mark.parametrize(
    "updates",
    [
        {"criticality": None},
        {"basis": ()},
        {"basis": ("factor.999.unknown",)},
    ],
)
def test_recommendation_policy_does_not_pass_unavailable_or_unknown_basis_as_executable(
    updates: dict,
) -> None:
    criticality = updates.pop("criticality", "medium")
    assert evaluate_recommendation_policy(_input("warning", criticality, **updates)) is None


def test_policy_version_mismatch_does_not_pass_as_executable_recommendation() -> None:
    recommendation = evaluate_recommendation_policy(
        _input("warning", "high", policy_version="recommendation-policy-v2")
    )

    assert recommendation is None


def test_recommendation_policy_is_independent_from_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    before = evaluate_recommendation_policy(_input("critical", "high"))
    monkeypatch.setenv("LLM_PROVIDER", "off")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    after = evaluate_recommendation_policy(_input("critical", "high"))

    assert after == before
