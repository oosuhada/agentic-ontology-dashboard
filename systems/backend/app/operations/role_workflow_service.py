from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .contracts import ReportRequest
from app.dashboard.dashboard_schema import DashboardTemplatePublishRequest
from app.dashboard.ports import DashboardApplicationPort
from app.identity.contracts import AuthError, Principal
from app.ontology.ontology_domain import registry_payload
from app.ontology.ports import OntologyActionHistoryPort
from .role_workflow_models import (
    ApprovalDecisionRequest,
    AuditExportCheckpointRequest,
    AuditReconstruction,
    ExecutiveOverview,
    FDEWorkbench,
    FieldTaskActionRequest,
    FieldTaskWorkspace,
    ModelConsole,
    ModelReleaseRequestCreate,
    TemplatePublishRequestCreate,
)
from .ports import FactorySignalApplicationPort, RoleWorkflowRepositoryPort
from .service import EventNotFound, RISK_PRIORITY


class RoleWorkflowService:
    def __init__(
        self,
        legacy_service: FactorySignalApplicationPort,
        *,
        repository: RoleWorkflowRepositoryPort,
        ontology: OntologyActionHistoryPort,
        dashboards: DashboardApplicationPort,
    ) -> None:
        self.legacy_service = legacy_service
        self.repository = repository
        self.ontology = ontology
        self.dashboards = dashboards

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _require_role(principal: Principal, *roles: str) -> None:
        if not set(principal.roles).intersection(roles):
            raise AuthError(403, "role_context_denied", "현재 역할에 허용되지 않은 역할 전용 화면입니다.")

    def executive_overview(self, *, principal: Principal, workspace_id: str) -> ExecutiveOverview:
        self._require_role(principal, "executive_viewer", "tenant_admin", "fde")
        events = self.legacy_service.list_events()
        activities = {
            event["event_id"]: self.legacy_service.event_activity(event["event_id"])
            for event in events
        }
        status_counts = Counter(event["status"] for event in events)
        unresolved = [
            event
            for event in events
            if event["status"] in {"critical", "warning", "data_quality_hold"}
            and not activities[event["event_id"]]["decisions"]
        ]
        unresolved.sort(
            key=lambda event: (
                RISK_PRIORITY[event["status"]],
                -(event["failure_probability"] or 0.0),
            )
        )
        affected = [event for event in events if event["status"] != "normal"]
        estimated_minutes = sum(
            int(event["equipment"].get("estimated_downtime_minutes") or 0)
            for event in affected
        )
        high_criticality_minutes = sum(
            int(event["equipment"].get("estimated_downtime_minutes") or 0)
            for event in affected
            if event["equipment"].get("criticality") == "high"
        )
        risk_values = [event["failure_probability"] for event in events if event["failure_probability"] is not None]
        risk_trend = []
        for event in sorted(
            events,
            key=lambda item: self.legacy_service.fixture_snapshot(item["event_id"])[
                "observation"
            ]["timestamp"],
        ):
            fixture = self.legacy_service.fixture_snapshot(event["event_id"])
            risk_trend.append(
                {
                    "observed_at": fixture["observation"]["timestamp"],
                    "event_id": event["event_id"],
                    "equipment": event["equipment"]["display_name"],
                    "status": event["status"],
                    "risk_score": event["failure_probability"],
                }
            )
        return ExecutiveOverview(
            workspace_id=workspace_id,
            generated_at=self._now(),
            aggregate={
                "equipment_count": len({event["equipment"]["equipment_id"] for event in events}),
                "event_count": len(events),
                "affected_event_count": len(affected),
                "unresolved_critical_count": len(unresolved),
                "average_failure_probability": round(statistics.mean(risk_values), 4) if risk_values else None,
                "estimated_downtime_minutes": estimated_minutes,
            },
            status_distribution=[
                {"status": status, "count": status_counts.get(status, 0)}
                for status in ["critical", "warning", "attention", "data_quality_hold", "normal"]
            ],
            risk_trend=risk_trend,
            unresolved_critical_events=[
                {
                    **event,
                    "estimated_downtime_minutes": event["equipment"].get("estimated_downtime_minutes"),
                    "decision_count": len(activities[event["event_id"]]["decisions"]),
                }
                for event in unresolved[:10]
            ],
            business_impact={
                "estimated_downtime_minutes": estimated_minutes,
                "high_criticality_estimated_minutes": high_criticality_minutes,
                "spare_part_gap_count": sum(
                    1 for event in affected if event["equipment"].get("spare_part_available") is False
                ),
                "currency_impact": None,
                "basis": "fixture equipment estimated_downtime_minutes 합계",
            },
            assumptions=[
                "정지 영향은 fixture에 기록된 설비별 estimated_downtime_minutes의 단순 합계입니다.",
                "금액 영향은 생산 단가·실제 정지 시간 데이터가 없어 계산하지 않습니다.",
                "미조치 사건은 운영 decision 기록이 없는 critical·warning·data-quality 사건입니다.",
            ],
        )

    def audit_reconstruction(
        self,
        *,
        principal: Principal,
        workspace_id: str,
        event_id: str,
    ) -> AuditReconstruction:
        self._require_role(principal, "quality_auditor", "tenant_admin", "fde")
        fixture = self.legacy_service.fixture_snapshot(event_id)
        evidence = self.legacy_service.evidence_snapshot(event_id)
        report, report_trace = self.legacy_service.report(
            event_id,
            ReportRequest(role="manager", use_llm=False),
        )
        activity = self.legacy_service.event_activity(event_id)
        ontology_actions = (
            self.ontology.list_actions_for_object(
                workspace_id=workspace_id,
                object_id=f"risk_event:{event_id}",
            )
            + self.ontology.list_actions_for_object(
                workspace_id=workspace_id,
                object_id=f"work_order:{event_id}",
            )
            + self.ontology.list_actions_for_object(
                workspace_id=workspace_id,
                object_id=f"inspection:{event_id}",
            )
        )
        field_actions = self.repository.list_field_actions(
            workspace_id=workspace_id,
            event_id=event_id,
        )
        action_history: list[dict[str, Any]] = []
        for decision in activity["decisions"]:
            action_history.append({"type": "decision", **decision})
        for note in activity["notes"]:
            action_history.append({"type": "note", **note})
        for action in ontology_actions:
            action_history.append(
                {
                    "type": "ontology_action",
                    "id": action["id"],
                    "action": action["action_type"],
                    "actor": action["actor_display_name"],
                    "state": action["state"],
                    "audit_id": action["audit_id"],
                    "created_at": action["created_at"],
                    "completed_at": action["completed_at"],
                }
            )
        for action in field_actions:
            action_history.append(
                {
                    "type": "field_task_action",
                    "id": action["id"],
                    "action": action["action"],
                    "actor": action["actor_display_name"],
                    "state": action["status"],
                    "payload": action["payload"],
                    "created_at": action["created_at"],
                }
            )
        action_history.sort(key=lambda item: item.get("created_at") or "")
        trace = [
            {
                "section_id": section.section_id,
                "title": section.title,
                "evidence_field_ids": section.evidence_field_ids,
                "report_id": report.report_id,
            }
            for section in report.sections
        ]
        return AuditReconstruction(
            workspace_id=workspace_id,
            event_id=event_id,
            reconstructed_at=self._now(),
            input_snapshot={
                "schema_version": fixture["schema_version"],
                "scenario_id": fixture["scenario_id"],
                "equipment": fixture["equipment"],
                "observation": fixture["observation"],
                "history": fixture["history"],
                "runtime": fixture["runtime"],
            },
            version_snapshot={
                "fixture_schema_version": evidence["lineage"].get("fixture_schema_version"),
                "model_version": evidence["model"]["model_version"],
                "policy_version": evidence["model"]["policy_version"],
                "context_version": evidence["maintenance_context"]["version"],
                "evidence_id": evidence["evidence_id"],
                "evidence_generated_at": evidence["generated_at"],
                "report_id": report.report_id,
                "report_mode": report.mode,
                "report_trace": report_trace,
            },
            evidence_to_report_trace=trace,
            action_history=action_history,
            export_checkpoints=self.repository.list_export_checkpoints(
                workspace_id=workspace_id,
                event_id=event_id,
            ),
        )

    def create_audit_export_checkpoint(
        self,
        *,
        principal: Principal,
        request: AuditExportCheckpointRequest,
    ) -> dict[str, Any]:
        self._require_role(principal, "quality_auditor", "tenant_admin")
        reconstruction = self.audit_reconstruction(
            principal=principal,
            workspace_id=request.workspace_id,
            event_id=request.event_id,
        )
        snapshot = reconstruction.model_dump(mode="json")
        snapshot["export_checkpoints"] = []
        checkpoint = self.repository.create_export_checkpoint(
            workspace_id=request.workspace_id,
            event_id=request.event_id,
            export_format=request.export_format,
            reason=request.reason,
            requested_by=principal.user_id,
            requested_by_name=principal.display_name,
            snapshot=snapshot,
        )
        audit = self.legacy_service.record_audit(
            event_id=request.event_id,
            run_id=checkpoint["id"],
            action="audit.export.checkpoint",
            model_version=reconstruction.version_snapshot.get("model_version"),
            payload=checkpoint,
        )
        return {**checkpoint, "audit_id": audit["id"]}

    def field_workspace(self, *, principal: Principal, workspace_id: str) -> FieldTaskWorkspace:
        self._require_role(principal, "maintenance_technician", "process_engineer", "tenant_admin", "fde")
        latest = self.repository.latest_field_statuses(workspace_id=workspace_id)
        tasks: list[dict[str, Any]] = []
        for event in self.legacy_service.list_events():
            if event["status"] == "normal":
                continue
            evidence = self.legacy_service.evidence_snapshot(event["event_id"])
            latest_action = latest.get(event["event_id"])
            tasks.append(
                {
                    "task_id": f"work_order:{event['event_id']}",
                    "event_id": event["event_id"],
                    "equipment": event["equipment"],
                    "risk_status": event["status"],
                    "task_status": latest_action["status"] if latest_action else "assigned",
                    "priority": RISK_PRIORITY[event["status"]],
                    "location": event["equipment"]["line"],
                    "safety": [
                        "작업 전 설비 에너지 차단 상태를 현장 절차에 따라 확인합니다.",
                        "회전체와 고온부 접근 전 보호구와 접근 허가를 확인합니다.",
                        "안전 위험이 있으면 작업을 진행하지 않고 blocked Action을 기록합니다.",
                    ],
                    "checklist": evidence["maintenance_context"]["checklist"],
                    "measurement_schema": {
                        "tool_wear_min": "number",
                        "torque_nm": "number",
                        "process_temperature_k": "number",
                        "rotational_speed_rpm": "number",
                    },
                    "photo_policy": {
                        "metadata_only": True,
                        "accepted_fields": ["filename", "captured_at", "mime_type", "size_bytes", "caption", "sha256"],
                    },
                    "latest_action": latest_action,
                }
            )
        tasks.sort(key=lambda item: (item["priority"], item["event_id"]))
        return FieldTaskWorkspace(
            workspace_id=workspace_id,
            generated_at=self._now(),
            tasks=tasks,
            offline_queue_design={
                "implemented": False,
                "future_option": True,
                "queue_key": "client_action_id",
                "conflict_policy": "server task status and idempotency key win",
                "note": "현재는 온라인 Action만 실행하며 offline queue는 후속 구현 경계로만 정의합니다.",
            },
        )

    def record_field_task_action(
        self,
        *,
        principal: Principal,
        request: FieldTaskActionRequest,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(principal, "maintenance_technician", "process_engineer", "tenant_admin", "fde")
        self.legacy_service.fixture_snapshot(request.event_id)
        if request.action == "complete" and not request.checklist:
            raise ValueError("complete Action에는 완료한 checklist가 필요합니다.")
        if request.action == "blocked" and not request.note:
            raise ValueError("blocked Action에는 작업 불가 사유가 필요합니다.")
        payload = request.model_dump(mode="json")
        record = self.repository.record_field_action(
            workspace_id=request.workspace_id,
            event_id=request.event_id,
            action=request.action,
            actor_user_id=principal.user_id,
            actor_display_name=principal.display_name,
            payload=payload,
        )
        audit = self.legacy_service.record_audit(
            event_id=request.event_id,
            run_id=invocation_id or record["id"],
            action=f"field.task.{request.action}",
            model_version=None,
            payload=record,
        )
        return {**record, "audit_id": audit["id"]}

    def fde_workbench(self, *, principal: Principal, workspace_id: str) -> FDEWorkbench:
        self._require_role(principal, "fde", "tenant_admin")
        registry = registry_payload()
        diagnostics: list[dict[str, Any]] = []
        integration_health: list[dict[str, Any]] = []
        for event_id, fixture in self.legacy_service.fixture_items():
            evidence = self.legacy_service.evidence_snapshot(event_id)
            runtime = fixture["runtime"]
            status = "healthy"
            issues: list[str] = []
            if not runtime["llm_available"]:
                issues.append("llm_provider_unavailable")
            if not runtime["planner_available"]:
                issues.append("planner_provider_unavailable")
            if evidence["data_quality_warnings"]:
                issues.append("data_quality_warning")
            if issues:
                status = "degraded"
                diagnostics.append(
                    {
                        "event_id": event_id,
                        "scenario_id": fixture["scenario_id"],
                        "severity": "warning" if len(issues) == 1 else "attention",
                        "codes": issues,
                        "safe_fallback": True,
                    }
                )
            integration_health.append(
                {
                    "event_id": event_id,
                    "context_provider": runtime["context_provider"],
                    "llm_available": runtime["llm_available"],
                    "planner_available": runtime["planner_available"],
                    "status": status,
                }
            )
        template_requests = self.repository.list_workflow_requests(
            table="template_publish_requests",
            workspace_id=workspace_id,
            requested_by=None if "tenant_admin" in principal.roles else principal.user_id,
        )
        return FDEWorkbench(
            workspace_id=workspace_id,
            generated_at=self._now(),
            customer_workspace={
                "workspace_id": workspace_id,
                "domain_pack": "manufacturing-predictive-maintenance",
                "event_count": self.legacy_service.fixture_count(),
                "equipment_count": len(self.legacy_service.list_equipment()),
                "template_roles": 8,
            },
            ontology_registry={
                "object_type_count": len(registry["object_types"]),
                "link_type_count": len(registry["link_types"]),
                "action_type_count": len(registry["action_types"]),
                "object_types": registry["object_types"],
                "link_types": registry["link_types"],
                "action_types": registry["action_types"],
            },
            integration_health=integration_health,
            deployment_checklist=[
                {"id": "identity", "label": "Identity·workspace scope 확인", "status": "ready"},
                {"id": "ontology", "label": "Object·Link·Action registry 검증", "status": "ready"},
                {"id": "fixtures", "label": "Gold fixture 8건 계약 검증", "status": "ready"},
                {"id": "providers", "label": "Provider fallback 및 diagnostic 확인", "status": "attention" if diagnostics else "ready"},
                {"id": "approval", "label": "Template publish 승인 workflow", "status": "ready"},
                {"id": "secrets", "label": "Credential·secret 비노출", "status": "ready"},
            ],
            diagnostic_events=diagnostics,
            template_requests=template_requests,
            security_boundaries=[
                "FDE는 사용자 비밀번호 hash, session token, provider secret을 조회할 수 없습니다.",
                "FDE template 변경은 pending approval 요청으로만 제출됩니다.",
                "Tenant admin 승인 전 published template version은 변경되지 않습니다.",
            ],
        )

    def create_template_publish_request(
        self,
        *,
        principal: Principal,
        request: TemplatePublishRequestCreate,
    ) -> dict[str, Any]:
        self._require_role(principal, "fde", "tenant_admin")
        current = self.dashboards.current_template(
            workspace_id=request.workspace_id,
            role_code=request.target_role,
        )
        publish_request = DashboardTemplatePublishRequest.model_validate(
            {
                "workspace_id": request.workspace_id,
                "display_name": request.display_name,
                "tabs": request.tabs,
                "parameter_definitions": request.parameter_definitions,
            }
        )
        self.dashboards.validate_template_draft(
            role_code=request.target_role,
            template=current,
            request=publish_request,
        )
        record = self.repository.create_template_publish_request(
            workspace_id=request.workspace_id,
            target_role=request.target_role,
            requested_by=principal.user_id,
            requested_by_name=principal.display_name,
            payload={
                **publish_request.model_dump(mode="json"),
                "change_summary": request.change_summary,
                "base_template_version": current.version,
            },
        )
        audit = self.legacy_service.record_audit(
            event_id=None,
            run_id=record["id"],
            action="dashboard.template.publish_requested",
            model_version=None,
            payload={
                "request_id": record["id"],
                "workspace_id": request.workspace_id,
                "target_role": request.target_role,
                "requested_by": principal.user_id,
                "base_template_version": current.version,
            },
        )
        return {**record, "audit_id": audit["id"]}

    def model_console(self, *, principal: Principal, workspace_id: str) -> ModelConsole:
        self._require_role(principal, "ml_validator", "tenant_admin", "fde")
        fixture_items = self.legacy_service.fixture_items()
        evidence_items = [
            self.legacy_service.evidence_snapshot(event_id)
            for event_id, _ in fixture_items
        ]
        model_counter = Counter(item["model"]["model_version"] for item in evidence_items)
        policy_counter = Counter(item["model"]["policy_version"] for item in evidence_items)
        schema_counter = Counter(item["lineage"].get("fixture_schema_version", "unknown") for item in evidence_items)
        actual_rows: list[dict[str, Any]] = []
        passed = 0
        for event_id, fixture in fixture_items:
            evidence = self.legacy_service.evidence_snapshot(event_id)
            expected = fixture["expected"]
            row_pass = (
                evidence["status"] == expected["risk_band"]
                and evidence["recommended_decision"] == expected["recommended_decision"]
                and evidence["confidence"] == expected["confidence"]
            )
            if row_pass:
                passed += 1
            actual_rows.append(
                {
                    "event_id": event_id,
                    "scenario_id": fixture["scenario_id"],
                    "expected_status": expected["risk_band"],
                    "actual_status": evidence["status"],
                    "expected_decision": expected["recommended_decision"],
                    "actual_decision": evidence["recommended_decision"],
                    "pass": row_pass,
                }
            )
        thresholds = sorted({float(item["threshold"]) for item in evidence_items})
        threshold_cost = []
        probabilities = [item["failure_probability"] for item in evidence_items]
        for threshold in [0.45, 0.55, 0.65]:
            intervention_count = sum(
                1 for probability in probabilities if probability is not None and probability >= threshold
            )
            missed_expected_risk = sum(
                1
                for evidence, (_, fixture) in zip(evidence_items, fixture_items)
                if fixture["expected"]["risk_band"] in {"warning", "critical"}
                and (evidence["failure_probability"] is None or evidence["failure_probability"] < threshold)
            )
            threshold_cost.append(
                {
                    "threshold": threshold,
                    "intervention_count": intervention_count,
                    "missed_expected_warning_or_critical": missed_expected_risk,
                    "cost_formula": "intervention_count + 5 * missed_expected_warning_or_critical",
                    "relative_cost": intervention_count + 5 * missed_expected_risk,
                }
            )
        slice_counts: dict[tuple[str, str], int] = defaultdict(int)
        for evidence in evidence_items:
            slice_counts[(evidence["status"], evidence["equipment"]["criticality"])] += 1
        drift_and_schema: list[dict[str, Any]] = []
        for evidence in evidence_items:
            if evidence["data_quality_warnings"]:
                drift_and_schema.append(
                    {
                        "event_id": evidence["event_id"],
                        "kind": "schema_or_quality_anomaly",
                        "warnings": evidence["data_quality_warnings"],
                    }
                )
        release_requests = self.repository.list_workflow_requests(
            table="model_release_requests",
            workspace_id=workspace_id,
            requested_by=None if "tenant_admin" in principal.roles else principal.user_id,
        )
        return ModelConsole(
            workspace_id=workspace_id,
            generated_at=self._now(),
            model_versions=[
                {"model_version": version, "evidence_count": count, "mode": "operational inference"}
                for version, count in sorted(model_counter.items())
            ],
            dataset_versions=[
                {"dataset_version": f"fixture-schema-{version}", "record_count": count, "source": "Gold fixtures"}
                for version, count in sorted(schema_counter.items())
            ],
            training_metrics={
                "scope": "training_or_offline_evaluation",
                "available": False,
                "reason": "현재 fixture heuristic에는 학습 run metric artifact가 연결되지 않았습니다.",
                "metrics": {},
            },
            operational_thresholds={
                "scope": "production_decision_policy",
                "policy_versions": [
                    {"policy_version": version, "evidence_count": count}
                    for version, count in sorted(policy_counter.items())
                ],
                "threshold_values": thresholds,
                "note": "운영 threshold는 학습 accuracy와 별도 계약으로 표시합니다.",
            },
            threshold_cost=threshold_cost,
            slices=[
                {"status": status, "criticality": criticality, "count": count}
                for (status, criticality), count in sorted(slice_counts.items())
            ],
            drift_and_schema=drift_and_schema or [
                {"kind": "schema_monitor", "status": "no_unresolved_schema_anomaly", "schema_versions": dict(schema_counter)}
            ],
            gold_regression={
                "scenario_count": len(actual_rows),
                "passed": passed,
                "failed": len(actual_rows) - passed,
                "pass": passed == len(actual_rows),
                "items": actual_rows,
            },
            release_requests=release_requests,
        )

    def create_model_release_request(
        self,
        *,
        principal: Principal,
        request: ModelReleaseRequestCreate,
    ) -> dict[str, Any]:
        self._require_role(principal, "ml_validator", "tenant_admin")
        record = self.repository.create_model_release_request(
            workspace_id=request.workspace_id,
            requested_by=principal.user_id,
            requested_by_name=principal.display_name,
            payload=request.model_dump(mode="json"),
        )
        audit = self.legacy_service.record_audit(
            event_id=None,
            run_id=record["id"],
            action="model.release.requested",
            model_version=request.model_version,
            payload={
                "request_id": record["id"],
                "workspace_id": request.workspace_id,
                "model_version": request.model_version,
                "dataset_version": request.dataset_version,
                "policy_version": request.policy_version,
                "requested_by": principal.user_id,
            },
        )
        return {**record, "audit_id": audit["id"]}

    def list_admin_approvals(self, *, principal: Principal) -> dict[str, Any]:
        self._require_role(principal, "tenant_admin")
        return {
            "template_publish_requests": self.repository.list_workflow_requests(
                table="template_publish_requests",
                organization_id=principal.organization_id,
                project_id=principal.active_project_id,
            ),
            "model_release_requests": self.repository.list_workflow_requests(
                table="model_release_requests",
                organization_id=principal.organization_id,
                project_id=principal.active_project_id,
            ),
        }

    def decide_template_request(
        self,
        *,
        principal: Principal,
        request_id: str,
        decision: ApprovalDecisionRequest,
    ) -> dict[str, Any]:
        self._require_role(principal, "tenant_admin")
        existing = self.repository.get_workflow_request(
            table="template_publish_requests",
            request_id=request_id,
            project_id=principal.active_project_id,
        )
        published = None
        if decision.decision == "approve":
            payload = existing["payload"]
            publish_request = DashboardTemplatePublishRequest.model_validate(
                {
                    "workspace_id": existing["workspace_id"],
                    "display_name": payload["display_name"],
                    "tabs": payload["tabs"],
                    "parameter_definitions": payload.get("parameter_definitions", []),
                }
            )
            published = self.dashboards.publish_template(
                principal=principal,
                target_role=existing["target_role"],
                request=publish_request,
            )
        updated = self.repository.decide_workflow_request(
            table="template_publish_requests",
            request_id=request_id,
            decision=decision.decision,
            decision_by=principal.user_id,
            decision_by_name=principal.display_name,
            note=decision.note,
            project_id=existing["project_id"],
        )
        audit = self.legacy_service.record_audit(
            event_id=None,
            run_id=request_id,
            action=f"dashboard.template.publish_{decision.decision}d",
            model_version=None,
            payload={
                "request_id": request_id,
                "target_role": existing["target_role"],
                "decision_by": principal.user_id,
                "published_version": published.version if published is not None else None,
                "note": decision.note,
            },
        )
        return {
            **updated,
            "published_template": published.model_dump(mode="json") if published is not None else None,
            "audit_id": audit["id"],
        }

    def decide_model_release_request(
        self,
        *,
        principal: Principal,
        request_id: str,
        decision: ApprovalDecisionRequest,
    ) -> dict[str, Any]:
        self._require_role(principal, "tenant_admin")
        existing = self.repository.get_workflow_request(
            table="model_release_requests",
            request_id=request_id,
            project_id=principal.active_project_id,
        )
        updated = self.repository.decide_workflow_request(
            table="model_release_requests",
            request_id=request_id,
            decision=decision.decision,
            decision_by=principal.user_id,
            decision_by_name=principal.display_name,
            note=decision.note,
            project_id=existing["project_id"],
        )
        audit = self.legacy_service.record_audit(
            event_id=None,
            run_id=request_id,
            action=f"model.release.{decision.decision}d",
            model_version=existing["payload"].get("model_version"),
            payload={
                "request_id": request_id,
                "decision_by": principal.user_id,
                "status": updated["status"],
                "note": decision.note,
            },
        )
        return {**updated, "audit_id": audit["id"]}
