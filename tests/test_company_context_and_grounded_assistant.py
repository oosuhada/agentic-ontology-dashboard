from __future__ import annotations

from types import SimpleNamespace

from app.common.company_context import (
    load_company_context,
    public_company_context,
    retrieve_company_documents,
)
from app.ontology.projection import ManufacturingOntologyAdapter
from app.operations.agent_answer_provider import GroundedAgentAnswerProvider
from app.infra.db.company_context_repository import CompanyContextRepository
from app.infra.db.migrations import migrate


class _EmptyActivityRepository:
    def event_activity(self, _event_id: str):
        return {"decisions": [], "notes": [], "conversations": [], "field_actions": []}


class _ContextOnlyProjectionSource:
    fixtures = {}
    repository = _EmptyActivityRepository()

    def evidence_snapshot(self, _event_id: str):  # pragma: no cover - no fixture events in this projection test
        raise AssertionError("context-only projection must not request event evidence")


class _AnswerProvider:
    name = "test-llm"

    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, *_args, **_kwargs):
        return self.payload


def test_company_context_has_operational_business_and_history_records():
    context = load_company_context()

    assert context["context_kind"] == "company_operational_context"
    assert context["company"]["name"] == "한빛테크"
    assert {item["persona_roles"][0] for item in context["organization_units"] if item["persona_roles"]} >= {
        "executive_viewer",
        "process_manager",
        "process_engineer",
        "maintenance_technician",
    }
    assert context["products"]
    assert context["materials"]
    assert context["business_metrics"]
    assert context["maintenance_records"]
    assert context["meeting_minutes"]
    assert context["decisions"]
    assert len(context["assets"]) >= 88
    assert len(context["maintenance_records"]) >= 700
    assert len(context["materials"]) >= 70
    assert len(context["kpi_snapshots"]) >= 160
    assert len(context["financial_periods"]) == 18
    assert len(context["meeting_minutes"]) >= 80
    assert len(context["decisions"]) >= 170
    assert len(context["documents"]) >= 90
    assert context["corpus_summary"]["generated_history_months"] == 18
    assert "disclaimer" not in public_company_context()


def test_public_company_context_keeps_large_history_bounded():
    full = load_company_context()
    public = public_company_context(full)

    assert len(full["maintenance_records"]) > len(public["maintenance_records"])
    assert len(public["maintenance_records"]) <= 24
    assert len(public["meeting_minutes"]) <= 12
    assert len(public["decisions"]) <= 24
    assert len(public["kpi_snapshots"]) <= 54
    assert public["corpus_summary"]["maintenance_records"] == len(full["maintenance_records"])


def test_company_context_can_be_promoted_to_project_scoped_db_records(tmp_path):
    database_path = tmp_path / "company-context.db"
    migrate(str(database_path))
    repository = CompanyContextRepository(database_path)
    inserted = repository.seed_records(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        context=load_company_context(),
    )

    records = repository.list_records(
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
    )
    assert inserted > 0
    assert records
    assert {record["record_type"] for record in records} >= {
        "assets",
        "vendors",
        "materials",
        "maintenance_records",
        "business_metrics",
        "kpi_snapshots",
        "financial_periods",
        "meeting_minutes",
        "decisions",
        "documents",
    }
    assert any(record["payload"].get("name") == "한빛테크" for record in records) is False


def test_company_rag_prefers_asset_history_and_material_context():
    results = retrieve_company_documents(
        "최근 정비 이력과 자재 재고, 과거 의사결정을 알려줘",
        asset_id="CNC-S04-L02-03",
        top_k=8,
    )

    assert results
    assert any(
        item["document_type"] == "maintenance_history"
        and "CNC-S04-L02-03" in item.get("related_asset_ids", [])
        for item in results
    )
    assert any(item["document_type"] == "material_master" for item in results)
    assert any(item["document_type"] == "decision_record" for item in results)
    assert all(item["context_kind"] == "company_operational_context" for item in results)
    assert all(len(str(item.get("source_sha256") or "")) == 64 for item in results)


