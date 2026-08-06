from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnalysisStatus = Literal["draft", "published", "archived"]
AnalysisRunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
VersionPolicy = Literal["pinned", "latest_published"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisNodeSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=240)
    type: str | None = Field(default=None, max_length=120)
    position: dict[str, float] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class AnalysisEdgeSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=240)
    source: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    sourceHandle: str | None = Field(default=None, max_length=160)
    targetHandle: str | None = Field(default=None, max_length=160)
    type: str | None = Field(default=None, max_length=120)
    animated: bool | None = None
    markerEnd: dict[str, Any] | None = None


class AnalysisCreateRequest(StrictModel):
    id: str | None = Field(default=None, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    nodes: list[AnalysisNodeSnapshot] = Field(default_factory=list)
    edges: list[AnalysisEdgeSnapshot] = Field(default_factory=list)
    publish: bool = False


class AnalysisUpdateRequest(StrictModel):
    workspace_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    nodes: list[AnalysisNodeSnapshot]
    edges: list[AnalysisEdgeSnapshot]
    base_version: int = Field(ge=1)
    publish: bool = False


class AnalysisRunRequest(StrictModel):
    workspace_id: str = Field(min_length=1, max_length=120)
    version_policy: VersionPolicy = "pinned"
    version: int | None = Field(default=None, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    preview_limit: int = Field(default=500, ge=1, le=5000)

    @field_validator("version")
    @classmethod
    def require_pinned_version(cls, value: int | None, info):
        if info.data.get("version_policy") == "pinned" and value is None:
            raise ValueError("version is required when version_policy is pinned")
        return value


class AnalysisSnapshot(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    display_name: str
    status: AnalysisStatus
    current_version: int
    published_version: int | None = None
    nodes: list[AnalysisNodeSnapshot]
    edges: list[AnalysisEdgeSnapshot]
    created_by: str
    created_at: str
    updated_at: str


class AnalysisRunResult(StrictModel):
    id: str
    analysis_id: str
    analysis_version: int
    organization_id: str
    project_id: str
    workspace_id: str
    requested_by: str
    status: AnalysisRunStatus
    parameters: dict[str, Any]
    node_results: dict[str, dict[str, Any]]
    started_at: str
    finished_at: str | None = None
    error: dict[str, Any] | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_node_id: str | None = None
    cancel_requested: bool = False
    cache_key: str | None = None
    cache_hit: bool = False
    rows_scanned: int = Field(default=0, ge=0)
    updated_at: str | None = None


class AnalysisNodeRowsPage(StrictModel):
    run_id: str
    node_id: str
    rows: list[dict[str, Any]]
    cursor: str | None = None
    next_cursor: str | None = None
    limit: int
    total: int


class AnalysisNodeResultResponse(StrictModel):
    analysis_id: str
    analysis_version: int
    node_id: str
    version_policy: VersionPolicy
    render_spec: dict[str, Any]
    result: dict[str, Any]
    run_id: str
    generated_at: str
