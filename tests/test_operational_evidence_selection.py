import json
from datetime import datetime, timezone
from pathlib import Path

from app.dependencies import build_manufacturing_service
from app.operations.operational_context_contract import (
    FreshnessMetadata,
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
)
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_evidence_selection import (
    EvidenceSelectionStrategy,
    evaluate_evidence_selection,
    project_evidence_candidates,
    select_evidence_candidates,
)
from app.operations.operational_relation_resolver import resolve_operational_relations


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "data" / "fixtures" / "operation_context"
IDENTITY = OperationalRequestIdentity(
    organization_id="ORG-001",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
)
RETRIEVED_AT = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)


def load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def contexts() -> dict[str, OperationalContextEnvelope]:
    return {
        "production": FixtureProductionDecisionContextReadPort(
            context=load("operational-decision-context-v1.json"),
            source_ref="fixture:production",
        ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT),
        "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
            context=load("maintenance-readiness-context-v1.json"),
            source_ref="fixture:maintenance",
        ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT),
        "quality_delivery": FixtureQualityDeliveryContextReadPort(
            context=load("quality-delivery-context-v1.json"),
            source_ref="fixture:quality",
        ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT),
    }


def test_projects_relation_aware_candidates_with_complete_lineage() -> None:
    supplied = contexts()
    relations = resolve_operational_relations(identity=IDENTITY, contexts=supplied)

    candidates = project_evidence_candidates(
        identity=IDENTITY,
        contexts=supplied,
        relation_resolution=relations,
    )

    assert candidates
    assert all(candidate.source_ref for candidate in candidates)
    assert all(candidate.source_version for candidate in candidates)
    assert all(candidate.as_of == IDENTITY.decision_as_of for candidate in candidates)
    assert any(
        "order_contains_wip" in candidate.relation_path
        and candidate.source_ref == "operational-decision-context-demo-v1#/wip/0"
        for candidate in candidates
    )
    assert any(
        candidate.domain == "quality_delivery"
        and candidate.fact_type == "quality_gate"
        and candidate.required_for_boundary
        for candidate in candidates
    )


def test_deterministic_selection_preserves_required_evidence_and_reduces_context() -> None:
    supplied = contexts()
    relations = resolve_operational_relations(identity=IDENTITY, contexts=supplied)
    candidates = project_evidence_candidates(
        identity=IDENTITY,
        contexts=supplied,
        relation_resolution=relations,
    )
    required = {
        "operational-decision-context-demo-v1#/production_orders/0",
        "operational-decision-context-demo-v1#/wip/0",
        "maintenance-readiness-context-demo-v1#/part_requirements/0",
        "quality-delivery-context-demo-v1#/quality_lots/1",
        "quality-delivery-context-demo-v1#/delivery_commitments/0",
    }

    full = select_evidence_candidates(
        candidates,
        strategy=EvidenceSelectionStrategy.FULL_CONTEXT,
    )
    selected = select_evidence_candidates(
        candidates,
        strategy=EvidenceSelectionStrategy.DETERMINISTIC,
        role="process_manager",
        max_candidates=8,
    )
    metrics = evaluate_evidence_selection(
        full_context=full,
        selected=selected,
        required_evidence_ids=required,
        required_limitation_ids=set(),
    )

    assert metrics.required_evidence_recall == 1.0
    assert metrics.selected_candidate_count < metrics.full_candidate_count
    assert metrics.context_reduction > 0
    assert not metrics.missing_required_evidence_ids


def test_stale_context_becomes_limitation_not_normal_fact() -> None:
    supplied = contexts()
    stale = supplied["production"].model_copy(
        update={
            "status": OperationalContextStatus.STALE,
            "source_updated_at": None,
            "freshness": FreshnessMetadata(
                policy_version="production-decision-fixture-freshness-v1",
                max_age_seconds=0,
                state=FreshnessState.STALE,
            ),
            "data": {},
            "limitations": ("Production context exceeded its freshness policy.",),
        }
    )
    supplied["production"] = stale
    relations = resolve_operational_relations(identity=IDENTITY, contexts=supplied)

    candidates = project_evidence_candidates(
        identity=IDENTITY,
        contexts=supplied,
        relation_resolution=relations,
    )

    assert not any(
        candidate.domain == "production"
        and candidate.candidate_type == "fact"
        for candidate in candidates
    )
    limitation = next(
        candidate
        for candidate in candidates
        if candidate.domain == "production"
        and candidate.candidate_type == "limitation"
    )
    assert limitation.required_for_boundary
    selected = select_evidence_candidates(
        candidates,
        strategy=EvidenceSelectionStrategy.DETERMINISTIC,
        max_candidates=1,
    )
    assert limitation.candidate_id in {
        candidate.candidate_id for candidate in selected.selected
    }


def test_service_exposes_s0_s1_selection_trace(tmp_path: Path) -> None:
    service = build_manufacturing_service(
        tmp_path / "selection-service.db",
        root=ROOT,
    )

    result = service.agent_review_evidence_selection(
        "CNC-S04-L02-03",
        decision_as_of=IDENTITY.decision_as_of,
        retrieved_at=RETRIEVED_AT,
        required_evidence_ids={
            "operational-decision-context-demo-v1#/production_orders/0",
            "operational-decision-context-demo-v1#/wip/0",
            "quality-delivery-context-demo-v1#/quality_lots/1",
        },
    )

    assert result["schema_version"] == "agent-review-evidence-selection-v1.0"
    assert result["mutation_allowed"] is False
    assert result["strategies"]["S0"]["strategy"] == "S0_FULL_CONTEXT"
    assert result["strategies"]["S1"]["strategy"] == "S1_DETERMINISTIC_SELECTION"
    assert result["metrics"]["required_evidence_recall"] == 1.0
    assert result["metrics"]["context_reduction"] > 0
    assert result["relation_resolution"]["relationships"]
