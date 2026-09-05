from datetime import datetime, timezone
from types import SimpleNamespace

from app.identity import Principal
from app.operations.contracts import AgentQueryRequest
from app.operations.router import (
    _answer_from_packet,
    _merge_runtime_detail_supplemental,
    _packet_evidence,
    _runtime_agent_review_packet,
    _runtime_asset_detail_view_model,
    _runtime_operation_context,
    _runtime_sop_context,
    _summary_text,
)


def _runtime_result():
    return SimpleNamespace(
        artifact_id="RESULT#CNC-S01-L04-03#1",
        asset_id="CNC-S01-L04-03",
        asset_type="cnc",
        site_id="S01",
        cell_id="S01-L04",
        observed_at=datetime(2026, 9, 2, 7, 50, tzinfo=timezone.utc),
        status_grade="warning",
        predicted_failure_type="failure_risk",
        prediction_horizon_hours=24,
        failure_probability=0.72,
        confidence=0.91,
        source_contract="result_artifact",
        producer_artifact=None,
        recommended_action=SimpleNamespace(action="request_inspection"),
        provenance=SimpleNamespace(
            model_version="independent-logreg-v3.1",
            schema_version="result-artifact-v1.0",
            prediction_task="binary_failure_within_horizon",
            prediction_id="RESULT#CNC-S01-L04-03#1",
            prediction_result_id="prediction-result-1",
        ),
        top_factors=[
            SimpleNamespace(rank=1, feature="rotation_raw", feature_value=488.0, signed_contribution=0.31, direction="risk_up", explanation_method="linear_contribution"),
            SimpleNamespace(rank=2, feature="vibration_raw", feature_value=58.0, signed_contribution=0.24, direction="risk_up", explanation_method="linear_contribution"),
        ],
    )


def _principal() -> Principal:
    return Principal(
        user_id="engineer-1",
        organization_id="org-1",
        email="engineer@ontology.local",
        display_name="Engineer",
        status="active",
        roles=["process_engineer"],
        permissions=["events.read"],
        workspace_scopes=["manufacturing-demo"],
        project_scopes=["manufacturing-demo-project"],
        active_project_id="manufacturing-demo-project",
        active_project_roles=["process_engineer"],
        is_admin=False,
        default_path="/app",
        landing_key="process_engineer",
    )


class _RuntimeService:
    def __init__(self, result):
        self.result = result

    def latest_results(self, **_kwargs):
        return SimpleNamespace(
            items=[self.result],
            context=SimpleNamespace(dataset_id="manufacturing-canonical", dataset_version_id="dsv-canonical-v3-1"),
        )

    def observations(self, **_kwargs):
        return SimpleNamespace(observations=[])

    def timeline(self, **_kwargs):
        return {"items": []}

    def company_context_documents(self, *_args, **_kwargs):
        return []


def test_runtime_operation_context_is_explicit_and_actionable():
    result = _runtime_result()
    context = _runtime_operation_context(result, "RESULT#CNC-S01-L04-03#1")

    assert context["source_type"] == "capacity_model"
    assert context["production_plan"]["planned_units"] == 16200
    assert context["capacity_model"]["daily_capacity_units"] == 16200
    assert context["event_impact"]["line"] == "S01-L04"
    assert context["event_impact"]["estimated_lost_units"] > 0
    assert context["event_impact"]["basis"]["estimated_downtime_minutes"] == 120
    assert any("결산" in item for item in context["limitations"])


def test_runtime_sop_retrieval_returns_grounded_source_for_cnc_result():
    result = _runtime_result()
    context = _runtime_operation_context(result, "RESULT#CNC-S01-L04-03#1")

    retrieval, guidance = _runtime_sop_context(result, context)

    assert retrieval["provider"] == "local_sop_metadata_retriever"
    assert retrieval["top_k"] == 3
    assert retrieval["returned_count"] >= 1
    assert guidance
    assert guidance[0]["sop_id"] == "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001"
    assert guidance[0]["source_ref"].endswith("#SOP-DEMO-CNC-ROTATING-ASSEMBLY-001")
    assert "factor_keys" in guidance[0]["matched_fields"]


def test_runtime_sop_retrieval_normalizes_temporal_model_features_to_sensor_keys():
    result = _runtime_result()
    result.top_factors = [
        SimpleNamespace(feature="rotational_speed_rpm_6h_mean"),
        SimpleNamespace(feature="rotational_speed_rpm_6h_abs_mean"),
        SimpleNamespace(feature="rotational_speed_rpm_current"),
    ]
    context = _runtime_operation_context(result, "RESULT#CNC-S01-L04-03#temporal")

    retrieval, guidance = _runtime_sop_context(result, context)

    assert retrieval["query"]["factor_keys"] == ["rotational_speed_rpm"]
    assert retrieval["returned_count"] >= 1
    assert guidance
    assert guidance[0]["sop_id"] == "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001"
    assert "factor_keys" in guidance[0]["matched_fields"]


