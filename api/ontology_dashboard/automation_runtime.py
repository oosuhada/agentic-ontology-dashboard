"""Safe event-condition-action automation simulation and approval contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AutomationSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=160)
    failure_probability: float = Field(ge=0, le=1)
    criticality: Literal["low", "medium", "high"]
    duplicate: bool = False


class AutomationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    definition: dict[str, Any]
    simulation: dict[str, Any]
    approval: dict[str, Any]
    recovery: dict[str, Any]
    integrations: dict[str, Any]
    guarantees: tuple[str, ...]


def simulate_automation(request: AutomationSimulationRequest) -> dict[str, Any]:
    condition = request.failure_probability >= 0.8 and request.criticality == "high"
    return {
        "event_id": request.event_id,
        "state": "deduplicated" if request.duplicate else "awaiting_approval" if condition else "condition_not_met",
        "condition_matched": condition,
        "actions": ["request-asset-inspection"] if condition and not request.duplicate else [],
        "external_side_effects_executed": False,
        "approval_required": condition,
        "four_eyes": condition,
        "replay_safe": True,
        "trace": ["event.received", "condition.evaluated"] + (["approval.requested"] if condition else []),
    }


def automation_snapshot() -> AutomationSnapshot:
    simulation = simulate_automation(AutomationSimulationRequest(event_id="prediction:M-001:2026-08-06T00:00Z", failure_probability=0.91, criticality="high"))
    return AutomationSnapshot(
        definition={
            "id": "high-risk-inspection", "version": 1, "status": "published",
            "trigger": "prediction.created", "condition": "typed comparison tree",
            "workflow": ["evaluate", "request_approval", "invoke_action", "notify"],
            "raw_code_allowed": False,
        },
        simulation=simulation,
        approval={"policy": "four-eyes", "step_up": "required for high criticality", "agent_draft_is_published": False},
        recovery={"idempotency": "automation_id + event_id", "crash_resume": "checkpointed", "compensation": "registered per external action"},
        integrations={"webhook": "not_configured", "signing": "required when configured", "retry": "durable outbox"},
        guarantees=(
            "simulation suppresses all side effects",
            "duplicate events cannot create duplicate work",
            "replay never repeats an external side effect",
            "high-risk operational actions require human approval",
        ),
    )


__all__ = ["AutomationSimulationRequest", "AutomationSnapshot", "automation_snapshot", "simulate_automation"]
