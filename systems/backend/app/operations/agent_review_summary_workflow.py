"""Minimal orchestration boundary for Agent Review Summary materialization."""

from __future__ import annotations

from typing import Any, Protocol


AGENT_REVIEW_SUMMARY_FLOW_VERSION = "agent-review-summary-flow-v1.0"
AGENT_REVIEW_SUMMARY_WORKFLOW_ENGINE = "simple"
DEFAULT_WORKFLOW_MAX_ATTEMPTS = 2
DEFAULT_WATCHER_INTERVAL_SECONDS = 60.0
WORKFLOW_RETRY_POLICY = {
    "snapshot_scan": "retry transient service failures; fail fast on invalid project or asset scope",
    "packet_build": "service-owned validation; retry only if the whole run is retried",
    "summary_materialization": "provider failures become fallback summaries; service exceptions may retry",
    "consumer_ready": "no retry; reports stored materialization status only",
}


class AgentReviewSummaryWorkflowService(Protocol):
    """Service surface required by the read-only summary workflow."""

    def materialize_agent_review_summaries(
        self,
        project_id: str = "manufacturing-demo-project",
        *,
        history_window: str = "24h",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Create or reuse validated summaries for available snapshots."""


class AgentReviewSummaryWorkflow:
    """Run the polling-watcher AI flow without granting mutation authority."""

    def __init__(self, service: AgentReviewSummaryWorkflowService) -> None:
        self.service = service

    def run(
        self,
        project_id: str = "manufacturing-demo-project",
        *,
        history_window: str = "24h",
        limit: int | None = None,
        trigger: str = "polling_watcher",
        max_attempts: int = DEFAULT_WORKFLOW_MAX_ATTEMPTS,
        operating_mode: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt_limit = max(1, int(max_attempts))
        mode = _operating_mode(
            trigger=trigger,
            history_window=history_window,
            limit=limit,
            max_attempts=attempt_limit,
            operating_mode=operating_mode,
        )
        attempts: list[dict[str, Any]] = []
        materialization: dict[str, Any] | None = None
        for attempt in range(1, attempt_limit + 1):
            try:
                materialization = self.service.materialize_agent_review_summaries(
                    project_id,
                    history_window=history_window,
                    limit=limit,
                )
                attempts.append({"attempt": attempt, "status": "succeeded"})
                break
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                if attempt >= attempt_limit:
                    return _failed_workflow_result(
                        trigger=trigger,
                        attempts=attempts,
                        max_attempts=attempt_limit,
                        operating_mode=mode,
                    )

        if materialization is None:
            return _failed_workflow_result(
                trigger=trigger,
                attempts=attempts,
                max_attempts=attempt_limit,
                operating_mode=mode,
            )

        materialized_count = int(materialization.get("materialized_count") or 0)
        created_count = int(materialization.get("created_count") or 0)
        reused_count = int(materialization.get("reused_count") or 0)
        failed_count = sum(
            1
            for item in materialization.get("items") or []
            if str(item.get("status") or "") == "failed"
        )
        return {
            "flow_version": AGENT_REVIEW_SUMMARY_FLOW_VERSION,
            "trigger": trigger,
            "read_only": True,
            "mutation_allowed": False,
            "operating_mode": mode,
            "workflow": {
                "engine": AGENT_REVIEW_SUMMARY_WORKFLOW_ENGINE,
                "max_attempts": attempt_limit,
                "attempt_count": len(attempts),
                "terminal_status": "completed" if failed_count == 0 else "partial",
                "retry_policy": WORKFLOW_RETRY_POLICY,
                "attempts": attempts,
            },
            "stages": [
                {
                    "stage": "snapshot_scan",
                    "status": "completed",
                    "item_count": materialized_count,
                },
                {
                    "stage": "packet_build",
                    "status": "completed",
                    "item_count": materialized_count,
                },
                {
                    "stage": "summary_materialization",
                    "status": "completed" if failed_count == 0 else "partial",
                    "created_count": created_count,
                    "reused_count": reused_count,
                    "failed_count": failed_count,
                },
                {
                    "stage": "consumer_ready",
                    "status": "completed" if failed_count == 0 else "partial",
                    "consumer_contract": "agent-review-summary-v1.0",
                    "consumers": ["role_workflow_ui", "executive_brief_report"],
                },
            ],
            **materialization,
        }


def _failed_workflow_result(
    *,
    trigger: str,
    attempts: list[dict[str, Any]],
    max_attempts: int,
    operating_mode: dict[str, Any],
) -> dict[str, Any]:
    return {
        "flow_version": AGENT_REVIEW_SUMMARY_FLOW_VERSION,
        "trigger": trigger,
        "read_only": True,
        "mutation_allowed": False,
        "operating_mode": operating_mode,
        "workflow": {
            "engine": AGENT_REVIEW_SUMMARY_WORKFLOW_ENGINE,
            "max_attempts": max_attempts,
            "attempt_count": len(attempts),
            "terminal_status": "failed",
            "retry_policy": WORKFLOW_RETRY_POLICY,
            "attempts": attempts,
        },
        "materialized_count": 0,
        "created_count": 0,
        "reused_count": 0,
        "items": [],
        "stages": [
            {
                "stage": "snapshot_scan",
                "status": "failed",
                "item_count": 0,
            },
            {
                "stage": "packet_build",
                "status": "skipped",
                "item_count": 0,
            },
            {
                "stage": "summary_materialization",
                "status": "skipped",
                "created_count": 0,
                "reused_count": 0,
                "failed_count": 0,
            },
            {
                "stage": "consumer_ready",
                "status": "blocked",
                "consumer_contract": "agent-review-summary-v1.0",
                "consumers": ["role_workflow_ui", "executive_brief_report"],
            },
        ],
    }


def _operating_mode(
    *,
    trigger: str,
    history_window: str,
    limit: int | None,
    max_attempts: int,
    operating_mode: dict[str, Any] | None,
) -> dict[str, Any]:
    configured = dict(operating_mode or {})
    run_mode = str(configured.get("mode") or ("watch" if trigger == "polling_watcher" else "single_trigger"))
    interval = configured.get("poll_interval_seconds")
    if interval is None:
        interval = DEFAULT_WATCHER_INTERVAL_SECONDS if run_mode == "watch" else None
    return {
        "mode": run_mode,
        "target_scope": str(configured.get("target_scope") or "project"),
        "history_window": history_window,
        "limit": limit,
        "stale_detection": str(configured.get("stale_detection") or "summary_key"),
        "summary_duplicate_policy": str(
            configured.get("summary_duplicate_policy") or "reuse_existing_summary"
        ),
        "run_record_policy": str(
            configured.get("run_record_policy") or "record_each_explicit_trigger"
        ),
        "poll_interval_seconds": interval,
        "max_iterations": configured.get("max_iterations"),
        "max_attempts": max_attempts,
        "stop_behavior": str(
            configured.get("stop_behavior")
            or ("bounded_iterations_or_signal" if run_mode == "watch" else "return_after_run")
        ),
    }
