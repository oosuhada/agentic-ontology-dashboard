"""Bounded read-only operational decision agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.operations.operational_context_contract import (
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    context_version_set,
    context_version_set_hash,
)
from app.operations.operational_context_ports import OperationalContextReadPort
from app.operations.operational_relation_resolver import (
    RelationResolutionResult,
    resolve_operational_relations,
)
from app.operations.operational_impact_simulation import (
    ImpactCalculationState,
    ImpactSimulationAssumptions,
    ImpactSimulationResult,
    simulate_operational_impact,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentTerminalState(StrEnum):
    COMPLETE = "complete"
    PARTIAL_WITH_GAPS = "partial_with_gaps"
    BLOCKED = "blocked"
    FAILED = "failed"
    HUMAN_INPUT_REQUIRED = "human_input_required"


class OperationalAgentIntent(StrEnum):
    MAINTENANCE_TIMING_DECISION = "maintenance_timing_decision"


class OperationalAgentRequest(FrozenModel):
    identity: OperationalRequestIdentity
    actor_role: str = Field(min_length=1, max_length=120)
    intent: OperationalAgentIntent
    risk_status: str = Field(min_length=1, max_length=80)


class ReActExecutionPolicy(FrozenModel):
    policy_version: str = "bounded-operational-react-v1"
    max_steps: int = Field(default=8, ge=1, le=32)
    max_attempts_per_domain: int = Field(default=2, ge=1, le=3)
    required_domains: tuple[str, ...] = (
        "production",
        "maintenance_readiness",
        "quality_delivery",
    )
    mutation_allowed: bool = False


class AgentTrajectoryStep(FrozenModel):
    step: int = Field(ge=1)
    selected_tool: str
    selection_reason_code: str
    input_scope_hash: str
    input_context_versions: dict[str, str]
    attempt_count: int = Field(ge=1)
    status: str
    output_ref: str | None = None
    source_refs: tuple[str, ...] = ()
    next_action: str


class OperationalDecisionAgentResult(FrozenModel):
    schema_version: str = "operational-decision-agent-result-v1.0"
    policy_version: str
    terminal_state: AgentTerminalState
    identity: OperationalRequestIdentity
    actor_role: str
    intent: OperationalAgentIntent
    contexts: dict[str, OperationalContextEnvelope]
    context_version_set: dict[str, str]
    context_version_hash: str
    relation_context: RelationResolutionResult | None
    impact_simulation: ImpactSimulationResult | None
    facts: tuple[dict[str, Any], ...]
    gaps: tuple[dict[str, Any], ...]
    trajectory: tuple[AgentTrajectoryStep, ...]
    temporal_validation: dict[str, Any]
    mutation_attempted: bool = False


@dataclass
class BoundedOperationalDecisionAgent:
    """Single bounded coordinator over injected read-only domain ports."""

    ports: Mapping[str, OperationalContextReadPort]
    impact_assumptions: ImpactSimulationAssumptions
    policy: ReActExecutionPolicy = ReActExecutionPolicy()

    def __post_init__(self) -> None:
        if self.policy.mutation_allowed:
            raise ValueError("operational decision agent must remain read-only")
        missing = set(self.policy.required_domains).difference(self.ports)
        if missing:
            raise ValueError(
                f"missing required operational ports: {sorted(missing)}"
            )
        forbidden = [
            name
            for name in self.ports
            if any(
                token in name.lower()
                for token in ("create", "update", "delete", "approve", "start", "complete")
            )
        ]
        if forbidden:
            raise ValueError(f"mutation-like tools are forbidden: {forbidden}")

    def run(
        self,
        *,
        request: OperationalAgentRequest,
        retrieved_at: datetime,
        validated_at: datetime,
    ) -> OperationalDecisionAgentResult:
        scope_hash = _scope_hash(request.identity)
        trajectory: list[AgentTrajectoryStep] = [
            AgentTrajectoryStep(
                step=1,
                selected_tool="evidence.lookup",
                selection_reason_code="FIXED_EVIDENCE_REQUIRED",
                input_scope_hash=scope_hash,
                input_context_versions={},
                attempt_count=1,
                status="available",
                output_ref=request.identity.evidence_snapshot_id,
                source_refs=(request.identity.evidence_snapshot_id,),
                next_action="collect_operational_context",
            )
        ]
        contexts: dict[str, OperationalContextEnvelope] = {}
        errors: list[dict[str, Any]] = []

        for domain in self.policy.required_domains:
            if len(trajectory) >= self.policy.max_steps:
                errors.append(
                    {
                        "domain": domain,
                        "status": "budget_exhausted",
                        "reason": "MAX_STEP_BUDGET",
                    }
                )
                break

            envelope: OperationalContextEnvelope | None = None
            failure: ValueError | RuntimeError | TimeoutError | None = None
            attempts = 0
            for attempts in range(1, self.policy.max_attempts_per_domain + 1):
                try:
                    envelope = self.ports[domain].lookup(
                        identity=request.identity,
                        retrieved_at=retrieved_at,
                    )
                    failure = None
                    break
                except TimeoutError as exc:
                    failure = exc
                    if attempts >= self.policy.max_attempts_per_domain:
                        break
                except ValueError as exc:
                    failure = exc
                    break
                except RuntimeError as exc:
                    failure = exc
                    if attempts >= self.policy.max_attempts_per_domain:
                        break

            if envelope is not None:
                contexts[domain] = envelope
                trajectory.append(
                    AgentTrajectoryStep(
                        step=len(trajectory) + 1,
                        selected_tool=f"{domain}.lookup",
                        selection_reason_code=_domain_reason(domain),
                        input_scope_hash=scope_hash,
                        input_context_versions=context_version_set(contexts),
                        attempt_count=attempts,
                        status=envelope.status.value,
                        output_ref=(
                            f"{domain}:{envelope.source_version}"
                            if envelope.source_version
                            else None
                        ),
                        source_refs=envelope.source_refs,
                        next_action=(
                            "continue_context_collection"
                            if envelope.status
                            is OperationalContextStatus.AVAILABLE
                            else "record_gap_and_continue"
                        ),
                    )
                )
                continue

            assert failure is not None
            errors.append(
                {
                    "domain": domain,
                    "status": "failed",
                    "reason": type(failure).__name__,
                    "fallback_reason": _external_api_fallback_reason(failure),
                    "message": str(failure),
                    "attempt_count": attempts,
                    "retryable": isinstance(failure, (RuntimeError, TimeoutError)),
                }
            )
            trajectory.append(
                AgentTrajectoryStep(
                    step=len(trajectory) + 1,
                    selected_tool=f"{domain}.lookup",
                    selection_reason_code=_domain_reason(domain),
                    input_scope_hash=scope_hash,
                    input_context_versions=context_version_set(contexts),
                    attempt_count=attempts,
                    status="failed",
                    next_action="record_gap_and_continue",
                )
            )

        relation_context: RelationResolutionResult | None = None
        if len(trajectory) < self.policy.max_steps:
            relation_context = resolve_operational_relations(
                identity=request.identity,
                contexts=contexts,
            )
            trajectory.append(
                AgentTrajectoryStep(
                    step=len(trajectory) + 1,
                    selected_tool="relation.resolve",
                    selection_reason_code="RESOLVE_SOURCE_BACKED_RELATIONSHIPS",
                    input_scope_hash=scope_hash,
                    input_context_versions=context_version_set(contexts),
                    attempt_count=1,
                    status=(
                        "completed"
                        if not relation_context.conflicts
                        else "conflicting"
                    ),
                    output_ref=relation_context.schema_version,
                    source_refs=tuple(
                        reference
                        for relation in relation_context.relationships
                        for reference in relation.source_refs
                    ),
                    next_action=(
                        "compare_operational_options"
                        if not relation_context.conflicts
                        else "record_conflict_and_withhold"
                    ),
                )
            )

        simulation: ImpactSimulationResult | None = None
        if (
            len(trajectory) < self.policy.max_steps
            and relation_context is not None
            and not relation_context.conflicts
        ):
            simulation = simulate_operational_impact(
                identity=request.identity,
                risk_status=request.risk_status,
                contexts=contexts,
                assumptions=self.impact_assumptions,
            )
            trajectory.append(
                AgentTrajectoryStep(
                    step=len(trajectory) + 1,
                    selected_tool="impact.simulate",
                    selection_reason_code="COMPARE_OPERATIONAL_OPTIONS",
                    input_scope_hash=scope_hash,
                    input_context_versions=context_version_set(contexts),
                    attempt_count=1,
                    status="completed",
                    output_ref=simulation.schema_version,
                    source_refs=simulation.source_refs,
                    next_action="validate_temporal_versions",
                )
            )

        temporal = self._validate_versions(
            request=request,
            contexts=contexts,
            validated_at=validated_at,
        )
        if len(trajectory) < self.policy.max_steps:
            trajectory.append(
                AgentTrajectoryStep(
                    step=len(trajectory) + 1,
                    selected_tool="temporal.validate",
                    selection_reason_code="REVALIDATE_DYNAMIC_CONTEXT",
                    input_scope_hash=scope_hash,
                    input_context_versions=context_version_set(contexts),
                    attempt_count=1,
                    status=(
                        "valid" if temporal["valid"] else "snapshot_mismatch"
                    ),
                    source_refs=tuple(
                        reference
                        for envelope in contexts.values()
                        for reference in envelope.source_refs
                    ),
                    next_action=(
                        "compose_structured_brief"
                        if temporal["valid"]
                        else "discard_context_and_result"
                    ),
                )
            )

        if not temporal["valid"]:
            simulation = None
        facts, gaps = _facts_and_gaps(contexts, errors)
        terminal = _terminal_state(
            contexts=contexts,
            errors=errors,
            simulation=simulation,
            temporal_valid=bool(temporal["valid"]),
            budget_exhausted=len(trajectory) >= self.policy.max_steps
            and len(contexts) < len(self.policy.required_domains),
        )
        versions = context_version_set(contexts)
        return OperationalDecisionAgentResult(
            policy_version=self.policy.policy_version,
            terminal_state=terminal,
            identity=request.identity,
            actor_role=request.actor_role,
            intent=request.intent,
            contexts=contexts,
            context_version_set=versions,
            context_version_hash=context_version_set_hash(versions),
            relation_context=relation_context,
            impact_simulation=simulation,
            facts=facts,
            gaps=gaps,
            trajectory=tuple(trajectory),
            temporal_validation=temporal,
        )

    def _validate_versions(
        self,
        *,
        request: OperationalAgentRequest,
        contexts: Mapping[str, OperationalContextEnvelope],
        validated_at: datetime,
    ) -> dict[str, Any]:
        expected = context_version_set(contexts)
        current: dict[str, str] = {}
        mismatches: list[dict[str, Any]] = []
        for domain, original in contexts.items():
            try:
                refreshed = self.ports[domain].lookup(
                    identity=request.identity,
                    retrieved_at=validated_at,
                )
            except (ValueError, RuntimeError, TimeoutError) as exc:
                mismatches.append(
                    {
                        "domain": domain,
                        "expected": original.source_version,
                        "actual": None,
                        "reason": type(exc).__name__,
                        "fallback_reason": _external_api_fallback_reason(exc),
                    }
                )
                continue
            if (
                refreshed.status is OperationalContextStatus.AVAILABLE
                and refreshed.source_version
            ):
                current[domain] = refreshed.source_version
            if (
                refreshed.status != original.status
                or refreshed.source_version != original.source_version
            ):
                mismatches.append(
                    {
                        "domain": domain,
                        "expected": original.source_version,
                        "actual": refreshed.source_version,
                        "expected_status": original.status.value,
                        "actual_status": refreshed.status.value,
                    }
                )
        return {
            "valid": not mismatches,
            "expected_versions": expected,
            "current_versions": current,
            "mismatches": mismatches,
            "validated_at": validated_at.isoformat(),
        }


def _terminal_state(
    *,
    contexts: Mapping[str, OperationalContextEnvelope],
    errors: list[dict[str, Any]],
    simulation: ImpactSimulationResult | None,
    temporal_valid: bool,
    budget_exhausted: bool,
) -> AgentTerminalState:
    if not temporal_valid:
        return AgentTerminalState.BLOCKED
    if budget_exhausted:
        return AgentTerminalState.BLOCKED
    if errors and not contexts:
        return AgentTerminalState.FAILED
    if errors or any(
        envelope.status is not OperationalContextStatus.AVAILABLE
        for envelope in contexts.values()
    ):
        return AgentTerminalState.PARTIAL_WITH_GAPS
    if simulation is None:
        return AgentTerminalState.BLOCKED
    if any(
        option.state is ImpactCalculationState.NOT_CALCULABLE
        for option in simulation.options
    ):
        return AgentTerminalState.PARTIAL_WITH_GAPS
    return AgentTerminalState.COMPLETE


def _facts_and_gaps(
    contexts: Mapping[str, OperationalContextEnvelope],
    errors: list[dict[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    facts: list[dict[str, Any]] = []
    gaps = list(errors)
    for domain, envelope in contexts.items():
        if envelope.status is OperationalContextStatus.AVAILABLE:
            facts.append(
                {
                    "owner_domain": domain,
                    "source_version": envelope.source_version,
                    "as_of": envelope.as_of.isoformat(),
                    "source_refs": list(envelope.source_refs),
                    "data": envelope.data,
                }
            )
        else:
            gaps.append(
                {
                    "domain": domain,
                    "status": envelope.status.value,
                    "limitations": list(envelope.limitations),
                }
            )
    return tuple(facts), tuple(gaps)


def _scope_hash(identity: OperationalRequestIdentity) -> str:
    payload = {
        "organization_id": identity.organization_id,
        "project_id": identity.project_id,
        "workspace_id": identity.workspace_id,
        "asset_id": identity.asset_id,
        "evidence_snapshot_id": identity.evidence_snapshot_id,
    }
    return context_version_set_hash(payload)


def _domain_reason(domain: str) -> str:
    return {
        "production": "PRODUCTION_IMPACT_CONTEXT_REQUIRED",
        "maintenance_readiness": "MAINTENANCE_OPTION_REQUIRES_READINESS",
        "quality_delivery": "QUALITY_DELIVERY_CONSTRAINT_REQUIRED",
    }.get(domain, "OPERATIONAL_CONTEXT_REQUIRED")


def _external_api_fallback_reason(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "external_api_timeout"
    if isinstance(exc, ValueError):
        return "external_api_malformed_response"
    if isinstance(exc, RuntimeError):
        return "external_api_retry_exhausted"
    return "external_api_failed"
