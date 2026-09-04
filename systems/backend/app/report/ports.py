from __future__ import annotations

from typing import Any, Protocol, Sequence


class ReportPrincipal(Protocol):
    user_id: str
    display_name: str
    organization_id: str
    active_project_id: str | None
    roles: Sequence[str]
    is_admin: bool


class ReportGenerationProviderPort(Protocol):
    name: str

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ReportRepositoryPort(Protocol):
    def resolve_scope(self, workspace_id: str, **scope: Any) -> Any: ...
    def create_checkpoint(self, **command: Any) -> dict[str, Any]: ...
    def list_checkpoints(self, **query: Any) -> list[dict[str, Any]]: ...
    def get_draft(self, **query: Any) -> dict[str, Any] | None: ...
    def save_draft(self, **command: Any) -> dict[str, Any]: ...


class DashboardSnapshotPort(Protocol):
    def dashboard_snapshot(self, *, principal: ReportPrincipal, workspace_id: str) -> dict[str, Any]: ...


class DiagnosisEvidencePort(Protocol):
    def event_report_snapshot(self, *, event_id: str, principal: ReportPrincipal) -> dict[str, Any]: ...


class MaintenanceHistoryPort(Protocol):
    def role_workspace_snapshot(
        self,
        *,
        principal: ReportPrincipal,
        workspace_id: str,
    ) -> dict[str, Any]: ...


class ReportAuditPort(Protocol):
    def record_report_audit(self, **command: Any) -> dict[str, Any]: ...


__all__ = [
    "DashboardSnapshotPort",
    "DiagnosisEvidencePort",
    "MaintenanceHistoryPort",
    "ReportAuditPort",
    "ReportGenerationProviderPort",
    "ReportPrincipal",
    "ReportRepositoryPort",
]
