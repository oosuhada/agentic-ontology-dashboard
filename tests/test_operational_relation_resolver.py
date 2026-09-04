import json
from datetime import datetime, timezone
from pathlib import Path

from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_relation_resolver import (
    ResolvedRelationshipState,
    resolve_operational_relations,
)


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


def contexts() -> dict:
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


def edge_keys(result) -> set[tuple[str, str, str]]:
    return {
        (item.relationship_type, item.source_id, item.target_id)
        for item in result.relationships
    }


def test_resolver_builds_source_backed_operational_paths() -> None:
    result = resolve_operational_relations(
        identity=IDENTITY,
        contexts=contexts(),
    )
    edges = edge_keys(result)

    assert (
        "operation_assigned_to_order",
        "OP-MILL-20",
        "DEMO-PO-001",
    ) in edges
    assert (
        "order_contains_wip",
        "DEMO-PO-001",
        "DEMO-WIP-001",
    ) in edges
    assert (
        "wip_quality_state_reported_by_lot",
        "DEMO-WIP-001",
        "DEMO-LOT-015",
    ) in edges
    assert (
        "order_commits_delivery",
        "DEMO-PO-001",
        "DEMO-DELIVERY-009",
    ) in edges
    assert (
        "operation_has_alternative_resource",
        "OP-MILL-20",
        "CNC-03",
    ) in edges
    assert result.gaps == ()
    assert result.conflicts == ()


def test_part_relationship_stays_on_action_candidate_lifecycle() -> None:
    result = resolve_operational_relations(
        identity=IDENTITY,
        contexts=contexts(),
    )
    action_edge = next(
        item
        for item in result.relationships
        if item.relationship_type == "action_requires_part"
    )

    assert action_edge.source_type == "maintenance_action_candidate"
    assert action_edge.source_id == "ACTION-CANDIDATE-GS-004-TOOL"
    assert action_edge.target_id == "PREQ-001"
    assert action_edge.state is ResolvedRelationshipState.ASSUMED_DEMO
    assert not any(
        item.source_type == "maintenance_action"
        for item in result.relationships
    )


def test_cross_domain_unknown_wip_is_reported_not_joined() -> None:
    supplied = contexts()
    quality = supplied["quality_delivery"]
    data = json.loads(json.dumps(quality.data))
    data["quality_lots"][0]["wip_id"] = "UNKNOWN-WIP"
    supplied["quality_delivery"] = quality.model_copy(update={"data": data})

    result = resolve_operational_relations(
        identity=IDENTITY,
        contexts=supplied,
    )

    assert any(
        gap.get("missing_wip_id") == "UNKNOWN-WIP"
        for gap in result.gaps
    )
    assert (
        "wip_quality_state_reported_by_lot",
        "UNKNOWN-WIP",
        "DEMO-LOT-014",
    ) not in edge_keys(result)


def test_relation_gate_keeps_graph_runtime_deferred() -> None:
    gate = json.loads(
        (
            ROOT / "tests" / "eval" / "operational_relation_resolver_gate.json"
        ).read_text(encoding="utf-8")
    )
    available_relationships = {
        item.relationship_type
        for item in resolve_operational_relations(
            identity=IDENTITY,
            contexts=contexts(),
        ).relationships
    }

    for question in gate["questions"]:
        assert set(question["required_relationships"]).issubset(
            available_relationships
        )
    assert gate["current_decision"] == "keep_typed_rdb_resolver"
    assert gate["production_kg"] is False
    assert gate["production_langgraph"] is False


def test_every_relationship_retains_version_as_of_and_source_refs() -> None:
    result = resolve_operational_relations(
        identity=IDENTITY,
        contexts=contexts(),
    )

    assert result.relationships
    assert all(item.source_version for item in result.relationships)
    assert all(item.as_of == IDENTITY.decision_as_of.isoformat() for item in result.relationships)
    assert all(item.source_refs for item in result.relationships)
