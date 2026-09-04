from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from app.common.company_context import load_company_context

from .ontology_domain import LinkRecord, ObjectRecord

PREDICTIVE_MAINTENANCE_PROJECTION_ID = "manufacturing-predictive-maintenance"
MANUFACTURING_WORKSPACE = "manufacturing-demo"


class ProjectionActivityRepository(Protocol):
    def event_activity(self, event_id: str) -> dict[str, list[dict[str, Any]]]: ...


class PredictiveMaintenanceProjectionSource(Protocol):
    fixtures: Mapping[str, dict[str, Any]]
    repository: ProjectionActivityRepository

    def evidence_snapshot(self, event_id: str) -> dict[str, Any]: ...


class FieldActionProjectionSource(Protocol):
    def list_field_actions(self, *, workspace_id: str, event_id: str) -> list[dict[str, Any]]: ...


def equipment_object_id(equipment_id: str) -> str:
    return f"equipment:{equipment_id}"


def risk_event_object_id(event_id: str) -> str:
    return f"risk_event:{event_id}"


def evidence_object_id(evidence_id: str) -> str:
    return f"evidence_package:{evidence_id}"


def work_order_object_id(event_id: str) -> str:
    return f"work_order:{event_id}"


def inspection_object_id(event_id: str) -> str:
    """Deprecated compatibility alias for callers that have not migrated to WorkOrder."""
    return f"inspection:{event_id}"


def maintenance_action_object_id(record_id: str) -> str:
    return f"maintenance_action:{record_id}"


def source_identifier(object_id: str, expected_type: str) -> str:
    prefix = f"{expected_type}:"
    if not object_id.startswith(prefix) or len(object_id) == len(prefix):
        raise ValueError(f"object_id must use the '{prefix}<source-id>' format")
    return object_id[len(prefix) :]


@dataclass(frozen=True)
class OntologyProjectionInput:
    """Ontology-owned input contract for one idempotent projection snapshot."""

    workspace_id: str
    source_system: str
    source_revision: str
    objects: tuple[ObjectRecord, ...]
    links: tuple[LinkRecord, ...]


