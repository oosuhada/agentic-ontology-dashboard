from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ontology import LinkRecord, ObjectRecord
from .service import FactorySignalService

MANUFACTURING_DOMAIN_PACK = "manufacturing-predictive-maintenance"
MANUFACTURING_WORKSPACE = "manufacturing-demo"


def equipment_object_id(equipment_id: str) -> str:
    return f"equipment:{equipment_id}"


def risk_event_object_id(event_id: str) -> str:
    return f"risk_event:{event_id}"


def evidence_object_id(evidence_id: str) -> str:
    return f"evidence_package:{evidence_id}"


def inspection_object_id(event_id: str) -> str:
    return f"inspection:{event_id}"


def maintenance_action_object_id(record_id: str) -> str:
    return f"maintenance_action:{record_id}"


def source_identifier(object_id: str, expected_type: str) -> str:
    prefix = f"{expected_type}:"
    if not object_id.startswith(prefix) or len(object_id) == len(prefix):
        raise ValueError(f"object_id must use the '{prefix}<source-id>' format")
    return object_id[len(prefix) :]


@dataclass(frozen=True)
class OntologySnapshot:
    objects: tuple[ObjectRecord, ...]
    links: tuple[LinkRecord, ...]


class ManufacturingOntologyAdapter:
    """Projects existing manufacturing fixtures and activity into ontology records."""

    domain_pack = MANUFACTURING_DOMAIN_PACK
    workspace_id = MANUFACTURING_WORKSPACE

    def __init__(self, legacy_service: FactorySignalService) -> None:
        self.legacy_service = legacy_service

    def supports_workspace(self, workspace_id: str) -> bool:
        return workspace_id == self.workspace_id

    def snapshot(self) -> OntologySnapshot:
        objects: list[ObjectRecord] = []
        links: list[LinkRecord] = []
        seen_equipment: set[str] = set()

        for event_id, fixture in sorted(self.legacy_service.fixtures.items()):
            evidence = self.legacy_service.evidence_snapshot(event_id)
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

            activity = self.legacy_service.repository.event_activity(event_id)
            inspection_required = evidence["recommended_decision"] in {
                "request_inspection",
                "review_shutdown",
            }
            if inspection_required or activity["notes"]:
                inspection_oid = inspection_object_id(event_id)
                inspection_status = "in_progress" if activity["notes"] else "requested"
                objects.append(
                    ObjectRecord(
                        id=inspection_oid,
                        object_type="inspection",
                        workspace_id=self.workspace_id,
                        properties={
                            "status": inspection_status,
                            "assignee": equipment.get("assigned_engineer"),
                            "due_at": None,
                            "event_id": event_id,
                            "checklist": evidence["maintenance_context"]["checklist"],
                        },
                        source_refs=[f"event:{event_id}", f"evidence:{evidence['evidence_id']}"],
                    )
                )
                links.append(
                    LinkRecord(
                        id=f"risk_event_requires_inspection:{event_id}",
                        link_type="risk_event_requires_inspection",
                        source_object_id=event_oid,
                        target_object_id=inspection_oid,
                        workspace_id=self.workspace_id,
                    )
                )
                self._append_activity_objects(
                    event_id=event_id,
                    inspection_oid=inspection_oid,
                    activity=activity,
                    objects=objects,
                    links=links,
                )
            else:
                self._append_activity_objects(
                    event_id=event_id,
                    inspection_oid=None,
                    activity=activity,
                    objects=objects,
                    links=links,
                )

        return OntologySnapshot(objects=tuple(objects), links=tuple(links))

    def _append_activity_objects(
        self,
        *,
        event_id: str,
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

    def objects(self) -> Iterable[ObjectRecord]:
        return self.snapshot().objects

    def links(self) -> Iterable[LinkRecord]:
        return self.snapshot().links
