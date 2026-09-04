"""Dataset-owned public contracts shared with upstream and downstream domains."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class DatasetPrincipal(Protocol):
    organization_id: str
    user_id: str
    permissions: list[str]
    project_scopes: list[str]
    workspace_scopes: list[str]
    active_project_id: str | None


@runtime_checkable
class ObservationDatasetQuery(Protocol):
    """Public read contract that Diagnosis may consume without importing persistence."""

    def load(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        limit: int,
        version_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
        """Return immutable observation rows, freshness, and provenance metadata."""


__all__ = ["DatasetPrincipal", "ObservationDatasetQuery"]
