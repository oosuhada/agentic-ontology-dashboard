"""Measured agent-routing/tool/evidence benchmark over the committed 120-task matrix."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from app.dependencies import build_manufacturing_service
from app.operations.agent_context_tool_pipeline import (
    FORBIDDEN_TOOL_NAMES,
    execute_packet_context_tool,
    run_read_only_tool_pipeline,
)
from app.operations.agent_response_contract import (
    plan_agent_response_contract,
    route_for_response_contract,
)
from app.operations.agent_review_summary import (
    compose_deterministic_agent_review_summary,
    validate_agent_review_summary_contract,
)

from evaluation.agent_workflow_task_set import AGENT_WORKFLOW_TASKS, AgentWorkflowTask


ROOT = Path(__file__).resolve().parents[1]
TOOL_GOLD_PATH = ROOT / "tests" / "eval" / "agent_tool_trajectory_gold.jsonl"


def _load_tool_gold() -> dict[str, dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in TOOL_GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["case_id"]: row for row in rows}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(_percentile(values, 0.50), 4),
        "p95_ms": round(_percentile(values, 0.95), 4),
        "mean_ms": round(statistics.mean(values), 4) if values else 0.0,
        "variance_ms2": round(statistics.pvariance(values), 6) if values else 0.0,
    }


def _retryable_failure_tool(expected_tools: list[str]) -> str | None:
    for tool_name in (
        "maintenance_history.lookup",
        "operation_context.lookup",
        "sop_guidance.lookup",
        "ontology_neighbors.lookup",
        "spare_part.lookup",
        "similar_event.lookup",
    ):
        if tool_name in expected_tools:
            return tool_name
    return None


def _failure_executor(
    task: AgentWorkflowTask,
    expected_tools: list[str],
) -> tuple[Callable[[str, dict[str, Any]], dict[str, Any]] | None, str | None]:
    if not task.injected_failure:
        return None, None
    target = _retryable_failure_tool(expected_tools)
    if not target:
        return None, None

    attempts = Counter()

    def execute(tool_name: str, packet: dict[str, Any]) -> dict[str, Any]:
        attempts[tool_name] += 1
        if tool_name == target:
            if task.injected_failure == "transient_once" and attempts[tool_name] == 1:
                raise TimeoutError("benchmark injected transient timeout")
            if task.injected_failure == "timeout_exhausted":
                raise TimeoutError("benchmark injected persistent timeout")
        return execute_packet_context_tool(tool_name, packet)

    return execute, target


def _baseline_result(packet: dict[str, Any], expected_tools: list[str]) -> dict[str, Any]:
    source_refs = [str(ref) for ref in packet.get("source_refs") or [] if str(ref)]
    return {
        "route": "relational",
        "called_tools": [],
        "tool_exact": not expected_tools,
        "evidence_correct": all(ref in set(source_refs) for ref in source_refs[:4]),
        "role_policy_violation": False,
        "unsupported_claim": None,
        "fallback_success": None,
        "external_model_tokens": 0,
    }


def _candidate_result(
    *,
    task: AgentWorkflowTask,
    packet: dict[str, Any],
    expected_tools: list[str],
) -> dict[str, Any]:
    contract = plan_agent_response_contract(
        task.question,
        route="auto",
        object_id=task.asset_id,
    )
    route = route_for_response_contract(contract)
    executor, failure_tool = _failure_executor(task, expected_tools)
    pipeline = run_read_only_tool_pipeline(packet, executor=executor)
    summary = compose_deterministic_agent_review_summary(packet)
    summary_errors = validate_agent_review_summary_contract(summary, packet=packet)
    packet_refs = {str(ref) for ref in packet.get("source_refs") or [] if str(ref)}
    returned_refs = {
        str(ref)
        for call in pipeline.get("tool_calls") or []
        for ref in call.get("source_refs") or []
        if str(ref)
    }
    called_tools = list(pipeline.get("called_tools") or [])
    forbidden_called = bool(set(called_tools).intersection(FORBIDDEN_TOOL_NAMES))
    role_policy_violation = (
        pipeline.get("mutation_allowed") is not False
        or bool(pipeline.get("closed_loop_mutation_attempted"))
        or forbidden_called
        or any(
            error.startswith("forbidden_fields:") or error.startswith("forbidden_claims:")
            for error in summary_errors
        )
    )
    fallback_success = None
    if failure_tool:
        target_call = next(
            call
            for call in pipeline.get("tool_calls") or []
            if call.get("tool_name") == failure_tool
        )
        fallback_success = (
            target_call.get("status") in {"succeeded", "gap"}
            and pipeline.get("terminal_status") in {"completed", "partial"}
        )
    unsupported_claim = bool(summary_errors)
    return {
        "route": route,
        "called_tools": called_tools,
        "tool_exact": called_tools == expected_tools,
        "evidence_correct": returned_refs.issubset(packet_refs) and not any(
            "source_refs_unknown" in error for error in summary_errors
        ),
        "role_policy_violation": role_policy_violation,
        "unsupported_claim": unsupported_claim,
        "fallback_success": fallback_success,
        "external_model_tokens": 0,
        "terminal_status": pipeline.get("terminal_status"),
        "summary_validation_errors": summary_errors,
        "failure_tool": failure_tool,
    }


def _aggregate(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    count = len(rows)
    unsupported = [row[kind]["unsupported_claim"] for row in rows if row[kind]["unsupported_claim"] is not None]
    fallback = [row[kind]["fallback_success"] for row in rows if row[kind]["fallback_success"] is not None]
    return {
        "tasks": count,
        "route_accuracy": round(
            sum(row[kind]["route"] == row["expected_route"] for row in rows) / count,
            4,
        ),
        "exact_tool_selection_accuracy": round(
            sum(bool(row[kind]["tool_exact"]) for row in rows) / count,
            4,
        ),
        "evidence_correctness": round(
            sum(bool(row[kind]["evidence_correct"]) for row in rows) / count,
            4,
        ),
        "unsupported_claim_rate": (
            round(sum(bool(value) for value in unsupported) / len(unsupported), 4)
            if unsupported
            else None
        ),
        "role_policy_violation_rate": round(
            sum(bool(row[kind]["role_policy_violation"]) for row in rows) / count,
            4,
        ),
        "fallback_success_rate": (
            round(sum(bool(value) for value in fallback) / len(fallback), 4)
            if fallback
            else None
        ),
        "failure_injection_tasks": len(fallback),
        "external_model_tokens": sum(int(row[kind]["external_model_tokens"]) for row in rows),
        "latency_ms": _latency_summary([float(row[f"{kind}_latency_ms"]) for row in rows]),
    }


def run_benchmark(*, repeats: int = 3) -> dict[str, Any]:
    gold = _load_tool_gold()
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ontology-agent-bench-") as temporary_directory:
        service = build_manufacturing_service(
            Path(temporary_directory) / "benchmark.db",
            root=ROOT,
        )
        packets = {
            asset_id: service.agent_review_packet(asset_id)
            for asset_id in {task.asset_id for task in AGENT_WORKFLOW_TASKS}
        }

        for task in AGENT_WORKFLOW_TASKS:
            expected_tools = list(gold[task.gold_case_id]["expected_tools"])
            packet = packets[task.asset_id]
            baseline_latencies: list[float] = []
            candidate_latencies: list[float] = []
            baseline: dict[str, Any] = {}
            candidate: dict[str, Any] = {}
            for _ in range(max(1, repeats)):
                started = time.perf_counter_ns()
                baseline = _baseline_result(packet, expected_tools)
                baseline_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

                started = time.perf_counter_ns()
                candidate = _candidate_result(
                    task=task,
                    packet=packet,
                    expected_tools=expected_tools,
                )
                candidate_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

            rows.append(
                {
                    "case_id": task.case_id,
                    "difficulty": task.difficulty,
                    "audience": task.audience,
                    "gold_case_id": task.gold_case_id,
                    "asset_id": task.asset_id,
                    "expected_route": task.expected_route,
                    "expected_tools": expected_tools,
                    "injected_failure": task.injected_failure,
                    "baseline": baseline,
                    "candidate": candidate,
                    "baseline_latency_ms": statistics.median(baseline_latencies),
                    "candidate_latency_ms": statistics.median(candidate_latencies),
                }
            )

    by_difficulty = {
        difficulty: {
            "baseline": _aggregate(
                [row for row in rows if row["difficulty"] == difficulty], "baseline"
            ),
            "candidate": _aggregate(
                [row for row in rows if row["difficulty"] == difficulty], "candidate"
            ),
        }
        for difficulty in ("easy", "medium", "adversarial")
    }
    return {
        "experiment": "agentic-ontology-readonly-workflow-eval-v1",
        "question": (
            "Does situation-routed, read-only tool orchestration improve route/tool selection "
            "while preserving evidence and action boundaries over a packet-only baseline?"
        ),
        "dataset": {
            "tasks": len(rows),
            "easy": sum(row["difficulty"] == "easy" for row in rows),
            "medium": sum(row["difficulty"] == "medium" for row in rows),
            "adversarial": sum(row["difficulty"] == "adversarial" for row in rows),
            "audiences": ["engineering", "operations", "executive", "maintenance"],
            "gold_tool_plans": str(TOOL_GOLD_PATH.relative_to(ROOT)),
        },
        "repeats_per_task": max(1, repeats),
        "baseline_definition": (
            "packet-only relational baseline: no situation tool planner and no free-form model call"
        ),
        "candidate_definition": (
            "response-contract routing + situation-selected read-only tools + deterministic grounded summary validation"
        ),
        "baseline": _aggregate(rows, "baseline"),
        "candidate": _aggregate(rows, "candidate"),
        "by_difficulty": by_difficulty,
        "limitations": [
            "The 120 tasks expand three previously committed gold operational scenarios across wording, difficulty, and four audiences; they are not 120 independent factory incidents.",
            "External LLM composition is intentionally disabled to isolate deterministic routing, tool selection, evidence scope, fallback, and policy behavior; measured external model token usage is therefore zero for this experiment.",
            "Unsupported-claim rate is evaluated on the deterministic grounded summary contract; it is not a substitute for a separate live-provider factuality benchmark.",
            "Latency is local Python execution over fixture-backed packets, not a production network latency claim.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 120-task read-only agent workflow benchmark.")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = run_benchmark(repeats=max(1, args.repeats))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    if args.strict:
        candidate = result["candidate"]
        if candidate["route_accuracy"] < 0.8:
            raise SystemExit("candidate route accuracy below 0.80")
        if candidate["exact_tool_selection_accuracy"] < 0.95:
            raise SystemExit("candidate tool selection accuracy below 0.95")
        if candidate["evidence_correctness"] < 1.0:
            raise SystemExit("candidate evidence correctness below 1.00")
        if candidate["role_policy_violation_rate"] > 0.0:
            raise SystemExit("candidate role-policy violation rate above 0.00")
        if candidate["fallback_success_rate"] is not None and candidate["fallback_success_rate"] < 0.95:
            raise SystemExit("candidate fallback success below 0.95")


if __name__ == "__main__":
    main()
