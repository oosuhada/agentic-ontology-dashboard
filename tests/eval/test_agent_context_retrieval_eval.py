from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.dependencies import build_manufacturing_service
from app.operations.agent_context_graph import (
    answer_agent_context_graph,
    build_agent_context_graph,
)
from app.operations.agent_review_summary_workflow import AgentReviewSummaryWorkflow


ROOT = Path(__file__).resolve().parents[2]
QUESTION_PATH = ROOT / "tests" / "eval" / "agent_context_questions.jsonl"
QUESTION_BACKLOG_PATH = ROOT / "tests" / "eval" / "agent_context_question_backlog.jsonl"
RDB_BASELINE_PATH = ROOT / "tests" / "eval" / "agent_context_rdb_baseline.json"
RAG_GATE_PATH = ROOT / "tests" / "eval" / "rag_decision_gate.json"
LANGGRAPH_GATE_PATH = ROOT / "tests" / "eval" / "langgraph_decision_gate.json"
WORKFLOW_GATE_PATH = ROOT / "tests" / "eval" / "agent_workflow_eval_gate.json"


def _load_questions() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in QUESTION_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_question_backlog() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in QUESTION_BACKLOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_rdb_baseline() -> dict[str, Any]:
    return json.loads(RDB_BASELINE_PATH.read_text(encoding="utf-8"))


def _load_rag_gate() -> dict[str, Any]:
    return json.loads(RAG_GATE_PATH.read_text(encoding="utf-8"))


def _load_langgraph_gate() -> dict[str, Any]:
    return json.loads(LANGGRAPH_GATE_PATH.read_text(encoding="utf-8"))


def _load_workflow_gate() -> dict[str, Any]:
    return json.loads(WORKFLOW_GATE_PATH.read_text(encoding="utf-8"))


def test_agent_context_question_set_controls_eval_variables() -> None:
    questions = _load_questions()

    assert len(questions) >= 3
    assert len({question["case_id"] for question in questions}) == len(questions)
    for question in questions:
        assert question["question"]
        assert set(question["expected"]) == {
            "component_id",
            "factor_refs",
            "location_label",
            "sop_ids",
            "spare_part_ids",
            "similar_event_ids",
            "boundary",
        }


def test_agent_context_question_backlog_separates_current_coverage_from_kg_pressure() -> None:
    backlog = _load_question_backlog()

    assert len(backlog) >= 10
    assert len({question["case_id"] for question in backlog}) == len(backlog)
    answerability = {question["answerability"] for question in backlog}
    assert {
        "covered_by_current_packet",
        "requires_new_adapter_contract",
        "requires_structured_sop_extension",
        "defer_until_rag_or_document_store",
        "defer_until_multi_asset_graph_source",
    }.issubset(answerability)
    assert sum(
        1 for question in backlog if question["answerability"] == "covered_by_current_packet"
    ) >= 3
    assert sum(
        1
        for question in backlog
        if question["answerability"]
        in {
            "requires_new_adapter_contract",
            "requires_structured_sop_extension",
            "defer_until_rag_or_document_store",
            "defer_until_multi_asset_graph_source",
        }
    ) >= 6

    for question in backlog:
        assert set(question) == {
            "case_id",
            "question",
            "answerability",
            "primary_sources",
            "relationship_path",
            "kg_signal",
        }
        assert question["question"]
        assert len(question["relationship_path"]) >= 3
        assert question["primary_sources"]
        assert question["kg_signal"]


def test_agent_context_question_backlog_names_next_domain_sources() -> None:
    sources = {
        source
        for question in _load_question_backlog()
        for source in question["primary_sources"]
    }

    assert {
        "cmms",
        "erp_inventory",
        "mes",
        "sop_repository",
        "asset_registry",
    }.issubset(sources)


def test_agent_context_rdb_baseline_documents_current_default_and_pressure_points() -> None:
    baseline = _load_rdb_baseline()
    backlog = _load_question_backlog()

    assert baseline["baseline_id"] == "agent-context-rdb-baseline-v1"
    assert baseline["decision"]["current_default"] == "keep_rdb_packet_projection"
    assert baseline["decision"]["kg_next_step"] == (
        "run_in_memory_level1_traversal_experiment"
    )
    assert "KG is faster" in baseline["decision"]["do_not_claim"]
    assert len(baseline["current_strengths"]) >= 3
    assert len(baseline["pressure_points"]) >= 4
    assert baseline["controlled_variables"]["same_user_questions"].endswith(
        "agent_context_question_backlog.jsonl"
    )
    assert len(backlog) >= len(baseline["pressure_points"])


