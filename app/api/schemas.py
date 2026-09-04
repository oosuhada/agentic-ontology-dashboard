from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StartRunRequest(BaseModel):
    run_id: str | None = None
    simulation_session_id: str | None = Field(default=None, min_length=1, max_length=240)
    seed: int = 42
    start_at: datetime | None = None
    duration_hours: int = Field(default=24, ge=1)
    interval_minutes: int = Field(default=10, ge=1)
    product_cycle_minutes: int = Field(default=20, ge=1)
    rate_profile: str = "balanced_demo"
    scenario_profile: Literal["continuous_reliability"] = "continuous_reliability"
    speed: float = Field(default=60.0, gt=0)
    continuous: bool = True
    publish_opcua: bool = True
    source_kind: Literal["simulation", "opcua"] = "simulation"
    opcua_source_endpoint: str | None = None
    opcua_node_ids: list[str] = Field(default_factory=list)
    reconnect_seconds: float = Field(default=1.0, gt=0)
    runtime_overlay_fast_forward_rows: int | None = Field(
        default=None,
        ge=0,
        le=10_000,
        description=(
            "Post-maintenance Overlay Observation target for this simulation run. "
            "Omit to use the application default; set 0 to disable automatic "
            "branch-local acceleration."
        ),
    )


class FastForwardOverlayRequest(BaseModel):
    """Advance one post-maintenance branch without moving the global clock."""

    equipment_id: str = Field(min_length=1, max_length=240)
    target_generated_rows: int = Field(ge=1, le=10_000)


class FastForwardSimulationRequest(BaseModel):
    """Advance the complete simulation to an elapsed-hour target."""

    target_elapsed_hours: int = Field(
        ge=1,
        description=(
            "Elapsed simulation hour to reach by processing every intermediate "
            "tick for every asset."
        ),
    )
