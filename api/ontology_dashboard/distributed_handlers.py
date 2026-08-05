"""Durable worker handlers that invoke existing domain services."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .analysis_models import AnalysisRunRequest
from .analysis_service import AnalysisService
from .datasets import DatasetMaterializationSource, DatasetRepository
from .distributed_runtime import DurableJob
from .identity import Principal
from .ontology_service import OntologyService
from .postgresql_ontology_repository import PostgreSQLOntologyInstanceRepository
from .postgresql_repositories import (
    PostgreSQLOntologyActionRepository,
    PostgreSQLRoleWorkflowRepository,
    is_postgresql,
)
from .service import ManufacturingPredictiveMaintenanceService


def analysis_handler(database: str, root: Path) -> Callable[[DurableJob], dict[str, Any]]:
    dataset_source = DatasetMaterializationSource(DatasetRepository(database))
    analyses = AnalysisService(database, dataset_loader=dataset_source.load)

    def handle(job: DurableJob) -> dict[str, Any]:
        request = AnalysisRunRequest.model_validate(job.payload["request"])
        principal = Principal.model_validate(job.payload["principal"])
        service = ManufacturingPredictiveMaintenanceService(root, database_path=database)
        if is_postgresql(database):
            ontology = OntologyService(
                service,
                action_repository=PostgreSQLOntologyActionRepository(database),
                instance_repository=PostgreSQLOntologyInstanceRepository(
                    database,
                    organization_id=job.organization_id,
                    project_id=job.project_id,
                ),
                role_workflow_repository=PostgreSQLRoleWorkflowRepository(database),
            )
        else:
            ontology = OntologyService(service)
        result = analyses.execute_queued_run(
            run_id=str(job.payload["run_id"]),
            request=request,
            principal=principal,
            ontology=ontology,
        )
        return {
            "analysis_run_id": result.id,
            "status": result.status,
            "rows_scanned": result.rows_scanned,
            "cache_hit": result.cache_hit,
        }

    return handle


def configured_handlers(database: str, root: Path) -> dict[str, Callable[[DurableJob], dict[str, Any]]]:
    return {"analysis": analysis_handler(database, root)}
