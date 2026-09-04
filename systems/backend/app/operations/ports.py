"""Ports required by the manufacturing Operations application layer.

The Operations package is intentionally adapter-agnostic.  Concrete SQLite/PostgreSQL
repositories are assembled in ``app.dependencies`` and only these small
protocols cross the composition boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class AuditRepositoryPort(Protocol):
    path: str | Path

    def event_activity(self, event_id: str) -> dict[str, Any]: ...

    def record_decision(
        self,
        event_id: str,
        actor: str,
        decision: str,
        note: str | None,
    ) -> dict[str, Any]: ...

    def add_note(self, event_id: str, actor: str, body: str) -> dict[str, Any]: ...

    def add_conversation(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def record_audit(self, **command: Any) -> dict[str, Any]: ...

    def get_agent_review_summary(self, summary_key: str) -> dict[str, Any] | None: ...

    def create_agent_review_workflow_run(self, **record: Any) -> dict[str, Any]: ...

    def expire_stale_agent_review_workflow_run(self, **filters: Any) -> dict[str, Any] | None: ...

    def finish_agent_review_workflow_run(self, workflow_run_id: str, **updates: Any) -> dict[str, Any]: ...

    def get_agent_review_workflow_run(self, workflow_run_id: str) -> dict[str, Any] | None: ...

    def list_agent_review_workflow_runs(self, **filters: Any) -> list[dict[str, Any]]: ...

    def save_agent_review_summary(self, **record: Any) -> dict[str, Any]: ...

    def reset(self) -> None: ...


class MaintenanceLineageQueryPort(Protocol):
    def event_lineage(self, **identity: Any) -> dict[str, Any]: ...


class CompanyContextQueryPort(Protocol):
    def list_records(self, *, project_id: str, workspace_id: str) -> list[dict[str, Any]]: ...

    def seed_records(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        context: dict[str, Any],
    ) -> int: ...


class RoleWorkflowRepositoryPort(Protocol):
    def list_field_actions(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    def list_export_checkpoints(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    def create_export_checkpoint(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def latest_field_statuses(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def record_field_action(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def list_workflow_requests(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    def create_template_publish_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def create_model_release_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...

    def get_workflow_request(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None: ...

    def decide_workflow_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


class ReportAgentPort(Protocol):
    def generate(self, *args: Any, **kwargs: Any) -> tuple[Any, dict[str, Any]]: ...


class AgentReviewLLMPort(Protocol):
    name: str

    def generate_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]: ...


class LayoutPlannerPort(Protocol):
    def plan(self, *args: Any, **kwargs: Any) -> tuple[Any, dict[str, Any]]: ...


class FactorySignalApplicationPort(Protocol):
    def list_events(self, project_id: str = "manufacturing-demo-project") -> list[dict[str, Any]]: ...
    def list_equipment(self, project_id: str = "manufacturing-demo-project") -> list[dict[str, Any]]: ...
    def evidence_snapshot(self, event_id: str) -> dict[str, Any]: ...
    def report(self, event_id: str, request: Any) -> tuple[Any, dict[str, Any]]: ...
    def fixture_snapshot(self, event_id: str) -> dict[str, Any]: ...
    def fixture_items(self) -> list[tuple[str, dict[str, Any]]]: ...
    def fixture_count(self) -> int: ...
    def event_activity(self, event_id: str) -> dict[str, Any]: ...
    def record_audit(self, **command: Any) -> dict[str, Any]: ...


__all__ = [
    "AgentReviewLLMPort",
    "AuditRepositoryPort",
    "CompanyContextQueryPort",
    "FactorySignalApplicationPort",
    "LayoutPlannerPort",
    "MaintenanceLineageQueryPort",
    "ReportAgentPort",
    "RoleWorkflowRepositoryPort",
]
