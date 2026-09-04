import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.operations.operational_context_contract import (
    OperationalContextStatus,
    OperationalRequestIdentity,
    require_matching_scope,
)
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)


ROOT = Path(__file__).resolve().parents[1]
QUALITY_FIXTURE = json.loads(
    (
        ROOT
        / "data"
        / "fixtures"
        / "operation_context"
        / "quality-delivery-context-v1.json"
    ).read_text(encoding="utf-8")
)
MAINTENANCE_FIXTURE = json.loads(
    (
        ROOT
        / "data"
        / "fixtures"
        / "operation_context"
        / "maintenance-readiness-context-v1.json"
    ).read_text(encoding="utf-8")
)
DECISION_FIXTURE = json.loads(
    (
        ROOT
        / "data"
        / "fixtures"
        / "operation_context"
        / "operational-decision-context-v1.json"
    ).read_text(encoding="utf-8")
)
FIXTURE = json.loads(
    (
        ROOT
        / "data"
        / "fixtures"
        / "operation_context"
        / "production-planning-context-v1.json"
    ).read_text(encoding="utf-8")
)


def identity(
    *,
    asset_id: str = "CNC-S04-L02-03",
    as_of: datetime = datetime(2026, 8, 1, 1, tzinfo=timezone.utc),
) -> OperationalRequestIdentity:
    return OperationalRequestIdentity(
        organization_id="ORG-001",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        asset_id=asset_id,
        evidence_snapshot_id="ARTIFACT-GS-004",
        decision_as_of=as_of,
    )


def port(max_age_seconds: int = 86_400) -> FixtureProductionContextReadPort:
    return FixtureProductionContextReadPort(
        context=FIXTURE,
        organization_id="ORG-001",
        workspace_id="manufacturing-demo",
        source_ref=(
            "data/fixtures/operation_context/"
            "production-planning-context-v1.json"
        ),
        max_age_seconds=max_age_seconds,
    )


def test_fixture_port_returns_versioned_synthetic_context() -> None:
    result = port().lookup(
        identity=identity(),
        retrieved_at=datetime(2026, 8, 1, 2, tzinfo=timezone.utc),
    )

    require_matching_scope(identity(), result)
    assert result.status is OperationalContextStatus.AVAILABLE
    assert result.source_version == "OPS-SNAPSHOT-2026-08-01-A-B"
    assert result.data["source_type"] == "capacity_model"
    assert result.data["event_impact"]["event_id"] == "EVT-GS-004"


def test_fixture_port_does_not_invent_order_wip_or_alternative_records() -> None:
    result = port().lookup(
        identity=identity(),
        retrieved_at=datetime(2026, 8, 1, 2, tzinfo=timezone.utc),
    )

    assert result.data["production_orders"] == []
    assert result.data["wip"] == []
    assert result.data["alternative_resources"] == []
    assert result.data["availability"] == {
        "production_orders": "not_connected",
        "wip": "not_connected",
        "alternative_resources": "not_connected",
    }


def test_out_of_window_context_is_stale_and_carries_no_domain_data() -> None:
    result = port().lookup(
        identity=identity(
            as_of=datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
        ),
        retrieved_at=datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc),
    )

    assert result.status is OperationalContextStatus.STALE
    assert result.data == {}
    assert any("outside the fixture validity window" in item for item in result.limitations)


def test_freshness_expiry_is_stale_even_inside_fixture_window() -> None:
    result = port(max_age_seconds=60).lookup(
        identity=identity(),
        retrieved_at=datetime(2026, 8, 1, 2, tzinfo=timezone.utc),
    )

    assert result.status is OperationalContextStatus.STALE
    assert result.data == {}
    assert any("freshness policy" in item for item in result.limitations)


def test_missing_asset_impact_remains_explicit_without_fake_zero() -> None:
    result = port().lookup(
        identity=identity(asset_id="CNC-UNKNOWN"),
        retrieved_at=datetime(2026, 8, 1, 2, tzinfo=timezone.utc),
    )

    assert result.status is OperationalContextStatus.AVAILABLE
    assert result.data["event_impact"] is None
    assert any("No event impact" in item for item in result.limitations)


def decision_port() -> FixtureProductionDecisionContextReadPort:
    return FixtureProductionDecisionContextReadPort(
        context=DECISION_FIXTURE,
        source_ref=(
            "data/fixtures/operation_context/"
            "operational-decision-context-v1.json"
        ),
    )


