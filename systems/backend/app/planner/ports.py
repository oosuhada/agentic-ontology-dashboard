"""Public ports consumed or owned by the Planner application capability."""

from __future__ import annotations

from typing import Any, Protocol


class PlannerLLMPort(Protocol):
    """Planner-owned structured-generation contract implemented by Infra LLM adapters."""

    name: str

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class PlannerEvidencePort(Protocol):
    """Narrow read contract for evidence-backed narrative planning."""

    def evidence_snapshot(self, event_id: str) -> dict[str, Any]: ...


class PlannerDashboardPort(Protocol):
    """Dashboard-facing operations needed to preview Planner recommendations."""

    def resolve(self, *, principal: Any, workspace_id: str) -> Any: ...

    def catalog(self, *, principal: Any, role_code: str) -> Any: ...

    def current_template(self, *, workspace_id: str, role_code: str) -> Any: ...

    def make_board(self, **values: Any) -> Any: ...

    def make_tab(self, **values: Any) -> Any: ...

    def make_publish_request(self, **values: Any) -> Any: ...

    def validate_template_draft(
        self,
        *,
        role_code: str,
        template: Any,
        request: Any,
    ) -> list[Any]: ...


class PlannerVisualizationPort(Protocol):
    """Typed visualization primitives supplied by the visualization owner/composition."""

    source_version: str
    model_version: str
    result_schema_version: str
    registry_kinds: frozenset[str]

    def parse_field_profile(self, value: Any) -> Any: ...

    def parse_candidate(self, value: Any) -> Any: ...

    def parse_semantic_request(self, value: Any) -> Any: ...

    def context_from_source(self, source: Any) -> Any: ...

    def build_semantic_catalog(self, context: Any) -> dict[str, Any]: ...

    def build_typed_query_plan(
        self,
        request: Any,
        catalog: dict[str, Any],
        *,
        selected_kind: str | None = None,
    ) -> tuple[Any, list[Any]]: ...

    def validate_override(self, override: Any, plan: Any, catalog: dict[str, Any]) -> Any: ...

    def validate_override_channel_mapping(self, override: Any, plan: Any) -> None: ...

    def compile_query(self, plan: Any, catalog: dict[str, Any], *, clamp_limits: bool) -> Any: ...

    def make_semantic_response(self, **values: Any) -> Any: ...


__all__ = [
    "PlannerDashboardPort",
    "PlannerEvidencePort",
    "PlannerLLMPort",
    "PlannerVisualizationPort",
]
