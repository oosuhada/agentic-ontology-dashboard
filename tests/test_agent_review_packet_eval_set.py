from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.operations.agent_review_summary import (
    FORBIDDEN_SUMMARY_CLAIMS,
    compose_deterministic_agent_review_summary,
    validate_agent_review_summary_contract,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "agent_review_packets" / "manifest.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_packet(case: dict) -> dict:
    return json.loads((ROOT / case["fixture_path"]).read_text(encoding="utf-8"))


def test_agent_review_eval_manifest_defines_minimum_release_gate() -> None:
    manifest = _load_manifest()

    assert manifest["eval_set_id"] == "agent-review-packet-gold-v1"
    assert manifest["purpose"] == "pre_llm_release_gate"
    assert manifest["packet_schema_version"] == "agent-review-packet-v1.0"
    assert manifest["summary_schema_version"] == "agent-review-summary-v1.0"
    assert manifest["case_selection_policy"]["minimum_cases"] == 3
    assert len(manifest["cases"]) == 3
    assert len({case["scenario_id"] for case in manifest["cases"]}) == 3


def test_agent_review_eval_manifest_required_coverage_is_satisfied() -> None:
    manifest = _load_manifest()
    declared = {
        coverage for case in manifest["cases"] for coverage in case.get("covers", [])
    }

    assert set(manifest["required_coverage"]).issubset(declared)


def test_agent_review_eval_manifest_cases_match_fixture_facts() -> None:
    manifest = _load_manifest()

    for case in manifest["cases"]:
        packet = _load_packet(case)
        assert packet["asset_id"] == case["asset_id"]
        assert packet["schema_version"] == manifest["packet_schema_version"]

        for coverage in case["covers"]:
            assert COVERAGE_CHECKS[coverage](packet), case["scenario_id"] + ":" + coverage


def test_agent_review_eval_manifest_forbidden_claims_match_validator() -> None:
    manifest = _load_manifest()

    assert set(manifest["forbidden_summary_claims"]) == set(FORBIDDEN_SUMMARY_CLAIMS)

    rendered_review_drafts = "\n".join(
        json.dumps(_load_packet(case)["review_draft"], ensure_ascii=False)
        for case in manifest["cases"]
    )
    for claim in manifest["forbidden_summary_claims"]:
        assert claim not in rendered_review_drafts


def _has_location(packet: dict) -> bool:
    return any(target.get("location_label") for target in packet["inspection_targets"])


def _has_factor_bundle_target(packet: dict) -> bool:
    return any(
        len([ref for ref in target.get("basis_refs", []) if ref.startswith("factor.")]) >= 3
        for target in packet["inspection_targets"]
    )


def _is_data_quality_hold(packet: dict) -> bool:
    return (
        packet["risk_summary"]["status_grade"] is None
        and packet["risk_summary"]["failure_probability"] is None
        and packet["review_priority"] is None
        and packet["review_draft"]["priority_label"] == "미확정"
        and "데이터 품질 보류" in packet["review_draft"]["summary"]
        and "SOP 근거" not in packet["review_draft"]["summary"]
        and bool(packet["evidence_gaps"])
    )


def _summary_structured_grounded(packet: dict) -> bool:
    summary = compose_deterministic_agent_review_summary(packet)
    return (
        validate_agent_review_summary_contract(summary, packet=packet) == []
        and summary["asset_id"] == packet["asset_id"]
        and summary["generated_at"] == packet["generated_at"]
        and summary["packet_schema_version"] == packet["schema_version"]
        and set(summary["source_refs"]).issubset(set(packet["source_refs"]))
    )


def _summary_natural_language_grounded(packet: dict) -> bool:
    summary = compose_deterministic_agent_review_summary(packet)
    return (
        validate_agent_review_summary_contract(summary, packet=packet) == []
        and summary["history_summary"] == packet["review_draft"]["history_summary"]
        and summary["boundary_note"] == packet["review_draft"]["boundary_note"]
        and set(packet["limitations"]).issubset(set(summary["limitations"]))
    )


def _summary_evidence_gaps_complete(packet: dict) -> bool:
    summary = compose_deterministic_agent_review_summary(packet)
    packet_gaps = {
        (gap["field"], gap["reason"], gap["owner_domain"])
        for gap in packet["evidence_gaps"]
    }
    summary_gaps = {
        (gap["field"], gap["reason"], gap["owner_domain"])
        for gap in summary["evidence_gaps"]
    }
    return validate_agent_review_summary_contract(summary, packet=packet) == [] and summary_gaps == packet_gaps


def _inspection_focus_complete(packet: dict) -> bool:
    summary = compose_deterministic_agent_review_summary(packet)
    return len(summary["inspection_focus"]) == len(packet["inspection_targets"])


def _target_source_refs_grounded(packet: dict) -> bool:
    packet_refs = set(packet["source_refs"])
    return all(
        target.get("source_ref") in packet_refs
        and (
            not target.get("location_source_ref")
            or target.get("location_source_ref") in packet_refs
        )
        for target in packet["inspection_targets"]
    )


def _has_readonly_closed_loop_boundary(packet: dict) -> bool:
    boundary = packet["closed_loop_boundary"]
    return (
        boundary["mutation_allowed"] is False
        and "auto_approve" in boundary["forbidden_actions"]
        and "create_work_order" in boundary["forbidden_actions"]
    )


def _has_readonly_available_action(packet: dict) -> bool:
    return (
        bool(packet["closed_loop_boundary"]["available_action_ids"])
        and packet["closed_loop_boundary"]["mutation_allowed"] is False
    )


COVERAGE_CHECKS: dict[str, Callable[[dict], bool]] = {
    "sop_guidance_present": lambda packet: bool(packet["sop_guidance"]),
    "sop_guidance_absent": lambda packet: packet["sop_guidance"] == [],
    "field_location_present": _has_location,
    "history_review_items_present": lambda packet: bool(packet["history_review_items"]),
    "factor_bundle_to_single_inspection_target": lambda packet: len(
        packet["inspection_targets"]
    )
    == 1
    and _has_factor_bundle_target(packet),
    "data_quality_hold": _is_data_quality_hold,
    "data_quality_hold_review_draft": _is_data_quality_hold,
    "summary_structured_grounding": _summary_structured_grounded,
    "summary_natural_language_grounding": _summary_natural_language_grounded,
    "evidence_gap_completeness": _summary_evidence_gaps_complete,
    "inspection_focus_completeness": _inspection_focus_complete,
    "target_source_refs_grounded": _target_source_refs_grounded,
    "closed_loop_available_action_readonly": _has_readonly_available_action,
    "closed_loop_boundary_readonly": _has_readonly_closed_loop_boundary,
    "no_inspection_target": lambda packet: packet["inspection_targets"] == [],
}
