from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import (
    database_target,
    get_durable_job_repository,
    get_project_service,
    require_csrf,
    require_permission,
)
from ..distributed_runtime import (
    DistributedRuntimeSnapshot,
    DurableJobEventPage,
    DurableJobRepository,
    JobOperatorRequest,
    distributed_runtime_readiness,
)
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


@router.get("/projects/{project_id}/distributed-runtime")
def project_distributed_runtime(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    readiness = distributed_runtime_readiness(
        jobs.database,
        organization_id=principal.organization_id,
        project_id=project_id,
    )
    recent = jobs.list_jobs(
        organization_id=principal.organization_id,
        project_id=project_id,
        limit=30,
    )
    dead_letters = tuple(item for item in recent if item.state == "dead_letter")
    return DistributedRuntimeSnapshot(
        readiness=readiness,
        jobs=recent,
        dead_letters=dead_letters,
    ).model_dump(mode="json")


@router.get("/projects/{project_id}/distributed-job-events")
def project_distributed_job_events(
    project_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    items = jobs.events_after(
        organization_id=principal.organization_id,
        project_id=project_id,
        cursor=cursor,
        limit=limit,
    )
    return DurableJobEventPage(
        items=items,
        next_cursor=items[-1].cursor if items else cursor,
    ).model_dump(mode="json")


@router.post("/projects/{project_id}/distributed-jobs/{job_id}/cancel")
def cancel_distributed_job(
    project_id: str,
    job_id: str,
    request: JobOperatorRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    try:
        return jobs.cancel(
            organization_id=principal.organization_id,
            project_id=project_id,
            job_id=job_id,
            reason=request.reason,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="distributed job not found") from error


@router.post("/projects/{project_id}/distributed-jobs/{job_id}/replay")
def replay_distributed_job(
    project_id: str,
    job_id: str,
    request: JobOperatorRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    try:
        return jobs.replay(
            organization_id=principal.organization_id,
            project_id=project_id,
            job_id=job_id,
            actor_user_id=principal.user_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="distributed job not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
