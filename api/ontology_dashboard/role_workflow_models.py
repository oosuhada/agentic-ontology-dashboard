from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuditExportCheckpointRequest(StrictModel):
    workspace_id: str
    event_id: str
    export_format: Literal["json", "csv", "pdf"] = "json"
    reason: str = Field(min_length=2, max_length=240)


class FieldTaskActionRequest(StrictModel):
    workspace_id: str
    event_id: str
    action: Literal["complete", "issue_found", "blocked"]
    checklist: list[str] = Field(default_factory=list)
    measurements: dict[str, float | int | str | None] = Field(default_factory=dict)
    photo_metadata: list[dict[str, Any]] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)
    location: str | None = Field(default=None, max_length=160)
    safety_risk: bool = False

    @field_validator("photo_metadata")
    @classmethod
    def validate_photo_metadata(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {"filename", "captured_at", "mime_type", "size_bytes", "caption", "sha256"}
        for item in items:
            unknown = set(item) - allowed
            if unknown:
                raise ValueError(f"unknown photo metadata fields: {', '.join(sorted(unknown))}")
            if "binary" in item or "data" in item:
                raise ValueError("photo binary data is not accepted; metadata only")
        return items


class TemplatePublishRequestCreate(StrictModel):
    workspace_id: str
    target_role: str
    display_name: str = Field(min_length=1, max_length=120)
    tabs: list[dict[str, Any]]
    parameter_definitions: list[dict[str, Any]] = Field(default_factory=list)
    change_summary: str = Field(min_length=2, max_length=500)


class ModelReleaseRequestCreate(StrictModel):
    workspace_id: str
    model_version: str = Field(min_length=1, max_length=120)
    dataset_version: str = Field(min_length=1, max_length=120)
    policy_version: str = Field(min_length=1, max_length=120)
    metrics: dict[str, float | int | str]
    threshold_evaluation: dict[str, float | int | str]
    notes: str = Field(min_length=2, max_length=1000)


class ApprovalDecisionRequest(StrictModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


class WorkflowRecord(BaseModel):
    id: str
    workflow_type: str
    workspace_id: str
    status: str
    requested_by: str
    requested_by_name: str
    payload: dict[str, Any]
    decision_by: str | None = None
    decision_by_name: str | None = None
    decision_note: str | None = None
    created_at: str
    updated_at: str


class ExecutiveOverview(BaseModel):
    workspace_id: str
    generated_at: str
    aggregate: dict[str, Any]
    status_distribution: list[dict[str, Any]]
    risk_trend: list[dict[str, Any]]
    unresolved_critical_events: list[dict[str, Any]]
    business_impact: dict[str, Any]
    assumptions: list[str]


class AuditReconstruction(BaseModel):
    workspace_id: str
    event_id: str
    reconstructed_at: str
    input_snapshot: dict[str, Any]
    version_snapshot: dict[str, Any]
    evidence_to_report_trace: list[dict[str, Any]]
    action_history: list[dict[str, Any]]
    export_checkpoints: list[dict[str, Any]]


class FieldTaskWorkspace(BaseModel):
    workspace_id: str
    generated_at: str
    tasks: list[dict[str, Any]]
    offline_queue_design: dict[str, Any]


class FDEWorkbench(BaseModel):
    workspace_id: str
    generated_at: str
    customer_workspace: dict[str, Any]
    ontology_registry: dict[str, Any]
    integration_health: list[dict[str, Any]]
    deployment_checklist: list[dict[str, Any]]
    diagnostic_events: list[dict[str, Any]]
    template_requests: list[dict[str, Any]]
    security_boundaries: list[str]


class ModelConsole(BaseModel):
    workspace_id: str
    generated_at: str
    model_versions: list[dict[str, Any]]
    dataset_versions: list[dict[str, Any]]
    training_metrics: dict[str, Any]
    operational_thresholds: dict[str, Any]
    threshold_cost: list[dict[str, Any]]
    slices: list[dict[str, Any]]
    drift_and_schema: list[dict[str, Any]]
    gold_regression: dict[str, Any]
    release_requests: list[dict[str, Any]]
