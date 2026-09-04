from __future__ import annotations

from typing import Any, Protocol, Sequence


class GovernancePrincipal(Protocol):
    organization_id: str
    user_id: str
    project_scopes: Sequence[str]
    workspace_scopes: Sequence[str]
    active_project_id: str | None
    active_project_roles: Sequence[str]
    roles: Sequence[str]
    permissions: Sequence[str]


class GovernanceDatasetPort(Protocol):
    def list_datasets(self, **scope: Any) -> list[dict[str, Any]]: ...
    def list_project_projections(self, **scope: Any) -> list[dict[str, Any]]: ...
    def get_dataset(self, **scope: Any) -> dict[str, Any]: ...
    def list_versions(self, **scope: Any) -> list[dict[str, Any]]: ...
    def list_materializations(self, **scope: Any) -> list[dict[str, Any]]: ...
    def get_projection(self, **scope: Any) -> dict[str, Any]: ...
    def retry_projection(self, **scope: Any) -> None: ...


class GovernanceApprovalPort(Protocol):
    def list_workflow_requests(self, **scope: Any) -> list[dict[str, Any]]: ...


class ModelReleaseCandidateQueryPort(Protocol):
    """Diagnosis-owned release metadata boundary consumed by Governance."""

    def release_candidate(self, model_version_id: str, **scope: Any) -> dict[str, Any]: ...


__all__ = [
    "GovernanceApprovalPort",
    "GovernanceDatasetPort",
    "GovernancePrincipal",
    "ModelReleaseCandidateQueryPort",
]
