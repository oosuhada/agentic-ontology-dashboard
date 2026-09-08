from __future__ import annotations

from fastapi.testclient import TestClient

from app.project3_runtime.main import app, get_service
from app.project3_runtime.service import GraphRuntimeService


class FakeGraphStore:
    def __init__(self) -> None:
        self.initialized = False

    def ensure_schema(self) -> None:
        self.initialized = True

    def ping(self) -> bool:
        return True

    def readiness(self, project_id: str):
        assert project_id == "manufacturing-demo-project"
        return {"node_count": 8, "relationship_count": 10, "can_query": True}

    def schema(self, project_id: str):
        assert project_id == "manufacturing-demo-project"
        return {
            "nodes": [
                {"object_type": "equipment", "count": 1},
                {"object_type": "component", "count": 1},
                {"object_type": "sop", "count": 1},
            ],
            "relationship_types": ["HAS_COMPONENT", "INSPECTED_BY"],
        }

    def search(self, **kwargs):
        assert kwargs["query"] == "CNC"
        return [{"node": {"source_identity": "CNC-S04-L04-01", "object_type": "equipment"}}]

    def subgraph(self, **kwargs):
        return {
            "nodes": [
                {
                    "node_key": "equipment-key",
                    "source_identity": kwargs["identity"],
                    "object_type": "equipment",
                    "dataset_version_id": "dsv-1",
                },
                {
                    "node_key": "component-key",
                    "source_identity": f"{kwargs['identity']}:rotating_assembly",
                    "object_type": "component",
                    "dataset_version_id": "dsv-1",
                },
            ],
            "relationships": [
                {
                    "type": "HAS_COMPONENT",
                    "source": "equipment-key",
                    "target": "component-key",
                    "properties": {},
                }
            ],
        }

    def relationship_query(self, **kwargs):
        assert kwargs["identity"] == "CNC-S04-L04-01"
        assert "component" in kwargs["interests"]
        assert "sop" in kwargs["interests"]
        return [
            {
                "root_id": "CNC-S04-L04-01",
                "related_type": "component",
                "related_id": "CNC-S04-L04-01:rotating_assembly",
                "related_label": "회전/진동 계통",
                "relationship_path": ["HAS_COMPONENT"],
                "depth": 1,
                "dataset_version_id": "dsv-1",
            },
            {
                "root_id": "CNC-S04-L04-01",
                "related_type": "sop",
                "related_id": "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
                "related_label": "CNC 회전/구동 계통 점검 참고 절차",
                "relationship_path": ["HAS_COMPONENT", "INSPECTED_BY"],
                "depth": 2,
                "dataset_version_id": "dsv-1",
            },
        ]


def test_graph_runtime_service_uses_bounded_relationship_query_without_raw_cypher() -> None:
    service = GraphRuntimeService(FakeGraphStore())
    result = service.query(
        "manufacturing-demo-project",
        "선택된 설비 CNC-S04-L04-01 기준으로 부품과 SOP 연결을 보여줘",
    )

    assert result["status"] == "succeeded"
    assert result["row_count"] == 2
    assert result["cypher"] == ""
    assert result["validation"] == {"raw_cypher_exposed": False, "bounded_depth": 3}
    assert result["metadata"]["identity"] == "CNC-S04-L04-01"
    assert "component" in result["metadata"]["interests"]
    assert "sop" in result["metadata"]["interests"]


def test_project3_compatible_http_contract_exposes_health_search_subgraph_and_query() -> None:
    service = GraphRuntimeService(FakeGraphStore())
    service.initialize()
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").json()["status"] == "ready"
            readiness = client.get(
                "/api/v1/projects/manufacturing-demo-project/readiness"
            ).json()
            assert readiness["can_query"] is True
            assert readiness["source_type"] == "neo4j"

            schema = client.get(
                "/api/v1/graph/schema",
                params={"project_id": "manufacturing-demo-project"},
            ).json()
            assert "HAS_COMPONENT" in schema["relationship_types"]

            search = client.get(
                "/api/v1/graph/search",
                params={
                    "project_id": "manufacturing-demo-project",
                    "label": "equipment",
                    "q": "CNC",
                },
            ).json()
            assert search["count"] == 1

            subgraph = client.get(
                "/api/v1/graph/subgraph",
                params={
                    "project_id": "manufacturing-demo-project",
                    "label": "equipment",
                    "identity": "CNC-S04-L04-01",
                    "depth": 2,
                },
            ).json()
            assert subgraph["node_count"] == 2
            assert subgraph["relationship_count"] == 1

            query = client.post(
                "/api/v1/query",
                json={
                    "project_id": "manufacturing-demo-project",
                    "question": "선택된 설비 CNC-S04-L04-01 기준으로 부품과 SOP 연결을 보여줘",
                },
            ).json()
            assert query["provider"] == "neo4j-bounded-patterns"
            assert query["cypher"] == ""
    finally:
        app.dependency_overrides.clear()
