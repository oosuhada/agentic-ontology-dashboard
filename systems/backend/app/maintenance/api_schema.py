"""Product-facing command contracts for the canonical Maintenance loop."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .maintenance_schema import (
    EquipmentIdentity,
    InspectionChecklistItem,
    InspectionMeasurement,
    InspectionOutcome,
    OperationalDecisionKind,
    RecommendationDisposition,
)


class StrictCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSnapshotBasis(StrictCommand):
    artifact_id: str | None = Field(default=None, max_length=240)
    evidence_payload_reference: str | None = Field(default=None, max_length=500)
    asset_id: str | None = Field(default=None, max_length=240)
    event_id: str | None = Field(default=None, max_length=240)
    observed_at: str | None = Field(default=None, max_length=120)
    model_version: str | None = Field(default=None, max_length=240)
    dataset_version: str | None = Field(default=None, max_length=240)
    source_sha256: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_identity_fields(self) -> "EvidenceSnapshotBasis":
        missing = [
            field
            for field in ("artifact_id", "evidence_payload_reference", "asset_id", "event_id")
            if not isinstance(getattr(self, field), str) or not getattr(self, field)
        ]
        if missing:
            raise ValueError(
                f"snapshot_basis requires identity fields: {', '.join(missing)}"
            )
        return self


class InspectionWorkOrderCreateRequest(StrictCommand):
    """Request an inspection for an existing canonical Diagnosis event.

    Every authorization and equipment-lineage field is resolved server-side
    from the Diagnosis-owned Event Evidence Projection.  Accepting those
    fields from a caller would let the caller forge the authorization basis.
    The snapshot_basis is a required stale-view guard: its identity fields and
    any supplied provenance fields must match the server-resolved projection
    before a work order can be requested.
    """

    event_id: str = Field(min_length=1, max_length=240)
    snapshot_basis: EvidenceSnapshotBasis


class RecommendationInputSource(StrictCommand):
    source_product_result_id: str = Field(min_length=1, max_length=240)
    source_evidence_id: str = Field(min_length=1, max_length=240)
    source_action_id: str = Field(min_length=1, max_length=240)
    source_schema_version: str = Field(min_length=1, max_length=120)
    source_policy_version: str = Field(min_length=1, max_length=120)


class RecommendationInput(StrictCommand):
    """Closed-loop policy input derived from Product Result/Evidence only.

    UI ViewModels and Agent Review summaries may display or explain the same
    evidence basis, but they are not accepted as authorization sources for
    mutations.
    """

    schema_version: Literal["recommendation-input-v1"] = "recommendation-input-v1"
    event_id: str = Field(min_length=1, max_length=240)
    snapshot_basis: EvidenceSnapshotBasis
    equipment: EquipmentIdentity
    operational_decision_kind: OperationalDecisionKind
    source_context: RecommendationInputSource


class InspectionResultCreateRequest(StrictCommand):
    outcome: InspectionOutcome
    checklist: tuple[InspectionChecklistItem, ...] = Field(min_length=1)
    measurements: tuple[InspectionMeasurement, ...] = ()
    findings: tuple[str, ...] = Field(min_length=1)
    note: str = Field(default="", max_length=4000)


class OperationsManualRecommendationCreateRequest(StrictCommand):
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] = (
        "TOOL_REPLACEMENT"
    )
    basis: tuple[str, ...] = Field(min_length=1)
    cost_analysis_id: str | None = Field(default=None, min_length=1, max_length=240)
    cost_option_id: str | None = Field(default=None, min_length=1, max_length=240)
    action_candidate_id: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def require_coherent_cost_reference(
        self,
    ) -> "OperationsManualRecommendationCreateRequest":
        if (self.cost_analysis_id is None) != (self.action_candidate_id is None):
            raise ValueError(
                "cost analysis reference requires cost_analysis_id and action_candidate_id"
            )
        if self.cost_option_id is not None and self.cost_analysis_id is None:
            raise ValueError(
                "cost option reference requires cost analysis and action candidate"
            )
        return self


class MaintenanceCostAnalysisCreateRequest(StrictCommand):
    """Action plus consulted-SOP audit context.

    Economic inputs for every supported Action are owned by versioned Backend
    providers and must not be supplied by a product client.
    """

    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] = (
        "TOOL_REPLACEMENT"
    )
    sop_id: str = Field(
        min_length=1,
        max_length=240,
        description="SOP consulted by the user; never a maintenance authorization.",
    )
    sop_version: str = Field(
        min_length=1,
        max_length=160,
        description="Version of the consulted SOP audit reference.",
    )


class ToolReplacementCostAnalysisCreateRequest(MaintenanceCostAnalysisCreateRequest):
    """Server-calculated one-insert cost request."""

    action_code: Literal["TOOL_REPLACEMENT"] = "TOOL_REPLACEMENT"


class RecommendationDecisionCreateRequest(StrictCommand):
    disposition: RecommendationDisposition
    note: str = Field(default="", max_length=4000)


class MaintenanceWorkOrderApproveRequest(StrictCommand):
    """Approve a WorkOrder using Diagnosis-owned runtime lineage.

    ``simulation_session_id`` is compatibility-only for historical Product
    Results that predate source-session lineage. Live callers omit it; when
    lineage exists, the server resolves it from the authorized Product Result.
    """

    simulation_session_id: str | None = Field(default=None, min_length=1, max_length=240)


class MaintenanceActionStartRequest(StrictCommand):
    """The target action and canonical lineage are resolved from the route ID."""


class MaintenanceActionCompleteRequest(StrictCommand):
    outcome: str = Field(min_length=1, max_length=4000)


class MaintenanceReplayRequest(StrictCommand):
    restart_at: datetime

    @field_validator("restart_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("restart_at must include timezone")
        return value


__all__ = [
    "EvidenceSnapshotBasis",
    "InspectionResultCreateRequest",
    "InspectionWorkOrderCreateRequest",
    "MaintenanceActionCompleteRequest",
    "MaintenanceActionStartRequest",
    "MaintenanceCostAnalysisCreateRequest",
    "MaintenanceReplayRequest",
    "MaintenanceWorkOrderApproveRequest",
    "OperationsManualRecommendationCreateRequest",
    "RecommendationInput",
    "RecommendationInputSource",
    "RecommendationDecisionCreateRequest",
    "ToolReplacementCostAnalysisCreateRequest",
]
