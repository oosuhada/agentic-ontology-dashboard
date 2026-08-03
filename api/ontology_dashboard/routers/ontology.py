"""Ontology registry, persistent object, relation and action APIs."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_identity_service, get_ontology_service, require_csrf, require_permission
from ..identity import IdentityService, Principal
from ..ontology import (
    ACTION_TYPES,
    LINK_TYPES,
    MANUFACTURING_PACK,
    OBJECT_TYPES,
    ActionInvocation,
    registry_payload,
)
from ..ontology_service import OntologyService

router = APIRouter(tags=["ontology"])


@router.get("/api/workspaces")
def list_workspaces(
    principal: Principal = Depends(require_permission("app.access")),
    identity: IdentityService = Depends(get_identity_service),
):
    items = [
        workspace
        for workspace in identity.repository.list_workspaces(
            organization_id=principal.organization_id,
        )
        if workspace["id"] in principal.workspace_scopes
    ]
    return {"items": items}


@router.get("/api/domain-packs")
def list_domain_packs(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [MANUFACTURING_PACK.model_dump(mode="json")]}


@router.get("/api/ontology/registry")
def ontology_registry(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return registry_payload()


@router.get("/api/ontology/object-types")
def list_object_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in OBJECT_TYPES]}


@router.get("/api/ontology/link-types")
def list_link_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in LINK_TYPES]}


@router.get("/api/ontology/action-types")
def list_action_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in ACTION_TYPES]}


@router.get("/api/ontology/objects")
def query_ontology_objects(
    workspace_id: str,
    object_type: str | None = None,
    q: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    return ontology.query_objects(
        workspace_id=workspace_id,
        object_type=object_type,
        search=q,
        offset=offset,
        limit=limit,
    )


@router.get("/api/ontology/objects/aggregate")
def aggregate_ontology_objects(
    workspace_id: str,
    object_type: str,
    group_by: list[str] = Query(default=[]),
    metrics: list[str] = Query(default=[]),
    q: str | None = None,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    return ontology.aggregate_objects(
        workspace_id=workspace_id,
        object_type=object_type,
        group_by=group_by,
        metrics=metrics,
        search=q,
    )


@router.get("/api/ontology/objects/{object_id}")
def get_ontology_object(
    object_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    return ontology.get_object(
        workspace_id=workspace_id,
        object_id=object_id,
    ).model_dump(mode="json")


@router.get("/api/ontology/objects/{object_id}/links")
def traverse_ontology_object(
    object_id: str,
    workspace_id: str,
    direction: Literal["outgoing", "incoming", "both"] = "outgoing",
    depth: int = Query(default=1, ge=1, le=5),
    link_type: str | None = None,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    return ontology.traverse(
        workspace_id=workspace_id,
        object_id=object_id,
        direction=direction,
        depth=depth,
        link_type=link_type,
    ).model_dump(mode="json")


@router.get("/api/ontology/objects/{object_id}/action-invocations")
def list_ontology_action_invocations(
    object_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    return {
        "items": ontology.list_action_invocations(
            workspace_id=workspace_id,
            object_id=object_id,
        )
    }


@router.post("/api/ontology/actions/invoke")
def invoke_ontology_action(
    invocation: ActionInvocation,
    principal: Principal = Depends(require_permission("app.access")),
    _: None = Depends(require_csrf),
    ontology: OntologyService = Depends(get_ontology_service),
):
    return ontology.invoke(invocation, principal).model_dump(mode="json")
