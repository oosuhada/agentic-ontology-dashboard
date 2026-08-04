"""Typed Project 3 service contracts consumed by Ontology Dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class Project3Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class Project3HealthCheck(Project3Model):
    check: str
    status: str
    detail: str = ""
    required: bool = True


class Project3Health(Project3Model):
    status: Literal["ready", "degraded", "unavailable"]
    checks: list[Project3HealthCheck] = Field(default_factory=list)
    available: bool = True
    mapped_project_id: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class Project3Readiness(Project3Model):
    project_id: str
    lifecycle_status: str
    source_type: str
    upload_count: int = 0
    mapping_approved: bool = False
    schema_available: bool = False
    node_count: int = 0
    relationship_count: int = 0
    can_query: bool = False
    can_load: bool = False
    eligible_for_ready: bool = False
    next_action: str = "query"
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    versions: dict[str, str | None] = Field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    transitions: list[dict[str, Any]] = Field(default_factory=list)


class Project3NodeIdentity(Project3Model):
    label: str
    identity_property: str


class Project3GraphSchema(Project3Model):
    project_id: str
    schema_version: str = "1"
    title: str = "Project graph"
    schema_context: str = ""
    node_identities: list[Project3NodeIdentity] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class Project3NodeSearch(Project3Model):
    label: str
    query: str
    identity_property: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class Project3Subgraph(Project3Model):
    root: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    node_count: int = 0
    relationship_count: int = 0
    depth: int = 1
    truncated: bool = False


class Project3Query(Project3Model):
    question: str
    answer: str = ""
    status: str
    cypher: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    caveat: str | None = None
    provider: str = "unknown"
    fallback_reason: str | None = None
    run_id: str | None = None
    thread_id: str | None = None


class Project3RagResult(Project3Model):
    project_id: str | None = None
    query: str | None = None
    answer: str | None = None
    status: str | None = None
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        validation_alias=AliasChoices("results", "matches"),
    )
    citations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class Project3AgentRun(Project3Model):
    state_schema_version: int
    status: str
    run: dict[str, Any]
    checkpoint: dict[str, Any] = Field(default_factory=dict)


class Project3IntegrationSnapshot(Project3Model):
    health: Project3Health
    readiness: Project3Readiness | None = None
    graph_schema: Project3GraphSchema | None = Field(default=None, alias="schema")
    subgraph: Project3Subgraph | None = None
    degraded_reason: str | None = None


class Project3ProjectionModel(BaseModel):
    """Strict draft boundary for Project 2 → Project 3 graph projection."""

    model_config = ConfigDict(extra="forbid")


class Project3ProjectionIdentity(Project3ProjectionModel):
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version_id: str = Field(min_length=1, max_length=160)
    object_type: str = Field(min_length=1, max_length=160)
    source_identity: str = Field(min_length=1, max_length=256)


class Project3ProjectionNode(Project3ProjectionModel):
    identity: Project3ProjectionIdentity
    properties: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=2048)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Project3ProjectionRelationship(Project3ProjectionModel):
    relationship_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,127}$")
    from_identity: Project3ProjectionIdentity
    to_identity: Project3ProjectionIdentity
    properties: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=2048)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def relationship_scope_matches(self) -> "Project3ProjectionRelationship":
        source_scope = (
            self.from_identity.organization_id,
            self.from_identity.project_id,
            self.from_identity.dataset_id,
            self.from_identity.dataset_version_id,
        )
        target_scope = (
            self.to_identity.organization_id,
            self.to_identity.project_id,
            self.to_identity.dataset_id,
            self.to_identity.dataset_version_id,
        )
        if source_scope != target_scope:
            raise ValueError("projection relationship endpoints must share dataset version scope")
        return self


class Project3GraphProjectionRequest(Project3ProjectionModel):
    contract_version: Literal["1.0"] = "1.0"
    message_type: Literal["graph_projection_request"] = "graph_projection_request"
    projection_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=256)
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version_id: str = Field(min_length=1, max_length=160)
    bundle_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapping_version: str = Field(min_length=1, max_length=160)
    nodes: list[Project3ProjectionNode] = Field(default_factory=list)
    relationships: list[Project3ProjectionRelationship] = Field(default_factory=list)
    requested_at: datetime

    @model_validator(mode="after")
    def payload_scope_matches_envelope(self) -> "Project3GraphProjectionRequest":
        expected = (
            self.organization_id,
            self.project_id,
            self.dataset_id,
            self.dataset_version_id,
        )
        identities = [node.identity for node in self.nodes]
        identities.extend(relationship.from_identity for relationship in self.relationships)
        identities.extend(relationship.to_identity for relationship in self.relationships)
        for identity in identities:
            actual = (
                identity.organization_id,
                identity.project_id,
                identity.dataset_id,
                identity.dataset_version_id,
            )
            if actual != expected:
                raise ValueError("projection object scope must match request envelope")

        node_keys = [
            (node.identity.object_type, node.identity.source_identity)
            for node in self.nodes
        ]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("projection request contains duplicate node identities")
        return self


Project3ProjectionStatus = Literal["accepted", "processing", "completed", "failed", "blocked"]
Project3ProjectionErrorCode = Literal[
    "validation_failed",
    "project_not_ready",
    "schema_version_unsupported",
    "identity_conflict",
    "graph_unavailable",
    "timeout",
    "internal_error",
]


class Project3ProjectionError(Project3ProjectionModel):
    code: Project3ProjectionErrorCode
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool
    retry_after_seconds: int | None = Field(default=None, ge=1)
    details: dict[str, Any] = Field(default_factory=dict)


class Project3ProjectionCounts(Project3ProjectionModel):
    nodes_received: int = Field(default=0, ge=0)
    relationships_received: int = Field(default=0, ge=0)
    nodes_written: int = Field(default=0, ge=0)
    relationships_written: int = Field(default=0, ge=0)


class Project3GraphProjectionResponse(Project3ProjectionModel):
    contract_version: Literal["1.0"] = "1.0"
    message_type: Literal["graph_projection_response"] = "graph_projection_response"
    projection_id: str = Field(min_length=1, max_length=160)
    status: Project3ProjectionStatus
    project3_run_id: str | None = Field(default=None, max_length=160)
    counts: Project3ProjectionCounts = Field(default_factory=Project3ProjectionCounts)
    error: Project3ProjectionError | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def error_matches_status(self) -> "Project3GraphProjectionResponse":
        if self.status in {"failed", "blocked"} and self.error is None:
            raise ValueError("failed or blocked projection responses require an error")
        if self.status in {"accepted", "processing", "completed"} and self.error is not None:
            raise ValueError("non-error projection responses must not include an error")
        return self
