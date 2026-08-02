from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BoardCategory = Literal["suggested", "observe", "explore", "explain", "act", "audit", "build"]
BoardWidth = int
ParameterValueType = Literal["string", "number", "integer", "boolean", "datetime", "object", "array"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DashboardParameterDefinition(StrictModel):
    id: str
    display_name: str
    value_type: ParameterValueType
    scope: Literal["dashboard", "tab", "board"] = "dashboard"
    default_value: Any = None
    options: list[Any] = Field(default_factory=list)
    description: str | None = None


class DashboardBoardLayout(StrictModel):
    x: int = Field(default=0, ge=0, le=11)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=6, ge=1, le=12)
    h: int = Field(default=2, ge=1, le=12)
    min_w: int | None = Field(default=None, ge=1, le=12)
    min_h: int | None = Field(default=None, ge=1, le=12)
    max_w: int | None = Field(default=None, ge=1, le=12)
    max_h: int | None = Field(default=None, ge=1, le=12)


class DashboardBoardSourceReference(StrictModel):
    kind: Literal["analysis_board"] = "analysis_board"
    analysis_id: str
    analysis_node_id: str
    version_policy: Literal["pinned", "latest_published"] = "pinned"
    version: int | None = Field(default=None, ge=1)


class BoardCatalogDefinition(StrictModel):
    id: str
    display_name: str
    description: str
    category: BoardCategory
    renderer: str
    allowed_roles: list[str]
    object_types: list[str] = Field(default_factory=list)
    emits: list[str] = Field(default_factory=list)
    accepts: list[str] = Field(default_factory=list)
    binding_schema: dict[str, ParameterValueType] = Field(default_factory=dict)
    default_bindings: dict[str, Any] = Field(default_factory=dict)
    default_settings: dict[str, Any] = Field(default_factory=dict)
    default_data_binding: dict[str, Any] | None = None
    default_render_spec: dict[str, Any] | None = None
    default_width: int = Field(default=6, ge=1, le=12)
    minimum_width: int = Field(default=3, ge=1, le=12)
    maximum_width: int = Field(default=12, ge=1, le=12)
    allow_multiple: bool = False


class DashboardBoard(StrictModel):
    id: str = Field(min_length=3, max_length=160)
    definition_id: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    width: int = Field(default=6, ge=1, le=12)
    order: int = Field(ge=0)
    layout: DashboardBoardLayout | None = None
    source: DashboardBoardSourceReference | None = None
    hidden: bool = False
    mandatory: bool = False
    custom: bool = False
    bindings: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class DashboardTab(StrictModel):
    id: str = Field(min_length=3, max_length=160)
    title: str = Field(min_length=1, max_length=80)
    order: int = Field(ge=0)
    hidden: bool = False
    custom: bool = False
    parameter_ids: list[str] = Field(default_factory=list)
    boards: list[DashboardBoard] = Field(default_factory=list)


class DependencyEdge(StrictModel):
    source_board_id: str
    target_board_id: str
    parameter_ids: list[str]


class DashboardTemplateSnapshot(StrictModel):
    template_id: str
    workspace_id: str
    role_code: str
    display_name: str
    version: int = Field(ge=1)
    status: Literal["draft", "published", "archived"] = "published"
    tabs: list[DashboardTab]
    mandatory_board_ids: list[str] = Field(default_factory=list)
    parameter_definitions: list[DashboardParameterDefinition] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str


class ResolvedDashboard(StrictModel):
    dashboard_id: str
    template_id: str
    template_version: int
    preference_revision: int
    preference_template_version: int | None = None
    workspace_id: str
    role_code: str
    display_name: str
    tabs: list[DashboardTab]
    active_tab_id: str
    parameter_state: dict[str, Any] = Field(default_factory=dict)
    parameter_definitions: list[DashboardParameterDefinition] = Field(default_factory=list)
    dependency_graph: list[DependencyEdge] = Field(default_factory=list)
    merge_notices: list[str] = Field(default_factory=list)


class DashboardPreferenceSaveRequest(StrictModel):
    workspace_id: str
    base_revision: int = Field(ge=0)
    active_tab_id: str
    tabs: list[DashboardTab]
    parameter_state: dict[str, Any] = Field(default_factory=dict)


class DashboardPreferenceRestoreRequest(StrictModel):
    workspace_id: str


class DashboardSelectionFilter(StrictModel):
    id: str
    source_board_id: str
    field: str
    operator: Literal["eq", "in", "gte", "lte", "between"]
    values: list[str | int | float | bool]
    object_type: str | None = None
    created_at: str | None = None


class DashboardBoardQueryRequest(StrictModel):
    workspace_id: str
    parameter_state: dict[str, Any] = Field(default_factory=dict)
    selection_filters: list[DashboardSelectionFilter] = Field(default_factory=list)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
    search: str | None = Field(default=None, max_length=240)


class SavedViewCreateRequest(StrictModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=80)
    active_tab_id: str
    tabs: list[DashboardTab]
    parameter_state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class SavedViewRecord(StrictModel):
    id: str
    user_id: str
    workspace_id: str
    name: str
    active_tab_id: str
    tabs: list[DashboardTab]
    parameter_state: dict[str, Any]
    created_at: str
    updated_at: str


class DashboardShareCreateRequest(StrictModel):
    workspace_id: str
    active_tab_id: str
    parameter_state: dict[str, Any] = Field(default_factory=dict)
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)


class DashboardShareCreated(StrictModel):
    token: str
    path: str
    workspace_id: str
    active_tab_id: str
    parameter_state: dict[str, Any]
    expires_at: str


class DashboardSharePayload(StrictModel):
    workspace_id: str
    active_tab_id: str
    parameter_state: dict[str, Any]
    owner_user_id: str
    created_at: str
    expires_at: str


class DashboardTemplatePublishRequest(StrictModel):
    workspace_id: str
    display_name: str = Field(min_length=1, max_length=120)
    tabs: list[DashboardTab]
    parameter_definitions: list[DashboardParameterDefinition] = Field(default_factory=list)


class DashboardCatalogResponse(StrictModel):
    items: list[BoardCatalogDefinition]
    categories: list[BoardCategory]
