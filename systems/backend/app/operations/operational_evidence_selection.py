"""Deterministic evidence selection for ontology-aware operational context."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.operations.operational_context_contract import (
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    require_matching_scope,
)
from app.operations.operational_relation_resolver import RelationResolutionResult


SELECTION_POLICY_VERSION = "operational-evidence-selection-v0.1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceSelectionStrategy(StrEnum):
    FULL_CONTEXT = "S0_FULL_CONTEXT"
    DETERMINISTIC = "S1_DETERMINISTIC_SELECTION"


class EvidenceCandidate(FrozenModel):
    candidate_id: str = Field(min_length=1)
    candidate_type: str = Field(pattern="^(fact|relationship|limitation)$")
    source_ref: str = Field(min_length=1)
    source_snapshot_id: str
    source_version: str
    domain: str = Field(min_length=1)
    relation_path: tuple[str, ...] = ()
    fact_type: str = Field(min_length=1)
    role_relevance: tuple[str, ...] = ()
    priority_hint: int = 0
    freshness_state: FreshnessState
    as_of: datetime
    value_summary: str = Field(min_length=1)
    required_for_boundary: bool = False
    limitation_state: str | None = None
    eligible: bool = True
    rejected_reason: str | None = None


class EvidenceSelectionResult(FrozenModel):
    strategy: EvidenceSelectionStrategy
    policy_version: str
    selected: tuple[EvidenceCandidate, ...]
    rejected: tuple[EvidenceCandidate, ...]
    selected_source_refs: tuple[str, ...]
    selected_candidate_count: int
    full_candidate_count: int
    trace: tuple[dict[str, Any], ...]


class EvidenceSelectionMetrics(FrozenModel):
    required_evidence_recall: float
    required_limitation_preservation: float
    context_reduction: float
    full_candidate_count: int
    selected_candidate_count: int
    missing_required_evidence_ids: tuple[str, ...]
    missing_required_limitation_ids: tuple[str, ...]


def project_evidence_candidates(
    *,
    identity: OperationalRequestIdentity,
    contexts: Mapping[str, OperationalContextEnvelope],
    relation_resolution: RelationResolutionResult,
) -> tuple[EvidenceCandidate, ...]:
    """Project resolved operational context into traceable selection candidates."""

    candidates: list[EvidenceCandidate] = []
    relation_paths = _relation_paths_by_ref(relation_resolution)
    for envelope in contexts.values():
        require_matching_scope(identity, envelope)
        if envelope.status is OperationalContextStatus.AVAILABLE:
            candidates.extend(
                _fact_candidates(
                    identity=identity,
                    envelope=envelope,
                    relation_paths=relation_paths,
                )
            )
        else:
            candidates.extend(_context_limitation_candidates(identity, envelope))

    candidates.extend(_relationship_candidates(relation_resolution))
    candidates.extend(_gap_candidates(relation_resolution, contexts=contexts))
    return tuple(_dedupe_candidates(candidates))


def select_evidence_candidates(
    candidates: Iterable[EvidenceCandidate],
    *,
    strategy: EvidenceSelectionStrategy,
    role: str | None = None,
    max_candidates: int | None = None,
) -> EvidenceSelectionResult:
    """Select S0 full context or S1 deterministic subset without LLM ranking."""

    candidate_list = tuple(candidates)
    eligible = tuple(candidate for candidate in candidate_list if candidate.eligible)
    rejected = tuple(candidate for candidate in candidate_list if not candidate.eligible)
    if strategy is EvidenceSelectionStrategy.FULL_CONTEXT:
        selected = eligible
    else:
        selected = _deterministic_subset(
            eligible,
            role=role,
            max_candidates=max_candidates,
        )
        selected_ids = {candidate.candidate_id for candidate in selected}
        rejected = (
            *rejected,
            *(
                candidate.model_copy(update={"rejected_reason": "outside_selection_budget"})
                for candidate in eligible
                if candidate.candidate_id not in selected_ids
            ),
        )

    return EvidenceSelectionResult(
        strategy=strategy,
        policy_version=SELECTION_POLICY_VERSION,
        selected=tuple(selected),
        rejected=tuple(rejected),
        selected_source_refs=tuple(
            dict.fromkeys(candidate.source_ref for candidate in selected)
        ),
        selected_candidate_count=len(selected),
        full_candidate_count=len(eligible),
        trace=tuple(_trace_item(candidate) for candidate in selected),
    )


def evaluate_evidence_selection(
    *,
    full_context: EvidenceSelectionResult,
    selected: EvidenceSelectionResult,
    required_evidence_ids: set[str],
    required_limitation_ids: set[str],
) -> EvidenceSelectionMetrics:
    selected_refs = set(selected.selected_source_refs)
    selected_ids = {candidate.candidate_id for candidate in selected.selected}
    full_count = full_context.selected_candidate_count
    selected_count = selected.selected_candidate_count
    missing_evidence = tuple(sorted(required_evidence_ids - selected_refs))
    missing_limitations = tuple(sorted(required_limitation_ids - selected_ids))
    return EvidenceSelectionMetrics(
        required_evidence_recall=_ratio(
            len(required_evidence_ids) - len(missing_evidence),
            len(required_evidence_ids),
        ),
        required_limitation_preservation=_ratio(
            len(required_limitation_ids) - len(missing_limitations),
            len(required_limitation_ids),
        ),
        context_reduction=(
            0.0
            if full_count == 0
            else max(0.0, 1.0 - (selected_count / full_count))
        ),
        full_candidate_count=full_count,
        selected_candidate_count=selected_count,
        missing_required_evidence_ids=missing_evidence,
        missing_required_limitation_ids=missing_limitations,
    )


def _fact_candidates(
    *,
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
    relation_paths: Mapping[str, tuple[str, ...]],
) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    for path, value in _walk_context_records(envelope.data):
        if not isinstance(value, Mapping):
            continue
        refs = tuple(str(ref) for ref in value.get("source_refs") or [])
        if not refs:
            continue
        fact_type = _fact_type_from_path(path, fallback=envelope.owner_domain)
        for ref in refs:
            candidates.append(
                EvidenceCandidate(
                    candidate_id=f"fact:{ref}",
                    candidate_type="fact",
                    source_ref=ref,
                    source_snapshot_id=identity.evidence_snapshot_id,
                    source_version=envelope.source_version or "",
                    domain=envelope.owner_domain,
                    relation_path=relation_paths.get(ref, ()),
                    fact_type=str(fact_type),
                    role_relevance=_role_relevance(envelope.owner_domain, fact_type, value),
                    priority_hint=_priority_hint(envelope.owner_domain, fact_type, value),
                    freshness_state=envelope.freshness.state,
                    as_of=envelope.as_of,
                    value_summary=_value_summary(fact_type, value),
                    required_for_boundary=_required_for_boundary(
                        envelope.owner_domain,
                        fact_type,
                        value,
                    ),
                    eligible=_is_eligible_fact(envelope),
                    rejected_reason=(
                        None if _is_eligible_fact(envelope) else "context_not_eligible"
                    ),
                )
            )
    if envelope.data.get("quality_gate"):
        candidates.append(
            _quality_gate_candidate(identity=identity, envelope=envelope)
        )
    if envelope.data.get("readiness"):
        candidates.append(_readiness_candidate(identity=identity, envelope=envelope))
    return candidates


def _relationship_candidates(
    relation_resolution: RelationResolutionResult,
) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    for relationship in relation_resolution.relationships:
        source_ref = relationship.source_refs[0]
        candidates.append(
            EvidenceCandidate(
                candidate_id=(
                    "relationship:"
                    f"{relationship.relationship_type}:"
                    f"{relationship.source_id}->{relationship.target_id}"
                ),
                candidate_type="relationship",
                source_ref=source_ref,
                source_snapshot_id=relation_resolution.focus["evidence_snapshot_id"],
                source_version=relationship.source_version,
                domain=relationship.owner_domain,
                relation_path=(relationship.relationship_type,),
                fact_type=relationship.relationship_type,
                role_relevance=_relationship_role_relevance(
                    relationship.relationship_type
                ),
                priority_hint=_relationship_priority(relationship.relationship_type),
                freshness_state=FreshnessState.FRESH,
                as_of=datetime.fromisoformat(relationship.as_of),
                value_summary=(
                    f"{relationship.source_type}:{relationship.source_id} "
                    f"{relationship.relationship_type} "
                    f"{relationship.target_type}:{relationship.target_id}"
                ),
                required_for_boundary=relationship.state.value
                in {"conflicting", "not_connected"},
                limitation_state=(
                    relationship.state.value
                    if relationship.state.value in {"conflicting", "not_connected"}
                    else None
                ),
                eligible=True,
            )
        )
    return candidates


def _context_limitation_candidates(
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
) -> list[EvidenceCandidate]:
    limitations = envelope.limitations or (f"{envelope.status.value} context",)
    return [
        EvidenceCandidate(
            candidate_id=f"limitation:{envelope.owner_domain}:{index}",
            candidate_type="limitation",
            source_ref=(envelope.source_refs or (f"context:{envelope.owner_domain}",))[0],
            source_snapshot_id=identity.evidence_snapshot_id,
            source_version=envelope.source_version or envelope.status.value,
            domain=envelope.owner_domain,
            fact_type="context_limitation",
            role_relevance=("process_manager", "field_operator", "system_admin"),
            priority_hint=1_000,
            freshness_state=envelope.freshness.state,
            as_of=envelope.as_of,
            value_summary=str(limitation),
            required_for_boundary=True,
            limitation_state=envelope.status.value,
            eligible=True,
        )
        for index, limitation in enumerate(limitations)
    ]


def _gap_candidates(
    relation_resolution: RelationResolutionResult,
    *,
    contexts: Mapping[str, OperationalContextEnvelope],
) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    for index, gap in enumerate(relation_resolution.gaps):
        domain = str(gap.get("owner_domain") or "relation")
        envelope = contexts.get(domain)
        candidates.append(
            EvidenceCandidate(
                candidate_id=f"limitation:relation-gap:{domain}:{index}",
                candidate_type="limitation",
                source_ref=(
                    (envelope.source_refs[0] if envelope and envelope.source_refs else "")
                    or f"relation-gap:{domain}"
                ),
                source_snapshot_id=relation_resolution.focus["evidence_snapshot_id"],
                source_version=(
                    envelope.source_version
                    if envelope and envelope.source_version
                    else str(gap.get("status") or "missing")
                ),
                domain=domain,
                relation_path=("relation_gap",),
                fact_type="relation_gap",
                role_relevance=("process_manager", "system_admin"),
                priority_hint=1_000,
                freshness_state=(
                    envelope.freshness.state if envelope else FreshnessState.UNKNOWN
                ),
                as_of=(
                    envelope.as_of
                    if envelope
                    else datetime.fromisoformat(
                        relation_resolution.focus["decision_as_of"]
                    )
                ),
                value_summary=str(dict(sorted(gap.items()))),
                required_for_boundary=True,
                limitation_state=str(gap.get("status") or "missing"),
                eligible=True,
            )
        )
    return candidates


def _quality_gate_candidate(
    *,
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
) -> EvidenceCandidate:
    gate = envelope.data["quality_gate"]
    refs = _context_refs(envelope, fallback="quality_gate")
    return EvidenceCandidate(
        candidate_id=f"fact:{envelope.owner_domain}:quality_gate",
        candidate_type="fact",
        source_ref=refs[0],
        source_snapshot_id=identity.evidence_snapshot_id,
        source_version=envelope.source_version or "",
        domain=envelope.owner_domain,
        relation_path=("quality_gate",),
        fact_type="quality_gate",
        role_relevance=("process_manager", "field_operator"),
        priority_hint=950 if gate.get("state") == "blocked" else 650,
        freshness_state=envelope.freshness.state,
        as_of=envelope.as_of,
        value_summary=_value_summary("quality_gate", gate),
        required_for_boundary=gate.get("state") == "blocked",
        limitation_state="quality_blocked" if gate.get("state") == "blocked" else None,
        eligible=_is_eligible_fact(envelope),
        rejected_reason=None if _is_eligible_fact(envelope) else "context_not_eligible",
    )


def _readiness_candidate(
    *,
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
) -> EvidenceCandidate:
    readiness = envelope.data["readiness"]
    refs = _context_refs(envelope, fallback="readiness")
    blocked = readiness.get("overall_state") == "blocked"
    return EvidenceCandidate(
        candidate_id=f"fact:{envelope.owner_domain}:readiness",
        candidate_type="fact",
        source_ref=refs[0],
        source_snapshot_id=identity.evidence_snapshot_id,
        source_version=envelope.source_version or "",
        domain=envelope.owner_domain,
        relation_path=("maintenance_readiness",),
        fact_type="readiness",
        role_relevance=("process_manager", "field_operator"),
        priority_hint=930 if blocked else 720,
        freshness_state=envelope.freshness.state,
        as_of=envelope.as_of,
        value_summary=_value_summary("readiness", readiness),
        required_for_boundary=blocked,
        limitation_state="maintenance_blocked" if blocked else None,
        eligible=_is_eligible_fact(envelope),
        rejected_reason=None if _is_eligible_fact(envelope) else "context_not_eligible",
    )


def _walk_context_records(
    value: Any,
    path: tuple[str, ...] = (),
) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, Mapping):
        yield path, value
        for key, child in value.items():
            yield from _walk_context_records(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_context_records(child, (*path, str(index)))


def _fact_type_from_path(path: tuple[str, ...], *, fallback: str) -> str:
    for part in reversed(path):
        if not part.isdigit():
            return part
    return fallback


def _relation_paths_by_ref(
    relation_resolution: RelationResolutionResult,
) -> dict[str, tuple[str, ...]]:
    paths: dict[str, list[str]] = {}
    for relationship in relation_resolution.relationships:
        for ref in relationship.source_refs:
            paths.setdefault(str(ref), []).append(relationship.relationship_type)
    return {ref: tuple(dict.fromkeys(values)) for ref, values in paths.items()}


def _deterministic_subset(
    candidates: tuple[EvidenceCandidate, ...],
    *,
    role: str | None,
    max_candidates: int | None,
) -> tuple[EvidenceCandidate, ...]:
    must_include = _dedupe_by_source_ref(
        [candidate for candidate in candidates if candidate.required_for_boundary],
        role=role,
    )
    remaining = [
        candidate
        for candidate in candidates
        if candidate.candidate_id not in {item.candidate_id for item in must_include}
    ]
    ordered = sorted(
        remaining,
        key=lambda candidate: _selection_sort_key(candidate, role=role),
    )
    if max_candidates is None:
        limit = max(1, len(candidates))
    else:
        limit = max(max_candidates, len(must_include))
    return tuple([*must_include, *ordered[: max(0, limit - len(must_include))]])


def _dedupe_by_source_ref(
    candidates: list[EvidenceCandidate],
    *,
    role: str | None,
) -> list[EvidenceCandidate]:
    by_ref: dict[str, EvidenceCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: _selection_sort_key(item, role=role),
    ):
        by_ref.setdefault(candidate.source_ref, candidate)
    return list(by_ref.values())


def _selection_sort_key(
    candidate: EvidenceCandidate,
    *,
    role: str | None,
) -> tuple[int, int, str, str]:
    role_bonus = 100 if role and role in candidate.role_relevance else 0
    relation_bonus = min(len(candidate.relation_path), 5) * 10
    direct_limitation_bonus = 50 if candidate.fact_type == "context_limitation" else 0
    return (
        -(candidate.priority_hint + role_bonus + relation_bonus + direct_limitation_bonus),
        0 if candidate.candidate_type == "fact" else 1,
        candidate.domain,
        candidate.candidate_id,
    )


def _priority_hint(domain: str, fact_type: str, value: Mapping[str, Any]) -> int:
    if value.get("release_required") or value.get("quality_state") == "hold":
        return 950
    if value.get("priority") == 1:
        return 880
    if fact_type in {"production_orders", "wip", "delivery_commitments"}:
        return 840
    if fact_type in {"part_requirements", "inventory_snapshots"}:
        return 820
    if fact_type in {"maintenance_windows", "technician_candidates"}:
        return 760
    if fact_type == "alternative_resources":
        return 700
    if domain == "quality_delivery":
        return 680
    return 500


def _relationship_priority(relationship_type: str) -> int:
    if relationship_type in {"order_contains_wip", "order_commits_delivery"}:
        return 780
    if relationship_type in {"action_requires_part", "wip_quality_state_reported_by_lot"}:
        return 760
    return 520


def _role_relevance(
    domain: str,
    fact_type: str,
    value: Mapping[str, Any],
) -> tuple[str, ...]:
    if domain in {"production", "quality_delivery"}:
        return ("process_manager",)
    if domain == "maintenance_readiness":
        return ("field_operator", "process_manager")
    if value.get("source_refs"):
        return ("system_admin",)
    return ()


def _relationship_role_relevance(relationship_type: str) -> tuple[str, ...]:
    if relationship_type in {
        "operation_assigned_to_order",
        "order_contains_wip",
        "order_commits_delivery",
        "wip_quality_state_reported_by_lot",
    }:
        return ("process_manager",)
    if relationship_type in {
        "asset_has_maintenance_window",
        "action_requires_part",
        "part_requirement_accepts_part",
        "required_skill_has_technician_candidate",
    }:
        return ("field_operator", "process_manager")
    return ("system_admin",)


def _required_for_boundary(
    domain: str,
    fact_type: str,
    value: Mapping[str, Any],
) -> bool:
    return bool(
        value.get("release_required")
        or value.get("quality_state") == "hold"
        or value.get("active_work_order_conflict")
        or value.get("relationship_state") in {"not_connected", "conflicting"}
    )


def _is_eligible_fact(envelope: OperationalContextEnvelope) -> bool:
    return (
        envelope.status is OperationalContextStatus.AVAILABLE
        and envelope.freshness.state is FreshnessState.FRESH
        and envelope.source_version is not None
    )


def _context_refs(
    envelope: OperationalContextEnvelope,
    *,
    fallback: str,
) -> tuple[str, ...]:
    if envelope.source_refs:
        return envelope.source_refs
    return (f"context:{envelope.owner_domain}:{fallback}",)


def _value_summary(fact_type: str, value: Mapping[str, Any]) -> str:
    identifiers = [
        key
        for key in (
            "order_id",
            "wip_id",
            "lot_id",
            "delivery_id",
            "window_id",
            "part_requirement_id",
            "part_id",
            "technician_id",
            "resource_id",
            "state",
            "overall_state",
        )
        if value.get(key) is not None
    ]
    if identifiers:
        pairs = ", ".join(f"{key}={value[key]}" for key in identifiers[:3])
        return f"{fact_type}: {pairs}"
    return f"{fact_type}: {dict(value)}"


def _dedupe_candidates(
    candidates: list[EvidenceCandidate],
) -> list[EvidenceCandidate]:
    seen: set[str] = set()
    result: list[EvidenceCandidate] = []
    for candidate in candidates:
        if candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        result.append(candidate)
    return result


def _trace_item(candidate: EvidenceCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "source_ref": candidate.source_ref,
        "source_version": candidate.source_version,
        "domain": candidate.domain,
        "fact_type": candidate.fact_type,
        "relation_path": list(candidate.relation_path),
        "freshness_state": candidate.freshness_state.value,
        "as_of": candidate.as_of.isoformat(),
        "required_for_boundary": candidate.required_for_boundary,
        "limitation_state": candidate.limitation_state,
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
