"""Application boundary for read-only operational decision support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_decision_brief import (
    DecisionBriefRole,
    OperationalDecisionBrief,
)


DECISION_SUPPORT_RUNNING_LEASE_SECONDS = 120


class DecisionSupportMaterializationInProgress(RuntimeError):
    """Raised when the same immutable decision context already has an active run."""


@dataclass(frozen=True)
class DecisionSupportTrace:
    status: str
    reason: str | None
    reused: bool
    workflow_run_id: str | None
    context_version_set: dict[str, str]
    temporal_validation: str
    stale_recovered: bool = False
    trajectory: tuple[dict[str, Any], ...] = ()


class OperationalDecisionSupportService(Protocol):
    """Port consumed by the Operations HTTP boundary."""

    def cached_brief(
        self,
        *,
        identity: OperationalRequestIdentity,
        actor_role: DecisionBriefRole,
    ) -> tuple[OperationalDecisionBrief | None, DecisionSupportTrace]: ...

    def materialize(
        self,
        *,
        identity: OperationalRequestIdentity,
        actor_role: DecisionBriefRole,
        risk_status: str,
        trigger: str,
        now: Any | None = None,
    ) -> tuple[OperationalDecisionBrief, DecisionSupportTrace]: ...

    def workflow_runs(
        self,
        *,
        project_id: str,
        asset_id: str | None,
        status: str | None,
        limit: int,
        organization_id: str = "org-ontology-demo",
    ) -> list[dict[str, Any]]: ...
