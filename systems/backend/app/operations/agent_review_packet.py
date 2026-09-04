"""Read-only agent review packet composition for Operations asset workflows."""

from __future__ import annotations

from typing import Any

from app.operations.context_providers import (
    AgentReviewContext,
    compose_default_agent_review_context,
)
from app.diagnosis.presentation_dictionary import partition_factors


FORBIDDEN_AGENT_ACTIONS = [
    "create_work_order",
    "approve_work_order",
    "start_maintenance_action",
    "complete_maintenance_action",
    "create_maintenance_event",
    "request_replay",
    "auto_approve",
]


def compose_agent_review_packet(
    *,
    project_id: str,
    view_model: dict[str, Any],
    sop_retrieval: dict[str, Any],
    ontology_context: dict[str, Any] | None = None,
    context: AgentReviewContext | None = None,
) -> dict[str, Any]:
    agent_context = context or compose_default_agent_review_context(view_model=view_model)
    retrieval_results = sop_retrieval.get("results") or []
    procedures_by_id = {
        str((item.get("procedure") or {}).get("sop_id") or ""): item
        for item in retrieval_results
    }
    sop_guidance = []
    inspection_targets = []
    source_refs = []
    history_review_items = []
    limitations = [
        "Agent Review Packet is read-only and does not mutate Recommendation, WorkOrder, MaintenanceAction, MaintenanceEvent, or Replay state.",
        "SOP grounding supports inspection and replacement timing review drafts; it is not Product Evidence or a repair instruction.",
    ]

    evidence_ref = str((view_model.get("evidence") or {}).get("evidence_payload_reference") or "")
    if evidence_ref:
        source_refs.append(evidence_ref)
    source_refs.extend(_operation_context_source_refs(agent_context))

    for target in view_model.get("inspection_targets") or []:
        inspection_targets.append(_agent_inspection_target(target))
        if target.get("source_ref"):
            source_refs.append(str(target["source_ref"]))
        if target.get("location_source_ref"):
            source_refs.append(str(target["location_source_ref"]))
        guidance = target.get("inspection_guidance") or {}
        sop_id = str(guidance.get("sop_id") or "")
        if not guidance or not sop_id:
            continue
        retrieval_item = procedures_by_id.get(sop_id) or {}
        procedure = retrieval_item.get("procedure") or {}
        replacement = guidance.get("replacement_review_guidance") or _replacement_guidance_from_prerequisites(
            guidance.get("maintenance_review_prerequisites") or {}
        )
        review_items = [
            _history_review_item_from_question(str(item))
            for item in replacement.get("human_review_questions") or []
        ]
        history_review_items.extend(item for item in review_items if item)
        if guidance.get("source_ref"):
            source_refs.append(str(guidance["source_ref"]))
        if guidance.get("location_source_ref"):
            source_refs.append(str(guidance["location_source_ref"]))
        if guidance.get("disclaimer"):
            limitations.append(str(guidance["disclaimer"]))
        sop_guidance.append(
            {
                "target_id": str(target.get("target_id") or ""),
                "component_id": str(target.get("component_id") or ""),
                "component_label": str(target.get("component_label") or ""),
                "location_label": target.get("location_label"),
                "inspection_method": target.get("inspection_method"),
                "location_source_ref": target.get("location_source_ref"),
                "sop_id": sop_id,
                "source_type": str(guidance.get("source_type") or ""),
                "maturity": str(procedure.get("maturity") or "fixture"),
                "checklist_draft": [str(item) for item in guidance.get("checklist_draft") or []],
                "replacement_review_guidance": _agent_replacement_review_guidance(replacement),
                "sensor_judgment": procedure.get("sensor_judgment"),
                "retrieval_score": retrieval_item.get("retrieval_score", 0),
                "matched_fields": [
                    str(item) for item in retrieval_item.get("matched_fields") or []
                ],
                "disclaimer": str(guidance.get("disclaimer") or ""),
                "source_ref": str(guidance.get("source_ref") or ""),
            }
        )
    if ontology_context:
        source_refs.extend(str(ref) for ref in ontology_context.get("source_refs") or [])

    closed_loop = view_model.get("closed_loop") or {}
    model_expression_context = _model_expression_context(view_model)
    maintenance_history_summary = (
        _merge_maintenance_history_summary(
            agent_context.maintenance_history_summary,
            ontology_context=ontology_context,
        )
        if agent_context.maintenance_history_summary
        else _maintenance_history_summary(
            view_model=view_model,
            closed_loop=closed_loop,
            ontology_context=ontology_context,
        )
    )
    source_refs.extend(model_expression_context.get("source_refs") or [])
    source_refs.extend(maintenance_history_summary.get("source_refs") or [])
    source_refs.extend(_non_operation_context_source_refs(agent_context))
    available_actions = closed_loop.get("available_actions") or []
    evidence_gaps = _packet_evidence_gaps(
        view_model=view_model,
        context=agent_context,
    )
    review_draft = _compose_review_draft(
        asset=view_model.get("asset") or {},
        risk=view_model.get("risk") or {},
        review_priority=view_model.get("review_priority"),
        inspection_targets=inspection_targets,
        sop_guidance=sop_guidance,
        equipment_history=view_model.get("equipment_history") or [],
        maintenance_context=view_model.get("maintenance_context") or {},
        closed_loop=closed_loop,
        ontology_context=ontology_context,
        evidence_gaps=evidence_gaps,
    )
    return {
        "schema_version": "agent-review-packet-v1.0",
        "project_id": project_id,
        "asset_id": str((view_model.get("asset") or {}).get("asset_id") or ""),
        "asset_label": str(
            (view_model.get("asset") or {}).get("display_name")
            or (view_model.get("asset") or {}).get("asset_id")
            or ""
        ),
        "generated_at": str((view_model.get("asset") or {}).get("observed_at") or ""),
        "snapshot_basis": view_model.get("snapshot_basis") or {},
        "domain_sections": _domain_sections(
            has_operation_context=agent_context.operation_context_summary is not None,
            has_sop_guidance=bool(sop_guidance),
            has_ontology_context=bool(
                ontology_context and ontology_context.get("traversals")
            ),
            has_maintenance_history=bool(maintenance_history_summary),
        ),
        "risk_summary": {
            "status_grade": (view_model.get("risk") or {}).get("status_grade"),
            "failure_probability": (view_model.get("risk") or {}).get("current"),
            "prediction_horizon_hours": (view_model.get("risk") or {}).get(
                "prediction_horizon_hours"
            ),
        },
        "review_priority": view_model.get("review_priority"),
        "review_draft": review_draft,
        "model_expression_context": model_expression_context,
        "sop_retrieval": {
            "provider": str(sop_retrieval.get("provider") or ""),
            "query": sop_retrieval.get("query") or {},
            "top_k": int(sop_retrieval.get("top_k") or 0),
            "returned_count": int(sop_retrieval.get("returned_count") or 0),
            "mutation_allowed": False,
        },
        "inspection_targets": inspection_targets,
        "sop_guidance": sop_guidance,
        "operation_context_summary": agent_context.operation_context_summary,
        "ontology_context": _agent_ontology_context(ontology_context),
        "maintenance_history_summary": maintenance_history_summary,
        "history_review_items": list(dict.fromkeys(history_review_items)),
        "evidence_gaps": evidence_gaps,
        "source_refs": list(dict.fromkeys(source_refs)),
        "closed_loop_boundary": {
            "mutation_allowed": False,
            "available_action_ids": [
                str(item.get("action_id")) for item in available_actions if item.get("action_id")
            ],
            "forbidden_actions": FORBIDDEN_AGENT_ACTIONS,
            "note": "This packet may reference available actions for context, but it cannot execute or approve them.",
        },
        "limitations": list(dict.fromkeys(limitations)),
    }


