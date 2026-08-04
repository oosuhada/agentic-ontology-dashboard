"""Project-scoped proxy routes for the Project 3 graph/RAG service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from ..dependencies import (
    get_identity_service,
    get_project3_client,
    require_csrf,
    require_permission,
)
from ..identity import AuthError, IdentityService, Principal
from ..integrations.project3 import (
    Project3Client,
    Project3ContractError,
    Project3IntegrationSnapshot,
    Project3Unavailable,
)

router = APIRouter(prefix="/api/integrations/project3", tags=["project3"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project3QuestionRequest(StrictRequest):
    project_id: str = Field(min_length=3, max_length=120)
    question: str = Field(min_length=1, max_length=2000)


class Project3RagRequest(StrictRequest):
    project_id: str = Field(min_length=3, max_length=120)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    current_only: bool = True
    document_types: list[str] = Field(default_factory=list, max_length=20)


def scoped_project(
    *,
    principal: Principal,
    identity: IdentityService,
    project_id: str | None,
) -> str:
    resolved = project_id or principal.active_project_id
    if not resolved:
        raise AuthError(409, "active_project_required", "먼저 Project를 활성화해야 합니다.")
    identity.require_project(principal, resolved)
    if principal.active_project_id and resolved != principal.active_project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")
    return resolved


def degraded_payload(error: Exception, *, project_id: str) -> dict[str, Any]:
    code = getattr(error, "code", "project3_unavailable")
    retryable = bool(getattr(error, "retryable", True))
    return {
        "status": "degraded",
        "available": False,
        "project_id": project_id,
        "error": {"code": code, "message": str(error), "retryable": retryable},
    }


@router.get("/status")
def project3_status(
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_permission("ontology.registry.read")),
    identity: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(principal=principal, identity=identity, project_id=project_id)
    health = client.health(project_id=resolved)
    if not health.available:
        return Project3IntegrationSnapshot(
            health=health,
            degraded_reason=health.error or "Project 3 is unavailable",
        ).model_dump(mode="json", by_alias=True)
    try:
        readiness = client.readiness(resolved)
        schema = client.graph_schema(resolved)
        return Project3IntegrationSnapshot(
            health=health,
            readiness=readiness,
            schema=schema,
        ).model_dump(mode="json", by_alias=True)
    except (Project3Unavailable, Project3ContractError) as error:
        return Project3IntegrationSnapshot(
            health=health.model_copy(update={"status": "degraded"}),
            degraded_reason=str(error),
        ).model_dump(mode="json", by_alias=True)


@router.get("/schema")
def project3_schema(
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_permission("ontology.registry.read")),
    identity: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(principal=principal, identity=identity, project_id=project_id)
    try:
        return client.graph_schema(resolved).model_dump(mode="json")
    except (Project3Unavailable, Project3ContractError) as error:
        return degraded_payload(error, project_id=resolved)


@router.get("/search")
def project3_search(
    label: str = Query(min_length=1, max_length=120),
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=12, ge=1, le=50),
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(principal=principal, identity=identity, project_id=project_id)
    try:
        return client.graph_search(
            resolved,
            label=label,
            query=q,
            limit=limit,
        ).model_dump(mode="json")
    except (Project3Unavailable, Project3ContractError) as error:
        return degraded_payload(error, project_id=resolved)


@router.get("/subgraph")
def project3_subgraph(
    label: str = Query(min_length=1, max_length=120),
    identity_value: str = Query(alias="identity", min_length=1, max_length=200),
    depth: int = Query(default=2, ge=1, le=3),
    limit: int = Query(default=50, ge=1, le=100),
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity_service: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(
        principal=principal,
        identity=identity_service,
        project_id=project_id,
    )
    try:
        return client.subgraph(
            resolved,
            label=label,
            identity=identity_value,
            depth=depth,
            limit=limit,
        ).model_dump(mode="json")
    except (Project3Unavailable, Project3ContractError) as error:
        return degraded_payload(error, project_id=resolved)


@router.post("/query")
def project3_query(
    request: Project3QuestionRequest,
    principal: Principal = Depends(require_permission("planner.object_query")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
    )
    try:
        return client.query(resolved, question=request.question).model_dump(mode="json")
    except (Project3Unavailable, Project3ContractError) as error:
        return degraded_payload(error, project_id=resolved)


@router.post("/rag")
def project3_rag(
    request: Project3RagRequest,
    principal: Principal = Depends(require_permission("planner.narrative")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    client: Project3Client = Depends(get_project3_client),
):
    resolved = scoped_project(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
    )
    try:
        return client.rag_query(
            resolved,
            query=request.query,
            top_k=request.top_k,
            current_only=request.current_only,
            document_types=request.document_types,
        ).model_dump(mode="json")
    except (Project3Unavailable, Project3ContractError) as error:
        return degraded_payload(error, project_id=resolved)
