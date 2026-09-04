"""Canonical Maintenance application service for the two-stage human loop."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.diagnosis.ports import EventEvidenceProjectionQueryPort

from .api_schema import (
    EvidenceSnapshotBasis,
    InspectionResultCreateRequest,
    InspectionWorkOrderCreateRequest,
    MaintenanceActionCompleteRequest,
    MaintenanceActionStartRequest,
    MaintenanceCostAnalysisCreateRequest,
    MaintenanceReplayRequest,
    MaintenanceWorkOrderApproveRequest,
    OperationsManualRecommendationCreateRequest,
    RecommendationDecisionCreateRequest,
    RecommendationInput,
    RecommendationInputSource,
    ToolReplacementCostAnalysisCreateRequest,
)
from .cost_analysis_schema import (
    CostAnalysisBasis,
    MaintenanceActionCode,
)
from .cost_calculator import (
    MaintenanceCostAnalysisInput,
    calculate_maintenance_cost_scenarios,
)
from .integration import (
    CoolingSystemRestoreStatePatch,
    MaintenanceCause,
    MaintenanceCompletedEvent,
    MaintenanceReplayRequestedEvent,
    MaintenanceStartedEvent,
    ToolReplacementStatePatch,
)
from .maintenance_domain import (
    SourceSimulationSessionUnavailable,
    apply_recommendation_decision,
    create_inspection_work_order,
    create_operations_manual_recommendation,
    create_work_order_for_recommendation,
    derive_cost_basis_resolution_context,
    derive_cooling_system_restore_action_candidate,
    derive_tool_replacement_action_candidate,
    plan_maintenance_action,
    transition_work_order,
)
from .maintenance_schema import (
    EquipmentIdentity,
    InspectionOutcome,
    InspectionResult,
    OperationalDecisionKind,
    RecommendationDecision,
    RecommendationDisposition,
    WorkOrderStatus,
    WorkOrderType,
)
from .ports import (
    MaintenanceCostBasisProvider,
    MaintenanceCommandRepositoryPort,
    MaintenanceReplaySessionValidationPort,
)


class MaintenanceLoopService:
    def __init__(
        self,
        repository: MaintenanceCommandRepositoryPort,
        *,
        event_evidence_query: EventEvidenceProjectionQueryPort,
        replay_session_query: MaintenanceReplaySessionValidationPort | None = None,
        cost_basis_provider: MaintenanceCostBasisProvider | None = None,
    ) -> None:
        self.repository = repository
        self.event_evidence_query = event_evidence_query
        self.replay_session_query = replay_session_query
        self.cost_basis_provider = cost_basis_provider

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        source = ":".join(parts)
        return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, source)}"

    @staticmethod
    def _stable_event_id(*parts: str) -> str:
        """Return the deterministic UUID required by transactional_outbox.id."""

        return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(parts)))

    @staticmethod
    def _fingerprint(command: str, payload: Any) -> str:
        body = (
            payload.model_dump(mode="json")
            if hasattr(payload, "model_dump")
            else payload
        )
        encoded = json.dumps(
            {"command": command, "payload": body},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _require_scope(record: Any, *, organization_id: str, project_id: str, workspace_id: str) -> None:
        for field, expected in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("workspace_id", workspace_id),
        ):
            if getattr(record, field) != expected:
                raise ValueError(f"{field} scope mismatch")

    @staticmethod
    def _required_text(values: Mapping[str, Any], field: str) -> str:
        value = values.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Event Evidence Projection requires {field}")
        return value

    @staticmethod
    def _projection_snapshot_basis(projection: Mapping[str, Any]) -> dict[str, Any]:
        artifact = projection.get("artifact_reference")
        provenance = projection.get("provenance")
        if not isinstance(artifact, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError("Event Evidence Projection is missing snapshot basis sections")
        lineage = provenance.get("lineage") if isinstance(provenance.get("lineage"), Mapping) else {}
        evidence_reference = artifact.get("evidence_payload_reference")
        if isinstance(evidence_reference, Mapping):
            evidence_reference = evidence_reference.get("reference")
        return {
            "artifact_id": artifact.get("artifact_id"),
            "evidence_payload_reference": str(evidence_reference or ""),
            "asset_id": artifact.get("asset_id"),
            "event_id": projection.get("event_id") or artifact.get("event_id"),
            "observed_at": artifact.get("observed_at"),
            "model_version": provenance.get("model_version"),
            "dataset_version": provenance.get("dataset_version"),
            "source_sha256": (
                artifact.get("source_sha256")
                or provenance.get("source_sha256")
                or lineage.get("source_sha256")
            ),
        }

    @classmethod
    def _snapshot_basis_mismatches(
        cls,
        *,
        expected: EvidenceSnapshotBasis | None,
        projection: Mapping[str, Any],
    ) -> list[str]:
        if expected is None:
            return []
        current = cls._projection_snapshot_basis(projection)
        mismatched = []
        for field, expected_value in expected.model_dump(mode="json").items():
            if expected_value in {None, ""}:
                continue
            if current.get(field) != expected_value:
                mismatched.append(field)
        return sorted(mismatched)

    @classmethod
    def _require_snapshot_basis_match(
        cls,
        *,
        expected: EvidenceSnapshotBasis | None,
        projection: Mapping[str, Any],
    ) -> None:
        mismatched = cls._snapshot_basis_mismatches(
            expected=expected,
            projection=projection,
        )
        if mismatched:
            raise ValueError(
                f"snapshot_basis mismatch: {', '.join(mismatched)}"
            )

    @classmethod
    def _require_row_scope(
        cls,
        record: Mapping[str, Any],
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> None:
        for field, expected in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("workspace_id", workspace_id),
        ):
            if record.get(field) != expected:
                raise ValueError(f"{field} scope mismatch")

    @staticmethod
    def _stored_datetime(record: Mapping[str, Any], field: str) -> datetime:
        value = record.get(field)
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value:
            raise ValueError(f"persisted maintenance record requires {field}")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"persisted maintenance {field} must include timezone")
        return parsed

    @classmethod
    def _maintenance_cause(cls, record: Mapping[str, Any]) -> MaintenanceCause:
        return MaintenanceCause(
            source_product_result_id=cls._required_text(
                record, "source_product_result_id"
            ),
            source_evidence_id=cls._required_text(record, "source_evidence_id"),
            decision_id=cls._required_text(record, "recommendation_decision_id"),
        )

    def _event_evidence_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
        snapshot_basis: EvidenceSnapshotBasis | None = None,
    ) -> Mapping[str, Any]:
        projection = self.event_evidence_query.event_evidence_projection(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_id=event_id,
        )
        if projection is None:
            raise KeyError(event_id)
        if projection.get("contract_type") != "event_evidence_projection":
            raise ValueError("Diagnosis query returned a non-canonical evidence contract")
        if projection.get("schema_version") != "event-evidence-projection-v1":
            raise ValueError("unsupported Event Evidence Projection schema version")
        if self._required_text(projection, "event_id") != event_id:
            raise ValueError("Event Evidence Projection event_id mismatch")

        if snapshot_basis is not None:
            mismatched = self._snapshot_basis_mismatches(
                expected=snapshot_basis,
                projection=projection,
            )
            if mismatched:
                projection = self.event_evidence_query.event_evidence_projection(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_id=event_id,
                )
                if projection is None:
                    raise KeyError(event_id)
                if projection.get("contract_type") != "event_evidence_projection":
                    raise ValueError(
                        "Diagnosis query returned a non-canonical evidence contract"
                    )
                if projection.get("schema_version") != "event-evidence-projection-v1":
                    raise ValueError(
                        "unsupported Event Evidence Projection schema version"
                    )
                if self._required_text(projection, "event_id") != event_id:
                    raise ValueError("Event Evidence Projection event_id mismatch")
                self._require_snapshot_basis_match(
                    expected=snapshot_basis,
                    projection=projection,
                )
        return projection

    def _recommendation_input_from_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
        projection: Mapping[str, Any],
    ) -> RecommendationInput:
        subject = projection.get("subject")
        artifact = projection.get("artifact_reference")
        assessment = projection.get("assessment")
        report = projection.get("report_projection")
        provenance = projection.get("provenance")
        if not all(
            isinstance(value, Mapping)
            for value in (subject, artifact, assessment, report, provenance)
        ):
            raise ValueError("Event Evidence Projection is missing authorization sections")

        asset_id = self._required_text(artifact, "asset_id")
        asset_type = self._required_text(artifact, "asset_type")
        if self._required_text(artifact, "event_id") != event_id:
            raise ValueError("Event Evidence Projection artifact event_id mismatch")
        equipment_id = self._required_text(subject, "equipment_id")
        if equipment_id != asset_id:
            raise ValueError("Event Evidence Projection equipment identity mismatch")
        subject_asset_type = self._required_text(subject, "asset_type")
        if subject_asset_type != asset_type:
            raise ValueError("Event Evidence Projection asset_type mismatch")

        decision_raw = assessment.get("operational_decision_kind")
        try:
            decision = OperationalDecisionKind(decision_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Event Evidence Projection has no supported operational decision"
            ) from exc
        if decision not in {
            OperationalDecisionKind.REQUEST_INSPECTION,
            OperationalDecisionKind.REVIEW_SHUTDOWN,
        }:
            raise ValueError(
                "Event Evidence Projection does not authorize an inspection"
            )

        actions = report.get("recommended_actions")
        if not isinstance(actions, list) or len(actions) != 1:
            raise ValueError(
                "Event Evidence Projection requires one canonical recommendation"
            )
        action = actions[0]
        if not isinstance(action, Mapping):
            raise ValueError("Event Evidence Projection recommendation must be an object")
        source_action_id = self._required_text(action, "action_id")
        if source_action_id != decision.value:
            raise ValueError(
                "Event Evidence Projection decision does not match its source action"
            )

        lineage = provenance.get("lineage")
        if not isinstance(lineage, Mapping):
            raise ValueError("Event Evidence Projection provenance.lineage is required")
        return RecommendationInput(
            event_id=event_id,
            snapshot_basis=EvidenceSnapshotBasis.model_validate(
                self._projection_snapshot_basis(projection)
            ),
            equipment=EquipmentIdentity(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=asset_id,
                equipment_id=equipment_id,
                asset_type=asset_type,
            ),
            operational_decision_kind=decision,
            source_context=RecommendationInputSource(
                source_product_result_id=self._required_text(artifact, "artifact_id"),
                source_evidence_id=self._required_text(projection, "evidence_id"),
                source_action_id=source_action_id,
                source_schema_version=self._required_text(
                    artifact, "artifact_schema_version"
                ),
                source_policy_version=self._required_text(lineage, "policy_version"),
            ),
        )

    def recommendation_input(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
        snapshot_basis: EvidenceSnapshotBasis | None = None,
    ) -> dict[str, Any]:
        projection = self._event_evidence_projection(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_id=event_id,
            snapshot_basis=snapshot_basis,
        )
        return self._recommendation_input_from_projection(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_id=event_id,
            projection=projection,
        ).model_dump(mode="json")

    def _inspection_source(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
        snapshot_basis: EvidenceSnapshotBasis | None = None,
    ) -> tuple[EquipmentIdentity, OperationalDecisionKind, dict[str, str]]:
        recommendation_input = RecommendationInput.model_validate(
            self.recommendation_input(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_id=event_id,
                snapshot_basis=snapshot_basis,
            )
        )
        return (
            recommendation_input.equipment,
            recommendation_input.operational_decision_kind,
            recommendation_input.source_context.model_dump(mode="json"),
        )

    def request_inspection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        payload: InspectionWorkOrderCreateRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        identity, operational_decision, source = self._inspection_source(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_id=payload.event_id,
            snapshot_basis=payload.snapshot_basis,
        )
        work_order_id = self._stable_id(
            "INSPECTION-WO",
            organization_id,
            project_id,
            workspace_id,
            payload.event_id,
            identity.equipment_id,
            source["source_product_result_id"],
            source["source_action_id"],
        )
        work_order = create_inspection_work_order(
            work_order_id=work_order_id,
            identity=identity,
            event_id=payload.event_id,
            operational_decision=operational_decision,
            source_product_result_id=source["source_product_result_id"],
            source_evidence_id=source["source_evidence_id"],
            source_action_id=source["source_action_id"],
            source_schema_version=source["source_schema_version"],
            source_policy_version=source["source_policy_version"],
            idempotency_key=idempotency_key,
        )
        return self.repository.create_inspection_work_order(
            work_order=work_order,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "inspection.request",
                {"payload": payload.model_dump(mode="json"), "actor_id": actor_id},
            ),
        )

    def transition_inspection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        work_order_id: str,
        target: WorkOrderStatus,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        transitioned_at: datetime | None = None,
    ) -> dict[str, Any]:
        work_order = self.repository.get_work_order(
            workspace_id=workspace_id,
            work_order_id=work_order_id,
        )
        if work_order is None:
            raise KeyError(work_order_id)
        self._require_scope(
            work_order,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if work_order.work_type is not WorkOrderType.INSPECTION:
            raise ValueError("work order is not an inspection")
        transition_time = transitioned_at or datetime.now(timezone.utc)
        updates: dict[str, Any] = {
            "status": transition_work_order(work_order.status, target)
        }
        if target is WorkOrderStatus.APPROVED:
            updates.update(assigned_to=actor_id, assigned_at=transition_time)
        elif work_order.assigned_to != actor_id:
            raise PermissionError("only the assigned field operator can start this inspection")
        transitioned = work_order.model_copy(
            update=updates
        )
        return self.repository.transition_inspection_work_order(
            work_order=transitioned,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            transitioned_at=transition_time,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                f"inspection.{target.value}",
                {
                    "work_order_id": work_order_id,
                    "target": target.value,
                    "actor_id": actor_id,
                },
            ),
        )

    def list_open_inspection_work_orders(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        work_orders = self.repository.list_open_inspection_work_orders(
            workspace_id=workspace_id,
        )
        for work_order in work_orders:
            self._require_scope(
                work_order,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        items = []
        for work_order in work_orders:
            lineage = self.repository.event_lineage(
                workspace_id=workspace_id,
                event_id=work_order.event_id,
            )
            if self._post_maintenance_result_exists(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                work_order=work_order,
                lineage=lineage,
            ):
                continue
            inspection_results = [
                item
                for item in lineage.get("inspection_results") or []
                if item.get("work_order_id") == work_order.work_order_id
            ]
            items.append(
                {
                    **work_order.model_dump(mode="json"),
                    "inspection_outcome": (
                        inspection_results[-1].get("outcome")
                        if inspection_results
                        else None
                    ),
                    "current_step": self._inspection_workflow_current_step(
                        work_order=work_order,
                        lineage=lineage,
                    ),
                }
            )
        return {"items": items}

    def _post_maintenance_result_exists(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        work_order: Any,
        lineage: Mapping[str, Any],
    ) -> bool:
        maintenance_events = list(lineage.get("maintenance_events") or [])
        if not maintenance_events or self.replay_session_query is None:
            return False
        resolver = getattr(self.replay_session_query, "post_maintenance_result", None)
        if not callable(resolver):
            return False
        maintenance_event_id = maintenance_events[-1].get("maintenance_event_id")
        if not maintenance_event_id:
            return False
        try:
            result = resolver(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=work_order.asset_id,
                maintenance_event_id=maintenance_event_id,
            )
        except (KeyError, ValueError):
            return False
        return result is not None

    @staticmethod
    def _inspection_workflow_current_step(
        *,
        work_order: Any,
        lineage: Mapping[str, Any],
    ) -> str:
        if work_order.status is WorkOrderStatus.REQUESTED:
            return "inspection_requested"
        if work_order.status is WorkOrderStatus.APPROVED:
            return "inspection_approved"
        if work_order.status is WorkOrderStatus.IN_PROGRESS:
            return "inspection_in_progress"

        maintenance_actions = list(lineage.get("maintenance_actions") or [])
        if maintenance_actions:
            status = maintenance_actions[-1].get("status")
            if status == "in_progress":
                return "maintenance_in_progress"
            if status == "planned":
                return "maintenance_approved"
            if status == "completed":
                return "post_maintenance_observation_pending"

        maintenance_work_orders = [
            item
            for item in lineage.get("work_orders") or []
            if item.get("work_type") == WorkOrderType.MAINTENANCE.value
        ]
        if maintenance_work_orders:
            status = maintenance_work_orders[-1].get("status")
            if status == WorkOrderStatus.REQUESTED.value:
                return "maintenance_requested"
            if status == WorkOrderStatus.APPROVED.value:
                return "maintenance_approved"
            if status == WorkOrderStatus.IN_PROGRESS.value:
                return "maintenance_in_progress"
            if status == WorkOrderStatus.COMPLETED.value:
                return "post_maintenance_observation_pending"

        manual_recommendations = [
            item
            for item in lineage.get("recommendations") or []
            if item.get("recommendation_origin") == "operations_manual"
            and item.get("source_inspection_work_order_id") == work_order.work_order_id
        ]
        if manual_recommendations:
            return "recommendation_proposed"
        return "inspection_completed"

    def complete_inspection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        work_order_id: str,
        payload: InspectionResultCreateRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        work_order = self.repository.get_work_order(
            workspace_id=workspace_id,
            work_order_id=work_order_id,
        )
        if work_order is None:
            raise KeyError(work_order_id)
        self._require_scope(
            work_order,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if work_order.assigned_to != actor_id:
            raise PermissionError("only the assigned field operator can complete this inspection")
        completed_at = recorded_at or datetime.now(timezone.utc)
        completed = work_order.model_copy(
            update={
                "status": transition_work_order(
                    work_order.status,
                    WorkOrderStatus.COMPLETED,
                )
            }
        )
        inspection_result = InspectionResult(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            inspection_result_id=self._stable_id(
                "INSPECTION-RESULT",
                organization_id,
                project_id,
                workspace_id,
                work_order_id,
            ),
            work_order_id=work_order_id,
            event_id=work_order.event_id,
            asset_id=work_order.asset_id,
            equipment_id=work_order.equipment_id,
            asset_type=work_order.asset_type,
            outcome=payload.outcome,
            checklist=payload.checklist,
            measurements=payload.measurements,
            findings=payload.findings,
            note=payload.note,
            recorded_by=actor_id,
            recorded_at=completed_at,
        )
        return self.repository.complete_inspection(
            work_order=completed,
            inspection_result=inspection_result,
            actor_display_name=actor_display_name,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "inspection.complete",
                {
                    "work_order_id": work_order_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
        )

    def create_manual_recommendation(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        inspection_result_id: str,
        payload: OperationsManualRecommendationCreateRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        authored_at: datetime | None = None,
    ) -> dict[str, Any]:
        inspection_result = self.repository.get_inspection_result(
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
        )
        if inspection_result is None:
            raise KeyError(inspection_result_id)
        self._require_scope(
            inspection_result,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if inspection_result.outcome is not InspectionOutcome.MAINTENANCE_RECOMMENDED:
            raise ValueError(
                "operations manual recommendation requires maintenance_recommended inspection outcome"
            )
        action_code = MaintenanceActionCode(payload.action_code)
        action_candidate = self._derive_action_candidate(inspection_result, action_code)
        source_cost_analysis_id = payload.cost_analysis_id
        source_cost_option_id = payload.cost_option_id
        source_action_candidate_id = payload.action_candidate_id
        if (source_cost_analysis_id is None) != (source_action_candidate_id is None):
            raise ValueError(
                "manual recommendation cost reference requires analysis and action candidate"
            )
        if source_cost_option_id is not None and source_cost_analysis_id is None:
            raise ValueError(
                "manual recommendation cost option requires analysis and action candidate"
            )
        if source_cost_analysis_id is not None:
            if source_action_candidate_id != action_candidate.action_candidate_id:
                raise ValueError("manual recommendation action candidate mismatch")
            cost_analysis = self.repository.get_cost_analysis(
                workspace_id=workspace_id,
                analysis_id=str(source_cost_analysis_id),
            )
            if cost_analysis is None:
                raise KeyError(source_cost_analysis_id)
            self._require_scope(
                cost_analysis,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            if cost_analysis.based_on.inspection_result_id != inspection_result_id:
                raise ValueError("manual recommendation cost analysis lineage mismatch")
            matching_options = tuple(
                option
                for option in cost_analysis.options
                if option.action_candidate_id == action_candidate.action_candidate_id
                and option.action_code is action_code
            )
            if not matching_options:
                raise ValueError("manual recommendation cost analysis action mismatch")
            if source_cost_option_id is not None and not any(
                option.option_id == source_cost_option_id for option in matching_options
            ):
                raise ValueError(
                    "manual recommendation cost option does not exist or mismatches action"
                )
        inspection_work_order = self.repository.get_work_order(
            workspace_id=workspace_id,
            work_order_id=inspection_result.work_order_id,
        )
        if inspection_work_order is None:
            raise KeyError(inspection_result.work_order_id)
        authorization = inspection_work_order.authorization
        recommendation = create_operations_manual_recommendation(
            identity=EquipmentIdentity(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=inspection_result.asset_id,
                equipment_id=inspection_result.equipment_id,
                asset_type=inspection_result.asset_type,
            ),
            event_id=inspection_result.event_id,
            source_product_result_id=str(authorization.source_product_result_id),
            source_evidence_id=str(authorization.source_evidence_id),
            source_schema_version=str(authorization.source_schema_version),
            source_inspection_work_order_id=inspection_result.work_order_id,
            source_inspection_reference=inspection_result.inspection_result_id,
            authored_by=actor_id,
            authored_at=authored_at or datetime.now(timezone.utc),
            basis=(
                f"inspection_result:{inspection_result.inspection_result_id}",
                *payload.basis,
            ),
            action_code=action_code,
            source_cost_analysis_id=source_cost_analysis_id,
            source_cost_option_id=source_cost_option_id,
            source_action_candidate_id=source_action_candidate_id,
        )
        return self.repository.create_manual_recommendation(
            recommendation=recommendation,
            actor_display_name=actor_display_name,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "operations_manual.create",
                {
                    "inspection_result_id": inspection_result_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                    "source_cost_analysis_id": source_cost_analysis_id,
                    "source_cost_option_id": source_cost_option_id,
                    "source_action_candidate_id": source_action_candidate_id,
                },
            ),
        )

    @staticmethod
    def _derive_action_candidate(
        inspection_result: InspectionResult,
        action_code: MaintenanceActionCode,
    ):
        if action_code is MaintenanceActionCode.TOOL_REPLACEMENT:
            return derive_tool_replacement_action_candidate(inspection_result)
        if action_code is MaintenanceActionCode.COOLING_SYSTEM_RESTORE:
            return derive_cooling_system_restore_action_candidate(inspection_result)
        raise ValueError(f"unsupported maintenance action candidate: {action_code.value}")

    @staticmethod
    def _state_patch_for_action(
        action_code: MaintenanceActionCode,
        payload: Mapping[str, Any] | None = None,
    ) -> ToolReplacementStatePatch | CoolingSystemRestoreStatePatch:
        patch_type = {
            MaintenanceActionCode.TOOL_REPLACEMENT: ToolReplacementStatePatch,
            MaintenanceActionCode.COOLING_SYSTEM_RESTORE: CoolingSystemRestoreStatePatch,
        }[action_code]
        return patch_type() if payload is None else patch_type.model_validate(payload)

    def list_action_candidates(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        inspection_result_id: str,
    ) -> dict[str, Any]:
        inspection_result = self.repository.get_inspection_result(
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
        )
        if inspection_result is None:
            raise KeyError(inspection_result_id)
        self._require_scope(
            inspection_result,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if inspection_result.outcome is not InspectionOutcome.MAINTENANCE_RECOMMENDED:
            return {"inspection_result_id": inspection_result_id, "items": []}

        candidates = []
        for action_code in MaintenanceActionCode:
            try:
                candidate = self._derive_action_candidate(inspection_result, action_code)
            except ValueError:
                continue
            candidates.append(candidate.model_dump(mode="json"))
        return {"inspection_result_id": inspection_result_id, "items": candidates}

    def calculate_maintenance_cost(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        inspection_result_id: str,
        payload: MaintenanceCostAnalysisCreateRequest,
        actor_id: str,
        idempotency_key: str,
        calculated_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Calculate and append one decision-support snapshot.

        Scope, equipment, Diagnosis lineage, and Action candidate identity are
        resolved from canonical Maintenance records. TOOL_REPLACEMENT economic
        inputs come from the versioned Backend provider; the caller supplies
        only the Action and the SOP reference it consulted.
        """

        inspection_result = self.repository.get_inspection_result(
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
        )
        if inspection_result is None:
            raise KeyError(inspection_result_id)
        self._require_scope(
            inspection_result,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if inspection_result.outcome is not InspectionOutcome.MAINTENANCE_RECOMMENDED:
            raise ValueError(
                "cost analysis requires maintenance_recommended inspection outcome"
            )

        inspection_work_order = self.repository.get_work_order(
            workspace_id=workspace_id,
            work_order_id=inspection_result.work_order_id,
        )
        if inspection_work_order is None:
            raise KeyError(inspection_result.work_order_id)
        self._require_scope(
            inspection_work_order,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if inspection_work_order.work_type is not WorkOrderType.INSPECTION:
            raise ValueError("cost analysis requires an inspection work order")
        if inspection_work_order.status is not WorkOrderStatus.COMPLETED:
            raise ValueError("cost analysis requires a completed inspection work order")

        authorization = inspection_work_order.authorization
        source_product_result_id = authorization.source_product_result_id
        source_evidence_id = authorization.source_evidence_id
        if not source_product_result_id or not source_evidence_id:
            raise ValueError(
                "cost analysis requires Product Result/Evidence inspection lineage"
            )

        action_code = MaintenanceActionCode(payload.action_code)
        action_candidate = self._derive_action_candidate(inspection_result, action_code)
        action_candidate_id = action_candidate.action_candidate_id
        analysis_id = self._stable_id(
            "COST-ANALYSIS",
            organization_id,
            project_id,
            workspace_id,
            inspection_result_id,
            action_candidate_id,
            idempotency_key,
        )
        timestamp = calculated_at or datetime.now(timezone.utc)
        if self.cost_basis_provider is None:
            raise ValueError("Maintenance cost-basis provider is unavailable")
        resolution_context = derive_cost_basis_resolution_context(inspection_result)
        resolution_context.require_complete_for(action_code.value)
        if action_code is MaintenanceActionCode.TOOL_REPLACEMENT:
            cost_basis = self.cost_basis_provider.tool_replacement_basis(
                calculated_at=timestamp,
                context=resolution_context,
            )
        else:
            cost_basis = self.cost_basis_provider.cooling_system_restore_basis(
                calculated_at=timestamp,
                context=resolution_context,
            )
        result = calculate_maintenance_cost_scenarios(
            MaintenanceCostAnalysisInput(
                analysis_id=analysis_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=inspection_result.asset_id,
                equipment_id=inspection_result.asset_id,
                calculated_at=timestamp,
                based_on=CostAnalysisBasis(
                    product_result_id=source_product_result_id,
                    evidence_id=source_evidence_id,
                    inspection_work_order_id=inspection_result.work_order_id,
                    inspection_result_id=inspection_result.inspection_result_id,
                    sop_id=payload.sop_id,
                    sop_version=payload.sop_version,
                ),
                action_candidate_id=action_candidate_id,
                action_code=action_code,
                currency=cost_basis.currency,
                currency_minor_unit=cost_basis.currency_minor_unit,
                scenarios=cost_basis.scenarios,
                assumptions=cost_basis.assumptions,
                input_sources=cost_basis.input_sources,
                price_version=cost_basis.price_version,
                calculation_policy_version=cost_basis.calculation_policy_version,
            )
        )
        return self.repository.create_cost_analysis(
            result=result,
            event_id=inspection_result.event_id,
            actor_id=actor_id,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "maintenance.cost_analysis.calculate",
                {
                    "inspection_result_id": inspection_result_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
        )

    def calculate_tool_replacement_cost(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        inspection_result_id: str,
        payload: ToolReplacementCostAnalysisCreateRequest,
        actor_id: str,
        idempotency_key: str,
        calculated_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Compatibility entrypoint retained for existing TOOL_REPLACEMENT callers."""

        return self.calculate_maintenance_cost(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
            payload=payload,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            calculated_at=calculated_at,
        )

    def get_cost_analysis(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        analysis_id: str,
    ) -> dict[str, Any]:
        result = self.repository.get_cost_analysis(
            workspace_id=workspace_id,
            analysis_id=analysis_id,
        )
        if result is None:
            raise KeyError(analysis_id)
        self._require_scope(
            result,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        return result.model_dump(mode="json")

    def list_cost_analyses(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        inspection_result_id: str,
    ) -> dict[str, Any]:
        inspection_result = self.repository.get_inspection_result(
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
        )
        if inspection_result is None:
            raise KeyError(inspection_result_id)
        self._require_scope(
            inspection_result,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        results = self.repository.list_cost_analyses(
            workspace_id=workspace_id,
            inspection_result_id=inspection_result_id,
        )
        for result in results:
            self._require_scope(
                result,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        return {
            "inspection_result_id": inspection_result_id,
            "items": [result.model_dump(mode="json") for result in results],
        }

    def decide_manual_recommendation(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        recommendation_id: str,
        payload: RecommendationDecisionCreateRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        decided_at: datetime | None = None,
    ) -> dict[str, Any]:
        recommendation = self.repository.get_recommendation(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
        if recommendation is None:
            raise KeyError(recommendation_id)
        self._require_scope(
            recommendation,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if recommendation.recommendation_origin != "operations_manual":
            raise ValueError("only operations_manual recommendations use this command")
        timestamp = decided_at or datetime.now(timezone.utc)
        decision = RecommendationDecision(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            decision_id=self._stable_id(
                "RECOMMENDATION-DECISION",
                organization_id,
                project_id,
                workspace_id,
                recommendation_id,
                idempotency_key,
            ),
            event_id=recommendation.event_id,
            recommendation_id=recommendation_id,
            disposition=payload.disposition,
            actor_id=actor_id,
            decided_at=timestamp,
            note=payload.note,
        )
        decided = apply_recommendation_decision(recommendation, decision)
        work_order = None
        if payload.disposition is RecommendationDisposition.ACCEPT:
            work_order = create_work_order_for_recommendation(
                work_order_id=self._stable_id(
                    "MAINTENANCE-WO",
                    organization_id,
                    project_id,
                    workspace_id,
                    recommendation_id,
                ),
                recommendation=decided,
                decision=decision,
                idempotency_key=idempotency_key,
            )
        return self.repository.decide_recommendation(
            recommendation=decided,
            decision=decision,
            work_order=work_order,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "recommendation.decision",
                {
                    "recommendation_id": recommendation_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
            actor_display_name=actor_display_name,
        )

    def approve_maintenance_work_order(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        work_order_id: str,
        payload: MaintenanceWorkOrderApproveRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        approved_at: datetime | None = None,
    ) -> dict[str, Any]:
        work_order = self.repository.get_work_order(
            workspace_id=workspace_id,
            work_order_id=work_order_id,
        )
        if work_order is None:
            raise KeyError(work_order_id)
        self._require_scope(
            work_order,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if work_order.work_type is not WorkOrderType.MAINTENANCE:
            raise ValueError("work order is not maintenance work")
        if self.replay_session_query is None:
            raise ValueError("Diagnosis replay session validation is unavailable")

        recommendation_id = work_order.authorization.recommendation_id
        if recommendation_id is None:
            raise ValueError("maintenance work order has no recommendation authorization")
        recommendation = self.repository.get_recommendation(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
        if recommendation is None or recommendation.action_code is None:
            raise ValueError("authorized maintenance recommendation is unavailable")

        source_binding = self.replay_session_query.resolve_maintenance_source_session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            source_product_result_id=recommendation.source_product_result_id,
            equipment_id=work_order.equipment_id,
        )
        if source_binding is not None:
            replay_binding = source_binding
        elif payload.simulation_session_id is not None:
            # Historical Product Results may predate source-session lineage.
            # Compatibility never overrides lineage already recorded by a
            # current live Product Result.
            replay_binding = self.replay_session_query.resolve_maintenance_replay_session(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                session_id=payload.simulation_session_id,
                equipment_id=work_order.equipment_id,
            )
        else:
            raise SourceSimulationSessionUnavailable(
                "Product Result does not contain source simulation session lineage"
            )
        if not isinstance(replay_binding, Mapping):
            raise ValueError("Diagnosis returned an invalid replay session binding")
        self._require_row_scope(
            replay_binding,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if self._required_text(replay_binding, "equipment_id") != work_order.equipment_id:
            raise ValueError("replay session equipment identity mismatch")
        simulation_session_id = self._required_text(
            replay_binding, "simulation_session_id"
        )
        if (
            payload.simulation_session_id is not None
            and simulation_session_id != payload.simulation_session_id
        ):
            raise ValueError("replay session canonical identity mismatch")

        # Build the requested target without trusting caller-supplied lineage.
        # The repository checks the persisted current state before committing
        # and handles an identical Idempotency-Key replay before transition
        # validation.
        approved = work_order.model_copy(update={"status": WorkOrderStatus.APPROVED})
        action_code = MaintenanceActionCode(recommendation.action_code)
        action = plan_maintenance_action(
            work_order=approved,
            maintenance_action_id=self._stable_id(
                "MAINTENANCE-ACTION",
                organization_id,
                project_id,
                workspace_id,
                work_order_id,
            ),
            idempotency_key=idempotency_key,
        )
        return self.repository.approve_work_order(
            work_order=approved,
            action=action,
            simulation_session_id=simulation_session_id,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            approved_at=approved_at or datetime.now(timezone.utc),
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "maintenance.work_order.approve",
                {
                    "work_order_id": work_order_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
            action_code=action_code.value,
        )

    def start_maintenance(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        maintenance_action_id: str,
        payload: MaintenanceActionStartRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        started_at: datetime | None = None,
    ) -> dict[str, Any]:
        action = self.repository.get_maintenance_action(
            workspace_id=workspace_id,
            maintenance_action_id=maintenance_action_id,
        )
        if action is None:
            raise KeyError(maintenance_action_id)
        self._require_row_scope(
            action,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        event = MaintenanceStartedEvent(
            event_id=self._stable_event_id(
                "MAINTENANCE-INTEGRATION-EVENT", maintenance_action_id, "started"
            ),
            idempotency_key=f"{maintenance_action_id}:1",
            state_version=1,
            simulation_session_id=self._required_text(
                action, "simulation_session_id"
            ),
            maintenance_action_id=maintenance_action_id,
            work_order_id=self._required_text(action, "work_order_id"),
            equipment_id=self._required_text(action, "equipment_id"),
            maintenance_started_at=started_at or datetime.now(timezone.utc),
            action_code=self._required_text(action, "action_code"),
            caused_by=self._maintenance_cause(action),
        )
        return self.repository.start_maintenance(
            event,
            workspace_id=workspace_id,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "maintenance.action.start",
                {
                    "maintenance_action_id": maintenance_action_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
        )

    def complete_maintenance(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        maintenance_action_id: str,
        payload: MaintenanceActionCompleteRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        action = self.repository.get_maintenance_action(
            workspace_id=workspace_id,
            maintenance_action_id=maintenance_action_id,
        )
        if action is None:
            raise KeyError(maintenance_action_id)
        self._require_row_scope(
            action,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        timestamp = completed_at or datetime.now(timezone.utc)
        action_code = MaintenanceActionCode(self._required_text(action, "action_code"))
        event = MaintenanceCompletedEvent(
            event_id=self._stable_event_id(
                "MAINTENANCE-INTEGRATION-EVENT", maintenance_action_id, "completed"
            ),
            idempotency_key=f"{maintenance_action_id}:2",
            state_version=2,
            simulation_session_id=self._required_text(
                action, "simulation_session_id"
            ),
            maintenance_event_id=self._stable_id(
                "MAINTENANCE-EVENT",
                organization_id,
                project_id,
                workspace_id,
                maintenance_action_id,
            ),
            maintenance_action_id=maintenance_action_id,
            equipment_id=self._required_text(action, "equipment_id"),
            maintenance_started_at=self._stored_datetime(action, "started_at"),
            maintenance_completed_at=timestamp,
            action_code=action_code.value,
            state_patch=self._state_patch_for_action(action_code),
            caused_by=self._maintenance_cause(action),
        )
        return self.repository.complete_maintenance(
            event,
            workspace_id=workspace_id,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            outcome=payload.outcome,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "maintenance.action.complete",
                {
                    "maintenance_action_id": maintenance_action_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
        )

    def request_maintenance_replay(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        maintenance_event_id: str,
        payload: MaintenanceReplayRequest,
        actor_id: str,
        actor_display_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        maintenance = self.repository.get_maintenance_event(
            workspace_id=workspace_id,
            maintenance_event_id=maintenance_event_id,
        )
        if maintenance is None:
            raise KeyError(maintenance_event_id)
        self._require_row_scope(
            maintenance,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        action_code = MaintenanceActionCode(
            self._required_text(maintenance, "action_code")
        )
        event = MaintenanceReplayRequestedEvent(
            event_id=self._stable_event_id(
                "MAINTENANCE-INTEGRATION-EVENT",
                self._required_text(maintenance, "maintenance_action_id"),
                "replay-requested",
            ),
            idempotency_key=(
                f"{self._required_text(maintenance, 'maintenance_action_id')}:3"
            ),
            state_version=3,
            simulation_session_id=self._required_text(
                maintenance, "simulation_session_id"
            ),
            maintenance_event_id=maintenance_event_id,
            maintenance_action_id=self._required_text(
                maintenance, "maintenance_action_id"
            ),
            equipment_id=self._required_text(maintenance, "equipment_id"),
            maintenance_started_at=self._stored_datetime(
                maintenance, "maintenance_started_at"
            ),
            maintenance_completed_at=self._stored_datetime(
                maintenance, "completed_at"
            ),
            restart_at=payload.restart_at,
            action_code=action_code.value,
            state_patch=self._state_patch_for_action(
                action_code, maintenance["state_patch"]
            ),
            caused_by=self._maintenance_cause(maintenance),
        )
        return self.repository.request_replay(
            event,
            workspace_id=workspace_id,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            request_idempotency_key=idempotency_key,
            request_fingerprint=self._fingerprint(
                "maintenance.replay.request",
                {
                    "maintenance_event_id": maintenance_event_id,
                    "payload": payload.model_dump(mode="json"),
                    "actor_id": actor_id,
                },
            ),
        )

    def event_lineage(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        lineage = self.repository.event_lineage(
            workspace_id=workspace_id,
            event_id=event_id,
        )
        for collection in (
            "recommendations",
            "decisions",
            "work_orders",
            "inspection_results",
            "maintenance_actions",
            "maintenance_events",
            "cost_analyses",
            "activities",
        ):
            for record in lineage[collection]:
                for field, expected in (
                    ("organization_id", organization_id),
                    ("project_id", project_id),
                    ("workspace_id", workspace_id),
                ):
                    if record.get(field) != expected:
                        raise ValueError(f"{field} scope mismatch")
        return lineage


__all__ = ["MaintenanceLoopService"]
