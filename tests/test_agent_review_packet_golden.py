from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.dependencies import build_manufacturing_service
from app.operations.agent_review_packet import compose_agent_review_packet
from app.operations.context_providers import (
    AgentReviewContext,
    AgentReviewContextRegistry,
    default_agent_review_context_registry,
)
from app.operations.domain_context_adapters import ManufacturingFixtureReviewContextAdapter


ROOT = Path(__file__).resolve().parents[1]
GOLD_ROOT = ROOT / "tests" / "fixtures" / "agent_review_packets"
PACKET_SCHEMA = json.loads(
    (ROOT / "contracts" / "schemas" / "agent-review-packet.schema.json").read_text(
        encoding="utf-8"
    )
)


def _load_gold(scenario: str) -> dict:
    return json.loads((GOLD_ROOT / f"{scenario}.json").read_text(encoding="utf-8"))


def _stable_sop_guidance(item: dict) -> dict:
    """Compare stable SOP identity/content while allowing additive retrieval scoring changes."""

    return {key: value for key, value in item.items() if key != "retrieval_score"}


def _assert_ontology_context_preserves_gold(current: dict, gold: dict) -> None:
    """Require the Gold traversal while allowing additive SOP lineage enrichment."""

    assert current["provider"] == gold["provider"]
    assert current["mutation_allowed"] == gold["mutation_allowed"]
    current_by_component = {
        item["component_id"]: item for item in current.get("traversals", [])
    }
    for expected in gold.get("traversals", []):
        component_id = expected["component_id"]
        assert component_id in current_by_component
        actual = current_by_component[component_id]
        for key, value in expected.items():
            if key == "sop_ids":
                assert set(value) <= set(actual.get(key, []))
            elif key == "source_refs":
                assert set(value) <= set(actual.get(key, []))
            else:
                assert actual.get(key) == value
    assert set(gold.get("source_refs", [])) <= set(current.get("source_refs", []))


def _assert_review_draft_preserves_gold(current: dict, gold: dict) -> None:
    """Keep decision semantics stable while allowing newly grounded SOP guidance."""

    for key, value in gold.items():
        if key in {"summary", "checklist"}:
            continue
        assert current.get(key) == value
    assert set(gold.get("checklist", [])) <= set(current.get("checklist", []))
    if current.get("summary") != gold.get("summary"):
        gold_prefix = str(gold.get("summary") or "").split("입니다.", 1)[0]
        assert gold_prefix
        assert str(current.get("summary") or "").startswith(f"{gold_prefix}입니다.")
        assert "SOP" in str(current.get("summary") or "")


def test_agent_review_packet_gold_fixtures_match_schema() -> None:
    validator = Draft202012Validator(PACKET_SCHEMA)

    for scenario in ("GS-002", "GS-004", "GS-007"):
        payload = _load_gold(scenario)
        assert list(validator.iter_errors(payload)) == []
        assert payload["closed_loop_boundary"]["mutation_allowed"] is False
        assert payload["sop_retrieval"]["mutation_allowed"] is False
        assert "auto_approve" in payload["closed_loop_boundary"]["forbidden_actions"]
        assert payload["source_refs"]
        assert "human_questions" not in payload


def test_gs002_gold_carries_tooling_sop_location_and_history_review() -> None:
    packet = _load_gold("GS-002")

    assert packet["asset_id"] == "CNC-S04-L04-01"
    assert packet["inspection_targets"][0]["component_id"] == "tooling"
    assert packet["inspection_targets"][0]["location_label"] == "공구 매거진 및 스핀들 공구 체결부"
    for target in packet["inspection_targets"]:
        assert target["source_ref"] in packet["source_refs"]
        assert target["location_source_ref"] in packet["source_refs"]
    assert packet["sop_guidance"][0]["sop_id"] == "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001"
    assert packet["sop_guidance"][0]["sensor_judgment"]["inspection_result_mapping"] == {
        "records_operational_fact": True,
        "does_not_create_maintenance_event": True,
        "manual_recommendation_requires_manager_acceptance": True,
    }
    assert "최근 동일 부품 또는 동일 계통에 대한 점검/교체 이력 유무 조회" in packet[
        "history_review_items"
    ]