class ManufacturingOntologyAdapter:
    """PdM projection adapter consuming only the Ontology projection input ports."""

    projection_id = PREDICTIVE_MAINTENANCE_PROJECTION_ID
    workspace_id = MANUFACTURING_WORKSPACE

    def __init__(
        self,
        source: PredictiveMaintenanceProjectionSource,
        field_actions: FieldActionProjectionSource | None = None,
    ) -> None:
        self.source = source
        self.field_actions = field_actions

    def supports_workspace(self, workspace_id: str) -> bool:
        return workspace_id == self.workspace_id

    def snapshot(self) -> OntologyProjectionInput:
        objects: list[ObjectRecord] = []
        links: list[LinkRecord] = []
        seen_equipment: set[str] = set()

        for event_id, fixture in sorted(self.source.fixtures.items()):
            evidence = self.source.evidence_snapshot(event_id)
            equipment = fixture["equipment"]
            equipment_id = equipment["equipment_id"]
            equipment_oid = equipment_object_id(equipment_id)
            event_oid = risk_event_object_id(event_id)
            evidence_oid = evidence_object_id(evidence["evidence_id"])

            if equipment_id not in seen_equipment:
                seen_equipment.add(equipment_id)
                objects.append(
                    ObjectRecord(
                        id=equipment_oid,
                        object_type="equipment",
                        workspace_id=self.workspace_id,
                        properties={
                            "display_name": equipment["display_name"],
                            "line": equipment["line"],
                            "criticality": equipment["criticality"],
                            "assigned_engineer": equipment.get("assigned_engineer"),
                            "last_maintenance_date": equipment.get("last_maintenance_date"),
                            "estimated_downtime_minutes": equipment.get("estimated_downtime_minutes"),
                            "spare_part_available": equipment.get("spare_part_available"),
                        },
                        source_refs=[f"fixture:{fixture['scenario_id']}", f"equipment:{equipment_id}"],
                    )
                )

            objects.append(
                ObjectRecord(
                    id=event_oid,
                    object_type="risk_event",
                    workspace_id=self.workspace_id,
                    properties={
                        "status": evidence["status"],
                        "failure_probability": evidence["failure_probability"],
                        "recommended_decision": evidence["recommended_decision"],
                        "confidence": evidence["confidence"],
                        "predicted_failure_type": evidence["predicted_failure_type"],
                        "scenario_id": fixture["scenario_id"],
                        "observed_at": fixture["observation"]["timestamp"],
                    },
                    source_refs=[f"fixture:{fixture['scenario_id']}", f"event:{event_id}"],
                )
            )
            objects.append(
                ObjectRecord(
                    id=evidence_oid,
                    object_type="evidence_package",
                    workspace_id=self.workspace_id,
                    properties={
                        "model_version": evidence["model"]["model_version"],
                        "policy_version": evidence["model"]["policy_version"],
                        "generated_at": evidence["generated_at"],
                        "confidence": evidence["confidence"],
                        "threshold": evidence["threshold"],
                        "lineage": evidence["lineage"],
                        "data_quality_warnings": evidence["data_quality_warnings"],
                    },
                    source_refs=[
                        f"fixture:{fixture['scenario_id']}",
                        *[str(item) for item in evidence["maintenance_context"]["source_refs"]],
                    ],
                )
            )
            links.extend(
                [
                    LinkRecord(
                        id=f"equipment_has_risk_event:{equipment_id}:{event_id}",
                        link_type="equipment_has_risk_event",
                        source_object_id=equipment_oid,
                        target_object_id=event_oid,
                        workspace_id=self.workspace_id,
                    ),
                    LinkRecord(
                        id=f"risk_event_has_evidence:{event_id}:{evidence['evidence_id']}",
                        link_type="risk_event_has_evidence",
                        source_object_id=event_oid,
                        target_object_id=evidence_oid,
                        workspace_id=self.workspace_id,
                    ),
                ]
            )

            activity = self.source.repository.event_activity(event_id)
            activity["field_actions"] = (
                self.field_actions.list_field_actions(
                    workspace_id=self.workspace_id,
                    event_id=event_id,
                )
                if self.field_actions is not None
                else []
            )
            inspection_required = evidence["recommended_decision"] in {
                "request_inspection",
                "review_shutdown",
            }
            if inspection_required or activity["notes"] or activity["field_actions"]:
                work_order_oid = work_order_object_id(event_id)
                inspection_oid = inspection_object_id(event_id)
                work_order_status = "in_progress" if activity["notes"] else "requested"
                common_properties = {
                    "status": work_order_status,
                    "assignee": equipment.get("assigned_engineer"),
                    "due_at": None,
                    "event_id": event_id,
                    "work_type": "inspection",
                    "equipment_id": equipment_id,
                    "checklist": evidence["maintenance_context"]["checklist"],
                }
                objects.extend(
                    [
                        ObjectRecord(
                            id=work_order_oid,
                            object_type="work_order",
                            workspace_id=self.workspace_id,
                            properties=common_properties,
                            source_refs=[f"event:{event_id}", f"evidence:{evidence['evidence_id']}"],
                        ),
                        ObjectRecord(
                            id=inspection_oid,
                            object_type="inspection",
                            workspace_id=self.workspace_id,
                            properties={
                                **common_properties,
                                "canonical_work_order_id": work_order_oid,
                            },
                            source_refs=[f"work_order:{event_id}", "deprecated:inspection-alias"],
                        ),
                    ]
                )
                links.extend(
                    [
                        LinkRecord(
                            id=f"equipment_has_work_order:{equipment_id}:{event_id}",
                            link_type="equipment_has_work_order",
                            source_object_id=equipment_oid,
                            target_object_id=work_order_oid,
                            workspace_id=self.workspace_id,
                        ),
                        LinkRecord(
                            id=f"risk_event_requires_work_order:{event_id}",
                            link_type="risk_event_requires_work_order",
                            source_object_id=event_oid,
                            target_object_id=work_order_oid,
                            workspace_id=self.workspace_id,
                        ),
                        LinkRecord(
                            id=f"risk_event_requires_inspection:{event_id}",
                            link_type="risk_event_requires_inspection",
                            source_object_id=event_oid,
                            target_object_id=inspection_oid,
                            workspace_id=self.workspace_id,
                        ),
                    ]
                )
                self._append_activity_objects(
                    event_id=event_id,
                    work_order_oid=work_order_oid,
                    inspection_oid=inspection_oid,
                    activity=activity,
                    objects=objects,
                    links=links,
                )
            else:
                self._append_activity_objects(
                    event_id=event_id,
                    work_order_oid=None,
                    inspection_oid=None,
                    activity=activity,
                    objects=objects,
                    links=links,
                )

        self._append_company_context(objects=objects, links=links, seen_equipment=seen_equipment)

        return OntologyProjectionInput(
            workspace_id=self.workspace_id,
            source_system="manufacturing-predictive-maintenance",
            source_revision="operational-and-company-context-v2",
            objects=tuple(objects),
            links=tuple(links),
        )

    def _append_company_context(
        self,
        *,
        objects: list[ObjectRecord],
        links: list[LinkRecord],
        seen_equipment: set[str],
    ) -> None:
        """Project business/history context beside canonical PdM objects.

        These records provide contextual evidence. Current maintenance workflow
        state still comes exclusively from the closed-loop owner domain.
        """

        context = load_company_context()
        context_kind = str(context.get("context_kind") or "company_operational_context")
        company = context.get("company") or {}
        company_id = str(company.get("id") or "company:hanbit-tech")
        objects.append(
            ObjectRecord(
                id=company_id,
                object_type="company",
                workspace_id=self.workspace_id,
                properties={**company, "context_kind": context_kind},
                source_refs=["company-context:root"],
            )
        )

        for item in context.get("organization_units") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="organization_unit",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[f"company-context:{object_id}"],
                )
            )
            links.append(
                LinkRecord(
                    id=f"company_has_organization_unit:{object_id}",
                    link_type="company_has_organization_unit",
                    source_object_id=company_id,
                    target_object_id=object_id,
                    workspace_id=self.workspace_id,
                )
            )

        for item in context.get("products") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="product",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[f"company-context:{object_id}"],
                )
            )
            links.append(
                LinkRecord(
                    id=f"company_sells_product:{object_id}",
                    link_type="company_sells_product",
                    source_object_id=company_id,
                    target_object_id=object_id,
                    workspace_id=self.workspace_id,
                )
            )

        for item in context.get("materials") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="material",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[f"company-context:{object_id}"],
                )
            )
            links.append(
                LinkRecord(
                    id=f"company_has_material:{object_id}",
                    link_type="company_has_material",
                    source_object_id=company_id,
                    target_object_id=object_id,
                    workspace_id=self.workspace_id,
                )
            )
            for asset_id in item.get("related_asset_ids") or []:
                if str(asset_id) not in seen_equipment:
                    continue
                links.append(
                    LinkRecord(
                        id=f"equipment_uses_material:{asset_id}:{object_id}",
                        link_type="equipment_uses_material",
                        source_object_id=equipment_object_id(str(asset_id)),
                        target_object_id=object_id,
                        workspace_id=self.workspace_id,
                    )
                )

        for item in context.get("business_metrics") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="business_metric",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[f"company-context:{object_id}"],
                )
            )
            links.append(
                LinkRecord(
                    id=f"company_has_business_metric:{object_id}",
                    link_type="company_has_business_metric",
                    source_object_id=company_id,
                    target_object_id=object_id,
                    workspace_id=self.workspace_id,
                )
            )

        for item in context.get("maintenance_records") or []:
            object_id = str(item["id"])
            asset_id = str(item.get("asset_id") or "")
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="maintenance_history_record",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[str(item.get("source_ref") or f"company-context:{object_id}")],
                )
            )
            if asset_id in seen_equipment:
                links.append(
                    LinkRecord(
                        id=f"equipment_has_maintenance_history:{asset_id}:{object_id}",
                        link_type="equipment_has_maintenance_history",
                        source_object_id=equipment_object_id(asset_id),
                        target_object_id=object_id,
                        workspace_id=self.workspace_id,
                    )
                )

        for item in context.get("meeting_minutes") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="meeting_record",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[str(item.get("source_ref") or f"company-context:{object_id}")],
                )
            )

        for item in context.get("decisions") or []:
            object_id = str(item["id"])
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type="decision_record",
                    workspace_id=self.workspace_id,
                    properties={**item, "context_kind": context_kind},
                    source_refs=[str(item.get("source_ref") or f"company-context:{object_id}")],
                )
            )
            owner_id = str(item.get("owner_org_unit_id") or "")
            if owner_id:
                links.append(
                    LinkRecord(
                        id=f"organization_owns_decision:{owner_id}:{object_id}",
                        link_type="organization_owns_decision",
                        source_object_id=owner_id,
                        target_object_id=object_id,
                        workspace_id=self.workspace_id,
                    )
                )
            for asset_id in item.get("related_asset_ids") or []:
                if str(asset_id) not in seen_equipment:
                    continue
                links.append(
                    LinkRecord(
                        id=f"decision_concerns_equipment:{object_id}:{asset_id}",
                        link_type="decision_concerns_equipment",
                        source_object_id=object_id,
                        target_object_id=equipment_object_id(str(asset_id)),
                        workspace_id=self.workspace_id,
                    )
                )

        decision_ids = {str(item.get("id")) for item in context.get("decisions") or []}
        for meeting in context.get("meeting_minutes") or []:
            meeting_id = str(meeting["id"])
            for decision_id in meeting.get("decision_ids") or []:
                if str(decision_id) not in decision_ids:
                    continue
                links.append(
                    LinkRecord(
                        id=f"meeting_records_decision:{meeting_id}:{decision_id}",
                        link_type="meeting_records_decision",
                        source_object_id=meeting_id,
                        target_object_id=str(decision_id),
                        workspace_id=self.workspace_id,
                    )
                )

    def _append_activity_objects(
        self,
        *,
        event_id: str,
        work_order_oid: str | None,
        inspection_oid: str | None,
        activity: dict[str, list[dict]],
        objects: list[ObjectRecord],
        links: list[LinkRecord],
    ) -> None:
        for decision in activity["decisions"]:
            objects.append(
                ObjectRecord(
                    id=maintenance_action_object_id(decision["id"]),
                    object_type="maintenance_action",
                    workspace_id=self.workspace_id,
                    properties={
                        "action": "operational_decision",
                        "actor": decision["actor"],
                        "created_at": decision["created_at"],
                        "decision": decision["decision"],
                        "note": decision["note"],
                        "event_id": event_id,
                    },
                    source_refs=[f"decision:{decision['id']}", f"event:{event_id}"],
                )
            )

        for note in activity["notes"]:
            action_oid = maintenance_action_object_id(note["id"])
            objects.append(
                ObjectRecord(
                    id=action_oid,
                    object_type="maintenance_action",
                    workspace_id=self.workspace_id,
                    properties={
                        "action": "inspection_note",
                        "actor": note["actor"],
                        "created_at": note["created_at"],
                        "body": note["body"],
                        "event_id": event_id,
                    },
                    source_refs=[f"note:{note['id']}", f"event:{event_id}"],
                )
            )
            if work_order_oid is not None:
                links.append(
                    LinkRecord(
                        id=f"work_order_records_action:{event_id}:{note['id']}",
                        link_type="work_order_records_action",
                        source_object_id=work_order_oid,
                        target_object_id=action_oid,
                        workspace_id=self.workspace_id,
                    )
                )
            if inspection_oid is not None:
                links.append(
                    LinkRecord(
                        id=f"inspection_records_action:{event_id}:{note['id']}",
                        link_type="inspection_records_action",
                        source_object_id=inspection_oid,
                        target_object_id=action_oid,
                        workspace_id=self.workspace_id,
                    )
                )

        for field_action in activity.get("field_actions", []):
            action_oid = maintenance_action_object_id(field_action["id"])
            payload = field_action.get("payload") if isinstance(field_action.get("payload"), dict) else {}
            objects.append(
                ObjectRecord(
                    id=action_oid,
                    object_type="maintenance_action",
                    workspace_id=self.workspace_id,
                    properties={
                        "action": field_action.get("action"),
                        "status": field_action.get("status"),
                        "actor": field_action.get("actor_display_name"),
                        "created_at": field_action.get("created_at"),
                        "event_id": event_id,
                        "note": payload.get("note"),
                        "location": payload.get("location"),
                        "measurements": payload.get("measurements", {}),
                        "photo_metadata": payload.get("photo_metadata", []),
                        "checklist": payload.get("checklist", []),
                    },
                    source_refs=[f"field_action:{field_action['id']}", f"event:{event_id}"],
                )
            )
            if work_order_oid is not None:
                links.append(
                    LinkRecord(
                        id=f"work_order_records_action:{event_id}:{field_action['id']}",
                        link_type="work_order_records_action",
                        source_object_id=work_order_oid,
                        target_object_id=action_oid,
                        workspace_id=self.workspace_id,
                    )
                )
            if inspection_oid is not None:
                links.append(
                    LinkRecord(
                        id=f"inspection_records_action:{event_id}:{field_action['id']}",
                        link_type="inspection_records_action",
                        source_object_id=inspection_oid,
                        target_object_id=action_oid,
                        workspace_id=self.workspace_id,
                    )
                )

    def objects(self) -> Iterable[ObjectRecord]:
        return self.snapshot().objects

    def links(self) -> Iterable[LinkRecord]:
        return self.snapshot().links
