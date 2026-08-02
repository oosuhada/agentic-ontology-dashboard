"""Typed Project 3 service contracts consumed by Ontology Dashboard."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