def test_gs004_gold_preserves_three_factor_refs_for_one_inspection_target() -> None:
    packet = _load_gold("GS-004")

    assert packet["asset_id"] == "CNC-S04-L02-03"
    assert packet["sop_guidance"] == []
    assert len(packet["inspection_targets"]) == 1
    target = packet["inspection_targets"][0]
    assert target["component_id"] == "drive_power"
    assert target["location_label"] == "주축 모터, 커플링, 동력 전달 하우징"
    assert target["source_ref"] in packet["source_refs"]
    assert target["location_source_ref"] in packet["source_refs"]
    assert "동력 전달 계통 중심" in packet["review_draft"]["summary"]
    assert "SOP 근거" not in packet["review_draft"]["summary"]
    assert target["basis_refs"][:3] == [
        "factor.1.mechanical_power_w",
        "factor.2.overstrain_index",
        "factor.3.torque_nm",
    ]
    assert len([ref for ref in target["basis_refs"] if ref.startswith("factor.")]) == 3
    assert "sensor_evidence.sensors.torque_nm" in target["basis_refs"]
    assert packet["sop_retrieval"]["query"]["component_ids"] == ["drive_power"]
    assert packet["sop_retrieval"]["query"]["factor_keys"] == [
        "mechanical_power_w",
        "overstrain_index",
        "torque_nm",
    ]
    model_context = packet["model_expression_context"]
    assert model_context["model_version"] == "fixture-heuristic-v1"
    assert [factor["feature"] for factor in model_context["top_factors"][:3]] == [
        "mechanical_power_w",
        "overstrain_index",
        "torque_nm",
    ]
    assert model_context["top_factors"][0]["display_name"] == "기계 동력"
    assert model_context["top_factors"][0]["source_ref"] in packet["source_refs"]
    history = packet["maintenance_history_summary"]
    assert history["mutation_allowed"] is False
    assert history["work_orders"][0]["record_id"] == "WO-INS-GS-004-001"
    assert history["work_orders"][0]["status"] == "requested"
    assert history["activities"][0]["activity_type"] == "work_order.requested"
    assert history["similar_events"][0]["similar_event_id"] == (
        "SIM-EVT-CNC-DRIVE-2026-07-22"
    )
    assert packet["ontology_context"]["provider"] == (
        "manufacturing_fixture_ontology_context"
    )
    assert packet["ontology_context"]["mutation_allowed"] is False
    assert packet["ontology_context"]["traversals"] == [
        {
            "component_id": "drive_power",
            "component_label": "동력 전달 계통",
            "factor_refs": [
                "factor.1.mechanical_power_w",
                "factor.2.overstrain_index",
                "factor.3.torque_nm",
            ],
            "location_label": "주축 모터, 커플링, 동력 전달 하우징",
            "location_source_ref": (
                "data/fixtures/inspection_location/"
                "demo-cnc-inspection-location-reference-v1.json#drive_power"
            ),
            "sop_ids": [],
            "spare_parts": [
                {
                    "part_id": "SP-CNC-DRIVE-COUPLING-KIT",
                    "part_label": "주축 구동 커플링 키트",
                    "replacement_scope": "커플링 및 동력 전달부 교체 검토",
                    "availability": "unavailable_from_fixture",
                    "lead_time_days": 2,
                    "replacement_window_minutes": 180,
                    "assumption_level": "demo_planning_assumption",
                    "source_ref": (
                        "data/fixtures/spare_part/"
                        "demo-cnc-spare-part-context-v1.json#"
                        "SP-CNC-DRIVE-COUPLING-KIT"
                    ),
                }
            ],
            "similar_events": [
                {
                    "similar_event_id": "SIM-EVT-CNC-DRIVE-2026-07-22",
                    "asset_label": "4구역 · 2셀 · CNC 가공기 1",
                    "observed_at": "2026-07-22T14:10:00+09:00",
                    "matched_factor_keys": [
                        "mechanical_power_w",
                        "overstrain_index",
                        "torque_nm",
                    ],
                    "action_taken": "동력 전달부 체결 상태 확인 후 커플링 편심 재조정",
                    "outcome": "토크와 과부하 누적 지표가 다음 관측 구간에서 완화됨",
                    "post_action_observation_window_hours": 48,
                    "assumption_level": "demo_history_assumption",
                    "source_ref": (
                        "data/fixtures/similar_event/"
                        "demo-cnc-similar-event-context-v1.json#"
                        "SIM-EVT-CNC-DRIVE-2026-07-22"
                    ),
                }
            ],
            "source_refs": [
                (
                    "data/fixtures/inspection_location/"
                    "demo-cnc-inspection-location-reference-v1.json#drive_power"
                ),
                "data/fixtures/spare_part/"
                "demo-cnc-spare-part-context-v1.json#"
                "SP-CNC-DRIVE-COUPLING-KIT",
                "data/fixtures/similar_event/"
                "demo-cnc-similar-event-context-v1.json#"
                "SIM-EVT-CNC-DRIVE-2026-07-22",
            ],
        }
    ]


