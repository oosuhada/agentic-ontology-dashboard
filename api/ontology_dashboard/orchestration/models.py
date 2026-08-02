"""Typed state, evidence and response contracts for Project 2 orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentRoute = Literal["relational", "graph", "vector", "hybrid"]
AgentStatus = Literal["running", "succeeded", "failed", "awaiting_approval"]
EvidenceStore = Literal["postgresql", "neo4j", "pgvector", "project3_rag"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentQueryRequest(StrictModel):
    project_id: str = Field(min_length=3, max_length=160)
    workspace_id: str = Field(min_length=3, max_length=160)
    question: str = Field(min_length=2, max_length=4000)
    route: AgentRoute | Literal["auto"] = "auto"
    object_type: str | None = Field(default=None, max_length=160)
    object_id: str | None = Field(default=None, max_length=500)
    top_k: int = Field(default=8, ge=1, le=30)


class EvidenceItem(StrictModel):
    evidence_id: str
    store: EvidenceStore
    reference: str
    project_id: str
    workspace_id: str
    dataset_version_id: str | None = None
    object_id: str | None = None
    title: str
    content: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundedClaim(StrictModel):
    claim_id: str
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    validated: bool = True


class OrchestrationStep(StrictModel):
    name: str
    store: EvidenceStore | None = None
    status: Literal["succeeded", "failed", "skipped"]
    latency_ms: int | None = None
    detail: str = ""


class AgentState(StrictModel):
    run_id: str
    organization_id: str
    project_id: str
    workspace_id: str
    user_id: str
    question: str
    route: AgentRoute
    status: AgentStatus = "running"
    object_type: str | None = None
    object_id: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    claims: list[GroundedClaim] = Field(default_factory=list)
    steps: list[OrchestrationStep] = Field(default_factory=list)
    answer: str = ""
    caveats: list[str] = Field(default_factory=list)
    error: str | None = None
    checkpoint_sequence: int = 0

    @model_validator(mode="after")
    def claims_reference_evidence(self) -> "AgentState":
        evidence_ids = {item.evidence_id for item in self.evidence}
        for claim in self.claims:
            if not set(claim.evidence_ids).issubset(evidence_ids):
                raise ValueError("grounded claim references unknown evidence")
        if self.status == "succeeded" and self.claims and not self.evidence:
            raise ValueError("succeeded grounded claims require evidence")
        return self


class AgentTraceRecord(StrictModel):
    id: str
    run_id: str
    step_name: str
    store_kind: str | None = None
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    latency_ms: int | None = None
    created_at: datetime


class AgentRunSummary(StrictModel):
    run_id: str
    project_id: str
    workspace_id: str
    question: str
    route: AgentRoute
    status: AgentStatus
    evidence_count: int
    claim_count: int
    checkpoint_sequence: int
    created_at: datetime
    updated_at: datetime


class AgentRunPage(StrictModel):
    items: list[AgentRunSummary]
    offset: int
    limit: int
    total: int


class AgentRunResponse(StrictModel):
    state: AgentState
    traces: list[AgentTraceRecord] = Field(default_factory=list)
