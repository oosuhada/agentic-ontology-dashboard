from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from app.infra.external.project3.models import Project3GraphProjectionRequest
from .service import GraphRuntimeService
from .store import Neo4jGraphStore


app = FastAPI(title="Ontology Dashboard Graph Runtime", version="1.0")


@lru_cache(maxsize=1)
def get_service() -> GraphRuntimeService:
    service = GraphRuntimeService(Neo4jGraphStore.from_environment())
    service.initialize()
    return service


@app.get("/health")
@app.get("/api/v1/health")
def health(service: GraphRuntimeService = Depends(get_service)):
    return service.health()


@app.get("/api/v1/projects/{project_id}/readiness")
def readiness(project_id: str, service: GraphRuntimeService = Depends(get_service)):
    return service.readiness(project_id)


@app.get("/api/v1/graph/schema")
def graph_schema(project_id: str, service: GraphRuntimeService = Depends(get_service)):
    schema = service.store.schema(project_id)
    return {
        "project_id": project_id,
        "schema_version": "1",
        "title": "Versioned reliability ontology",
        "schema_context": "PostgreSQL-authoritative read projection",
        "node_identities": [{"label": row["object_type"], "identity_property": "source_identity"} for row in schema["nodes"]],
        "relationship_types": schema["relationship_types"],
        "nodes": schema["nodes"],
        "relationships": [],
    }


@app.get("/api/v1/graph/search")
def graph_search(
    project_id: str,
    label: str,
    q: str,
    limit: int = Query(default=12, ge=1, le=50),
    dataset_version_id: str | None = None,
    service: GraphRuntimeService = Depends(get_service),
):
    rows = service.store.search(
        project_id=project_id,
        label=label,
        query=q,
        limit=limit,
        dataset_version_id=dataset_version_id,
    )
    return {
        "label": label,
        "query": q,
        "identity_property": "source_identity",
        "dataset_version_id": dataset_version_id,
        "nodes": [row["node"] for row in rows],
        "count": len(rows),
    }


@app.get("/api/v1/graph/subgraph")
def subgraph(
    project_id: str,
    label: str,
    identity: str,
    depth: int = Query(default=2, ge=1, le=3),
    limit: int = Query(default=50, ge=1, le=100),
    dataset_version_id: str | None = None,
    service: GraphRuntimeService = Depends(get_service),
):
    del label
    result = service.store.subgraph(
        project_id=project_id,
        identity=identity,
        depth=depth,
        limit=limit,
        dataset_version_id=dataset_version_id,
    )
    root = next((item for item in result["nodes"] if item.get("source_identity") == identity), None)
    return {
        "root": root,
        "nodes": result["nodes"],
        "relationships": result["relationships"],
        "node_count": len(result["nodes"]),
        "relationship_count": len(result["relationships"]),
        "dataset_version_id": dataset_version_id or (root or {}).get("dataset_version_id"),
        "depth": depth,
        "truncated": len(result["nodes"]) >= limit,
    }


@app.post("/api/v1/query")
def query(payload: dict, service: GraphRuntimeService = Depends(get_service)):
    project_id = str(payload.get("project_id") or "").strip()
    question = str(payload.get("question") or "").strip()
    if not project_id or not question:
        raise HTTPException(status_code=422, detail="project_id and question are required")
    return service.query(project_id, question)


@app.post("/api/v1/projects/{project_id}/graph/projections")
def graph_projection(
    project_id: str,
    request: Project3GraphProjectionRequest,
    x_organization_id: Annotated[str | None, Header()] = None,
    x_project_id: Annotated[str | None, Header()] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
    service: GraphRuntimeService = Depends(get_service),
):
    if project_id != request.project_id:
        raise HTTPException(status_code=409, detail="projection path and payload project_id differ")
    expected = (request.organization_id, request.project_id, request.workspace_id)
    supplied = (x_organization_id, x_project_id, x_workspace_id)
    if any(value is not None for value in supplied) and supplied != expected:
        raise HTTPException(status_code=403, detail="projection scope headers differ from payload")
    return service.project(request)
