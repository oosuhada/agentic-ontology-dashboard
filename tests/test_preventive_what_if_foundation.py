from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from experiments.preventive_intervention.contracts import (
    ToolReplacementPolicy,
    WhatIfResult,
    preventive_what_if_schema,
)
from experiments.preventive_intervention.policies import apply_tool_replacement


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "preventive-what-if.schema.json"
POLICY_PATH = ROOT / "experiments" / "preventive_intervention" / "policies" / "tool-replacement-v1.json"
FIXTURE_PATH = ROOT / "data" / "fixtures" / "what_if" / "tool-replacement-contract-fixture.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_schema_matches_pydantic_contract() -> None:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert schema == preventive_what_if_schema()


def test_contract_fixture_passes_pydantic_and_json_schema() -> None:
    payload = load_json(FIXTURE_PATH)
    result = WhatIfResult.model_validate(payload)
    assert result.effect.estimated_probability_reduction == pytest.approx(0.61)
    assert result.provenance.canonical_source_mutated is False

    errors = list(
        Draft202012Validator(
            load_json(SCHEMA_PATH),
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    )
    assert errors == []


def test_contract_rejects_inconsistent_probability_reduction() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["effect"]["estimated_probability_reduction"] = 0.5
    with pytest.raises(ValidationError, match="baseline minus intervention"):
        WhatIfResult.model_validate(payload)


def test_contract_requires_synthetic_safety_limitations() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["limitations"] = [{"code": "SYNTHETIC_DATA_ONLY"}]
    with pytest.raises(ValidationError, match="all safety limitations"):
        WhatIfResult.model_validate(payload)


def test_contract_rejects_leading_indicator_for_another_asset() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["leading_indicators"][0]["source_reference"]["asset_id"] = "CNC-OTHER"
    with pytest.raises(ValidationError, match="asset IDs must match"):
        WhatIfResult.model_validate(payload)


def test_contract_rejects_policy_version_mismatch() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["provenance"]["simulation_policy_version"] = "different-policy"
    with pytest.raises(ValidationError, match="policy versions must match"):
        WhatIfResult.model_validate(payload)


@pytest.mark.parametrize("parameters", [{}, {"tool_wear_after": -1}])
def test_contract_requires_valid_tool_replacement_parameters(parameters: dict) -> None:
    payload = load_json(FIXTURE_PATH)
    payload["intervention"]["parameters"] = parameters
    with pytest.raises(ValidationError, match="tool_wear_after"):
        WhatIfResult.model_validate(payload)


def test_contract_rejects_inconsistent_time_to_peak() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["rise_event"]["time_to_peak_hours"] = 99
    with pytest.raises(ValidationError, match="started_at to peak_at"):
        WhatIfResult.model_validate(payload)


def test_contract_rejects_decision_before_rise_event() -> None:
    payload = load_json(FIXTURE_PATH)
    payload["decision_at"] = "2026-07-31T23:59:59Z"
    with pytest.raises(ValidationError, match="decision_at must not precede"):
        WhatIfResult.model_validate(payload)


def test_tool_replacement_policy_is_non_mutating_and_marks_maintenance() -> None:
    policy = ToolReplacementPolicy.model_validate(load_json(POLICY_PATH))
    original = {
        "asset_id": "CNC-S01-L01-04",
        "tool_wear_min": 211.0,
        "is_operating": 1,
        "operating_state": "running",
        "torque_nm": 56.8,
    }

    transformed = apply_tool_replacement(original, policy)

    assert original["tool_wear_min"] == 211.0
    assert original["operating_state"] == "running"
    assert transformed["tool_wear_min"] == 0.0
    assert transformed["is_operating"] == 0
    assert transformed["operating_state"] == "maintenance"
    assert transformed["torque_nm"] == original["torque_nm"]


def test_tool_replacement_rejects_missing_or_invalid_wear() -> None:
    policy = ToolReplacementPolicy.model_validate(load_json(POLICY_PATH))
    with pytest.raises(ValueError, match="requires tool_wear_min"):
        apply_tool_replacement({}, policy)
    with pytest.raises(ValueError, match="must be numeric"):
        apply_tool_replacement({"tool_wear_min": "bad"}, policy)
    with pytest.raises(ValueError, match="must not be negative"):
        apply_tool_replacement({"tool_wear_min": -1}, policy)


def test_producer_fixture_contains_no_role_rendered_report_fields() -> None:
    payload = load_json(FIXTURE_PATH)
    forbidden = {"role", "summary", "report", "blocks", "manager_view", "engineer_view"}
    assert forbidden.isdisjoint(payload)
