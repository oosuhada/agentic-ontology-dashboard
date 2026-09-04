"""Read-only context provider contracts for Agent Review Packet composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentReviewContext:
    """Adapter-supplied context that can be safely merged into a review packet."""

    operation_context_summary: dict[str, Any] | None = None
    maintenance_history_summary: dict[str, Any] | None = None
    evidence_gaps: list[dict[str, str]] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def merge_agent_review_contexts(contexts: list[AgentReviewContext]) -> AgentReviewContext:
    """Merge adapter outputs without allowing later adapters to erase earlier context."""

    operation_context_summary = next(
        (
            context.operation_context_summary
            for context in contexts
            if context.operation_context_summary
        ),
        None,
    )
    maintenance_history_summary = next(
        (
            context.maintenance_history_summary
            for context in contexts
            if context.maintenance_history_summary
        ),
        None,
    )
    evidence_gaps = _dedupe_gap_dicts(
        gap for context in contexts for gap in context.evidence_gaps
    )
    source_refs = list(
        dict.fromkeys(ref for context in contexts for ref in context.source_refs if ref)
    )
    limitations = list(
        dict.fromkeys(
            limitation
            for context in contexts
            for limitation in context.limitations
            if limitation
        )
    )
    return AgentReviewContext(
        operation_context_summary=operation_context_summary,
        maintenance_history_summary=maintenance_history_summary,
        evidence_gaps=evidence_gaps,
        source_refs=source_refs,
        limitations=limitations,
    )


class AgentReviewContextProvider(Protocol):
    """Port implemented by domain adapters that contribute AI review context."""

    adapter_id: str

    def context_for_packet(self, *, view_model: dict[str, Any]) -> AgentReviewContext:
        """Return source-ref grounded context without mutating domain state."""


class AgentReviewContextRegistry:
    """Ordered registry of domain adapters used by Agent Review Packet composition."""

    def __init__(
        self,
        providers: list[AgentReviewContextProvider],
        *,
        enabled_adapter_ids: list[str] | None = None,
    ) -> None:
        self._providers_by_id = {
            provider.adapter_id: provider
            for provider in providers
        }
        self._enabled_adapter_ids = list(
            enabled_adapter_ids or self._providers_by_id.keys()
        )

    def context_for_packet(self, *, view_model: dict[str, Any]) -> AgentReviewContext:
        contexts: list[AgentReviewContext] = []
        for adapter_id in self._enabled_adapter_ids:
            provider = self._providers_by_id.get(adapter_id)
            if provider is None:
                contexts.append(
                    _adapter_gap(
                        adapter_id=adapter_id,
                        reason="adapter_not_registered",
                    )
                )
                continue
            try:
                contexts.append(provider.context_for_packet(view_model=view_model))
            except Exception as exc:
                contexts.append(
                    _adapter_gap(
                        adapter_id=adapter_id,
                        reason="adapter_context_unavailable",
                        detail=str(exc),
                    )
                )
        return merge_agent_review_contexts(contexts)

    @property
    def enabled_adapter_ids(self) -> list[str]:
        return list(self._enabled_adapter_ids)


class OperationContextProvider:
    """Build the current operating context section from AssetDetailViewModel data."""

    adapter_id = "operation-context"

    def context_for_packet(self, *, view_model: dict[str, Any]) -> AgentReviewContext:
        operation_context = view_model.get("operation_context") or {}
        operation_summary = operation_context_summary(operation_context)
        source_refs = []
        if operation_summary and operation_summary.get("source_ref"):
            source_refs.append(str(operation_summary["source_ref"]))
        return AgentReviewContext(
            operation_context_summary=operation_summary,
            source_refs=source_refs,
            limitations=[
                str(item)
                for item in (operation_context.get("limitations") or [])
                if str(item)
            ],
        )


class MaintenanceHistoryContextProvider:
    """Build read-only maintenance history from existing ViewModel records."""

    adapter_id = "maintenance-history"

    def context_for_packet(self, *, view_model: dict[str, Any]) -> AgentReviewContext:
        closed_loop = view_model.get("closed_loop") or {}
        equipment_history = view_model.get("equipment_history") or []
        maintenance_context = view_model.get("maintenance_context") or {}
        work_orders = [
            _history_record(item, source_prefix="closed-loop://work-order")
            for item in closed_loop.get("work_orders") or []
            if isinstance(item, dict)
        ]
        inspection_results = [
            _history_record(item, source_prefix="closed-loop://inspection-result")
            for item in closed_loop.get("inspection_results") or []
            if isinstance(item, dict)
        ]
        maintenance_actions = [
            _history_record(item, source_prefix="closed-loop://maintenance-action")
            for item in closed_loop.get("maintenance_actions") or []
            if isinstance(item, dict)
        ]
        maintenance_events = [
            _history_record(item, source_prefix="closed-loop://maintenance-event")
            for item in closed_loop.get("maintenance_events") or []
            if isinstance(item, dict)
        ]
        activities = [
            _history_record(item, source_prefix="closed-loop://activity")
            for item in closed_loop.get("activities") or []
            if isinstance(item, dict)
        ]
        recent_equipment_history = [
            {
                "description": str(item.get("description") or ""),
                "occurred_at": str(item.get("occurred_at") or ""),
                "source_ref": f"equipment-history://{index + 1}",
            }
            for index, item in enumerate(equipment_history[:3])
            if isinstance(item, dict)
        ]
        source_refs = list(
            dict.fromkeys(
                ref
                for record in [
                    *work_orders,
                    *inspection_results,
                    *maintenance_actions,
                    *maintenance_events,
                    *activities,
                    *recent_equipment_history,
                ]
                for ref in [str(record.get("source_ref") or "")]
                if ref
            )
        )
        return AgentReviewContext(
            maintenance_history_summary={
                "provider": "closed_loop_maintenance_history_adapter",
                "mutation_allowed": False,
                "last_maintenance_days_ago": maintenance_context.get(
                    "last_maintenance_days_ago"
                ),
                "similar_events_30d": maintenance_context.get("similar_events_30d"),
                "open_work_order_exists": maintenance_context.get(
                    "open_work_order_exists"
                ),
                "work_orders": work_orders,
                "inspection_results": inspection_results,
                "maintenance_actions": maintenance_actions,
                "maintenance_events": maintenance_events,
                "activities": activities[:5],
                "similar_events": [],
                "recent_equipment_history": recent_equipment_history,
                "source_refs": source_refs,
            },
            source_refs=source_refs,
        )


def default_agent_review_context_registry() -> AgentReviewContextRegistry:
    """Return the default ordered domain adapter set for manufacturing Operations."""

    return AgentReviewContextRegistry(
        [OperationContextProvider(), MaintenanceHistoryContextProvider()]
    )


def compose_default_agent_review_context(*, view_model: dict[str, Any]) -> AgentReviewContext:
    """Return the built-in context set used by the Operations packet composer."""

    return default_agent_review_context_registry().context_for_packet(view_model=view_model)


def operation_context_summary(context: dict[str, Any]) -> dict[str, Any] | None:
    if not context:
        return None

    event_impact = context.get("event_impact") or {}
    event_basis = event_impact.get("basis") or {}
    production_plan = context.get("production_plan") or {}
    capacity_model = context.get("capacity_model") or {}
    context_id = str(context.get("context_id") or "")

    return {
        "production_impact": context.get("production_impact"),
        "estimated_downtime_minutes": _number_or_none(
            event_basis.get("estimated_downtime_minutes")
        ),
        "estimated_lost_units": _number_or_none(event_impact.get("estimated_lost_units")),
        "product_variant": event_impact.get("product_variant")
        or production_plan.get("product_variant"),
        "basis": str(capacity_model.get("basis") or ""),
        "limitations": [str(item) for item in context.get("limitations") or []],
        "source_ref": f"operation-context://{context_id}" if context_id else None,
    }


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _adapter_gap(
    *,
    adapter_id: str,
    reason: str,
    detail: str = "",
) -> AgentReviewContext:
    return AgentReviewContext(
        evidence_gaps=[
            {
                "field": f"adapter_context.{adapter_id}",
                "reason": reason if not detail else f"{reason}: {detail}",
                "owner_domain": adapter_id,
            }
        ]
    )


def _history_record(item: dict[str, Any], *, source_prefix: str) -> dict[str, Any]:
    record_type = source_prefix.removeprefix("closed-loop://")
    preferred_ids = {
        "work-order": ("work_order_id",),
        "inspection-result": ("inspection_result_id", "work_order_id"),
        "maintenance-action": ("maintenance_action_id", "work_order_id"),
        "maintenance-event": (
            "maintenance_event_id",
            "maintenance_action_id",
            "work_order_id",
        ),
        "activity": ("activity_id", "id", "work_order_id"),
    }.get(record_type, ())
    record_id = str(
        next((item.get(key) for key in preferred_ids if item.get(key)), None)
        or item.get("id")
        or ""
    )
    return {
        "record_id": record_id,
        "record_type": record_type,
        "status": str(item.get("status") or item.get("outcome") or ""),
        "activity_type": str(item.get("activity_type") or ""),
        "recorded_at": str(
            item.get("recorded_at")
            or item.get("completed_at")
            or item.get("created_at")
            or item.get("updated_at")
            or ""
        ),
        "summary": str(
            item.get("label") or item.get("note") or item.get("outcome") or ""
        ),
        "source_ref": f"{source_prefix}/{record_id}" if record_id else source_prefix,
    }


def _dedupe_gap_dicts(gaps: Any) -> list[dict[str, str]]:
    return [
        dict(zip(("field", "reason", "owner_domain"), key))
        for key in dict.fromkeys(
            (
                str(gap.get("field") or ""),
                str(gap.get("reason") or ""),
                str(gap.get("owner_domain") or ""),
            )
            for gap in gaps
        )
    ]