def _operation_context_source_refs(context: AgentReviewContext) -> list[str]:
    source_ref = (context.operation_context_summary or {}).get("source_ref")
    return [str(source_ref)] if source_ref else []


def _non_operation_context_source_refs(context: AgentReviewContext) -> list[str]:
    operation_refs = set(_operation_context_source_refs(context))
    return [
        str(ref)
        for ref in context.source_refs
        if ref and str(ref) not in operation_refs
    ]


def _domain_sections(
    *,
    has_operation_context: bool,
    has_sop_guidance: bool,
    has_ontology_context: bool,
    has_maintenance_history: bool,
) -> list[dict[str, Any]]:
    sections = [
        {
            "section_id": "risk",
            "owner_domain": "diagnosis",
            "source": "Product Result Artifact promoted through AssetDetailViewModel",
            "packet_paths": [
                "risk_summary",
                "review_priority",
                "model_expression_context",
            ],
            "mutation_allowed": False,
            "materialization": "inline_packet_section",
            "notes": [
                "Carries product-facing risk facts; does not expose raw Generator payloads."
            ],
        },
        {
            "section_id": "inspection",
            "owner_domain": "maintenance",
            "source": "AssetDetailViewModel inspection target projection",
            "packet_paths": ["inspection_targets"],
            "mutation_allowed": False,
            "materialization": "inline_packet_section",
            "notes": [
                "Groups model factors into field inspection targets without creating work orders."
            ],
        },
        {
            "section_id": "closed_loop_boundary",
            "owner_domain": "closed_loop",
            "source": "AssetDetailViewModel closed-loop projection",
            "packet_paths": ["closed_loop_boundary"],
            "mutation_allowed": False,
            "materialization": "inline_packet_section",
            "notes": [
                "Documents available action context and explicitly forbids execution authority."
            ],
        },
    ]

    if has_operation_context:
        sections.append(
            {
                "section_id": "operation",
                "owner_domain": "operations",
                "source": "AgentReviewContextProvider operation adapter",
                "packet_paths": ["operation_context_summary"],
                "mutation_allowed": False,
                "materialization": "inline_packet_section",
                "notes": [
                    "Supports role-specific production impact wording without becoming MES truth."
                ],
            }
        )
    else:
        sections.append(
            {
                "section_id": "operation",
                "owner_domain": "operations",
                "source": "future operation adapter",
                "packet_paths": ["operation_context_summary"],
                "mutation_allowed": False,
                "materialization": "future_external_adapter",
                "notes": ["No operation context was available for this packet."],
            }
        )

    if has_maintenance_history:
        sections.append(
            {
                "section_id": "maintenance_history",
                "owner_domain": "closed_loop",
                "source": "AssetDetailViewModel closed-loop and ontology history projection",
                "packet_paths": ["maintenance_history_summary", "history_review_items"],
                "mutation_allowed": False,
                "materialization": "inline_packet_section",
                "notes": [
                    "May summarize existing records but cannot create maintenance events."
                ],
            }
        )

    sections.append(
        {
            "section_id": "sop",
            "owner_domain": "procedure",
            "source": "SOP metadata retrieval adapter",
            "packet_paths": ["sop_retrieval", "sop_guidance"],
            "mutation_allowed": False,
            "materialization": (
                "inline_packet_section"
                if has_sop_guidance
                else "future_external_adapter"
            ),
            "notes": [
                "Structured SOP metadata is used before RAG; missing guidance stays a gap."
            ],
        }
    )
    sections.append(
        {
            "section_id": "ontology",
            "owner_domain": "ontology",
            "source": "Ontology traversal adapter",
            "packet_paths": ["ontology_context"],
            "mutation_allowed": False,
            "materialization": (
                "inline_packet_section"
                if has_ontology_context
                else "future_external_adapter"
            ),
            "notes": [
                "Normalizes component, factor, location, SOP, spare-part, and similar-event relations."
            ],
        }
    )

    return sections