def test_gs007_gold_fails_closed_for_data_quality_hold() -> None:
    packet = _load_gold("GS-007")

    assert packet["asset_id"] == "CNC-S04-L05-01"
    assert packet["risk_summary"]["status_grade"] is None
    assert packet["risk_summary"]["failure_probability"] is None
    assert packet["review_priority"] is None
    assert packet["review_draft"]["priority_label"] == "미확정"
    assert "데이터 품질 보류" in packet["review_draft"]["summary"]
    assert "의심 부품 중심" not in packet["review_draft"]["summary"]
    assert "SOP 근거" not in packet["review_draft"]["summary"]
    assert packet["inspection_targets"] == []
    assert packet["sop_guidance"] == []
    assert packet["review_draft"]["evidence_gap_count"] >= 1
    rendered = json.dumps(packet, ensure_ascii=False)
    assert "정비로 downtime 절감" not in rendered
    assert "실제 고장 예방 입증" not in rendered
    assert "SOP가 자동 정비 승인" not in rendered


def test_current_service_packets_keep_gold_contract_shape(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-review-gold.db", root=ROOT)
    cases = {
        "GS-002": "CNC-S04-L04-01",
        "GS-004": "CNC-S04-L02-03",
        "GS-007": "CNC-S04-L05-01",
    }

    for scenario, asset_id in cases.items():
        current = service.agent_review_packet(asset_id, "manufacturing-demo-project")
        gold = _load_gold(scenario)
        assert current["schema_version"] == gold["schema_version"]
        assert current["asset_id"] == gold["asset_id"]
        assert current["snapshot_basis"] == gold["snapshot_basis"]
        assert current["risk_summary"] == gold["risk_summary"]
        assert current["review_priority"] == gold["review_priority"]
        _assert_review_draft_preserves_gold(current["review_draft"], gold["review_draft"])
        assert current["inspection_targets"] == gold["inspection_targets"]
        assert current["sop_retrieval"]["provider"] == gold["sop_retrieval"]["provider"]
        assert current["sop_retrieval"]["query"] == gold["sop_retrieval"]["query"]
        assert current["sop_retrieval"]["top_k"] == gold["sop_retrieval"]["top_k"]
        assert current["sop_retrieval"]["mutation_allowed"] is False
        assert current["sop_retrieval"]["returned_count"] == len(
            {item["sop_id"] for item in current["sop_guidance"]}
        )
        assert current["sop_retrieval"]["returned_count"] >= gold["sop_retrieval"]["returned_count"]
        current_guidance = {
            (item["component_id"], item["sop_id"]): _stable_sop_guidance(item)
            for item in current["sop_guidance"]
        }
        for expected in gold["sop_guidance"]:
            key = (expected["component_id"], expected["sop_id"])
            assert key in current_guidance
            assert current_guidance[key] == _stable_sop_guidance(expected)
        for item in current["sop_guidance"]:
            assert item["source_type"] in {"demo_sop_fixture", "site_sop"}
            assert item["retrieval_score"] > 0
        _assert_ontology_context_preserves_gold(
            current["ontology_context"],
            gold["ontology_context"],
        )
        assert set(gold["history_review_items"]) <= set(current["history_review_items"])
        assert current["evidence_gaps"] == gold["evidence_gaps"]
        current_source_refs = set(current["source_refs"])
        assert all(
            target["source_ref"] in current_source_refs
            and target["location_source_ref"] in current_source_refs
            for target in current["inspection_targets"]
        )
        assert all(
            guidance["source_ref"] in current_source_refs
            for guidance in current["sop_guidance"]
        )
        assert set(current["maintenance_history_summary"]["source_refs"]) <= current_source_refs
        assert current["closed_loop_boundary"] == gold["closed_loop_boundary"]
        sections = {section["section_id"]: section for section in current["domain_sections"]}
        assert {"risk", "operation", "inspection", "sop", "ontology"}.issubset(
            sections
        )
        assert all(section["mutation_allowed"] is False for section in sections.values())
        assert "model_expression_context" in sections["risk"]["packet_paths"]
        assert sections["operation"]["owner_domain"] == "operations"
        assert sections["closed_loop_boundary"]["owner_domain"] == "closed_loop"


def test_agent_review_packet_uses_same_snapshot_basis_as_view_model(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-review-snapshot.db", root=ROOT)

    view_model = service.asset_detail_view_model(
        "CNC-S04-L02-03",
        "manufacturing-demo-project",
    )
    packet = service.agent_review_packet(
        "CNC-S04-L02-03",
        "manufacturing-demo-project",
    )

    assert packet["snapshot_basis"] == view_model["snapshot_basis"]
    assert packet["snapshot_basis"]["event_id"] == "EVT-GS-004"


def test_default_context_registry_projects_maintenance_history_from_view_model(
    tmp_path: Path,
) -> None:
    service = build_manufacturing_service(
        tmp_path / "agent-review-maintenance-context.db",
        root=ROOT,
    )
    view_model = service.asset_detail_view_model(
        "CNC-S04-L02-03",
        "manufacturing-demo-project",
    )

    context = default_agent_review_context_registry().context_for_packet(
        view_model=view_model
    )

    history = context.maintenance_history_summary
    assert history is not None
    assert history["provider"] == "closed_loop_maintenance_history_adapter"
    assert history["mutation_allowed"] is False
    assert history["work_orders"][0]["record_id"] == "WO-INS-GS-004-001"
    assert history["activities"][0]["activity_type"] == "work_order.requested"
    assert "closed-loop://work-order/WO-INS-GS-004-001" in context.source_refs


def test_service_packet_merges_maintenance_adapter_with_ontology_history(
    tmp_path: Path,
) -> None:
    service = build_manufacturing_service(
        tmp_path / "agent-review-maintenance-merge.db",
        root=ROOT,
    )

    packet = service.agent_review_packet(
        "CNC-S04-L02-03",
        "manufacturing-demo-project",
    )

    history = packet["maintenance_history_summary"]
    assert history["provider"] == "closed_loop_maintenance_history_adapter"
    assert history["mutation_allowed"] is False
    assert history["work_orders"][0]["record_id"] == "WO-INS-GS-004-001"
    assert history["similar_events"][0]["similar_event_id"] == (
        "SIM-EVT-CNC-DRIVE-2026-07-22"
    )
    assert "closed-loop://work-order/WO-INS-GS-004-001" in packet["source_refs"]
    assert (
        "data/fixtures/similar_event/demo-cnc-similar-event-context-v1.json#"
        "SIM-EVT-CNC-DRIVE-2026-07-22"
    ) in packet["source_refs"]


def test_agent_review_packet_accepts_adapter_supplied_context(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-review-context.db", root=ROOT)
    fixture = service._fixture_for_asset("CNC-S04-L02-03", "manufacturing-demo-project")
    artifact = service._product_result_artifact(fixture)
    view_model = service.asset_detail_view_model(
        "CNC-S04-L02-03",
        "manufacturing-demo-project",
    )
    sop_retrieval = ManufacturingFixtureReviewContextAdapter(ROOT).sop_retrieval(
        fixture=fixture,
        artifact=artifact,
    )
    context = AgentReviewContext(
        operation_context_summary={
            "production_impact": "high",
            "estimated_downtime_minutes": 240,
            "estimated_lost_units": 51,
            "product_variant": "L",
            "basis": "adapter supplied context",
            "limitations": [],
            "source_ref": "adapter://operation-context/test",
        },
        evidence_gaps=[
            {
                "field": "adapter_context.inventory",
                "reason": "adapter_context_missing_or_unresolved",
                "owner_domain": "inventory",
            }
        ],
        maintenance_history_summary={
            "provider": "stub-maintenance-history-adapter",
            "mutation_allowed": False,
            "open_work_order_exists": True,
            "similar_events_30d": 2,
            "work_orders": [
                {
                    "id": "WO-STUB-001",
                    "status": "requested",
                    "source_ref": "stub-maintenance://work-orders/WO-STUB-001",
                }
            ],
            "inspection_results": [],
            "maintenance_actions": [],
            "maintenance_events": [],
            "activities": [],
            "equipment_history": [],
            "similar_events": [],
            "source_refs": ["stub-maintenance://work-orders/WO-STUB-001"],
        },
        source_refs=["adapter://operation-context/test"],
    )

    packet = compose_agent_review_packet(
        project_id="manufacturing-demo-project",
        view_model=view_model,
        sop_retrieval=sop_retrieval,
        context=context,
    )

    assert packet["operation_context_summary"]["source_ref"] == (
        "adapter://operation-context/test"
    )
    assert "adapter://operation-context/test" in packet["source_refs"]
    assert {
        "field": "adapter_context.inventory",
        "reason": "adapter_context_missing_or_unresolved",
        "owner_domain": "inventory",
    } in packet["evidence_gaps"]
    assert packet["maintenance_history_summary"]["provider"] == (
        "stub-maintenance-history-adapter"
    )
    assert packet["maintenance_history_summary"]["mutation_allowed"] is False
    assert "stub-maintenance://work-orders/WO-STUB-001" in packet["source_refs"]
    sections = {section["section_id"]: section for section in packet["domain_sections"]}
    assert sections["operation"]["source"] == (
        "AgentReviewContextProvider operation adapter"
    )
    assert sections["operation"]["packet_paths"] == ["operation_context_summary"]
    assert sections["maintenance_history"]["mutation_allowed"] is False
    assert "role_summaries" not in packet


def test_agent_review_context_registry_merges_registered_domain_adapters() -> None:
    class InventoryContextProvider:
        adapter_id = "inventory"

        def context_for_packet(self, *, view_model: dict) -> AgentReviewContext:
            assert view_model["asset"]["asset_id"] == "CNC-S04-L02-03"
            return AgentReviewContext(
                evidence_gaps=[
                    {
                        "field": "adapter_context.inventory.parts_on_hand",
                        "reason": "adapter_context_missing_or_unresolved",
                        "owner_domain": "inventory",
                    }
                ],
                source_refs=["inventory://demo/parts/CNC-S04-L02-03"],
                limitations=["Inventory adapter is read-only."],
            )

    registry = AgentReviewContextRegistry(
        [InventoryContextProvider()],
        enabled_adapter_ids=["inventory"],
    )
    context = registry.context_for_packet(
        view_model={"asset": {"asset_id": "CNC-S04-L02-03"}}
    )

    assert context.evidence_gaps == [
        {
            "field": "adapter_context.inventory.parts_on_hand",
            "reason": "adapter_context_missing_or_unresolved",
            "owner_domain": "inventory",
        }
    ]
    assert context.source_refs == ["inventory://demo/parts/CNC-S04-L02-03"]
    assert context.limitations == ["Inventory adapter is read-only."]


def test_agent_review_context_registry_fails_closed_for_unknown_adapter() -> None:
    registry = AgentReviewContextRegistry([], enabled_adapter_ids=["mes"])

    context = registry.context_for_packet(
        view_model={"asset": {"asset_id": "CNC-S04-L02-03"}}
    )

    assert context.evidence_gaps == [
        {
            "field": "adapter_context.mes",
            "reason": "adapter_not_registered",
            "owner_domain": "mes",
        }
    ]


def test_agent_review_context_registry_captures_adapter_exceptions_as_gaps() -> None:
    class FailingContextProvider:
        adapter_id = "maintenance-history"

        def context_for_packet(self, *, view_model: dict) -> AgentReviewContext:
            raise RuntimeError("history repository unavailable")

    registry = AgentReviewContextRegistry(
        [FailingContextProvider()],
        enabled_adapter_ids=["maintenance-history"],
    )

    context = registry.context_for_packet(
        view_model={"asset": {"asset_id": "CNC-S04-L02-03"}}
    )

    assert context.evidence_gaps == [
        {
            "field": "adapter_context.maintenance-history",
            "reason": (
                "adapter_context_unavailable: history repository unavailable"
            ),
            "owner_domain": "maintenance-history",
        }
    ]
