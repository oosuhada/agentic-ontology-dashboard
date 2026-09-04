"""Versioned integration events emitted by the Closed-loop domain.

These DTOs model only the ``maintenance.*`` events owned by Closed-loop.  The
Generator-owned ``runtime_overlay.observations.available`` event deliberately
lives outside this module.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal, TypeAlias

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.runtime_settings import project_root


class FrozenEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaintenanceCause(FrozenEventModel):
    source_product_result_id: str = Field(min_length=1, max_length=240)
    source_evidence_id: str = Field(min_length=1, max_length=240)
    decision_id: str = Field(min_length=1, max_length=240)


class ToolWearReset(FrozenEventModel):
    operation: Literal["reset"] = "reset"
    value: Literal[0] = 0
    unit: Literal["min"] = "min"


class ToolReplacementStatePatch(FrozenEventModel):
    tool_wear_min: ToolWearReset = Field(default_factory=ToolWearReset)


class CoolingSystemRestore(FrozenEventModel):
    operation: Literal["restore"] = "restore"
    value: Literal["nominal"] = "nominal"
    unit: Literal["state"] = "state"


class CoolingSystemRestoreStatePatch(FrozenEventModel):
    cooling_system_state: CoolingSystemRestore = Field(
        default_factory=CoolingSystemRestore
    )


MaintenanceStatePatch: TypeAlias = (
    ToolReplacementStatePatch | CoolingSystemRestoreStatePatch
)


class MaintenanceIntegrationEvent(FrozenEventModel):
    contract_version: Literal["maintenance-replay-v1"] = "maintenance-replay-v1"
    event_type: str
    event_id: str = Field(min_length=1, max_length=240)
    idempotency_key: str = Field(min_length=8, max_length=200)
    state_version: int = Field(ge=1)
    simulation_session_id: str = Field(min_length=1, max_length=240)
    maintenance_action_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    caused_by: MaintenanceCause

    def as_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json", exclude_none=True)
        validate_maintenance_event(payload)
        return payload


class MaintenanceStartedEvent(MaintenanceIntegrationEvent):
    event_type: Literal["maintenance.started"] = "maintenance.started"
    work_order_id: str = Field(min_length=1, max_length=240)
    maintenance_started_at: datetime
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] = (
        "TOOL_REPLACEMENT"
    )


class MaintenanceCompletedEvent(MaintenanceIntegrationEvent):
    event_type: Literal["maintenance.completed"] = "maintenance.completed"
    maintenance_event_id: str = Field(min_length=1, max_length=240)
    maintenance_started_at: datetime | None = None
    maintenance_completed_at: datetime
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] = (
        "TOOL_REPLACEMENT"
    )
    state_patch: MaintenanceStatePatch = Field(default_factory=ToolReplacementStatePatch)

    @model_validator(mode="after")
    def require_time_order(self) -> MaintenanceCompletedEvent:
        if (
            self.maintenance_started_at is not None
            and self.maintenance_completed_at < self.maintenance_started_at
        ):
            raise ValueError("maintenance completion cannot precede its start")
        _require_matching_state_patch(self.action_code, self.state_patch)
        return self


class MaintenanceReplayRequestedEvent(MaintenanceIntegrationEvent):
    event_type: Literal["maintenance.replay_requested"] = "maintenance.replay_requested"
    maintenance_event_id: str = Field(min_length=1, max_length=240)
    maintenance_started_at: datetime | None = None
    maintenance_completed_at: datetime | None = None
    restart_at: datetime
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] | None = None
    state_patch: MaintenanceStatePatch | None = None

    @model_validator(mode="after")
    def require_time_order(self) -> MaintenanceReplayRequestedEvent:
        if self.maintenance_completed_at is not None and self.restart_at < self.maintenance_completed_at:
            raise ValueError("restart cannot precede maintenance completion")
        if (
            self.maintenance_started_at is not None
            and self.maintenance_completed_at is not None
            and self.maintenance_completed_at < self.maintenance_started_at
        ):
            raise ValueError("maintenance completion cannot precede its start")
        if (self.action_code is None) != (self.state_patch is None):
            raise ValueError("replay action_code and state_patch must be provided together")
        if self.action_code is not None and self.state_patch is not None:
            _require_matching_state_patch(self.action_code, self.state_patch)
        return self


def _require_matching_state_patch(
    action_code: str, state_patch: MaintenanceStatePatch
) -> None:
    if action_code == "TOOL_REPLACEMENT" and not isinstance(
        state_patch, ToolReplacementStatePatch
    ):
        raise ValueError("TOOL_REPLACEMENT requires tool_wear_min reset state_patch")
    if action_code == "COOLING_SYSTEM_RESTORE" and not isinstance(
        state_patch, CoolingSystemRestoreStatePatch
    ):
        raise ValueError(
            "COOLING_SYSTEM_RESTORE requires cooling_system_state restore state_patch"
        )


MaintenanceEvent: TypeAlias = Annotated[
    MaintenanceStartedEvent | MaintenanceCompletedEvent | MaintenanceReplayRequestedEvent,
    Field(discriminator="event_type"),
]


@lru_cache(maxsize=1)
def _maintenance_event_validator() -> Draft202012Validator:
    schema_path = project_root() / "contracts" / "schemas" / "maintenance-replay-event.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_maintenance_event(payload: dict[str, object]) -> None:
    errors = sorted(
        _maintenance_event_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"maintenance integration event schema validation failed: {rendered}")
