"""Typed domain-pack registry used by the shared platform runtime."""

from __future__ import annotations

from .models import (
    BoundedContextDefinition,
    DomainPackDefinition,
    DomainVocabulary,
)


GENERIC_OPERATIONS = DomainPackDefinition(
    code="generic-operations",
    version="1.0.0",
    display_name="Generic Operations",
    description="Domain-neutral Object, Event, Action and Evidence semantics for new vertical packs.",
    status="active",
    namespace="ontology_dashboard.domain_packs.generic_operations",
    vocabulary=DomainVocabulary(
        object_label="Object",
        object_plural_label="Objects",
        event_label="Event",
        action_label="Action",
        risk_label="Signal",
    ),
    bounded_contexts=(
        BoundedContextDefinition(
            id="object-model",
            display_name="Object Model",
            kind="core",
            owns=("ObjectType", "Object", "LinkType", "Link"),
            publishes=("object.changed",),
        ),
        BoundedContextDefinition(
            id="decision-workflow",
            display_name="Decision Workflow",
            kind="supporting",
            owns=("ActionType", "ActionInvocation", "Approval"),
            consumes=("object.changed",),
            publishes=("action.requested", "action.completed"),
        ),
    ),
    interface_ids=("Identifiable", "Auditable"),
    feature_flags={"predictive_modeling": False, "maintenance_workflow": False},
)


PREDICTIVE_MAINTENANCE = DomainPackDefinition(
    code="manufacturing-predictive-maintenance",
    version="3.1.0",
    display_name="Manufacturing Predictive Maintenance",
    description="The first governed vertical pack built on domain-neutral platform primitives.",
    status="active",
    namespace="ontology_dashboard.domain_packs.predictive_maintenance",
    vocabulary=DomainVocabulary(
        object_label="Asset",
        object_plural_label="Assets",
        event_label="Risk Event",
        action_label="Maintenance Action",
        risk_label="Failure Risk",
    ),
    bounded_contexts=(
        BoundedContextDefinition(
            id="asset-reliability",
            display_name="Asset Reliability",
            kind="core",
            owns=("Asset", "SensorObservation", "RiskEvent"),
            publishes=("asset.observed", "risk.assessed"),
        ),
        BoundedContextDefinition(
            id="maintenance-execution",
            display_name="Maintenance Execution",
            kind="core",
            owns=("Inspection", "WorkOrder", "MaintenanceOutcome"),
            consumes=("risk.assessed",),
            publishes=("inspection.requested", "maintenance.completed"),
        ),
        BoundedContextDefinition(
            id="model-operations",
            display_name="Model Operations",
            kind="supporting",
            owns=("FeatureView", "ModelVersion", "PredictionResult"),
            consumes=("asset.observed", "maintenance.completed"),
            publishes=("prediction.created", "model.drifted"),
        ),
        BoundedContextDefinition(
            id="source-integration",
            display_name="Source Integration",
            kind="integration",
            owns=("Connector", "Checkpoint", "QuarantineRecord"),
            publishes=("dataset.version.created",),
        ),
    ),
    object_type_ids=("Equipment", "RiskEvent", "Inspection", "WorkOrder"),
    interface_ids=("Asset", "Auditable", "TimeSeriesSource"),
    action_type_ids=("request-inspection", "complete-inspection", "review-shutdown"),
    feature_flags={"predictive_modeling": True, "maintenance_workflow": True},
)


DOMAIN_PACKS = {
    GENERIC_OPERATIONS.code: GENERIC_OPERATIONS,
    PREDICTIVE_MAINTENANCE.code: PREDICTIVE_MAINTENANCE,
    # Existing seed data used a short code. Keep the persisted value stable and
    # resolve it to the canonical pack definition at the platform boundary.
    "predictive-maintenance": PREDICTIVE_MAINTENANCE,
}


def list_domain_packs() -> tuple[DomainPackDefinition, ...]:
    unique = {item.code: item for item in DOMAIN_PACKS.values()}
    return tuple(unique[key] for key in sorted(unique))


def resolve_domain_pack(code: str | None) -> tuple[DomainPackDefinition, str]:
    if code and code in DOMAIN_PACKS:
        return DOMAIN_PACKS[code], "project_metadata"
    return GENERIC_OPERATIONS, "default_platform"