def test_company_rag_can_answer_asset_economics_finance_kpi_and_sop_questions():
    asset_results = retrieve_company_documents(
        "CNC-S04-L02-03 장비 가격과 교체비 장부가를 알려줘",
        asset_id="CNC-S04-L02-03",
        top_k=8,
    )
    finance_results = retrieve_company_documents(
        "2026년 재무 손익 매출 OPEX CAPEX",
        roles=["executive_viewer"],
        top_k=8,
    )
    kpi_results = retrieve_company_documents("최근 OEE MTBF MTTR KPI 추세", top_k=8)
    sop_results = retrieve_company_documents("스핀들 베어링 SOP 점검 절차", top_k=8)

    assert any(item["document_type"] == "asset_master" for item in asset_results)
    assert any(item["document_type"] in {"financial_actual", "financial_statement"} for item in finance_results)
    assert any(item["document_type"] == "kpi_actual" for item in kpi_results)
    assert any(item["document_type"] == "site_sop" for item in sop_results)


def test_company_context_is_projected_as_ontology_objects_and_links():
    snapshot = ManufacturingOntologyAdapter(_ContextOnlyProjectionSource()).snapshot()
    object_types = {item.object_type for item in snapshot.objects}
    link_types = {item.link_type for item in snapshot.links}

    assert {
        "company",
        "organization_unit",
        "product",
        "material",
        "business_metric",
        "maintenance_history_record",
        "meeting_record",
        "decision_record",
        "production_order",
        "quality_incident",
        "purchase_order",
        "capa_record",
    } <= object_types
    assert "company_has_organization_unit" in link_types
    assert "company_sells_product" in link_types
    assert "company_has_business_metric" in link_types
    assert "meeting_records_decision" in link_types
    assert "equipment_runs_production_order" in link_types
    assert "quality_incident_affects_order" in link_types
    assert "purchase_order_replenishes_material" in link_types
    assert "capa_addresses_quality_incident" in link_types
    assert snapshot.source_revision == "operational-and-company-context-v2"


def test_grounded_answer_provider_accepts_only_supplied_evidence_ids():
    provider = GroundedAgentAnswerProvider(_AnswerProvider({
        "answer": "최근 스핀들 정비 이력과 현재 위험 근거를 함께 확인하고 작업 승인 여부를 판단해야 합니다.",
        "evidence_ids": ["packet-factor-1", "company-context-1"],
        "caveats": ["현재 고장 확정이 아니라 검토 우선순위입니다."],
    }))
    evidence = [
        {"evidence_id": "packet-factor-1", "content": "회전 속도 변화"},
        {"evidence_id": "company-context-1", "content": "최근 스핀들 정비 이력"},
    ]

    answer, citations, caveats, trace = provider.generate(
        question="최근 정비와 관련 있나?",
        audience="operations",
        packet={"asset_id": "CNC-S04-L02-03", "risk_summary": {}, "review_priority": {}},
        evidence=evidence,
        baseline_answer="fallback",
        summary=None,
    )

    assert answer.startswith("최근 스핀들")
    assert citations == ["packet-factor-1", "company-context-1"]
    assert caveats
    assert trace["mode"] == "llm"


def test_grounded_answer_provider_fails_closed_on_unknown_citation():
    provider = GroundedAgentAnswerProvider(_AnswerProvider({
        "answer": "검증되지 않은 외부 숫자를 사용했습니다.",
        "evidence_ids": ["not-supplied"],
        "caveats": [],
    }))

    answer, citations, _caveats, trace = provider.generate(
        question="매출 영향은?",
        audience="executive",
        packet={"asset_id": "CNC-S04-L02-03"},
        evidence=[{"evidence_id": "company-context-1", "content": "연결된 경영 문맥"}],
        baseline_answer="근거가 확인된 범위에서만 답변합니다.",
        summary=None,
    )

    assert answer == "근거가 확인된 범위에서만 답변합니다."
    assert citations == []
    assert trace["mode"] == "deterministic_fallback"
