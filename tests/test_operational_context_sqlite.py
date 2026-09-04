import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.operations.operational_context_contract import (
    OperationalContextStatus,
    OperationalRequestIdentity,
)
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.infra.db.operational_context_sqlite import (
    OPERATIONAL_CONTEXT_SNAPSHOT_DDL,
    SqliteOperationalContextReadPort,
)
from app.operations.operational_decision_agent import (
    AgentTerminalState,
    BoundedOperationalDecisionAgent,
    OperationalAgentIntent,
    OperationalAgentRequest,
)
from app.operations.operational_impact_simulation import (
    ImpactOption,
    ImpactSimulationAssumptions,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "data" / "fixtures" / "operation_context"
RETRIEVED_AT = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)
IDENTITY = OperationalRequestIdentity(
    organization_id="ORG-001",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
)


def load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(OPERATIONAL_CONTEXT_SNAPSHOT_DDL)


def insert_snapshot(
    path: Path,
    *,
    owner_domain: str,
    source_version: str,
    source_updated_at: datetime,
    payload: dict,
    organization_id: str = "ORG-001",
    project_id: str = "manufacturing-demo-project",
    workspace_id: str = "manufacturing-demo",
    asset_id: str = "CNC-S04-L02-03",
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO operational_context_snapshot (
                owner_domain, organization_id, project_id, workspace_id,
                asset_id, source_version, source_updated_at, valid_from,
                valid_to, source_ref, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_domain,
                organization_id,
                project_id,
                workspace_id,
                asset_id,
                source_version,
                source_updated_at.isoformat(),
                datetime(2026, 9, 1, tzinfo=timezone.utc).isoformat(),
                datetime(2026, 9, 4, tzinfo=timezone.utc).isoformat(),
                f"sqlite:operational_context_snapshot/{source_version}",
                json.dumps(payload),
            ),
        )


def test_sqlite_port_reads_latest_scope_bound_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "operational.db"
    create_database(database)
    insert_snapshot(
        database,
        owner_domain="production",
        source_version="plan-16",
        source_updated_at=RETRIEVED_AT - timedelta(hours=2),
        payload={"marker": "older"},
    )
    insert_snapshot(
        database,
        owner_domain="production",
        source_version="plan-17",
        source_updated_at=RETRIEVED_AT - timedelta(minutes=1),
        payload={"marker": "latest"},
    )
    insert_snapshot(
        database,
        owner_domain="production",
        source_version="other-tenant",
        source_updated_at=RETRIEVED_AT,
        payload={"marker": "forbidden"},
        organization_id="OTHER",
    )

    result = SqliteOperationalContextReadPort(
        database_path=database,
        owner_domain="production",
        freshness_policy_version="production-db-v1",
        max_age_seconds=3600,
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    assert result.status is OperationalContextStatus.AVAILABLE
    assert result.source_version == "plan-17"
    assert result.data == {"marker": "latest"}
    assert "forbidden" not in json.dumps(result.model_dump(mode="json"))


def test_sqlite_port_withholds_stale_values_and_does_not_invent_zero(
    tmp_path: Path,
) -> None:
    database = tmp_path / "operational.db"
    create_database(database)
    insert_snapshot(
        database,
        owner_domain="production",
        source_version="plan-stale",
        source_updated_at=RETRIEVED_AT - timedelta(hours=4),
        payload={"wip": [{"quantity": 200}]},
    )

    result = SqliteOperationalContextReadPort(
        database_path=database,
        owner_domain="production",
        freshness_policy_version="production-db-v1",
        max_age_seconds=60,
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    assert result.status is OperationalContextStatus.STALE
    assert result.data == {}
    assert result.source_version == "plan-stale"


def test_sqlite_port_returns_not_connected_for_missing_scope(tmp_path: Path) -> None:
    database = tmp_path / "operational.db"
    create_database(database)

    result = SqliteOperationalContextReadPort(
        database_path=database,
        owner_domain="inventory",
        freshness_policy_version="inventory-db-v1",
        max_age_seconds=60,
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    assert result.status is OperationalContextStatus.NOT_CONNECTED
    assert result.data == {}
    assert result.source_version is None


def test_bounded_agent_runs_against_isolated_sqlite_snapshots(
    tmp_path: Path,
) -> None:
    database = tmp_path / "operational.db"
    create_database(database)
    maintenance_fixture = load("maintenance-readiness-context-v1.json")
    maintenance_fixture["inventory_snapshots"][0]["reserved_quantity"] = 0
    maintenance_fixture["inventory_snapshots"][0]["available_quantity"] = 2
    quality_fixture = load("quality-delivery-context-v1.json")
    quality_fixture["quality_lots"][1]["quality_state"] = "released"
    quality_fixture["quality_lots"][1]["release_required"] = False
    fixture_ports = {
        "production": FixtureProductionDecisionContextReadPort(
            context=load("operational-decision-context-v1.json"),
            source_ref="fixture:production",
        ),
        "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
            context=maintenance_fixture,
            source_ref="fixture:maintenance",
        ),
        "quality_delivery": FixtureQualityDeliveryContextReadPort(
            context=quality_fixture,
            source_ref="fixture:quality",
        ),
    }
    for domain, port in fixture_ports.items():
        envelope = port.lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)
        insert_snapshot(
            database,
            owner_domain=domain,
            source_version=f"db-{domain}-1",
            source_updated_at=RETRIEVED_AT - timedelta(seconds=10),
            payload=envelope.data,
        )

    database_ports = {
        domain: SqliteOperationalContextReadPort(
            database_path=database,
            owner_domain=domain,
            freshness_policy_version=f"{domain}-db-v1",
            max_age_seconds=3600,
        )
        for domain in fixture_ports
    }
    assumptions = ImpactSimulationAssumptions(
        policy_version="operational-impact-demo-v1",
        primary_capacity_units={
            ImpactOption.STOP_NOW: 0,
            ImpactOption.PLANNED_MAINTENANCE: 120,
            ImpactOption.CONTINUE_OPERATION: 200,
        },
        alternative_capacity_allowed={
            ImpactOption.STOP_NOW: True,
            ImpactOption.PLANNED_MAINTENANCE: True,
            ImpactOption.CONTINUE_OPERATION: False,
        },
        source_refs=("policy:operational-impact-demo-v1",),
    )
    request = OperationalAgentRequest(
        identity=IDENTITY,
        actor_role="process_manager",
        intent=OperationalAgentIntent.MAINTENANCE_TIMING_DECISION,
        risk_status="critical",
    )

    result = BoundedOperationalDecisionAgent(
        ports=database_ports,
        impact_assumptions=assumptions,
    ).run(
        request=request,
        retrieved_at=RETRIEVED_AT,
        validated_at=RETRIEVED_AT + timedelta(seconds=3),
    )

    assert result.terminal_state is AgentTerminalState.COMPLETE
    assert result.context_version_set == {
        "maintenance_readiness": "db-maintenance_readiness-1",
        "production": "db-production-1",
        "quality_delivery": "db-quality_delivery-1",
    }
    assert result.impact_simulation is not None
    assert result.temporal_validation["valid"] is True
