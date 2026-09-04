"""Read-only domain tool trajectory experiment for agent review context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable


TOOL_PIPELINE_VERSION = "agent-context-tool-pipeline-v0.1"
LANGGRAPH_TOOL_PIPELINE_VERSION = "agent-context-tool-pipeline-langgraph-v0.1"
FORBIDDEN_TOOL_NAMES = {
    "closed_loop.approve_work_order",
    "closed_loop.create_work_order",
    "closed_loop.start_maintenance_action",
    "closed_loop.complete_maintenance_action",
    "closed_loop.create_maintenance_event",
    "closed_loop.request_replay",
    "closed_loop.auto_approve",
}
DEFAULT_TOOL_RETRY_POLICY = {
    "max_attempts": 1,
    "retryable_errors": [],
    "fallback_behavior": "fail_pipeline",
}
TOOL_RETRY_POLICIES = {
    "model_evidence.lookup": {
        "max_attempts": 1,
        "retryable_errors": [],
        "fallback_behavior": "fail_pipeline",
    },
    "maintenance_history.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "operation_context.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "inspection_location.lookup": {
        "max_attempts": 1,
        "retryable_errors": [],
        "fallback_behavior": "fail_pipeline",
    },
    "sop_guidance.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "ontology_neighbors.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "spare_part.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "similar_event.lookup": {
        "max_attempts": 2,
        "retryable_errors": ["TimeoutError", "ConnectionError"],
        "fallback_behavior": "continue_with_gap",
    },
    "data_quality.lookup": {
        "max_attempts": 1,
        "retryable_errors": [],
        "fallback_behavior": "fail_pipeline",
    },
}


@dataclass(frozen=True)
class SituationQuestion:
    question_id: str
    tool_name: str
    reason: str


class SituationQuestionRouter:
    """Select read-only context tools from packet shape and risk situation."""

    def route(self, packet: dict[str, Any]) -> list[SituationQuestion]:
        if _is_data_quality_hold(packet):
            return [
                SituationQuestion(
                    "data-quality-hold",
                    "data_quality.lookup",
                    "validated factors are unavailable; do not invent locations or SOP guidance",
                )
            ]

        questions = [
            SituationQuestion(
                "model-factor-basis",
                "model_evidence.lookup",
                "validated model factors explain why this asset is being reviewed",
            ),
            SituationQuestion(
                "maintenance-history",
                "maintenance_history.lookup",
                "closed-loop history helps avoid duplicate field direction",
            ),
        ]
        if str((packet.get("risk_summary") or {}).get("status_grade") or "") == "critical":
            questions.append(
                SituationQuestion(
                    "production-impact",
                    "operation_context.lookup",
                    "critical reviews need production and cell impact context",
                )
            )
        if packet.get("inspection_targets"):
            questions.append(
                SituationQuestion(
                    "field-location",
                    "inspection_location.lookup",
                    "inspection targets should map model factors to field terms",
                )
            )
        if packet.get("sop_guidance"):
            questions.append(
                SituationQuestion(
                    "standard-inspection-procedure",
                    "sop_guidance.lookup",
                    "structured procedure guidance is available for this component",
                )
            )
        if _has_ontology_context(packet):
            questions.append(
                SituationQuestion(
                    "ontology-neighborhood",
                    "ontology_neighbors.lookup",
                    "ontology context connects component, field location, parts, and similar events",
                )
            )
        if _has_spare_part_context(packet):
            questions.append(
                SituationQuestion(
                    "spare-part-candidate",
                    "spare_part.lookup",
                    "spare-part candidates are available as review context only",
                )
            )
        if _has_similar_event_context(packet):
            questions.append(
                SituationQuestion(
                    "similar-event-history",
                    "similar_event.lookup",
                    "similar resolved events can enrich the summary without creating an action",
                )
            )
        return questions


def run_read_only_tool_pipeline(
    packet: dict[str, Any],
    *,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run deterministic read-only domain tools and return an auditable trajectory."""

    return _run_selected_tools(
        packet,
        SituationQuestionRouter().route(packet),
        executor=executor,
    )


