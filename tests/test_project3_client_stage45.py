from __future__ import annotations

import json

import httpx
import pytest

from app.infra.external.project3 import (
    Project3Client,
    Project3ContractError,
    Project3Unavailable,
    parse_project_mapping,
)


def response(request: httpx.Request, status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=request,
        headers={"Content-Type": "application/json"},
    )


def test_project3_contract_client_maps_project_and_validates_schema_and_subgraph() -> None:
    seen: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path == "/api/v1/health":
            return response(
                request,
                200,
                {
                    "status": "ready",
                    "checks": [
                        {
                            "check": "neo4j",
                            "status": "ready",
                            "detail": "connected",
                            "required": True,
                        }
                    ],
                },
            )
        if request.url.path == "/api/v1/projects/cip-dmd/readiness":
            return response(
                request,
                200,
                {
                    "project_id": "cip-dmd",
                    "lifecycle_status": "ready",
                    "source_type": "neo4j",
                    "schema_available": True,
                    "node_count": 12,
                    "relationship_count": 8,
                    "can_query": True,
                    "next_action": "query",
                },
            )
        if request.url.path == "/api/v1/graph/schema":
            return response(
                request,
                200,
                {
                    "project_id": "cip-dmd",
                    "schema_version": "1.1",
                    "title": "Manufacturing graph",
                    "schema_context": "Equipment and failures",
                    "node_identities": [
                        {"label": "Equipment", "identity_property": "equipment_id"}
                    ],
                    "relationship_types": ["HAS_RISK_EVENT"],
                },
            )
        if request.url.path == "/api/v1/graph/subgraph":
            return response(
                request,
                200,
                {
                    "root": {"label": "Equipment", "identity": "M-014"},
                    "nodes": [{"id": "M-014", "label": "Equipment"}],
                    "relationships": [],
                    "node_count": 1,
                    "relationship_count": 0,
                    "depth": 2,
                    "truncated": False,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = Project3Client(
        base_url="http://project3.test",
        project_mapping={"manufacturing-demo-project": "cip-dmd"},
        transport=httpx.MockTransport(handler),
    )

    health = client.health(project_id="manufacturing-demo-project")
    readiness = client.readiness("manufacturing-demo-project")
    schema = client.graph_schema("manufacturing-demo-project")
    subgraph = client.subgraph(
        "manufacturing-demo-project",
        label="Equipment",
        identity="M-014",
    )

    assert health.status == "ready"
    assert health.available is True
    assert health.mapped_project_id == "cip-dmd"
    assert readiness.can_query is True
    assert schema.node_identities[0].identity_property == "equipment_id"
    assert subgraph.node_count == 1
    assert ("GET", "/api/v1/projects/cip-dmd/readiness", {}) in seen
    assert any(
        path == "/api/v1/graph/schema" and params.get("project_id") == "cip-dmd"
        for _, path, params in seen
    )


def test_project3_rag_matches_alias_is_preserved_by_typed_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/rag/search"
        return response(
            request,
            200,
            {
                "project_id": "cip-dmd",
                "query": "quality SOP",
                "status": "success",
                "matches": [
                    {
                        "citation_id": "quality-inspection-sop#chunk-1",
                        "title": "Quality Inspection SOP",
                        "text": "Trace the finished product to components and upstream process runs.",
                        "score": 0.91,
                        "document_type": "quality_standard",
                    }
                ],
                "citations": [
                    {
                        "citation_id": "quality-inspection-sop#chunk-1",
                        "document_id": "quality-inspection-sop",
                    }
                ],
            },
        )

    client = Project3Client(
        base_url="http://project3.test",
        project_mapping={"manufacturing-demo-project": "cip-dmd"},
        transport=httpx.MockTransport(handler),
    )
    result = client.rag_search("manufacturing-demo-project", query="quality SOP", top_k=3)
    assert result.results[0]["citation_id"] == "quality-inspection-sop#chunk-1"
    assert result.results[0]["score"] == 0.91
    assert result.citations[0]["document_id"] == "quality-inspection-sop"


def test_project3_client_returns_degraded_health_and_opens_circuit() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    client = Project3Client(
        base_url="http://project3.test",
        max_retries=0,
        circuit_failure_threshold=1,
        circuit_reset_seconds=60,
        transport=httpx.MockTransport(handler),
    )

    health = client.health(project_id="manufacturing-demo-project")
    assert health.status == "unavailable"
    assert health.available is False
    assert health.error
    with pytest.raises(Project3Unavailable, match="circuit breaker"):
        client.graph_schema("manufacturing-demo-project")
    assert calls == 1


def test_project3_client_rejects_contract_mismatch_and_has_no_raw_cypher_method() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(request, 200, {"title": "missing required fields"})

    client = Project3Client(
        base_url="http://project3.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(Project3ContractError, match="contract mismatch"):
        client.graph_schema("manufacturing-demo-project")
    assert not hasattr(client, "execute_cypher")
    assert not hasattr(client, "cypher")


def test_project_mapping_supports_json_and_pair_syntax() -> None:
    assert parse_project_mapping(
        json.dumps({"manufacturing-demo-project": "cip-dmd"})
    ) == {"manufacturing-demo-project": "cip-dmd"}
    assert parse_project_mapping("alpha=graph-a,beta=graph-b") == {
        "alpha": "graph-a",
        "beta": "graph-b",
    }
    with pytest.raises(ValueError):
        parse_project_mapping("invalid")
