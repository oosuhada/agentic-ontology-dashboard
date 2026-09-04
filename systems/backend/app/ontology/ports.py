"""Public dependency-inversion ports owned by the Ontology domain."""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from app.project.project_domain import ProjectContext

from .ontology_domain import LinkRecord, ObjectRecord


class OntologyActionRepositoryPort(Protocol):
    def resolve_scope(self, workspace_id: str) -> ProjectContext: ...

    def reserve(
        self,
        *,
        idempotency_key: str,
        workspace_id: str,
        action_type: str,
        object_id: str,
        actor_user_id: str,
        actor_display_name: str,
        request_hash: str,
        request: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]: ...

    def succeed(
        self,
        invocation_id: str,
        *,
        project_id: str,
        result: dict[str, Any],
        audit_id: str,
    ) -> dict[str, Any]: ...

    def fail(
        self,
        invocation_id: str,
        *,
        project_id: str,
        code: str,
        message: str,
        recovery_state: str = "retryable",
    ) -> None: ...

    def list_for_object(self, *, workspace_id: str, object_id: str) -> list[dict[str, Any]]: ...


class OntologyInstanceRepositoryPort(Protocol):
    def replace_source_snapshot(
        self,
        *,
        workspace_id: str,
        source_system: str,
        source_revision: str,
        objects: Iterable[ObjectRecord],
        links: Iterable[LinkRecord],
    ) -> None: ...

    def list_objects(
        self,
        *,
        workspace_id: str,
        object_type: str | None = None,
    ) -> list[ObjectRecord]: ...

    def get_object(self, *, workspace_id: str, object_id: str) -> ObjectRecord | None: ...

    def list_links(
        self,
        *,
        workspace_id: str,
        link_type: str | None = None,
    ) -> list[LinkRecord]: ...


class OntologyObjectQueryPort(Protocol):
    """Public Ontology read contract consumed by Planner and other query clients."""

    def query_objects(
        self,
        *,
        workspace_id: str,
        object_type: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]: ...

    def object_type_registry(self) -> dict[str, Any]: ...


class OntologyActionHistoryPort(Protocol):
    """Read-only action history exposed without leaking repository internals."""

    def list_actions_for_object(
        self, *, workspace_id: str, object_id: str
    ) -> list[dict[str, Any]]: ...


class LiveOntologyProjectionPort(Protocol):
    def materialize_live_projection(self, batch: dict[str, Any]) -> dict[str, Any]: ...


class OntologyAuditPort(Protocol):
    def record_audit(
        self,
        *,
        event_id: str,
        run_id: str,
        action: str,
        model_version: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class OntologyEventCommandPort(Protocol):
    repository: OntologyAuditPort

    def decide(self, event_id: str, request: object) -> dict[str, Any]: ...

    def note(self, event_id: str, request: object) -> dict[str, Any]: ...

    def _fixture(self, event_id: str) -> dict[str, Any]: ...


class OntologyFieldActionPort(Protocol):
    def list_field_actions(self, *, workspace_id: str, event_id: str) -> list[dict[str, Any]]: ...

    def record_field_action(
        self,
        *,
        workspace_id: str,
        event_id: str,
        action: str,
        actor_user_id: str,
        actor_display_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


__all__ = [
    "OntologyActionRepositoryPort",
    "OntologyActionHistoryPort",
    "OntologyAuditPort",
    "OntologyEventCommandPort",
    "OntologyFieldActionPort",
    "OntologyInstanceRepositoryPort",
    "LiveOntologyProjectionPort",
    "OntologyObjectQueryPort",
]
