from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ..dependencies import database_target, get_project_service, require_permission
from ..domain_packs import ProjectApplicationDefinition, list_domain_packs, resolve_domain_pack
from ..enterprise_identity import enterprise_identity_readiness
from ..deployment import deployment_readiness
from ..identity import Principal
from ..projects import ProjectService
from ..persistence_readiness import persistence_readiness

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/domain-packs")
def domain_pack_catalog(
    _: Principal = Depends(require_permission("app.access")),
):
    return {"items": [item.model_dump(mode="json") for item in list_domain_packs()]}


@router.get("/projects/{project_id}/applications/v4")
def project_v4_application(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    project = projects.get_for_principal(principal, project_id)
    workspaces = projects.list_workspaces(principal, project_id)
    domain_pack, configuration_source = resolve_domain_pack(project.domain_pack_code)
    return ProjectApplicationDefinition(
        application_id="ontology-commercial-v4",
        project_id=project.id,
        workspace_ids=tuple(item["id"] for item in workspaces),
        domain_pack=domain_pack,
        configuration_source=configuration_source,
    ).model_dump(mode="json")


@router.get("/projects/{project_id}/persistence-readiness")
def project_persistence_readiness(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return persistence_readiness(database_target()).model_dump(mode="json")


@router.get("/projects/{project_id}/enterprise-identity")
def project_enterprise_identity(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return enterprise_identity_readiness().model_dump(mode="json")


@router.get("/projects/{project_id}/deployment-readiness")
def project_deployment_readiness(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return deployment_readiness(Path(__file__).resolve().parents[3]).model_dump(mode="json")
