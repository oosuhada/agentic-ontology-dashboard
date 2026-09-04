"""Deterministic SOP retrieval for read-only Operations agent packets."""

from __future__ import annotations

from typing import Any


_TEMPORAL_FACTOR_SUFFIXES = (
    "_6h_max_abs",
    "_6h_abs_mean",
    "_abs_current",
    "_6h_change",
    "_6h_mean",
    "_6h_std",
    "_1h_change",
    "_current",
)


def retrieve_inspection_sops(
    *,
    fixture: dict[str, Any],
    artifact: dict[str, Any],
    procedures: list[dict[str, Any]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Return scored SOP candidates without creating operational state.

    This is intentionally a local lexical/metadata retriever. A future vector
    provider can keep the same result contract and replace only this boundary.
    """
    query = _query_from_context(fixture, artifact)
    results = []
    for procedure in procedures:
        if not _is_displayable_procedure(procedure):
            continue
        score, matched_fields = _score_procedure(query, procedure)
        if score <= 0:
            continue
        results.append(
            {
                "procedure": procedure,
                "retrieval_score": score,
                "matched_fields": matched_fields,
                "source_ref": f"{procedure.get('source_uri')}#{procedure.get('sop_id')}",
            }
        )
    results.sort(
        key=lambda item: (
            -int(item["retrieval_score"]),
            str(item["procedure"].get("sop_id") or ""),
        )
    )
    return {
        "provider": "local_sop_metadata_retriever",
        "query": query,
        "top_k": top_k,
        "returned_count": min(len(results), top_k),
        "mutation_allowed": False,
        "results": results[:top_k],
    }


def _query_from_context(fixture: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    equipment = fixture.get("equipment") or {}
    evidence_payload = artifact.get("evidence_payload") or {}
    component_hypotheses = evidence_payload.get("component_hypotheses") or []
    expected = fixture.get("expected") or {}
    operation_context = fixture.get("operation_context") or {}
    event_impact = operation_context.get("event_impact") or {}
    return {
        "asset_type": str(equipment.get("asset_type") or artifact.get("asset_type") or ""),
        "failure_mode": str(
            artifact.get("predicted_failure_type")
            or expected.get("predicted_failure_type")
            or ""
        ),
        "factor_keys": sorted(
            {
                _canonical_factor_key(str(factor.get("feature")))
                for factor in artifact.get("top_factors") or []
                if factor.get("feature")
            }
        ),
        "component_ids": sorted(
            {
                str(item.get("component_id"))
                for item in component_hypotheses
                if isinstance(item, dict) and item.get("component_id")
            }
        ),
        "risk_grade": str(artifact.get("status_grade") or expected.get("risk_band") or ""),
        "criticality": str(equipment.get("criticality") or ""),
        "production_impact": str(
            operation_context.get("production_impact") or event_impact.get("impact_level") or ""
        ),
    }


def _score_procedure(query: dict[str, Any], procedure: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    matched_fields = []
    applicability = procedure.get("applicability") or {}

    if _contains(procedure.get("asset_types"), query["asset_type"]):
        score += 3
        matched_fields.append("asset_type")
    if _contains(procedure.get("failure_modes"), query["failure_mode"]):
        score += 4
        matched_fields.append("failure_mode")

    factor_matches = set(query["factor_keys"]).intersection(
        str(item) for item in procedure.get("factor_keys") or []
    )
    if factor_matches:
        score += 2 * len(factor_matches)
        matched_fields.append("factor_keys")

    component_matches = set(query["component_ids"]).intersection(
        str(item) for item in procedure.get("component_ids") or []
    )
    if component_matches:
        score += 3 * len(component_matches)
        matched_fields.append("component_ids")

    if _contains(applicability.get("risk_grades"), query["risk_grade"]):
        score += 1
        matched_fields.append("risk_grade")
    if _contains(applicability.get("criticality"), query["criticality"]):
        score += 1
        matched_fields.append("criticality")
    if _contains(applicability.get("production_impact"), query["production_impact"]):
        score += 1
        matched_fields.append("production_impact")

    # Runtime Product Results may not yet carry a component hypothesis.  In that
    # case keep retrieval conservative by requiring asset/failure-mode matches
    # and at least one factor match instead of rejecting the whole SOP corpus.
    required = {"asset_type", "failure_mode"}
    if query["component_ids"]:
        required.add("component_ids")
    if not required.issubset(set(matched_fields)):
        return 0, matched_fields
    if not query["component_ids"] and query["factor_keys"] and "factor_keys" not in matched_fields:
        return 0, matched_fields
    return score, matched_fields


def _contains(values: Any, value: str) -> bool:
    return bool(value) and value in {str(item) for item in values or []}


def _canonical_factor_key(value: str) -> str:
    """Map derived runtime feature names back to their governed sensor key.

    The V3.1 runtime model explains temporal features such as
    ``rotational_speed_rpm_6h_mean`` while SOP applicability is intentionally
    expressed against the stable source sensor ``rotational_speed_rpm``.
    Only the temporal suffixes owned by the CNC/compressor feature contract are
    removed; arbitrary feature names are left untouched.
    """
    for suffix in _TEMPORAL_FACTOR_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def _is_displayable_procedure(procedure: dict[str, Any]) -> bool:
    source_kind = str(procedure.get("source_kind") or "")
    maturity = str(procedure.get("maturity") or "")
    return (
        (source_kind == "demo_sop_fixture" and maturity == "fixture")
        or (source_kind == "site_sop" and maturity == "approved")
    )
