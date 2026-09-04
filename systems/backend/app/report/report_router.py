"""Report draft, export artifact, and checkpoint HTTP adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from app.common.rate_limit import EXPORT_RATE, RateLimiter

from .report_schema import AppLocale, ExportRequest, ReportDraftSaveRequest, Role
from .report_service import ReportService


def build_report_router(
    *,
    get_report_service: Callable[..., ReportService],
    get_identity_service: Callable[..., Any],
    get_rate_limiter: Callable[..., RateLimiter],
    rate_limit_subject: Callable[..., str],
    require_csrf: Callable[..., None],
    require_permission: Callable[[str], Any],
) -> APIRouter:
    router = APIRouter(tags=["reports", "exports"])

    @router.get("/api/reports/draft")
    def get_report_draft(
        workspace_id: str,
        event_id: str,
        role: Role = Query(default="engineer"),
        locale: AppLocale = Query(default="ko-KR"),
        principal: Any = Depends(require_permission("events.read")),
        identity: Any = Depends(get_identity_service),
        reports: ReportService = Depends(get_report_service),
    ):
        identity.require_workspace(principal, workspace_id)
        draft = reports.get_draft(
            workspace_id=workspace_id,
            event_id=event_id,
            role=role,
            locale=locale,
        )
        return {"draft": draft.model_dump(mode="json") if draft is not None else None}

    @router.put("/api/reports/draft")
    def save_report_draft(
        request: ReportDraftSaveRequest,
        principal: Any = Depends(require_permission("events.note")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        reports: ReportService = Depends(get_report_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return reports.save_draft(principal=principal, request=request).model_dump(mode="json")

    @router.post("/api/exports")
    def create_export(
        request: ExportRequest,
        principal: Any = Depends(require_permission("exports.create")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        reports: ReportService = Depends(get_report_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        limiter.check(
            bucket="exports.create",
            subject=rate_limit_subject(principal.user_id),
            rule=EXPORT_RATE,
        )
        identity.require_workspace(principal, request.workspace_id)
        artifact = reports.create_export(principal=principal, request=request)
        checkpoint = artifact.checkpoint
        return Response(
            content=artifact.content,
            media_type=checkpoint.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{checkpoint.filename}"',
                "X-Export-Checkpoint-ID": checkpoint.id,
                "X-Content-SHA256": checkpoint.content_hash,
                "X-Snapshot-SHA256": checkpoint.snapshot_hash,
                "Cache-Control": "no-store",
            },
        )

    @router.get("/api/exports/checkpoints")
    def list_export_checkpoints(
        workspace_id: str,
        limit: int = Query(default=100, ge=1, le=200),
        principal: Any = Depends(require_permission("exports.read_own")),
        identity: Any = Depends(get_identity_service),
        reports: ReportService = Depends(get_report_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return {
            "items": reports.list_checkpoints(
                principal=principal,
                workspace_id=workspace_id,
                limit=limit,
            )
        }

    return router


__all__ = ["build_report_router"]