def test_exact_runtime_event_connects_sop_inspection_target_and_assistant_evidence():
    result = _runtime_result()
    service = _RuntimeService(result)
    event_id = result.artifact_id

    packet = _runtime_agent_review_packet(
        asset_id=result.asset_id,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        dataset_version_id="dsv-canonical-v3-1",
        selected_event_id=event_id,
        principal=_principal(),
        runtime_service=service,
    )
    detail = _runtime_asset_detail_view_model(
        asset_id=result.asset_id,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        dataset_version_id="dsv-canonical-v3-1",
        selected_event_id=event_id,
        history_window="24h",
        principal=_principal(),
        runtime_service=service,
    )
    evidence = _packet_evidence(
        packet,
        service=service,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        top_k=8,
    )

    assert packet["snapshot_basis"]["event_id"] == event_id
    assert packet["sop_retrieval"]["returned_count"] >= 1
    assert len(packet["inspection_targets"]) >= 1
    assert len(detail["inspection_targets"]) >= 1
    assert any(item["store"] == "project3_rag" for item in evidence)
    assert any(
        item["reference"].endswith("#SOP-DEMO-CNC-ROTATING-ASSEMBLY-001")
        for item in evidence
    )


def test_agent_query_audience_selects_distinct_role_summary():
    summary = {
        "summary": "경영진용 전체 운영 요약",
        "role_summaries": [
            {"role": "field_operator", "quote": "엔지니어 기술 근거 요약"},
            {"role": "process_manager", "quote": "관리자 Decision Packet 요약"},
        ],
    }

    assert _summary_text(summary, "engineering") == "엔지니어 기술 근거 요약"
    assert _summary_text(summary, "operations") == "관리자 Decision Packet 요약"
    assert _summary_text(summary, "executive") == "경영진용 전체 운영 요약"


def test_executive_agent_answer_adds_business_impact_context():
    packet = {
        "asset_id": "CNC-S01-L04-03",
        "asset_label": "CNC-S01-L04-03",
        "risk_summary": {"status_grade": "warning", "failure_probability": 0.7},
        "review_priority": {"reasons": ["warning"]},
        "operation_context_summary": {
            "production_impact": "medium",
            "estimated_downtime_minutes": 120,
            "estimated_lost_units": 25,
        },
    }
    summary = {
        "summary": "현재 운영 판단이 필요한 주요 이슈입니다.",
        "role_summaries": [],
    }
    evidence = [{"content": "SOP 점검 근거"}]

    answer = _answer_from_packet("경영 보고 요약", packet, evidence, summary, "executive")

    assert "생산 영향 medium" in answer
    assert "예상 정지 120분" in answer
    assert "계획 영향 약 25개" in answer
    assert "생산 연속성과 손실 노출을 선제적으로 보호" in answer
    assert "실제 비용 절감 실적으로 확정하지 않습니다" in answer
    assert "SOP 점검 근거" in answer


def test_agent_answer_frames_modeled_exposure_as_value_not_realized_savings():
    packet = {
        "asset_id": "CNC-S01-L04-03",
        "asset_label": "CNC-S01-L04-03",
        "risk_summary": {"status_grade": "warning", "failure_probability": 0.7},
        "review_priority": {"reasons": ["warning"]},
        "operation_context_summary": {
            "production_impact": "high",
            "estimated_downtime_minutes": 120,
            "estimated_lost_units": 25,
            "product_variant": "HX-M",
        },
    }
    evidence = [
        {
            "content": "Decision Lead Time target 90 min",
            "title": "Decision Lead Time",
            "metadata": {"document_type": "business_metric"},
        },
        {
            "content": "HX-M unit contribution margin 132000 KRW",
            "title": "HX-M",
            "metadata": {"document_type": "product_economics"},
        },
    ]

    answer = _answer_from_packet(
        "이 조치의 비용 절감과 KPI 가치는?",
        packet,
        evidence,
        None,
        "executive",
    )

    assert "가치 관점" in answer
    assert "계획 손실 노출 약 25개" in answer
    assert "KPI 연결 근거는 Decision Lead Time" in answer
    assert "재무·제품 경제성 근거로 HX-M" in answer
    assert "실제 비용 절감 실적으로 확정하지 않습니다" in answer


def test_agent_query_contract_accepts_role_audience():
    request = AgentQueryRequest(
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        question="이 이슈를 경영진 관점에서 요약해줘",
        audience="executive",
        event_id="RESULT#CNC-S01-L04-03#1",
    )

    assert request.audience == "executive"
    assert request.event_id == "RESULT#CNC-S01-L04-03#1"


def test_canonical_live_detail_keeps_evidence_and_adds_presentation_context():
    canonical = {
        "snapshot_basis": {"artifact_id": "RESULT#1"},
        "features": [{"feature": "rotation_raw"}],
        "inspection_targets": [],
        "review_priority": None,
        "evidence": {
            "artifact_id": "RESULT#1",
            "gaps": [
                {"field": "operation_context.production_impact", "reason": "missing"},
                {"field": "review_priority", "reason": "missing"},
                {"field": "equipment_history", "reason": "missing"},
            ],
        },
    }
    supplemental = {
        "operation_context": {"source_type": "capacity_model"},
        "inspection_targets": [{"target_id": "inspection-target:1"}],
        "review_priority": {"level": "high"},
    }

    merged = _merge_runtime_detail_supplemental(canonical, supplemental)

    assert merged["snapshot_basis"] == canonical["snapshot_basis"]
    assert merged["features"] == canonical["features"]
    assert merged["operation_context"]["source_type"] == "capacity_model"
    assert merged["inspection_targets"] == supplemental["inspection_targets"]
    assert merged["review_priority"] == supplemental["review_priority"]
    assert merged["evidence"]["gaps"] == [
        {"field": "equipment_history", "reason": "missing"}
    ]