def _merge_maintenance_history_summary(
    summary: dict[str, Any],
    *,
    ontology_context: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(summary)
    similar_events = [
        *[
            item
            for item in merged.get("similar_events") or []
            if isinstance(item, dict)
        ],
        *_similar_events_from_ontology(ontology_context),
    ]
    merged["similar_events"] = list(
        {
            str(item.get("similar_event_id") or ""): item
            for item in similar_events
        }.values()
    )[:5]
    merged["source_refs"] = list(
        dict.fromkeys(
            ref
            for ref in [
                *[str(item) for item in merged.get("source_refs") or []],
                *[
                    str(item.get("source_ref") or "")
                    for item in merged["similar_events"]
                    if isinstance(item, dict)
                ],
            ]
            if ref
        )
    )
    return merged


def _model_expression_context(view_model: dict[str, Any]) -> dict[str, Any]:
    risk = view_model.get("risk") or {}
    evidence = view_model.get("evidence") or {}
    snapshot_basis = view_model.get("snapshot_basis") or {}
    source_ref = str(evidence.get("evidence_payload_reference") or "")
    factors = []
    for feature in view_model.get("features") or []:
        if not isinstance(feature, dict):
            continue
        contribution = feature.get("top_factor") or {}
        if not contribution:
            continue
        current = feature.get("current")
        current_value = current.get("value") if isinstance(current, dict) else current
        source_field_id = str(contribution.get("evidence_field_id") or "")
        factor_source_ref = (
            f"{source_ref}#{source_field_id}"
            if source_ref and source_field_id
            else source_ref
        )
        factors.append(
            {
                "feature": str(feature.get("key") or ""),
                "display_name": str(feature.get("label") or feature.get("key") or ""),
                "value": current_value,
                "unit": str(feature.get("unit") or ""),
                "direction": str(contribution.get("direction") or ""),
                "contribution": contribution.get("contribution"),
                "explanation_method": str(
                    contribution.get("explanation_method") or ""
                ),
                "source_ref": factor_source_ref,
            }
        )
    partitioned = partition_factors(factors, "ko-KR")
    physical_factors = [
        {key: value for key, value in item.items() if key != "presentation_kind"}
        for item in partitioned["physical"]
    ]
    return {
        "source_type": str(evidence.get("source_kind") or "product_result_artifact"),
        "model_version": str(evidence.get("model_version") or snapshot_basis.get("model_version") or ""),
        "dataset_version": str(evidence.get("dataset_version") or snapshot_basis.get("dataset_version") or ""),
        "failure_probability": risk.get("current"),
        "threshold": risk.get("threshold"),
        "confidence_label": str(risk.get("confidence_label") or ""),
        "top_factors": sorted(
            physical_factors,
            key=lambda item: abs(float(item.get("contribution") or 0.0)),
            reverse=True,
        )[:5],
        "source_refs": list(
            dict.fromkeys(
                ref
                for ref in [
                    source_ref,
                    *[str(item.get("source_ref") or "") for item in factors],
                ]
                if ref
            )
        ),
    }


def _maintenance_history_summary(
    *,
    view_model: dict[str, Any],
    closed_loop: dict[str, Any],
    ontology_context: dict[str, Any] | None,
) -> dict[str, Any]:
    equipment_history = view_model.get("equipment_history") or []
    maintenance_context = view_model.get("maintenance_context") or {}
    work_orders = [
        _closed_loop_record(item, source_prefix="closed-loop://work-order")
        for item in closed_loop.get("work_orders") or []
        if isinstance(item, dict)
    ]
    inspection_results = [
        _closed_loop_record(item, source_prefix="closed-loop://inspection-result")
        for item in closed_loop.get("inspection_results") or []
        if isinstance(item, dict)
    ]
    maintenance_actions = [
        _closed_loop_record(item, source_prefix="closed-loop://maintenance-action")
        for item in closed_loop.get("maintenance_actions") or []
        if isinstance(item, dict)
    ]
    maintenance_events = [
        _closed_loop_record(item, source_prefix="closed-loop://maintenance-event")
        for item in closed_loop.get("maintenance_events") or []
        if isinstance(item, dict)
    ]
    activities = [
        _closed_loop_record(item, source_prefix="closed-loop://activity")
        for item in closed_loop.get("activities") or []
        if isinstance(item, dict)
    ]
    similar_events = _similar_events_from_ontology(ontology_context)
    recent_equipment_history = [
        {
            "description": str(item.get("description") or ""),
            "occurred_at": str(item.get("occurred_at") or ""),
            "source_ref": f"equipment-history://{index + 1}",
        }
        for index, item in enumerate(equipment_history[:3])
        if isinstance(item, dict)
    ]
    source_refs = list(
        dict.fromkeys(
            ref
            for record in [
                *work_orders,
                *inspection_results,
                *maintenance_actions,
                *maintenance_events,
                *activities,
                *similar_events,
                *recent_equipment_history,
            ]
            for ref in [str(record.get("source_ref") or "")]
            if ref
        )
    )
    return {
        "provider": "asset_detail_view_model_closed_loop_projection",
        "mutation_allowed": False,
        "last_maintenance_days_ago": maintenance_context.get("last_maintenance_days_ago"),
        "similar_events_30d": maintenance_context.get("similar_events_30d"),
        "open_work_order_exists": maintenance_context.get("open_work_order_exists"),
        "work_orders": work_orders,
        "inspection_results": inspection_results,
        "maintenance_actions": maintenance_actions,
        "maintenance_events": maintenance_events,
        "activities": activities[:5],
        "similar_events": similar_events[:5],
        "recent_equipment_history": recent_equipment_history,
        "source_refs": source_refs,
    }


def _closed_loop_record(item: dict[str, Any], *, source_prefix: str) -> dict[str, Any]:
    record_id = str(
        item.get("work_order_id")
        or item.get("inspection_result_id")
        or item.get("maintenance_action_id")
        or item.get("maintenance_event_id")
        or item.get("activity_id")
        or item.get("id")
        or ""
    )
    return {
        "record_id": record_id,
        "record_type": source_prefix.removeprefix("closed-loop://"),
        "status": str(item.get("status") or item.get("outcome") or ""),
        "activity_type": str(item.get("activity_type") or ""),
        "recorded_at": str(
            item.get("recorded_at")
            or item.get("completed_at")
            or item.get("created_at")
            or item.get("updated_at")
            or ""
        ),
        "summary": str(item.get("label") or item.get("note") or item.get("outcome") or ""),
        "source_ref": f"{source_prefix}/{record_id}" if record_id else source_prefix,
    }


def _similar_events_from_ontology(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    events = []
    for traversal in (context or {}).get("traversals") or []:
        if not isinstance(traversal, dict):
            continue
        for event in traversal.get("similar_events") or []:
            if not isinstance(event, dict):
                continue
            events.append(
                {
                    "similar_event_id": str(event.get("similar_event_id") or ""),
                    "asset_label": str(event.get("asset_label") or ""),
                    "observed_at": str(event.get("observed_at") or ""),
                    "action_taken": str(event.get("action_taken") or ""),
                    "outcome": str(event.get("outcome") or ""),
                    "source_ref": str(event.get("source_ref") or ""),
                }
            )
    return list({event["similar_event_id"]: event for event in events}.values())


def _agent_ontology_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {
            "provider": "none",
            "mutation_allowed": False,
            "traversals": [],
            "source_refs": [],
        }
    return {
        "provider": str(context.get("provider") or ""),
        "mutation_allowed": False,
        "traversals": [
            {
                "component_id": str(item.get("component_id") or ""),
                "component_label": str(item.get("component_label") or ""),
                "factor_refs": [str(ref) for ref in item.get("factor_refs") or []],
                "location_label": item.get("location_label"),
                "location_source_ref": item.get("location_source_ref"),
                "sop_ids": [str(ref) for ref in item.get("sop_ids") or []],
                "spare_parts": [
                    {
                        "part_id": str(part.get("part_id") or ""),
                        "part_label": str(part.get("part_label") or ""),
                        "replacement_scope": str(part.get("replacement_scope") or ""),
                        "availability": str(part.get("availability") or ""),
                        "lead_time_days": part.get("lead_time_days"),
                        "replacement_window_minutes": part.get(
                            "replacement_window_minutes"
                        ),
                        "assumption_level": str(part.get("assumption_level") or ""),
                        "source_ref": str(part.get("source_ref") or ""),
                    }
                    for part in item.get("spare_parts") or []
                    if isinstance(part, dict)
                ],
                "similar_events": [
                    {
                        "similar_event_id": str(event.get("similar_event_id") or ""),
                        "asset_label": str(event.get("asset_label") or ""),
                        "observed_at": str(event.get("observed_at") or ""),
                        "matched_factor_keys": [
                            str(factor)
                            for factor in event.get("matched_factor_keys") or []
                        ],
                        "action_taken": str(event.get("action_taken") or ""),
                        "outcome": str(event.get("outcome") or ""),
                        "post_action_observation_window_hours": event.get(
                            "post_action_observation_window_hours"
                        ),
                        "assumption_level": str(event.get("assumption_level") or ""),
                        "source_ref": str(event.get("source_ref") or ""),
                    }
                    for event in item.get("similar_events") or []
                    if isinstance(event, dict)
                ],
                "source_refs": [str(ref) for ref in item.get("source_refs") or []],
            }
            for item in context.get("traversals") or []
            if isinstance(item, dict)
        ],
        "source_refs": [str(ref) for ref in context.get("source_refs") or []],
    }


def _packet_evidence_gaps(
    *,
    view_model: dict[str, Any],
    context: AgentReviewContext,
) -> list[dict[str, str]]:
    gaps = [
        {
            "field": str(gap.get("field") or ""),
            "reason": str(gap.get("reason") or ""),
            "owner_domain": str(gap.get("owner_domain") or ""),
        }
        for gap in (view_model.get("evidence") or {}).get("gaps") or []
    ]
    gaps.extend(context.evidence_gaps)
    return [
        dict(zip(("field", "reason", "owner_domain"), key))
        for key in dict.fromkeys(
            (
                str(gap.get("field") or ""),
                str(gap.get("reason") or ""),
                str(gap.get("owner_domain") or ""),
            )
            for gap in gaps
        )
    ]


def _agent_inspection_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(target.get("target_id") or ""),
        "component_id": str(target.get("component_id") or ""),
        "component_label": str(target.get("component_label") or ""),
        "association": str(target.get("association") or ""),
        "location_label": target.get("location_label"),
        "inspection_method": target.get("inspection_method"),
        "location_source_ref": target.get("location_source_ref"),
        "basis_refs": [str(value) for value in target.get("basis_refs") or []],
        "source_ref": str(target.get("source_ref") or ""),
        "unavailable_reason": target.get("unavailable_reason"),
    }


def _compose_review_draft(
    *,
    asset: dict[str, Any],
    risk: dict[str, Any],
    review_priority: dict[str, Any] | None,
    inspection_targets: list[dict[str, Any]],
    sop_guidance: list[dict[str, Any]],
    equipment_history: list[dict[str, Any]],
    maintenance_context: dict[str, Any],
    closed_loop: dict[str, Any],
    ontology_context: dict[str, Any] | None,
    evidence_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    asset_id = str(asset.get("asset_id") or "")
    asset_name = str(asset.get("display_name") or asset_id)
    raw_status_grade = risk.get("status_grade")
    status_grade = str(raw_status_grade or "unknown")
    probability = risk.get("current")
    probability_label = f"{float(probability) * 100:.1f}%" if isinstance(probability, (int, float)) else "미제공"
    is_data_quality_hold = raw_status_grade is None or probability is None
    primary_guidance = sop_guidance[0] if sop_guidance else {}
    primary_target = inspection_targets[0] if inspection_targets else {}
    component_label = str(
        primary_guidance.get("component_label")
        or primary_target.get("component_label")
        or "의심 부품"
    )
    location_label = str(primary_guidance.get("location_label") or "")
    checklist = [str(item) for item in primary_guidance.get("checklist_draft") or []][:4]
    if location_label:
        checklist.insert(0, f"현장 확인 위치: {location_label}")
    if evidence_gaps:
        checklist.append("근거 공백 항목을 먼저 확인하고 확정 판단에서 제외합니다.")
    history_summary = _compose_history_summary(
        equipment_history=equipment_history,
        maintenance_context=maintenance_context,
        closed_loop=closed_loop,
        similar_events=_similar_events_from_ontology(ontology_context),
    )
    if is_data_quality_hold:
        priority_level = "미확정"
        recommended_next_step = (
            "근거 공백을 먼저 해소한 뒤 위험도와 검토 우선순위를 다시 산정합니다."
        )
        summary = (
            f"{asset_id}는 데이터 품질 보류 상태라 위험 등급과 예측 위험도를 확정하지 않습니다. "
            "근거 공백이 있어 확정 판단보다 데이터 보강과 이력 조회가 우선입니다."
        )
    else:
        priority_level = str((review_priority or {}).get("level") or "medium")
        recommended_next_step = (
            "조회된 이력과 SOP 근거를 대조한 뒤, 필요한 경우 관리자 승인 절차로 이관합니다."
        )
        grounding_label = "SOP 근거, 위치 reference, 관측값"
        if not sop_guidance:
            grounding_label = "현장 위치 reference, 관측값, 조회된 이력"
        summary = (
            f"{asset_id}는 현재 {status_grade} 상태이며 예측 위험도는 {probability_label}입니다. "
            f"{component_label} 중심으로 {grounding_label}을 대조해야 합니다."
        )
    return {
        "title": f"{asset_name} 담당자 검토 초안",
        "summary": summary,
        "priority_label": priority_level,
        "recommended_next_step": recommended_next_step,
        "checklist": checklist,
        "history_summary": history_summary,
        "evidence_gap_count": len(evidence_gaps),
        "boundary_note": "이 초안은 담당자 검토를 돕기 위한 read-only 문서이며 작업요청 생성, 정비 승인, 자동 승인을 수행하지 않습니다.",
    }


def _agent_replacement_review_guidance(guidance: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_label": str(guidance.get("review_label") or ""),
        "review_triggers": [str(item) for item in guidance.get("review_triggers") or []],
        "required_measurements": [
            str(item) for item in guidance.get("required_measurements") or []
        ],
        "operator_review_items": [
            item
            for item in (
                _history_review_item_from_question(str(value))
                for value in guidance.get("human_review_questions") or []
            )
            if item
        ],
        "decision_boundary": str(guidance.get("decision_boundary") or ""),
    }


def _replacement_guidance_from_prerequisites(guidance: dict[str, Any]) -> dict[str, Any]:
    label = str(guidance.get("label") or "교체 시기 검토 기준")
    if label == "정비 판단 전 확인사항":
        label = "교체 시기 검토 기준"
    boundary = str(guidance.get("decision_boundary") or "")
    if boundary:
        boundary = "이 기준은 교체 시기 검토 초안이며, 교체 필요 확정·작업요청 생성·정비 승인·자동 승인을 수행하지 않습니다."
    return {
        "review_label": label,
        "review_triggers": [
            str(item) for item in guidance.get("review_conditions") or []
        ],
        "required_measurements": [
            str(item) for item in guidance.get("required_measurements") or []
        ],
        "human_review_questions": [
            str(item) for item in guidance.get("human_review_questions") or []
        ],
        "decision_boundary": boundary,
    }


def _history_review_item_from_question(value: str) -> str:
    text = value.strip().rstrip("?")
    if not text:
        return ""
    if "설비 정지 가능 시간" in text and "부품 가용성" in text:
        return "교체 전 생산 정지 가능 시간과 부품 가용성 확인 상태 조회"
    if "추가 조치 판단" in text and ("반복적" in text or "악화 중" in text):
        return "점검 결과가 교체 요청으로 이어질 만큼 반복적이거나 악화 중 여부 조회"
    for suffix in ("확인됐습니까", "확인되었습니까"):
        if text.endswith(suffix):
            return f"{_without_subject_particle(text.removesuffix(suffix))} 확인 상태 조회"
    if text.endswith("있습니까"):
        return f"{_without_subject_particle(text.removesuffix('있습니까'))} 유무 조회"
    if text.endswith("입니까"):
        return f"{_without_subject_particle(text.removesuffix('입니까'))} 여부 조회"
    return f"이력 조회 필요: {text}"


def _without_subject_particle(value: str) -> str:
    text = value.strip()
    return text[:-1] if text.endswith(("이", "가", "은", "는")) else text


def _compose_history_summary(
    *,
    equipment_history: list[dict[str, Any]],
    maintenance_context: dict[str, Any],
    closed_loop: dict[str, Any],
    similar_events: list[dict[str, Any]],
) -> list[str]:
    summaries = []
    if equipment_history:
        latest = equipment_history[0]
        days_ago = maintenance_context.get("last_maintenance_days_ago")
        days_label = f" · {days_ago}일 전" if isinstance(days_ago, int) and not isinstance(days_ago, bool) else ""
        summaries.append(
            f"최근 정비 이력: {latest.get('description', '정비 이력')} · {latest.get('occurred_at', '일시 미제공')}{days_label}"
        )
    else:
        summaries.append("최근 정비 이력: 전용 Activity/Maintenance 이력 조회 결과 없음")

    work_orders = closed_loop.get("work_orders") or []
    open_work_orders = [
        item for item in work_orders if str(item.get("status") or "") not in {"completed", "cancelled"}
    ]
    if open_work_orders:
        work_order = open_work_orders[0]
        summaries.append(
            f"열린 작업요청: {work_order.get('work_order_id', 'ID 미제공')} · {work_order.get('status', '상태 미제공')}"
        )
    elif maintenance_context.get("open_work_order_exists") is False:
        summaries.append("열린 작업요청: 없음")
    else:
        summaries.append("열린 작업요청: Closed-loop 이력 연결 전이라 확정하지 않음")

    similar_count = maintenance_context.get("similar_events_30d")
    if isinstance(similar_count, int) and not isinstance(similar_count, bool):
        summaries.append(f"최근 30일 유사 이벤트: {similar_count}건")
    elif similar_events:
        latest_similar = similar_events[0]
        observed_at = str(latest_similar.get("observed_at") or "")
        if observed_at:
            summaries.append(f"최근 30일 유사 이벤트: {observed_at} · 1건")
        else:
            summaries.append("최근 30일 유사 이벤트: 1건")
    else:
        summaries.append("최근 30일 유사 이벤트: 전용 이력 계약 미연결")
    return summaries