def test_decision_port_links_order_wip_and_alternative_capacity() -> None:
    requested = identity(
        as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
    )
    result = decision_port().lookup(
        identity=requested,
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    require_matching_scope(requested, result)
    assert result.status is OperationalContextStatus.AVAILABLE
    assert result.source_version == "OPS-DECISION-SNAPSHOT-2026-09-02-01"
    assert result.data["source_classification"] == "synthetic_demo_context"
    assert result.data["production_orders"][0]["order_id"] == "DEMO-PO-001"
    assert result.data["wip"][0]["quantity"] == 200
    assert result.data["wip"][0]["lot_ids"] == [
        "DEMO-LOT-014",
        "DEMO-LOT-015",
    ]
    assert (
        result.data["alternative_resources"][0]["net_transferable_units"]
        == 50
    )


def test_decision_port_filters_context_by_requested_asset() -> None:
    requested = identity(
        asset_id="CNC-UNKNOWN",
        as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
    )
    result = decision_port().lookup(
        identity=requested,
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    assert result.data["production_orders"] == []
    assert result.data["wip"] == []
    assert result.data["alternative_resources"] == []
    assert any("No production order" in item for item in result.limitations)


def test_decision_port_rejects_broken_wip_relationship() -> None:
    broken = json.loads(json.dumps(DECISION_FIXTURE))
    broken["wip"][0]["order_id"] = "UNKNOWN"
    adapter = FixtureProductionDecisionContextReadPort(
        context=broken,
        source_ref="broken",
    )

    with pytest.raises(ValueError, match="references unknown order"):
        adapter.lookup(
            identity=identity(
                as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
            ),
            retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        )


def maintenance_port() -> FixtureMaintenanceReadinessContextReadPort:
    return FixtureMaintenanceReadinessContextReadPort(
        context=MAINTENANCE_FIXTURE,
        source_ref=(
            "data/fixtures/operation_context/"
            "maintenance-readiness-context-v1.json"
        ),
    )


def test_maintenance_readiness_links_action_part_inventory_and_skill() -> None:
    requested = identity(
        as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
    )
    result = maintenance_port().lookup(
        identity=requested,
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    require_matching_scope(requested, result)
    assert result.status is OperationalContextStatus.AVAILABLE
    requirement = result.data["part_requirements"][0]
    assert requirement["action_candidate_id"] == (
        "ACTION-CANDIDATE-GS-004-TOOL"
    )
    assert requirement["acceptable_part_ids"] == ["PART-001", "PART-002"]
    assert result.data["inventory_snapshots"][0]["on_hand_quantity"] == 2
    assert result.data["inventory_snapshots"][0]["reserved_quantity"] == 2
    assert result.data["inventory_snapshots"][0]["available_quantity"] == 0
    assert result.data["readiness"]["overall_state"] == "blocked"
    assert result.data["readiness"]["blockers"] == ["part_inventory"]


def test_maintenance_readiness_does_not_invent_execution_records() -> None:
    result = maintenance_port().lookup(
        identity=identity(
            as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
        ),
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    records = result.data["execution_records"]
    assert all(value == [] for value in records.values())
    assert result.data["readiness"]["assignment_state"] == "candidate_only"
    assert result.data["readiness"]["execution_state"] == "not_started"


def test_maintenance_readiness_rejects_invalid_available_quantity() -> None:
    broken = json.loads(json.dumps(MAINTENANCE_FIXTURE))
    broken["inventory_snapshots"][0]["available_quantity"] = 2
    adapter = FixtureMaintenanceReadinessContextReadPort(
        context=broken,
        source_ref="broken",
    )

    with pytest.raises(ValueError, match="on-hand minus reserved"):
        adapter.lookup(
            identity=identity(
                as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
            ),
            retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        )


def test_maintenance_readiness_for_other_asset_is_unavailable() -> None:
    result = maintenance_port().lookup(
        identity=identity(
            asset_id="CNC-UNKNOWN",
            as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
        ),
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    assert result.status is OperationalContextStatus.UNAVAILABLE
    assert result.data == {}
    assert result.source_version is None


def quality_port() -> FixtureQualityDeliveryContextReadPort:
    return FixtureQualityDeliveryContextReadPort(
        context=QUALITY_FIXTURE,
        source_ref=(
            "data/fixtures/operation_context/"
            "quality-delivery-context-v1.json"
        ),
    )


def test_quality_delivery_links_lot_wip_order_and_delivery() -> None:
    requested = identity(
        as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
    )
    result = quality_port().lookup(
        identity=requested,
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    assert result.status is OperationalContextStatus.AVAILABLE
    lots = result.data["quality_lots"]
    assert {item["lot_id"] for item in lots} == {
        "DEMO-LOT-014",
        "DEMO-LOT-015",
    }
    assert {item["wip_id"] for item in lots} == {"DEMO-WIP-001"}
    assert result.data["delivery_commitments"][0]["order_id"] == "DEMO-PO-001"


def test_quality_hold_is_an_explicit_calculation_blocker() -> None:
    result = quality_port().lookup(
        identity=identity(
            as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
        ),
        retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
    )

    assert result.data["quality_gate"] == {
        "state": "blocked",
        "held_lot_ids": ["DEMO-LOT-015"],
        "blocked_quantity": 80,
    }


def test_quality_delivery_rejects_unknown_order_relationship() -> None:
    broken = json.loads(json.dumps(QUALITY_FIXTURE))
    broken["delivery_commitments"][0]["order_id"] = "UNKNOWN"
    adapter = FixtureQualityDeliveryContextReadPort(
        context=broken,
        source_ref="broken",
    )

    with pytest.raises(ValueError, match="references unknown order"):
        adapter.lookup(
            identity=identity(
                as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
            ),
            retrieved_at=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
        )


def test_configured_scope_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="configured scope mismatch"):
        port().lookup(
            identity=identity().model_copy(
                update={"workspace_id": "other-workspace"}
            ),
            retrieved_at=datetime(2026, 8, 1, 2, tzinfo=timezone.utc),
        )
