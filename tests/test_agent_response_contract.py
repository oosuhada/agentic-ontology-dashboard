from app.operations.agent_response_contract import (
    plan_agent_response_contract,
    route_for_response_contract,
)
from app.operations import router as operations_router


class _FakeGraphQueryResult:
    answer = "CNC-03은 Line-4와 Product-HX를 통해 연결됩니다."
    status = "succeeded"
    cypher = "MATCH (n) RETURN n"
    rows = [{"asset": "CNC-03", "line": "Line-4", "product": "Product-HX"}]
    row_count = 1
    metadata = {}
    evidence = {}
    validation = {"validated": True}
    usage = {}
    caveat = None
    provider = "project3-test"
    fallback_reason = None
    run_id = "graph-run-1"
    thread_id = None


class _FakeProject3Client:
    def query(self, project_id: str, *, question: str):
        assert project_id == "manufacturing-demo-project"
        assert "CNC-03" in question
        return _FakeGraphQueryResult()


def test_relationship_question_adds_graph_without_replacing_relational_truth() -> None:
    contract = plan_agent_response_contract(
        "이 bearing 문제가 어느 라인과 제품까지 영향을 줄 수 있어? 연결 경로도 보여줘",
        object_id="CNC-S04-L04-01",
    )

    assert contract.scope == "object"
    assert contract.stores == ("relational", "graph")
    assert "relationship_paths" in contract.required_facts
    assert contract.presentation == "relationship"
    assert route_for_response_contract(contract) == "hybrid"


def test_sop_question_uses_relational_state_plus_vector_evidence() -> None:
    contract = plan_agent_response_contract(
        "이 설비의 점검 SOP와 현재 위험 근거를 설명해줘",
        object_id="CNC-03",
    )

    assert contract.stores == ("relational", "vector")
    assert "current_risk" in contract.required_facts
    assert "governed_knowledge" in contract.required_facts
    assert contract.presentation == "metric_summary"


def test_workspace_risk_question_stays_relational_when_no_graph_or_document_is_requested() -> None:
    contract = plan_agent_response_contract("현재 위험도가 높은 설비 순위를 보여줘")

    assert contract.scope == "workspace"
    assert contract.stores == ("relational",)
    assert contract.presentation == "risk_ranking"
    assert route_for_response_contract(contract) == "relational"


def test_workspace_kpi_question_keeps_company_context_retrieval_available() -> None:
    contract = plan_agent_response_contract("회사 KPI와 최근 운영 의사결정 문맥을 요약해줘")

    assert contract.stores == ("relational", "vector")
    assert "company_context" in contract.required_facts
    assert "organization_context" in contract.required_entities


def test_explicit_route_override_is_respected() -> None:
    contract = plan_agent_response_contract(
        "이 설비의 관계와 SOP 근거를 보여줘",
        route="graph",
        object_id="CNC-03",
    )

    assert contract.stores == ("graph",)
    assert route_for_response_contract(contract) == "graph"


def test_combined_relationship_and_sop_question_plans_all_three_stores() -> None:
    contract = plan_agent_response_contract(
        "이 부품과 연결된 제품 영향, 현재 위험, 관련 SOP 문서를 함께 보여줘",
        object_id="CNC-03",
    )

    assert contract.stores == ("relational", "graph", "vector")
    assert route_for_response_contract(contract) == "hybrid"
    assert set(contract.required_entities) >= {"asset", "component", "product", "knowledge_document"}


def test_project3_graph_evidence_uses_validated_boundary_without_exposing_cypher(monkeypatch) -> None:
    monkeypatch.setattr(operations_router, "_agent_project3_client", lambda: _FakeProject3Client())

    result = operations_router._project3_graph_evidence(
        question="제품까지 연결 경로를 보여줘",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        object_id="CNC-03",
        top_k=3,
    )

    assert result["status"] == "succeeded"
    assert result["row_count"] == 1
    assert result["evidence"][0]["store"] == "neo4j"
    assert result["evidence"][0]["metadata"]["validation"] == {"validated": True}
    assert "cypher" not in str(result["evidence"]).lower()
