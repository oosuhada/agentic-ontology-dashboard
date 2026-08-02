"""Typed contracts for the project-scoped Governance Workbench."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..orchestration.models import AgentState, AgentTraceRecord


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GovernanceAccess(StrictModel):
    organization_id: str
    project_id: str
    workspace_id: str
    user_id: str
    roles: list[str]
    permissions: list[str]
    can_retry_projection: bool
    tenant_admin_controls_excluded: bool = True


class GovernanceCounts(StrictModel):
    datasets: int = 0
    dataset_versions: int = 0
    materializations: int = 0
    projections: int = 0
    failed_projections: int = 0
    pending_projections: int = 0
    agent_runs: int = 0
    failed_agent_runs: int = 0
    pending_approvals: int = 0


class GovernanceProjection(StrictModel):
    id: str
    dataset_id: str
    dataset_name: str
    dataset_version_id: str
    version_label: str
    store_kind: Literal["relational", "graph", "vector"]
    status: str
    source_version: str
    object_namespace: str
    record_count: int
    attempt_count: int
    last_error: str | None = None
    updated_at: datetime
    can_retry: bool = False


class GovernanceAgentRun(StrictModel):
    run_id: str
    workspace_id: str
    question: str
    route: str
    status: str
    evidence_count: int
    claim_count: int
    checkpoint_sequence: int
    caveats: list[str] = Field(default_factory=list)
    error: str | None = None


class GovernanceApproval(StrictModel):
    id: str
    workflow_type: str
    workspace_id: str
    target_role: str | None = None
    requested_by: str
    requested_by_name: str
    status: str
    payload: dict[str, Any]
    created_at: datetime
    decision_by_name: str | None = None
    decision_note: str | None = None


class GovernanceLineage(StrictModel):
    dataset_id: str
    dataset_name: str
    latest_version_id: str | None = None
    latest_source_version: str | None = None
    version_count: int
    materialization_count: int
    downstream_references: list[str] = Field(default_factory=list)


class GovernanceOverview(StrictModel):
    generated_at: datetime
    access: GovernanceAccess
    counts: GovernanceCounts
    projections: list[GovernanceProjection]
    agent_runs: list[GovernanceAgentRun]
    approvals: list[GovernanceApproval]
    lineage: list[GovernanceLineage]
    policy_boundaries: list[str]


class GovernanceAgentRunDetail(StrictModel):
    state: AgentState
    traces: list[AgentTraceRecord]
    checkpoints: list[dict[str, Any]]


class ProjectionRetryResult(StrictModel):
    projection: GovernanceProjection
    message: str