def test_kg_level0_packet_and_ontology_context_answer_same_facets(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-eval.db", root=ROOT)

    for question in _load_questions():
        packet = service.agent_review_packet(question["asset_id"])
        expected = question["expected"]

        packet_answer = _answer_from_packet(packet)
        ontology_answer = _answer_from_ontology_context(packet)

        assert _matches_expected(packet_answer, expected), question["case_id"]
        assert _matches_expected(ontology_answer, expected), question["case_id"]
        assert packet_answer["boundary"] == ontology_answer["boundary"]


def test_kg_level0_trace_remains_read_only(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-readonly.db", root=ROOT)

    for question in _load_questions():
        packet = service.agent_review_packet(question["asset_id"])
        assert packet["ontology_context"]["mutation_allowed"] is False
        assert packet["closed_loop_boundary"]["mutation_allowed"] is False
        rendered = json.dumps(packet["ontology_context"], ensure_ascii=False)
        assert "approve_work_order" not in rendered
        assert "auto_approve" not in rendered


def test_kg_level1_in_memory_graph_answers_current_facets(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-kg-level1.db", root=ROOT)

    for question in _load_questions():
        packet = service.agent_review_packet(question["asset_id"])
        expected = question["expected"]
        graph_answer = answer_agent_context_graph(packet)

        assert _matches_expected(graph_answer, expected), question["case_id"]
        assert graph_answer["node_count"] >= 1
        assert graph_answer["edge_count"] >= 0
        if graph_answer["similar_event_ids"]:
            assert graph_answer["similar_event_outcomes"]


def test_kg_level1_in_memory_graph_records_relationship_fanout(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-kg-level1-fanout.db", root=ROOT)
    packet = service.agent_review_packet("CNC-S04-L02-03")
    graph = build_agent_context_graph(packet)
    node_types = {node.node_type for node in graph.nodes.values()}
    relations = {edge.relation for edge in graph.edges}

    assert {
        "PredictionSnapshot",
        "Asset",
        "Factor",
        "Component",
        "InspectionLocation",
        "SparePart",
        "SimilarEvent",
        "Outcome",
    }.issubset(node_types)
    assert {
        "has_factor",
        "maps_to_component",
        "checked_at",
        "has_spare_part_candidate",
        "has_similar_event",
        "resulted_in",
    }.issubset(relations)
    assert "approve_work_order" not in json.dumps(
        {
            "nodes": [node.__dict__ for node in graph.nodes.values()],
            "edges": [edge.__dict__ for edge in graph.edges],
        },
        ensure_ascii=False,
    )


def test_rag_decision_gate_defers_runtime_rag_for_structured_sop(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-rag-gate.db", root=ROOT)
    gate = _load_rag_gate()

    assert gate["current_decision"] == "defer_runtime_rag"
    assert gate["current_sop_source"] == {
        "format": "structured_fixture_metadata",
        "retriever": "local_sop_metadata_retriever",
        "paragraph_level_citations_required": False,
        "multiple_overlapping_versions": False,
        "unstructured_documents_present": False,
    }
    assert "llamaindex_runtime_retrieval" in gate["deferred_runtime_components"]

    for question in _load_questions():
        packet = service.agent_review_packet(question["asset_id"])
        assert packet["sop_retrieval"]["provider"] == "local_sop_metadata_retriever"
        assert "vector" not in packet["sop_retrieval"]["provider"]
        assert packet["sop_retrieval"]["mutation_allowed"] is False

    assert set(gate["adopt_rag_when_any"]) == {
        "site_sops_arrive_as_pdf_or_free_form_documents",
        "multiple_sop_versions_overlap_for_same_component_or_failure_mode",
        "paragraph_level_citations_are_required_for_user_facing_guidance",
        "structured_metadata_cannot_answer_agent_context_eval_questions",
    }


def test_langgraph_decision_gate_keeps_simple_workflow_default(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-context-langgraph-gate.db", root=ROOT)
    gate = _load_langgraph_gate()
    workflow_result = AgentReviewSummaryWorkflow(service).run(limit=1, max_attempts=1)

    assert gate["current_decision"] == "keep_simple_workflow_default"
    assert gate["current_engine"] == "simple"
    assert gate["experimental_status"] == {
        "tool_trajectory_eval": "implemented_eval_only",
        "per_tool_retry_trace": "implemented_eval_only",
        "langgraph_runtime": "implemented_experiment_only",
        "production_default": "simple",
    }
    assert workflow_result["workflow"]["engine"] == gate["current_engine"]
    assert gate["first_experiment_shape"]["public_boundary"] == "AgentReviewSummaryWorkflow"
    assert gate["first_experiment_shape"]["default"] == "simple"
    assert gate["first_experiment_shape"]["experimental"] == "langgraph"
    assert "AI_WORKFLOW_ENGINE" == gate["first_experiment_shape"]["flag"]
    assert len(gate["current_context_facets"]) >= 3
    assert "three_or_more_independent_runtime_domain_tools" in (
        gate["minimum_trigger_conditions"]
    )


def test_langgraph_gate_keeps_closed_loop_state_out_of_graph_contract() -> None:
    gate = _load_langgraph_gate()

    assert len(gate["minimum_trigger_conditions"]) >= 3
    assert "domain_context" in gate["first_experiment_shape"]["allowed_state"]
    assert "agent_review_packet" in gate["first_experiment_shape"]["allowed_state"]
    assert "executable_closed_loop_command" in gate["first_experiment_shape"]["forbidden_state"]
    assert "mutable_work_order_state" in gate["first_experiment_shape"]["forbidden_state"]
    assert "approval_action_tool" in gate["first_experiment_shape"]["forbidden_state"]
    assert gate["independent_runtime_tool_definition"][
        "requires_tool_trajectory_eval"
    ] is True


def test_workflow_eval_gate_covers_minimum_release_axes(tmp_path: Path) -> None:
    service = build_manufacturing_service(tmp_path / "agent-workflow-eval-gate.db", root=ROOT)
    gate = _load_workflow_gate()
    workflow_result = AgentReviewSummaryWorkflow(service).run(limit=1, max_attempts=1)

    assert gate["current_decision"] == (
        "keep_simple_workflow_with_materialized_summary_contract"
    )
    assert gate["current_engine"] == "simple"
    assert workflow_result["workflow"]["engine"] == gate["current_engine"]
    assert set(gate["evaluation_scope"]) == {
        "output_contract",
        "groundedness",
        "workflow_stages",
        "summary_reuse",
        "fallback_retry",
        "domain_context_grounding",
        "closed_loop_boundary",
    }
    assert set(gate["minimum_release_gates"]) == set(gate["evaluation_scope"])
    assert {
        "workflow_engine_reported",
        "attempt_count_reported",
        "terminal_status_reported",
        "retry_policy_reported",
    }.issubset(set(gate["minimum_release_gates"]["workflow_stages"]))
    assert workflow_result["workflow"]["terminal_status"] == "completed"
    assert workflow_result["workflow"]["attempt_count"] >= 1
    assert workflow_result["workflow"]["max_attempts"] == 1
    assert "summary_materialization" in workflow_result["workflow"]["retry_policy"]
    assert {
        "db_backed_maintenance_history_reaches_role_summary",
        "future_inventory_mes_schedule_claims_are_blocked_until_source_contract",
        "adapter_source_refs_remain_inside_packet_scope",
    }.issubset(set(gate["minimum_release_gates"]["domain_context_grounding"]))


def test_workflow_eval_gate_defers_langgraph_until_tool_trajectory_pressure() -> None:
    gate = _load_workflow_gate()

    assert gate["candidate_engine"] == "langgraph"
    assert "three_or_more_independent_runtime_domain_tools_require_ordered_calls" in (
        gate["adopt_langgraph_when_any"]
    )
    assert "tool_trajectory_accuracy_becomes_release_gate" in gate["adopt_langgraph_when_any"]
    assert "workflow_eval_gate_passes_without_tool_trajectory_checks" in (
        gate["defer_langgraph_when_all"]
    )
    assert "context_facets_are_multiple_but_resolved_by_one_single_process_adapter" in (
        gate["defer_langgraph_when_all"]
    )
    assert len(gate["current_context_facets"]) >= 3
    assert "maintenance_history_context" in gate["current_context_facets"]
    assert gate["independent_runtime_tool_definition"][
        "requires_separate_retry_policy"
    ] is True
    assert "direct_llm_domain_database_reads" in gate["forbidden_runtime_shortcuts"]
    assert "raw_sql_or_cypher_generated_by_llm" in gate["forbidden_runtime_shortcuts"]
    assert "closed_loop_mutation_from_ai_summary" in gate["forbidden_runtime_shortcuts"]
    assert "approval_action_tool_in_ai_workflow" in gate["forbidden_runtime_shortcuts"]
    assert "uncited_summary_fact" in gate["forbidden_runtime_shortcuts"]

    alignment = gate["reference_alignment"]
    assert set(alignment) == {
        "openai_evals",
        "langsmith_agent_evals",
        "azure_agent_and_rag_evals",
        "ragas_rag_metrics",
    }


def test_workflow_eval_gate_defers_production_rag_runtime_until_retrieval_metrics() -> None:
    gate = _load_workflow_gate()
    retrieval_gate = gate["retrieval_runtime_decision_gate"]

    assert retrieval_gate["current_decision"] == (
        "defer_production_graphrag_vector_db_llamaindex"
    )
    assert retrieval_gate["current_runtime_source"] == (
        "structured_adapter_context_inside_agent_review_packet"
    )
    assert set(retrieval_gate["candidate_stack"]) == {
        "GraphRAG",
        "Vector DB",
        "LlamaIndex",
    }
    assert {
        "context_precision_recall_not_yet_measured",
        "retrieval_freshness_contract_not_yet_release_gated",
        "packet_snapshot_alignment_is_the_primary_current_gate",
    }.issubset(set(retrieval_gate["defer_when_all"]))
    assert {
        "retrieval_context_precision_recall_becomes_release_gate",
        "retrieved_chunks_have_source_sha256_and_freshness_metadata",
        "retrieval_results_are_bound_to_agent_review_packet_snapshot",
        "llm_summary_validation_rejects_uncited_retrieval_claims",
    }.issubset(set(retrieval_gate["adopt_when_all"]))


def _answer_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    target = (packet.get("inspection_targets") or [{}])[0]
    guidance = (packet.get("sop_guidance") or [{}])[0]
    traversal = _matching_ontology_traversal(packet, target.get("component_id"))
    return {
        "component_id": target.get("component_id"),
        "factor_refs": [
            ref for ref in target.get("basis_refs") or [] if str(ref).startswith("factor.")
        ],
        "location_label": target.get("location_label"),
        "sop_ids": [guidance["sop_id"]] if guidance.get("sop_id") else [],
        "spare_part_ids": [
            part["part_id"]
            for part in traversal.get("spare_parts") or []
            if part.get("part_id")
        ],
        "similar_event_ids": [
            event["similar_event_id"]
            for event in traversal.get("similar_events") or []
            if event.get("similar_event_id")
        ],
        "boundary": _boundary(packet),
    }


def _answer_from_ontology_context(packet: dict[str, Any]) -> dict[str, Any]:
    traversal = (packet.get("ontology_context") or {}).get("traversals") or []
    first = traversal[0] if traversal else {}
    return {
        "component_id": first.get("component_id"),
        "factor_refs": first.get("factor_refs") or [],
        "location_label": first.get("location_label"),
        "sop_ids": first.get("sop_ids") or [],
        "spare_part_ids": [
            part["part_id"]
            for part in first.get("spare_parts") or []
            if part.get("part_id")
        ],
        "similar_event_ids": [
            event["similar_event_id"]
            for event in first.get("similar_events") or []
            if event.get("similar_event_id")
        ],
        "boundary": _boundary(packet),
    }


def _matches_expected(answer: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        answer["component_id"] == expected["component_id"]
        and answer["factor_refs"] == expected["factor_refs"]
        and answer["location_label"] == expected["location_label"]
        and answer["sop_ids"] == expected["sop_ids"]
        and answer["spare_part_ids"] == expected["spare_part_ids"]
        and answer["similar_event_ids"] == expected["similar_event_ids"]
        and answer["boundary"] == expected["boundary"]
    )


def _matching_ontology_traversal(
    packet: dict[str, Any],
    component_id: Any,
) -> dict[str, Any]:
    for traversal in (packet.get("ontology_context") or {}).get("traversals") or []:
        if traversal.get("component_id") == component_id:
            return traversal
    return {}


def _boundary(packet: dict[str, Any]) -> str:
    if packet["review_draft"]["priority_label"] == "미확정":
        return "data_quality_hold_no_invention"
    if packet["closed_loop_boundary"]["mutation_allowed"] is False:
        return "no_closed_loop_mutation"
    return "unsafe_mutation_boundary"
