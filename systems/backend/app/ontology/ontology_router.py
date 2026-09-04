"""FastAPI adapter for the canonical Ontology domain."""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, Query

from .ontology_domain import ACTION_TYPES, LINK_TYPES, OBJECT_TYPES, ActionInvocation, registry_payload
from .ontology_service import OntologyService


DependencyFactory = Callable[[], Any]
PermissionFactory = Callable[[str], Callable[..., Any]]


def _call(operation: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    return operation(*args, **kwargs)


def create_ontology_router(
    *,
    get_identity_service: DependencyFactory,
    get_ontology_service: DependencyFactory,
    require_csrf: DependencyFactory,
    require_permission: PermissionFactory,
) -> APIRouter:
    """Build the HTTP adapter from composition-provided public dependencies.

    The domain package deliberately does not import Identity, Project, DB, or the
    legacy application package.  Composition supplies those adapters here.
    """

    router = APIRouter(tags=["ontology"])

    @router.get("/api/workspaces")
    def list_workspaces(
        principal: Any = Depends(require_permission("app.access")),
        identity: Any = Depends(get_identity_service),
    ):
        items = [
            workspace
            for workspace in identity.repository.list_workspaces(
                organization_id=principal.organization_id,
            )
            if workspace["id"] in principal.workspace_scopes
        ]
        return {"items": items}

    @router.get("/api/ontology/registry")
    def ontology_registry(_: Any = Depends(require_permission("ontology.registry.read"))):
        return registry_payload()

    @router.get("/api/ontology/object-types")
    def list_object_types(_: Any = Depends(require_permission("ontology.registry.read"))):
        return {"items": [item.model_dump(mode="json") for item in OBJECT_TYPES]}

    @router.get("/api/ontology/link-types")
    def list_link_types(_: Any = Depends(require_permission("ontology.registry.read"))):
        return {"items": [item.model_dump(mode="json") for item in LINK_TYPES]}

    @router.get("/api/ontology/action-types")
    def list_action_types(_: Any = Depends(require_permission("ontology.registry.read"))):
        return {"items": [item.model_dump(mode="json") for item in ACTION_TYPES]}

    @router.get("/api/ontology/objects")
    def query_ontology_objects(
        workspace_id: str,
        object_type: str | None = None,
        dataset_version_id: str | None = None,
        q: str | None = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        principal: Any = Depends(require_permission("ontology.objects.read")),
        identity: Any = Depends(get_identity_service),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return _call(
            ontology.query_objects,
            workspace_id=workspace_id,
            object_type=object_type,
            dataset_version_id=dataset_version_id,
            search=q,
            offset=offset,
            limit=limit,
        )

    @router.get("/api/ontology/objects/aggregate")
    def aggregate_ontology_objects(
        workspace_id: str,
        object_type: str,
        dataset_version_id: str | None = None,
        group_by: list[str] = Query(default=[]),
        metrics: list[str] = Query(default=[]),
        q: str | None = None,
        principal: Any = Depends(require_permission("ontology.objects.read")),
        identity: Any = Depends(get_identity_service),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return _call(
            ontology.aggregate_objects,
            workspace_id=workspace_id,
            object_type=object_type,
            dataset_version_id=dataset_version_id,
            group_by=group_by,
            metrics=metrics,
            search=q,
        )

    @router.get("/api/ontology/objects/{object_id}")
    def get_ontology_object(
        object_id: str,
        workspace_id: str,
        dataset_version_id: str | None = None,
        principal: Any = Depends(require_permission("ontology.objects.read")),
        identity: Any = Depends(get_identity_service),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return _call(
            ontology.get_object,
            workspace_id=workspace_id,
            object_id=object_id,
            dataset_version_id=dataset_version_id,
        ).model_dump(mode="json")

    @router.get("/api/ontology/objects/{object_id}/links")
    def traverse_ontology_object(
        object_id: str,
        workspace_id: str,
        dataset_version_id: str | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "outgoing",
        depth: int = Query(default=1, ge=1, le=5),
        link_type: str | None = None,
        principal: Any = Depends(require_permission("ontology.objects.read")),
        identity: Any = Depends(get_identity_service),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return _call(
            ontology.traverse,
            workspace_id=workspace_id,
            object_id=object_id,
            direction=direction,
            depth=depth,
            link_type=link_type,
            dataset_version_id=dataset_version_id,
        ).model_dump(mode="json")

    @router.get("/api/ontology/objects/{object_id}/action-invocations")
    def list_ontology_action_invocations(
        object_id: str,
        workspace_id: str,
        principal: Any = Depends(require_permission("ontology.objects.read")),
        identity: Any = Depends(get_identity_service),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return {
            "items": _call(
                ontology.list_action_invocations,
                workspace_id=workspace_id,
                object_id=object_id,
            )
        }

    @router.post("/api/ontology/actions/invoke")
    def invoke_ontology_action(
        invocation: ActionInvocation,
        principal: Any = Depends(require_permission("app.access")),
        _: None = Depends(require_csrf),
        ontology: OntologyService = Depends(get_ontology_service),
    ):
        return _call(ontology.invoke, invocation, principal).model_dump(mode="json")

    return router


__all__ = ["create_ontology_router"]
