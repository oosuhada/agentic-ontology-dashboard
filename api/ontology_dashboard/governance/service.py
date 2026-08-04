"""Project-scoped governance aggregation without tenant-admin account controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..datasets.repository import DatasetRepository
from ..identity import AuthError, Principal
from ..orchestration.repository import AgentRunRepository
from ..role_workflow_service import RoleWorkflowService
from .models import (
    GovernanceAccess,
    GovernanceAgentRun,
    GovernanceAgentRunDetail,
    GovernanceApproval,
    GovernanceCounts,
    GovernanceLineage,
    GovernanceOverview,
    GovernanceProjection,
    ProjectionRetryResult,
)


class GovernanceService:
    def __init__(
        self,
        *,
        datasets: DatasetRepository,
        agents: AgentRunRepository,
        workflows: RoleWorkflowService,
    ) -> None:
        self.datasets = datasets
        self.agents = agents
        self.workflows = workflows

    @staticmethod
    def _require_scope(principal: Principal, project_id: str, workspace_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id and principal.active_project_id != project_id:
            raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")
        if workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "허용된 workspace 범위를 벗어난 요청입니다.")

    @staticmethod
    def _projection(record: dict[str, Any], *, can_retry: bool) -> GovernanceProjection:
        return GovernanceProjection(
            id=record["id"],
            dataset_id=record["dataset_id"],
            dataset_name=record.get("dataset_name") or record["dataset_id"],
            dataset_version_id=record["dataset_version_id"],
            version_label=record.get("version_label") or record["dataset_version_id"],
            store_kind=record["store_kind"],
            status=record["status"],
            source_version=record["source_version"],
            object_namespace=record["object_namespace"],
            record_count=int(record.get("record_count") or 0),
            attempt_count=int(record.get("attempt_count") or 0),
            last_error=record.get("last_error"),
            updated_at=record["updated_at"],
            can_retry=can_retry and record["status"] == "failed",
        )

    def overview(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
    ) -> GovernanceOverview:
        self._require_scope(principal, project_id, workspace_id)
        can_retry = "governance.projection.retry" in principal.permissions
        datasets = [
            item
            for item in self.datasets.list_datasets(
                organization_id=principal.organization_id,
                project_id=project_id,
            )
            if item["workspace_id"] == workspace_id
        ]
        projection_rows = self.datasets.list_project_projections(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        projections = [self._projection(item, can_retry=can_retry) for item in projection_rows]
        runs = self.agents.list_runs(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=100,
        )
        agent_runs = [
            GovernanceAgentRun(
                run_id=item.run_id,
                workspace_id=item.workspace_id,
                question=item.question,
                route=item.route,
                status=item.status,
                evidence_count=len(item.evidence),
                claim_count=len(item.claims),
                checkpoint_sequence=item.checkpoint_sequence,
                caveats=item.caveats,
                error=item.error,
            )
            for item in runs
        ]
        approvals = self._approvals(
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        lineage: list[GovernanceLineage] = []
        version_count = 0
        materialization_count = 0
        for dataset in datasets:
            detail = self.datasets.get_dataset(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset["id"],
            )
            versions = self.datasets.list_versions(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset["id"],
            )
            materializations = self.datasets.list_materializations(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset["id"],
            )
            version_count += len(versions)
            materialization_count += len(materializations)
            references = sorted(
                {
                    str(item.get("source_reference"))
                    for item in materializations
                    if item.get("source_reference")
                }
            )
            lineage.append(
                GovernanceLineage(
                    dataset_id=detail["id"],
                    dataset_name=detail["display_name"],
                    latest_version_id=detail.get("latest_version_id"),
                    latest_source_version=detail.get("latest_source_version"),
                    version_count=len(versions),
                    materialization_count=len(materializations),
                    downstream_references=references,
                )
            )
        counts = GovernanceCounts(
            datasets=len(datasets),
            dataset_versions=version_count,
            materializations=materialization_count,
            projections=len(projections),
            failed_projections=sum(item.status == "failed" for item in projections),
            pending_projections=sum(item.status in {"pending", "indexing"} for item in projections),
            agent_runs=len(agent_runs),
            failed_agent_runs=sum(item.status == "failed" for item in agent_runs),
            pending_approvals=sum(item.status == "pending_approval" for item in approvals),
        )
        return GovernanceOverview(
            generated_at=datetime.now(timezone.utc),
            access=GovernanceAccess(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=principal.user_id,
                roles=principal.active_project_roles or principal.roles,
                permissions=sorted(principal.permissions),
                can_retry_projection=can_retry,
            ),
            counts=counts,
            projections=projections,
            agent_runs=agent_runs,
            approvals=approvals,
            lineage=lineage,
            policy_boundaries=[
                "이 화면은 Project governance만 다루며 사용자 계정·비밀번호·tenant admin 제어는 포함하지 않습니다.",
                "Agent claim은 저장된 evidence ID와 trace가 연결된 경우에만 재구성합니다.",
                "Graph/vector projection이 stale 또는 failed이면 relational source와 동일한 fresh 상태로 표현하지 않습니다.",
                "Projection retry는 governance.projection.retry 권한이 있는 FDE 또는 tenant admin만 수행할 수 있습니다.",
            ],
        )

    def _approvals(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
    ) -> list[GovernanceApproval]:
        rows: list[dict[str, Any]] = []
        for table in ("template_publish_requests", "model_release_requests"):
            rows.extend(
                self.workflows.repository.list_workflow_requests(
                    table=table,
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
            )
        rows.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)
        return [
            GovernanceApproval(
                id=item["id"],
                workflow_type=item["workflow_type"],
                workspace_id=item["workspace_id"],
                target_role=item.get("target_role"),
                requested_by=item["requested_by"],
                requested_by_name=item["requested_by_name"],
                status=item["status"],
                payload=item.get("payload") or {},
                created_at=item["created_at"],
                decision_by_name=item.get("decision_by_name"),
                decision_note=item.get("decision_note"),
            )
            for item in rows
        ]

    def agent_run(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
        run_id: str,
    ) -> GovernanceAgentRunDetail:
        self._require_scope(principal, project_id, workspace_id)
        state = self.agents.get(
            organization_id=principal.organization_id,
            project_id=project_id,
            run_id=run_id,
        )
        if state.workspace_id != workspace_id:
            raise AuthError(403, "workspace_scope_denied", "Agent run은 다른 workspace에 속합니다.")
        return GovernanceAgentRunDetail(
            state=state,
            traces=self.agents.traces(
                organization_id=principal.organization_id,
                project_id=project_id,
                run_id=run_id,
            ),
            checkpoints=self.agents.checkpoints(
                organization_id=principal.organization_id,
                project_id=project_id,
                run_id=run_id,
            ),
        )

    def retry_projection(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
        projection_id: str,
    ) -> ProjectionRetryResult:
        self._require_scope(principal, project_id, workspace_id)
        if "governance.projection.retry" not in principal.permissions:
            raise AuthError(403, "permission_denied", "Projection retry 권한이 없습니다.")
        projection = self.datasets.get_projection(
            organization_id=principal.organization_id,
            project_id=project_id,
            projection_id=projection_id,
        )
        if projection["workspace_id"] != workspace_id:
            raise AuthError(403, "workspace_scope_denied", "Projection은 다른 workspace에 속합니다.")
        self.datasets.retry_projection(
            organization_id=principal.organization_id,
            project_id=project_id,
            projection_id=projection_id,
        )
        refreshed = next(
            item
            for item in self.datasets.list_project_projections(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            if item["id"] == projection_id
        )
        return ProjectionRetryResult(
            projection=self._projection(refreshed, can_retry=True),
            message="실패한 projection을 pending 상태로 되돌렸습니다. Worker가 다음 cycle에 재처리합니다.",
        )
