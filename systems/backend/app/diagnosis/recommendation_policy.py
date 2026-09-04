from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .recommendation_schema import ProducerRecommendation

POLICY_VERSION = "recommendation-policy-v1"


class RecommendationPolicyError(ValueError):
    """Raised when source evidence cannot produce an executable recommendation."""


@dataclass(frozen=True)
class RecommendationPolicyInput:
    source_product_result_id: str
    source_evidence_id: str
    source_schema_version: str
    status: str
    equipment: dict[str, Any]
    basis: tuple[str, ...]
    source_fields: tuple[str, ...]
    data_quality_hold: bool = False
    source_action_id: str | None = None
    policy_version: str = POLICY_VERSION


def load_recommendation_policy(path: Path | None = None) -> dict[str, Any]:
    source = path or Path(__file__).with_name("recommendation_policy.json")
    policy = json.loads(source.read_text(encoding="utf-8"))
    if policy.get("version") != POLICY_VERSION:
        raise RecommendationPolicyError("unexpected recommendation policy version")
    return policy


def evaluate_recommendation_policy(
    policy_input: RecommendationPolicyInput,
    *,
    policy: dict[str, Any] | None = None,
) -> ProducerRecommendation | None:
    """Return a producer-owned recommendation without consulting Maintenance state.

    ``None`` means the policy could not create a recommendation. That is an
    evidence availability state, not a recommendation kind to materialize.
    """

    policy = policy or load_recommendation_policy()
    _require_identity(policy_input)
    if policy_input.policy_version != policy["version"]:
        return None
    action_key = _action_key(policy_input, policy)
    if action_key is None:
        return None
    action = policy["actions"][action_key]
    source_action_id = policy_input.source_action_id or f"{POLICY_VERSION}:{action_key}"
    basis = policy_input.basis
    if action_key == "hold_for_data_check" and not basis:
        basis = ("policy.data_quality_hold",)
    return ProducerRecommendation(
        source_action_id=source_action_id,
        source_product_result_id=policy_input.source_product_result_id,
        source_evidence_id=policy_input.source_evidence_id,
        source_schema_version=policy_input.source_schema_version,
        source_policy_version=policy_input.policy_version,
        label=str(action["label"]),
        kind=str(action["kind"]),
        requires_human_approval=bool(action["requires_human_approval"]),
        basis=basis,
    )


def recommendation_policy_input_from_artifact(artifact: dict[str, Any]) -> RecommendationPolicyInput:
    evidence_payload = artifact.get("evidence_payload") or {}
    actions = evidence_payload.get("recommended_actions") or []
    first_action = actions[0] if actions else {}
    source_fields = tuple(str(field.get("field_id")) for field in evidence_payload.get("source_fields") or [])
    return RecommendationPolicyInput(
        source_product_result_id=str(artifact.get("artifact_id") or ""),
        source_evidence_id=str((artifact.get("provenance") or {}).get("evidence_payload_reference", {}).get("reference") or ""),
        source_schema_version=str(artifact.get("schema_version") or ""),
        status=str(artifact.get("status_grade") or ""),
        equipment=dict(artifact.get("equipment") or {}),
        basis=tuple(str(item) for item in first_action.get("basis") or ()),
        source_fields=source_fields,
        data_quality_hold=str(artifact.get("status_grade") or "") == "data_quality_hold"
        or bool(artifact.get("data_quality_warnings")),
    )


def _require_identity(policy_input: RecommendationPolicyInput) -> None:
    required = {
        "source_product_result_id": policy_input.source_product_result_id,
        "source_evidence_id": policy_input.source_evidence_id,
        "source_schema_version": policy_input.source_schema_version,
        "status": policy_input.status,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RecommendationPolicyError(f"missing recommendation source identity: {missing}")


def resolve_status_criticality_action(
    status: str,
    criticality: str | None,
    *,
    policy: dict[str, Any] | None = None,
) -> tuple[str, str, str] | None:
    """Look up the recommendation-policy-v1 action for a status/criticality pair.

    This is the single source of truth for status x criticality -> action
    mapping. It backs both the operational policy evaluator below and any
    display-facing code (e.g. Diagnosis evidence enrichment) that needs to show
    a status/criticality-consistent action without going through the full
    identity/basis-gated ``evaluate_recommendation_policy`` contract. Returns
    ``None`` when criticality is missing, not an allowed value, or no rule
    matches, so callers fall back to their own default instead of fabricating
    a policy action from partial context.
    """

    if not criticality:
        return None
    policy = policy or load_recommendation_policy()
    normalized_criticality = str(criticality)
    if normalized_criticality not in set(policy["allowed_criticality"]):
        return None
    for rule in policy["rules"]:
        if rule["status"] == status and rule.get("criticality") == normalized_criticality:
            action_key = str(rule["action"])
            action = policy["actions"][action_key]
            return action_key, str(action["label"]), str(action["kind"])
    return None


def _action_key(policy_input: RecommendationPolicyInput, policy: dict[str, Any]) -> str | None:
    if policy_input.data_quality_hold or policy_input.status == "data_quality_hold":
        return "hold_for_data_check"
    if not policy_input.basis:
        return None
    unresolved = sorted(set(policy_input.basis) - set(policy_input.source_fields))
    if unresolved:
        return None
    criticality = str(policy_input.equipment.get("criticality") or "")
    resolved = resolve_status_criticality_action(policy_input.status, criticality, policy=policy)
    if resolved is None:
        return None
    action_key, _label, _kind = resolved
    return action_key
