"""Governed project-scoped enterprise knowledge API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.identity import Principal
from app.common.rate_limit import KNOWLEDGE_SEARCH_RATE, KNOWLEDGE_WRITE_RATE, RateLimiter


class KnowledgeIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    document_type: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=500_000)
    source_ref: str = Field(min_length=1, max_length=500)
    source_updated_at: str | None = Field(default=None, max_length=80)
    allowed_roles: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeReindexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=160)


def create_knowledge_router(
    *,
    get_knowledge_service,
    require_permission,
    require_csrf,
    get_rate_limiter,
    rate_limit_subject,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["knowledge"])

    def _scope(principal: Principal, project_id: str, workspace_id: str) -> None:
        if not principal.is_admin and project_id not in principal.project_scopes:
            raise HTTPException(status_code=403, detail="project scope denied")
        if principal.active_project_id != project_id:
            raise HTTPException(status_code=409, detail="activate the project first")
        if not principal.is_admin and workspace_id not in principal.workspace_scopes:
            raise HTTPException(status_code=403, detail="workspace scope denied")

    @router.get("/projects/{project_id}/knowledge/search")
    def search_knowledge(
        project_id: str,
        q: str = Query(min_length=1, max_length=1000),
        workspace_id: str = Query(default="manufacturing-demo", max_length=160),
        asset_id: str | None = Query(default=None, max_length=180),
        top_k: int = Query(default=8, ge=1, le=20),
        principal: Principal = Depends(require_permission("knowledge.read")),
        service=Depends(get_knowledge_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        _scope(principal, project_id, workspace_id)
        limiter.check(
            bucket="knowledge-search",
            subject=rate_limit_subject(principal.user_id),
            rule=KNOWLEDGE_SEARCH_RATE,
        )
        return {
            "items": service.search(
                q,
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                roles=principal.roles,
                asset_id=asset_id,
                top_k=top_k,
                actor_user_id=principal.user_id,
            )
        }

    @router.get("/projects/{project_id}/knowledge/status")
    def knowledge_status(
        project_id: str,
        workspace_id: str = Query(default="manufacturing-demo", max_length=160),
        principal: Principal = Depends(require_permission("knowledge.read")),
        service=Depends(get_knowledge_service),
    ):
        _scope(principal, project_id, workspace_id)
        return service.stats(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )

    @router.post("/projects/{project_id}/knowledge/documents", status_code=status.HTTP_201_CREATED)
    def ingest_knowledge(
        project_id: str,
        request: KnowledgeIngestRequest,
        principal: Principal = Depends(require_permission("knowledge.ingest")),
        _: None = Depends(require_csrf),
        service=Depends(get_knowledge_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        _scope(principal, project_id, request.workspace_id)
        limiter.check(
            bucket="knowledge-ingest",
            subject=rate_limit_subject(principal.user_id),
            rule=KNOWLEDGE_WRITE_RATE,
        )
        return service.ingest(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
            actor_user_id=principal.user_id,
            title=request.title,
            document_type=request.document_type,
            content=request.content,
            source_ref=request.source_ref,
            source_updated_at=request.source_updated_at,
            allowed_roles=request.allowed_roles or None,
            metadata=request.metadata,
        )

    @router.post("/projects/{project_id}/knowledge/reindex")
    def reindex_knowledge(
        project_id: str,
        request: KnowledgeReindexRequest,
        principal: Principal = Depends(require_permission("knowledge.index")),
        _: None = Depends(require_csrf),
        service=Depends(get_knowledge_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        _scope(principal, project_id, request.workspace_id)
        limiter.check(
            bucket="knowledge-reindex",
            subject=rate_limit_subject(principal.user_id),
            rule=KNOWLEDGE_WRITE_RATE,
        )
        return service.reindex(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
            actor_user_id=principal.user_id,
        )

    return router


__all__ = ["create_knowledge_router", "KnowledgeIngestRequest", "KnowledgeReindexRequest"]