def run_langgraph_tool_pipeline(
    packet: dict[str, Any],
    *,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the same experiment through LangGraph when the dependency is available."""

    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:  # pragma: no cover - dependency varies by environment.
        result = run_read_only_tool_pipeline(packet, executor=executor)
        result["engine"] = "simple"
        result["requested_engine"] = "langgraph"
        result["langgraph_available"] = False
        result["fallback_reason"] = f"{type(exc).__name__}: {exc}"
        return result

    graph = StateGraph(dict)

    def select_questions(state: dict[str, Any]) -> dict[str, Any]:
        state["selected_questions"] = SituationQuestionRouter().route(state["packet"])
        return state

    def execute_tools(state: dict[str, Any]) -> dict[str, Any]:
        state["pipeline_result"] = _run_selected_tools(
            state["packet"],
            state["selected_questions"],
            engine="langgraph",
            pipeline_version=LANGGRAPH_TOOL_PIPELINE_VERSION,
            executor=executor,
        )
        return state

    def validate_boundary(state: dict[str, Any]) -> dict[str, Any]:
        errors = validate_tool_trajectory(state["pipeline_result"])
        state["pipeline_result"]["validation_errors"] = errors
        state["pipeline_result"]["terminal_status"] = "completed" if not errors else "failed"
        return state

    graph.add_node("select_questions", select_questions)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("validate_boundary", validate_boundary)
    graph.set_entry_point("select_questions")
    graph.add_edge("select_questions", "execute_tools")
    graph.add_edge("execute_tools", "validate_boundary")
    graph.add_edge("validate_boundary", END)
    compiled = graph.compile()
    state = compiled.invoke({"packet": packet})
    return state["pipeline_result"]


def validate_tool_trajectory(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("mutation_allowed") is not False:
        errors.append("tool pipeline must remain read-only")
    called_tools = set(result.get("called_tools") or [])
    forbidden = called_tools.intersection(FORBIDDEN_TOOL_NAMES)
    if forbidden:
        errors.append("forbidden closed-loop tools were called: " + ", ".join(sorted(forbidden)))
    packet_refs = set(result.get("source_ref_scope") or [])
    for call in result.get("tool_calls") or []:
        if call.get("status") == "failed":
            errors.append(f"{call.get('tool_name')} failed without an allowed gap fallback")
        source_refs = set(call.get("source_refs") or [])
        if not source_refs.issubset(packet_refs):
            errors.append(f"{call.get('tool_name')} returned source refs outside packet scope")
    return errors


def _run_selected_tools(
    packet: dict[str, Any],
    questions: list[SituationQuestion],
    *,
    engine: str = "simple",
    pipeline_version: str = TOOL_PIPELINE_VERSION,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    packet_hash = _hash(packet)
    packet_refs = _packet_source_refs(packet)
    tool_executor = executor or execute_packet_context_tool
    tool_calls = [
        _execute_tool(
            question,
            packet=packet,
            packet_hash=packet_hash,
            executor=tool_executor,
        )
        for question in questions
    ]
    failed_count = sum(1 for call in tool_calls if call["status"] == "failed")
    gap_count = sum(1 for call in tool_calls if call["status"] == "gap")
    result = {
        "pipeline_version": pipeline_version,
        "engine": engine,
        "langgraph_available": engine == "langgraph",
        "asset_id": str(packet.get("asset_id") or ""),
        "snapshot_basis": packet.get("snapshot_basis") or {},
        "packet_hash": packet_hash,
        "source_ref_scope": sorted(packet_refs),
        "selected_questions": [question.__dict__ for question in questions],
        "called_tools": [call["tool_name"] for call in tool_calls],
        "tool_calls": tool_calls,
        "mutation_allowed": False,
        "closed_loop_mutation_attempted": False,
        "forbidden_tools": sorted(FORBIDDEN_TOOL_NAMES),
        "terminal_status": _terminal_status(failed_count=failed_count, gap_count=gap_count),
    }
    result["validation_errors"] = validate_tool_trajectory(result)
    if result["validation_errors"]:
        result["terminal_status"] = "failed"
    return result


def _execute_tool(
    question: SituationQuestion,
    *,
    packet: dict[str, Any],
    packet_hash: str,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    retry_policy = _tool_retry_policy(question.tool_name)
    max_attempts = max(1, int(retry_policy.get("max_attempts") or 1))
    attempts: list[dict[str, Any]] = []
    output: dict[str, Any] = {}
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            output = executor(question.tool_name, packet)
            attempts.append({"attempt": attempt, "status": "succeeded"})
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            error_type = type(exc).__name__
            retryable = _is_retryable_error(error_type, retry_policy)
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error_type": error_type,
                    "message": str(exc),
                    "retryable": retryable,
                }
            )
            if not retryable or attempt >= max_attempts:
                break
    if last_error is not None:
        fallback_behavior = str(retry_policy.get("fallback_behavior") or "fail_pipeline")
        status = "gap" if fallback_behavior == "continue_with_gap" else "failed"
        return {
            "question_id": question.question_id,
            "tool_name": question.tool_name,
            "status": status,
            "read_only": True,
            "mutation_allowed": False,
            "retry_policy": retry_policy,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "input_snapshot_hash": packet_hash,
            "output_hash": _hash(output),
            "source_refs": [],
            "output": output,
            "fallback_behavior": fallback_behavior,
            "error_type": type(last_error).__name__,
            "error_message": str(last_error),
        }
    return {
        "question_id": question.question_id,
        "tool_name": question.tool_name,
        "status": "succeeded",
        "read_only": True,
        "mutation_allowed": False,
        "retry_policy": retry_policy,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "input_snapshot_hash": packet_hash,
        "output_hash": _hash(output),
        "source_refs": sorted(_collect_source_refs(output).intersection(_packet_source_refs(packet))),
        "output": output,
    }


def _tool_retry_policy(tool_name: str) -> dict[str, Any]:
    policy = TOOL_RETRY_POLICIES.get(tool_name) or DEFAULT_TOOL_RETRY_POLICY
    return {
        "max_attempts": int(policy["max_attempts"]),
        "retryable_errors": list(policy["retryable_errors"]),
        "fallback_behavior": str(policy["fallback_behavior"]),
    }


def _is_retryable_error(error_type: str, retry_policy: dict[str, Any]) -> bool:
    return error_type in set(retry_policy.get("retryable_errors") or [])


def _terminal_status(*, failed_count: int, gap_count: int) -> str:
    if failed_count:
        return "failed"
    if gap_count:
        return "partial"
    return "completed"


def execute_packet_context_tool(tool_name: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Return the packet slice for a read-only context tool."""

    if tool_name == "model_evidence.lookup":
        return packet.get("model_expression_context") or {}
    if tool_name == "maintenance_history.lookup":
        return packet.get("maintenance_history_summary") or {}
    if tool_name == "operation_context.lookup":
        return packet.get("operation_context_summary") or {}
    if tool_name == "inspection_location.lookup":
        return {"inspection_targets": packet.get("inspection_targets") or []}
    if tool_name == "sop_guidance.lookup":
        return {
            "sop_retrieval": packet.get("sop_retrieval") or {},
            "sop_guidance": packet.get("sop_guidance") or [],
        }
    if tool_name == "ontology_neighbors.lookup":
        return packet.get("ontology_context") or {}
    if tool_name == "spare_part.lookup":
        return {"traversals": _traversals_with_key(packet, "spare_parts")}
    if tool_name == "similar_event.lookup":
        return {"traversals": _traversals_with_key(packet, "similar_events")}
    if tool_name == "data_quality.lookup":
        return {
            "review_draft": packet.get("review_draft") or {},
            "evidence_gaps": packet.get("evidence_gaps") or [],
            "limitations": packet.get("limitations") or [],
        }
    return {}


def _traversals_with_key(packet: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [
        traversal
        for traversal in (packet.get("ontology_context") or {}).get("traversals") or []
        if traversal.get(key)
    ]


def _is_data_quality_hold(packet: dict[str, Any]) -> bool:
    return str((packet.get("review_draft") or {}).get("priority_label") or "") == "미확정"


def _has_ontology_context(packet: dict[str, Any]) -> bool:
    return bool((packet.get("ontology_context") or {}).get("traversals"))


def _has_spare_part_context(packet: dict[str, Any]) -> bool:
    return any(
        traversal.get("spare_parts")
        for traversal in (packet.get("ontology_context") or {}).get("traversals") or []
    )


def _has_similar_event_context(packet: dict[str, Any]) -> bool:
    return any(
        traversal.get("similar_events")
        for traversal in (packet.get("ontology_context") or {}).get("traversals") or []
    )


def _packet_source_refs(packet: dict[str, Any]) -> set[str]:
    return {str(ref) for ref in packet.get("source_refs") or [] if ref}


def _collect_source_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_ref" and child:
                refs.add(str(child))
            elif key == "source_refs" and isinstance(child, list):
                refs.update(str(item) for item in child if item)
            else:
                refs.update(_collect_source_refs(child))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_source_refs(item))
    return refs


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
