"""Project-scoped export artifact and checkpoint routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ..dependencies import (
    get_export_service,
    get_identity_service,
    get_rate_limiter,
    rate_limit_subject,
    require_csrf,
    require_permission,
)
from ..export_models import ExportRequest
from ..export_service import ExportService
from ..identity import IdentityService, Principal
from ..security import EXPORT_RATE, RateLimiter

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.post("")
def create_export(
    request: ExportRequest,
    principal: Principal = Depends(require_permission("exports.create")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    exports: ExportService = Depends(get_export_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    limiter.check(
        bucket="exports.create",
        subject=rate_limit_subject(principal.user_id),
        rule=EXPORT_RATE,
    )
    identity.require_workspace(principal, request.workspace_id)
    artifact = exports.create_export(principal=principal, request=request)
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


@router.get("/checkpoints")
def list_export_checkpoints(
    workspace_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_permission("exports.read_own")),
    identity: IdentityService = Depends(get_identity_service),
    exports: ExportService = Depends(get_export_service),
):
    identity.require_workspace(principal, workspace_id)
    return {
        "items": exports.list_checkpoints(
            principal=principal,
            workspace_id=workspace_id,
            limit=limit,
        )
    }
