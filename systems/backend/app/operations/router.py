"""Manufacturing-compatible Event routes shared by Project showcase domain packs."""

from __future__ import annotations

import json
import uuid

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.common.rate_limit import RateLimitRule, RateLimiter
from app.common.runtime_settings import project_root
from app.equipment.equipment_router import register_equipment_routes

from .contracts import AgentQueryRequest, DecisionRequest, FollowUpRequest, LayoutRequest, NoteRequest, ReportRequest
from .agent_context_tool_pipeline import run_read_only_tool_pipeline
from .agent_review_summary import compose_deterministic_agent_review_summary, validate_agent_review_summary_contract
from .asset_detail_view_model import AssetDetailViewModelService, compose_asset_detail_view_model
from app.dependencies import (
    MANUFACTURING_WORKSPACE,
    get_identity_service,
    get_ontology_service,
    get_operational_decision_support_service,
    get_predictive_maintenance_runtime_service,
    get_rate_limiter,
    get_runtime_asset_detail_service,
    get_service,
    rate_limit_subject,
    require_csrf,
    require_manufacturing_scope,
    require_permission,
)
from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService
from app.identity import AuthError, IdentityService, Principal
from app.ontology.ontology_domain import ActionInvocation
from app.ontology.projection import inspection_object_id, risk_event_object_id
from app.ontology.ontology_service import OntologyService
from .service import EventNotFound, ManufacturingPredictiveMaintenanceService
from .operational_context_contract import OperationalRequestIdentity
from .operational_decision_brief import DecisionBriefRole
from .operational_decision_support_port import (
    DecisionSupportMaterializationInProgress,
    OperationalDecisionSupportService,
)
from .sop_retrieval import retrieve_inspection_sops

router = APIRouter(prefix="/api", tags=["manufacturing-domain-pack"])
AGENT_REVIEW_SUMMARY_MATERIALIZE_RATE = RateLimitRule(limit=12, window_seconds=60)
DECISION_SUPPORT_MATERIALIZE_RATE = RateLimitRule(limit=12, window_seconds=60)
register_equipment_routes(
    router,
    service_dependency=get_service,
    authorization_dependency=require_manufacturing_scope,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _runtime_line(asset_id: str) -> str:
    parts = asset_id.split("-")
    return "-".join(parts[1:3]) if len(parts) >= 4 else asset_id


def _runtime_operation_context(result: Any, event_id: str) -> dict[str, Any]:
    """Materialize planning and capacity context for runtime Product Results."""

    observed = result.observed_at.astimezone(timezone(timedelta(hours=9)))
    status = str(result.status_grade)
    downtime_by_status = {
        "critical": 240,
        "warning": 120,
        "attention": 60,
        "normal": 0,
    }
    downtime = downtime_by_status.get(status, 45)
    asset_units_per_hour = 12.69
    lost_units = round(downtime / 60 * asset_units_per_hour) if downtime else 0
    if downtime >= 180:
        production_impact = "high"
        screen_priority = "plan_at_risk"
    elif downtime >= 90:
        production_impact = "medium"
        screen_priority = "shift_inspection"
    elif downtime > 0:
        production_impact = "low"
        screen_priority = "monitor"
    else:
        production_impact = "none"
        screen_priority = "none"
    variants = ("L", "M", "H")
    product_variant = variants[sum(ord(char) for char in result.asset_id) % len(variants)]
    snapshot_id = f"OPS-DEMO-{observed.strftime('%Y%m%dT%H%M%S')}-{result.asset_id}"
    plan_id = f"PLAN-{observed.strftime('%Y-%m-%d')}-DEMO"
    line = _runtime_line(result.asset_id)
    return {
        "load_level": "high" if production_impact in {"high", "medium"} else "normal",
        "runtime_hours_7d": None,
        "production_impact": production_impact,
        "context_id": f"runtime-planning:{observed.date().isoformat()}",
        "source_type": "capacity_model",
        "temporal_scope": {
            "snapshot_id": snapshot_id,
            "timezone": "Asia/Seoul",
            "valid_from": observed.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "valid_to": (observed.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
            "generated_at": observed.isoformat(),
        },
        "production_plan": {
            "plan_id": plan_id,
            "plan_date": observed.date().isoformat(),
            "planned_units": 16200,
            "product_mix": [
                {"variant": "L", "share": 0.5, "planned_units": 8100},
                {"variant": "M", "share": 0.3, "planned_units": 4860},
                {"variant": "H", "share": 0.2, "planned_units": 3240},
            ],
        },
        "capacity_model": {
            "active_asset_count": 80,
            "planned_operating_hours": 16,
            "oee": 0.846,
            "standard_cycle_minutes_per_unit": 4.0,
            "asset_units_per_hour": asset_units_per_hour,
            "daily_capacity_units": 16200,
            "basis": "운영 capacity model · 80 CNC, 16h/day, OEE 0.846, cycle 4min",
        },
        "event_impact": {
            "event_id": event_id,
            "equipment_id": result.asset_id,
            "line": line,
            "product_variant": product_variant,
            "screen_priority": screen_priority,
            "impact_status": "not_applicable" if downtime == 0 else "estimated",
            "estimated_lost_units": lost_units,
            "basis": {
                "estimated_downtime_minutes": downtime,
                "asset_units_per_hour": asset_units_per_hour,
                "formula": "estimated_downtime_minutes / 60 * asset_units_per_hour",
            },
        },
        "limitations": [
            "예상 손실 수량과 downtime은 현재 운영 계획과 capacity model을 기준으로 계산된 추정치입니다.",
            "확정 재무 손실은 별도 결산 및 원가 정산 데이터로 검증해야 합니다.",
        ],
    }


def _runtime_sop_context(result: Any, operation_context: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    procedures = []
    for path in sorted((project_root() / "data" / "fixtures" / "inspection_sop").glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            procedures.append(json.load(handle))
    artifact = {
        "asset_type": result.asset_type,
        "predicted_failure_type": result.predicted_failure_type,
        "status_grade": result.status_grade,
        "top_factors": [{"feature": factor.feature} for factor in result.top_factors],
        "evidence_payload": {"component_hypotheses": []},
    }
    fixture = {
        "equipment": {
            "asset_type": result.asset_type,
            "criticality": "high" if result.status_grade in {"critical", "warning"} else "medium",
        },
        "expected": {"predicted_failure_type": result.predicted_failure_type},
        "operation_context": operation_context,
    }
    retrieval = retrieve_inspection_sops(
        fixture=fixture,
        artifact=artifact,
        procedures=procedures,
        top_k=3,
    )
    guidance = []
    for item in retrieval.get("results") or []:
        procedure = item.get("procedure") or {}
        procedure_guidance = procedure.get("guidance") or {}
        guidance.append({
            "source_type": procedure.get("source_kind"),
            "sop_id": procedure.get("sop_id"),
            "title": procedure.get("title"),
            "version": procedure.get("version"),
            "component_ids": [str(value) for value in procedure.get("component_ids") or []],
            "reference_location_label": procedure_guidance.get("reference_location_label"),
            "suggested_check_method": procedure_guidance.get("suggested_check_method"),
            "checklist_draft": procedure_guidance.get("checklist_draft") or [],
            "maintenance_review_prerequisites": procedure_guidance.get("maintenance_review_prerequisites") or {},
            "safety_level": procedure.get("safety_level"),
            "requires_human_approval": procedure.get("requires_human_approval", True),
            "source_ref": item.get("source_ref"),
            "retrieval_score": item.get("retrieval_score"),
            "matched_fields": item.get("matched_fields") or [],
            "disclaimer": procedure_guidance.get("disclaimer"),
        })
    return retrieval, guidance


def _runtime_inspection_targets(sop_guidance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose retrieved SOP components as read-only inspection targets."""

    targets: list[dict[str, Any]] = []
    for guidance in sop_guidance:
        source_ref = str(guidance.get("source_ref") or guidance.get("sop_id") or "")
        component_ids = [str(value) for value in guidance.get("component_ids") or [] if value]
        for component_id in component_ids:
            targets.append({
                "target_id": f"runtime-sop:{component_id}",
                "component_id": component_id,
                "component_label": component_id.replace("_", " "),
                "association": "sop_retrieved_inspection_candidate",
                "location_label": guidance.get("reference_location_label"),
                "inspection_method": guidance.get("suggested_check_method"),
                "location_source_ref": source_ref or None,
                "basis_refs": [source_ref] if source_ref else [],
                "source_ref": source_ref or f"runtime-sop:{component_id}",
                "unavailable_reason": None,
            })
    return targets


def _packet_title(packet: dict[str, Any]) -> str:
    identity = packet.get("asset_identity") or {}
    return str(
        identity.get("asset_name")
        or identity.get("asset_id")
        or packet.get("asset_label")
        or packet.get("asset_id")
        or "selected asset"
    )


def _packet_asset_id(packet: dict[str, Any]) -> str | None:
    identity = packet.get("asset_identity") or {}
    value = identity.get("asset_id") or packet.get("asset_id")
    return str(value) if value else None


def _packet_dataset_version(packet: dict[str, Any]) -> str | None:
    basis = packet.get("snapshot_basis") or {}
    value = packet.get("dataset_version_id") or basis.get("dataset_version_id") or basis.get("dataset_version")
    return str(value) if value else None


def _packet_evidence(
    packet: dict[str, Any],
    *,
    service: ManufacturingPredictiveMaintenanceService,
    project_id: str,
    workspace_id: str,
    question: str = "",
    roles: list[str] | None = None,
    top_k: int,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    model_context = packet.get("model_expression_context") or {}
    for index, factor in enumerate((model_context.get("top_factors") or [])[:top_k], start=1):
        if not isinstance(factor, dict):
            continue
        feature = str(factor.get("display_name") or factor.get("feature") or f"factor {index}")
        raw_value = factor.get("value")
        unit = factor.get("unit")
        value = f"{raw_value}{(' ' + str(unit)) if unit else ''}" if raw_value is not None else "value unavailable"
        evidence.append({
            "evidence_id": f"packet-factor-{index}",
            "store": "postgresql",
            "reference": str(factor.get("feature") or feature),
            "project_id": project_id,
            "workspace_id": workspace_id,
            "dataset_version_id": _packet_dataset_version(packet),
            "object_id": _packet_asset_id(packet),
            "title": feature,
            "content": f"{feature}: {value}",
            "score": _coerce_float(factor.get("contribution") or factor.get("importance")),
            "metadata": {key: value for key, value in factor.items() if key not in {"display_name", "feature", "value", "unit"}},
        })

    sop_items = []
    sop_retrieval = packet.get("sop_retrieval") or {}
    for key in ("items", "results", "documents"):
        items = sop_retrieval.get(key)
        if isinstance(items, list):
            sop_items = items
            break
    if not sop_items and isinstance(packet.get("sop_guidance"), list):
        sop_items = packet.get("sop_guidance") or []
    for index, item in enumerate(sop_items[: max(0, top_k - len(evidence))], start=1):
        if not isinstance(item, dict):
            continue
        procedure = item.get("procedure") if isinstance(item.get("procedure"), dict) else {}
        guidance = procedure.get("guidance") if isinstance(procedure.get("guidance"), dict) else {}
        title = str(
            item.get("title")
            or procedure.get("title")
            or item.get("component")
            or f"SOP guidance {index}"
        )
        content = str(
            item.get("summary")
            or item.get("content")
            or item.get("guidance")
            or guidance.get("suggested_check_method")
            or title
        )
        evidence.append({
            "evidence_id": f"packet-sop-{index}",
            "store": "project3_rag",
            "reference": str(
                item.get("source_ref")
                or item.get("source")
                or procedure.get("source_uri")
                or item.get("id")
                or title
            ),
            "project_id": project_id,
            "workspace_id": workspace_id,
            "dataset_version_id": _packet_dataset_version(packet),
            "object_id": _packet_asset_id(packet),
            "title": title,
            "content": content,
            "score": _coerce_float(item.get("score") or item.get("retrieval_score")),
            "metadata": item,
        })
    asset_id = _packet_asset_id(packet)
    remaining = max(0, top_k - len(evidence))
    if remaining:
        for index, item in enumerate(
            service.company_context_documents(
                question,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=asset_id,
                roles=roles,
                top_k=remaining,
            ),
            start=1,
        ):
            evidence.append({
                "evidence_id": f"company-context-{index}",
                "store": "company_context",
                "reference": str(item.get("source_ref") or item.get("id") or f"company-context-{index}"),
                "project_id": project_id,
                "workspace_id": workspace_id,
                "dataset_version_id": _packet_dataset_version(packet),
                "object_id": asset_id,
                "title": str(item.get("title") or "Company context"),
                "content": str(item.get("content") or item.get("title") or ""),
                "score": _coerce_float(item.get("retrieval_score")),
                "metadata": {
                    "document_type": item.get("document_type"),
                    "related_asset_ids": item.get("related_asset_ids") or [],
                    "context_kind": item.get("context_kind"),
                    "source_sha256": item.get("source_sha256"),
                    "source_updated_at": item.get("source_updated_at"),
                },
            })
    return evidence[:top_k]


def _summary_text(summary: dict[str, Any] | None, audience: str | None = None) -> str | None:
    if not isinstance(summary, dict):
        return None
    if audience == "executive" and summary.get("summary"):
        return str(summary["summary"])
    role_summaries = summary.get("role_summaries") or []
    if isinstance(role_summaries, list):
        target_role = (
            "process_manager"
            if audience == "operations"
            else "field_operator"
            if audience in {"engineering", "maintenance"}
            else None
        )
        if target_role:
            for item in role_summaries:
                if (
                    isinstance(item, dict)
                    and item.get("role") == target_role
                    and item.get("quote")
                ):
                    return str(item["quote"])
        if summary.get("summary"):
            return str(summary["summary"])
        for item in role_summaries:
            if isinstance(item, dict) and item.get("quote"):
                return str(item["quote"])
    if summary.get("summary"):
        return str(summary["summary"])
    return None


def _answer_from_packet(
    question: str,
    packet: dict[str, Any],
    evidence: list[dict[str, Any]],
    summary: dict[str, Any] | None,
    audience: str | None = None,
) -> str:
    title = _packet_title(packet)
    risk_summary = packet.get("risk_summary") or {}
    probability = risk_summary.get("failure_probability") or risk_summary.get("probability")
    status = risk_summary.get("status_grade") or risk_summary.get("status")
    risk = f"{round(float(probability) * 100)}%" if isinstance(probability, (int, float)) else "위험도 미제공"
    reasons = (packet.get("review_priority") or {}).get("reasons") or []
    reason_text = " · ".join(str(item) for item in reasons[:4] if item)
    summary_text = _summary_text(summary, audience)
    evidence_text = " · ".join(item["content"] for item in evidence[:4])
    lower = question.lower()
    if summary_text:
        if audience == "executive":
            operation_context = packet.get("operation_context_summary") or {}
            downtime = operation_context.get("estimated_downtime_minutes")
            lost_units = operation_context.get("estimated_lost_units")
            production_impact = operation_context.get("production_impact")
            impact_parts = [
                f"생산 영향 {production_impact}" if production_impact else None,
                f"예상 정지 {int(downtime)}분" if isinstance(downtime, (int, float)) else None,
                f"계획 영향 약 {int(lost_units)}개" if isinstance(lost_units, (int, float)) else None,
            ]
            impact_text = " · ".join(item for item in impact_parts if item)
            return (
                f"{title}: {summary_text}"
                f"{f' 경영 영향: {impact_text}.' if impact_text else ''} "
                f"근거: {evidence_text or reason_text or '근거 미제공'}"
            )
        return f"{title}: {summary_text} 연결 근거: {evidence_text or reason_text or '근거 미제공'}"
    if any(token in lower for token in ("우선", "priority", "prioritized", "why")):
        return f"{title}는 현재 {status or '상태 미제공'} / {risk}로 검토 우선순위에 올라 있습니다. 핵심 근거는 {reason_text or evidence_text or '현재 연결된 정본 근거 없음'}입니다. 이는 고장 확정이 아니라 운영 검토 우선순위입니다."
    if any(token in lower for token in ("근거", "evidence", "factor", "요인")):
        return f"{title}의 현재 연결 근거는 {evidence_text or reason_text or '제공되지 않았습니다'}입니다."
    return f"{title}에 대한 답변입니다. 현재 상태는 {status or '미제공'}, 위험도는 {risk}이며, 연결 근거는 {evidence_text or reason_text or '제공되지 않았습니다'}입니다."


def _runtime_event_id(result: Any) -> str:
    return str(getattr(result, "artifact_id", None) or result.provenance.prediction_id)


def _runtime_factor_source_ref(event_id: str, feature: str, rank: int) -> str:
    safe_feature = feature or f"factor-{rank}"
    return f"result-artifact:{event_id}#factor:{safe_feature}"


_RUNTIME_HISTORY_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}


def _runtime_feature_and_risk_history(
    *,
    runtime_service: PredictiveMaintenanceRuntimeService,
    principal: Principal,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str,
    asset_id: str,
    observed_at: datetime,
    history_window: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Read bounded runtime history through the Diagnosis service contracts."""

    hours = _RUNTIME_HISTORY_HOURS.get(history_window)
    if hours is None:
        raise ValueError(f"unsupported runtime history window: {history_window}")
    start = observed_at - timedelta(hours=hours)
    grain = "1h" if history_window == "30d" else "10m"
    observation_response = runtime_service.observations(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        start=start,
        end=observed_at,
        asset_id=asset_id,
        site_id=None,
        cell_id=None,
        asset_type=None,
        grain=grain,
        derived_measures=set(),
        limit=5000,
    )
    feature_series: dict[str, dict[str, Any]] = {}
    for observation in observation_response.observations:
        values = {**observation.measurements, **observation.derived_measures}
        for feature, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            series = feature_series.setdefault(
                str(feature),
                {
                    "source_ref": f"runtime-observation:{dataset_version_id}:{asset_id}:{feature}",
                    "points": [],
                },
            )
            series["points"].append(
                {
                    "observed_at": observation.observed_at.isoformat(),
                    "value": float(value),
                    "quality_status": "good",
                }
            )

    timeline_response = runtime_service.timeline(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        asset_id=asset_id,
        start=start,
        end=observed_at,
        offset=0,
        limit=5000,
    )
    risk_history = [
        {
            "observed_at": str(item["observed_at"]),
            "failure_probability": item["failure_probability"],
            "status_grade": item["status"],
            "prediction_id": item["prediction_id"],
            "source_kind": item["source_type"],
            "source_ref": f"result-artifact:{item['prediction_id']}",
        }
        for item in timeline_response.get("items", [])
    ]
    return feature_series, risk_history


def _runtime_agent_review_packet(
    *,
    asset_id: str,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None,
    selected_event_id: str | None = None,
    principal: Principal,
    runtime_service: PredictiveMaintenanceRuntimeService,
) -> dict[str, Any]:
    page = runtime_service.latest_results(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        asset_id=asset_id,
        limit=1,
    )
    if not page.items:
        raise EventNotFound(asset_id)

    result = page.items[0]
    event_id = _runtime_event_id(result)
    if selected_event_id and event_id != selected_event_id:
        raise EventNotFound(selected_event_id)
    observed_at = result.observed_at.isoformat()
    model_version = result.provenance.model_version
    dataset_id = page.context.dataset_id
    active_dataset_version = page.context.dataset_version_id
    source_refs = [
        f"dataset-version:{active_dataset_version}",
        f"result-artifact:{event_id}",
        f"prediction-result:{result.provenance.prediction_result_id}",
    ]
    factors = [
        {
            "rank": factor.rank,
            "feature": factor.feature,
            "display_name": factor.feature.replace("_", " "),
            "value": factor.feature_value,
            "unit": "model unit",
            "contribution": factor.signed_contribution,
            "direction": factor.direction,
            "explanation_method": factor.explanation_method,
            "source_ref": _runtime_factor_source_ref(event_id, factor.feature, factor.rank),
        }
        for factor in result.top_factors
    ]
    source_refs.extend(item["source_ref"] for item in factors)
    operation_context = _runtime_operation_context(result, event_id)
    sop_retrieval, sop_guidance = _runtime_sop_context(result, operation_context)
    inspection_targets = _runtime_inspection_targets(sop_guidance)
    source_refs.extend(
        str(item.get("source_ref"))
        for item in sop_guidance
        if item.get("source_ref")
    )

    recommendation = result.recommended_action.action if result.recommended_action else "Review governed prediction"
    risk_percent = round(result.failure_probability * 100)
    priority_level = (
        "immediate" if result.status_grade == "critical"
        else "high" if result.status_grade == "warning"
        else "medium" if result.status_grade == "attention"
        else "low"
    )
    factor_reason = " · ".join(
        f"{item['display_name']} {item['value']} {item['unit']}" for item in factors[:3]
    )
    reasons = [
        f"상태 {result.status_grade}",
        f"고장 위험 {risk_percent}%",
        f"권고 판단 {recommendation}",
    ]
    if factor_reason:
        reasons.append(f"상위 모델 근거 {factor_reason}")

    return {
        "schema_version": "agent-review-packet-v1.0",
        "project_id": project_id,
        "asset_id": result.asset_id,
        "asset_label": f"{result.asset_type.upper()} · {result.asset_id}",
        "generated_at": observed_at,
        "snapshot_basis": {
            "event_id": event_id,
            "dataset_id": dataset_id,
            "dataset_version_id": active_dataset_version,
            "dataset_version": active_dataset_version,
            "model_version": model_version,
            "observed_at": observed_at,
            "source": "predictive-maintenance-runtime",
        },
        "domain_sections": [
            {
                "section_id": "runtime-risk",
                "owner_domain": "diagnosis",
                "source": "PostgreSQL Product Result runtime",
                "packet_paths": ["risk_summary", "review_priority", "model_expression_context"],
                "mutation_allowed": False,
                "materialization": "runtime_packet_section",
                "notes": ["Derived from the currently selected Team DB result artifact."],
            },
            {
                "section_id": "runtime-operations-context",
                "owner_domain": "operations",
                "source": "Synthetic planning context adapter",
                "packet_paths": ["operation_context_summary"],
                "mutation_allowed": False,
                "materialization": "runtime_packet_section",
                "notes": ["Presentation planning assumptions; not MES/ERP/APS actuals."],
            },
            {
                "section_id": "runtime-sop",
                "owner_domain": "maintenance",
                "source": "Local SOP metadata retrieval",
                "packet_paths": ["sop_retrieval", "sop_guidance"],
                "mutation_allowed": False,
                "materialization": "runtime_packet_section",
                "notes": ["Read-only guidance with human approval boundary."],
            },
        ],
        "risk_summary": {
            "status_grade": result.status_grade,
            "failure_probability": result.failure_probability,
            "prediction_horizon_hours": result.prediction_horizon_hours,
        },
        "review_priority": {
            "level": priority_level,
            "reasons": reasons,
            "source_fields": [item["source_ref"] for item in factors] or source_refs,
        },
        "review_draft": {
            "title": f"{result.asset_id} 운영 위험 검토",
            "summary": (
                f"Team DB의 최신 Product Result는 {result.asset_id}의 {result.prediction_horizon_hours}시간 이내 "
                f"고장 위험을 {risk_percent}%로 산출했습니다. 권고 판단은 {recommendation}이며, "
                "읽기 전용 검토 문맥으로만 사용됩니다."
            ),
            "priority_label": priority_level,
            "recommended_next_step": recommendation,
            "checklist": [
                "상위 모델 근거와 센서 구간을 확인합니다.",
                "권고 판단을 실행 전 사람 승인 경계에서 검토합니다.",
                "정비/작업 상태는 별도 Closed-loop Action에서 확인합니다.",
            ],
            "history_summary": [
                f"{observed_at} 관측 기준 Product Result",
                f"dataset {active_dataset_version} · model {model_version}",
            ],
            "evidence_gap_count": 0 if factors else 1,
            "boundary_note": "읽기 전용 Agent Review 문맥이며 workflow 상태를 변경하지 않습니다.",
        },
        "model_expression_context": {
            "source_type": result.source_contract,
            "model_version": model_version,
            "dataset_version": active_dataset_version,
            "failure_probability": result.failure_probability,
            "threshold": None,
            "confidence_label": f"{result.confidence * 100:.1f}% calibrated",
            "top_factors": factors,
            "source_refs": source_refs,
        },
        "sop_retrieval": sop_retrieval,
        "inspection_targets": inspection_targets,
        "sop_guidance": sop_guidance,
        "operation_context_summary": {
            "production_impact": operation_context["production_impact"],
            "estimated_downtime_minutes": operation_context["event_impact"]["basis"]["estimated_downtime_minutes"],
            "estimated_lost_units": operation_context["event_impact"]["estimated_lost_units"],
            "product_variant": operation_context["event_impact"]["product_variant"],
            "line": operation_context["event_impact"]["line"],
            "planned_units": operation_context["production_plan"]["planned_units"],
            "capacity_units": operation_context["capacity_model"]["daily_capacity_units"],
            "basis": operation_context["capacity_model"]["basis"],
            "limitations": operation_context["limitations"],
            "source_ref": f"operation-context:{operation_context['temporal_scope']['snapshot_id']}",
        },
        "ontology_context": {
            "provider": "runtime-result-context",
            "mutation_allowed": False,
            "traversals": [],
            "source_refs": [],
        },
        "maintenance_history_summary": {
            "provider": "runtime-result-context",
            "mutation_allowed": False,
            "open_work_order_exists": None,
            "similar_events_30d": None,
            "work_orders": [],
            "inspection_results": [],
            "maintenance_actions": [],
            "maintenance_events": [],
            "activities": [],
            "equipment_history": [],
            "recent_equipment_history": [],
            "similar_events": [],
            "source_refs": [],
        },
        "history_review_items": [],
        "evidence_gaps": [] if factors else [{
            "field": "top_factors",
            "reason": "Runtime result did not expose ranked factor context.",
            "owner_domain": "diagnosis",
        }],
        "source_refs": list(dict.fromkeys(source_refs)),
        "closed_loop_boundary": {
            "mutation_allowed": False,
            "available_action_ids": [],
            "forbidden_actions": [
                "create_work_order",
                "approve_work_order",
                "start_maintenance_action",
                "complete_maintenance_action",
                "create_maintenance_event",
                "request_replay",
                "auto_approve",
            ],
            "note": "Runtime Agent Review context is read-only and cannot execute or approve actions.",
        },
        "limitations": [
            "This packet is derived from Team DB runtime Product Result context and connected operational records.",
            "Production planning impact is an estimate derived from the current capacity model and must be validated against financial settlement data before accounting use.",
            "The assistant may explain priority and evidence but cannot approve, execute, or mutate workflow state.",
        ],
    }


def _runtime_asset_detail_view_model(
    *,
    asset_id: str,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None,
    selected_event_id: str | None = None,
    history_window: str,
    principal: Principal,
    runtime_service: PredictiveMaintenanceRuntimeService,
) -> dict[str, Any]:
    page = runtime_service.latest_results(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        asset_id=asset_id,
        limit=1,
    )
    if not page.items:
        raise EventNotFound(asset_id)
    result = page.items[0]
    event_id = _runtime_event_id(result)
    if selected_event_id and event_id != selected_event_id:
        raise EventNotFound(selected_event_id)
    observed_at = result.observed_at.isoformat()
    artifact = result.producer_artifact
    if artifact is None:
        sensors = {
            factor.feature: {
                "display_name": factor.feature.replace("_", " "),
                "current": factor.feature_value,
                "unit": "model unit",
                "basis": {},
            }
            for factor in result.top_factors
        }
        artifact = {
            "artifact_id": event_id,
            "asset_id": result.asset_id,
            "asset_type": result.asset_type,
            "observed_at": observed_at,
            "prediction_horizon_hours": result.prediction_horizon_hours,
            "failure_probability": result.failure_probability,
            "predicted_failure_type": result.predicted_failure_type,
            "status_grade": result.status_grade,
            "confidence": result.confidence,
            "top_factors": [
                {
                    "rank": factor.rank,
                    "feature": factor.feature,
                    "feature_value": factor.feature_value,
                    "signed_contribution": factor.signed_contribution,
                    "direction": factor.direction,
                    "explanation_method": factor.explanation_method,
                }
                for factor in result.top_factors
            ],
            "ranked_factor_evidence": [
                {
                    "evidence_field_id": f"factor:{factor.feature}",
                    "feature": factor.feature,
                    "display_name": factor.feature.replace("_", " "),
                    "value": factor.feature_value,
                    "unit": "model unit",
                }
                for factor in result.top_factors
            ],
            "evidence_payload": {
                "sensor_evidence": {"sensors": sensors},
                "evidence_gaps": [],
            },
            "provenance": {
                "dataset_id": page.context.dataset_id,
                "dataset_version": page.context.dataset_version_id,
                "model_version": result.provenance.model_version,
                "result_schema": result.provenance.schema_version,
                "prediction_task": result.provenance.prediction_task,
                "prediction_id": result.provenance.prediction_id,
                "prediction_result_id": result.provenance.prediction_result_id,
                "source_type": "product_runtime_inference",
                "artifact_id": event_id,
            },
        }
    criticality = "high" if result.status_grade in {"critical", "warning"} else "medium" if result.status_grade == "attention" else "low"
    operation_context = _runtime_operation_context(result, event_id)
    _, sop_guidance = _runtime_sop_context(result, operation_context)
    inspection_guidance: dict[str, dict[str, Any]] = {}
    if sop_guidance:
        artifact = dict(artifact)
        evidence_payload = dict(artifact.get("evidence_payload") or {})
        component_hypotheses = list(evidence_payload.get("component_hypotheses") or [])
        if not component_hypotheses:
            for guidance in sop_guidance:
                component_ids = guidance.get("component_ids") or []
                if not component_ids:
                    continue
                component_id = str(component_ids[0])
                component_hypotheses.append({
                    "component_id": component_id,
                    "component_label": component_id.replace("_", " "),
                    "association": "sop_retrieved_inspection_candidate",
                    "basis": [str(guidance.get("source_ref") or guidance.get("sop_id") or "")],
                })
                inspection_guidance[component_id] = guidance
        else:
            for hypothesis in component_hypotheses:
                component_id = str(hypothesis.get("component_id") or "") if isinstance(hypothesis, dict) else ""
                if not component_id:
                    continue
                matching = next((item for item in sop_guidance if component_id in (item.get("component_ids") or [])), None)
                if matching:
                    inspection_guidance[component_id] = matching
        evidence_payload["component_hypotheses"] = component_hypotheses
        artifact["evidence_payload"] = evidence_payload
    asset = {
        "asset_id": result.asset_id,
        "asset_type": result.asset_type,
        "display_name": f"{result.asset_type.upper()} · {result.asset_id}",
        "site_id": result.site_id,
        "cell_id": result.cell_id,
        "observed_at": observed_at,
        "criticality": criticality,
        "criticality_basis": ["runtime result status grade"],
        "criticality_source": "project_context",
        "operation_context": operation_context,
        "maintenance_context": {
            "last_maintenance_days_ago": None,
            "similar_events_30d": None,
            "open_work_order_exists": None,
        },
    }
    feature_series, runtime_prediction_history = _runtime_feature_and_risk_history(
        runtime_service=runtime_service,
        principal=principal,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=page.context.dataset_version_id,
        asset_id=asset_id,
        observed_at=result.observed_at,
        history_window=history_window,
    )
    if not runtime_prediction_history:
        runtime_prediction_history = [
            {
                "observed_at": observed_at,
                "failure_probability": result.failure_probability,
                "status_grade": result.status_grade,
                "prediction_id": result.provenance.prediction_id,
                "source_kind": result.source_contract,
                "source_ref": f"result-artifact:{event_id}",
            }
        ]
    return compose_asset_detail_view_model(
        asset=asset,
        result_artifact=artifact,
        feature_series=feature_series,
        runtime_prediction_history=runtime_prediction_history,
        equipment_history=[],
        operation_context=asset["operation_context"],
        inspection_guidance=inspection_guidance,
        data_status={
            "source": "canonical-runtime",
            "last_updated_at": observed_at,
            "is_stale": None,
            "warnings": [],
        },
        history_window=history_window,
        event_id=event_id,
    )


def _merge_runtime_detail_supplemental(
    canonical: dict[str, Any],
    supplemental: dict[str, Any],
) -> dict[str, Any]:
    """Add presentation context without replacing canonical evidence facts."""

    merged = dict(canonical)
    merged["operation_context"] = supplemental.get("operation_context")
    supplemental_features = {
        str(feature.get("key") or ""): feature
        for feature in supplemental.get("features") or []
        if isinstance(feature, dict) and feature.get("key")
    }
    if supplemental_features:
        merged_features: list[dict[str, Any]] = []
        seen_feature_keys: set[str] = set()
        for feature in merged.get("features") or []:
            if not isinstance(feature, dict):
                continue
            key = str(feature.get("key") or "")
            seen_feature_keys.add(key)
            supplemental_feature = supplemental_features.get(key)
            canonical_history = (feature.get("history") or {}) if isinstance(feature.get("history"), dict) else {}
            supplemental_history = (
                supplemental_feature.get("history") or {}
                if isinstance(supplemental_feature, dict) and isinstance(supplemental_feature.get("history"), dict)
                else {}
            )
            canonical_points = canonical_history.get("points") or []
            supplemental_points = supplemental_history.get("points") or []
            if len(supplemental_points) > len(canonical_points):
                merged_features.append({**feature, "history": supplemental_history})
            else:
                merged_features.append(feature)
        for key, supplemental_feature in supplemental_features.items():
            if key not in seen_feature_keys:
                merged_features.append(supplemental_feature)
        if merged_features:
            merged["features"] = merged_features
    supplemental_risk_series = supplemental.get("risk_series") or []
    canonical_risk_series = merged.get("risk_series") or []
    if len(supplemental_risk_series) > len(canonical_risk_series):
        merged["risk_series"] = supplemental_risk_series
    if not merged.get("inspection_targets") and supplemental.get("inspection_targets"):
        merged["inspection_targets"] = supplemental["inspection_targets"]
    if not merged.get("review_priority") and supplemental.get("review_priority"):
        merged["review_priority"] = supplemental["review_priority"]
    evidence = dict(merged.get("evidence") or {})
    gaps = [
        gap
        for gap in evidence.get("gaps") or []
        if not str((gap or {}).get("field") or "").startswith("operation_context")
        and str((gap or {}).get("field") or "") != "review_priority"
    ]
    evidence["gaps"] = gaps
    merged["evidence"] = evidence
    return merged


def _dynamic_summary_from_packet(
    *,
    service: ManufacturingPredictiveMaintenanceService,
    packet: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = service.agent_review_summary_provider
    provider_name = getattr(provider, "name", "none") if provider else "none"
    if provider is not None and getattr(provider, "provider", None) is not None:
        try:
            summary = provider.generate(packet)
            errors = validate_agent_review_summary_contract(summary, packet=packet)
            if not errors:
                return summary, {
                    "provider": provider_name,
                    "fallback": False,
                    "reason": None,
                    "validation_errors": [],
                    "materialization": {
                        "summary_id": None,
                        "summary_key": f"runtime:{packet.get('asset_id')}",
                        "workflow_run_id": None,
                        "status": "ready",
                        "reused": False,
                        "source_sha256": "runtime-packet",
                        "context_sha256": None,
                        "prompt_version": "agent-review-summary-prompt-v1.0",
                        "model_version": getattr(getattr(provider, "provider", None), "model", provider_name),
                        "generated_at": summary.get("generated_at"),
                        "created_at": None,
                        "updated_at": None,
                    },
                }
            fallback = compose_deterministic_agent_review_summary(packet)
            return fallback, {
                "provider": provider_name,
                "fallback": True,
                "reason": "llm_summary_validation_failed",
                "validation_errors": errors,
                "fallback_validation_errors": validate_agent_review_summary_contract(fallback, packet=packet),
            }
        except Exception as exc:
            fallback = compose_deterministic_agent_review_summary(packet)
            return fallback, {
                "provider": provider_name,
                "fallback": True,
                "reason": f"{type(exc).__name__}: {exc}",
                "validation_errors": [],
                "fallback_validation_errors": validate_agent_review_summary_contract(fallback, packet=packet),
            }
    fallback = compose_deterministic_agent_review_summary(packet)
    return fallback, {
        "provider": provider_name,
        "fallback": True,
        "reason": "agent_review_summary_provider_disabled",
        "validation_errors": [],
        "fallback_validation_errors": validate_agent_review_summary_contract(fallback, packet=packet),
    }


def _require_active_event_project(
    principal: Principal,
    service: ManufacturingPredictiveMaintenanceService,
    event_id: str,
) -> str:
    project_id = service.project_id_for_event(event_id)
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 Event입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Event가 속한 Project를 활성화해야 합니다.")
    return project_id


def _require_configured_action_project(project_id: str) -> None:
    if project_id != "manufacturing-demo-project":
        raise AuthError(
            422,
            "project_action_not_configured",
            "이 showcase Project는 현재 Evidence 조회 전용입니다. Action mapping을 먼저 게시해야 합니다.",
        )


@router.get("/events")
def list_events(
    _: Principal = Depends(require_manufacturing_scope),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    return {"items": service.list_events()}


@router.get("/projects/{project_id}/company-context")
def get_company_context(
    project_id: str,
    workspace_id: str = Query(default=MANUFACTURING_WORKSPACE, max_length=160),
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 회사 문맥입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Project를 활성화해야 합니다.")
    if not principal.is_admin and workspace_id not in principal.workspace_scopes:
        raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 회사 문맥입니다.")
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        **service.company_context(project_id=project_id, workspace_id=workspace_id),
    }


@router.get("/events/{event_id}")
def get_event(
    event_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    return service.event(event_id)


@router.get("/objects/{asset_id}/detail-view")
def get_asset_detail_view(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    workspace_id: str = Query(default=MANUFACTURING_WORKSPACE, max_length=160),
    dataset_version_id: str | None = Query(default=None, max_length=160),
    event_id: str | None = Query(default=None, max_length=240),
    history_window: Literal["24h", "7d", "30d"] = Query(default="24h"),
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    runtime_detail: AssetDetailViewModelService | None = Depends(get_runtime_asset_detail_service),
):
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 Object입니다.")
    if not principal.is_admin and workspace_id not in principal.workspace_scopes:
        raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 Object입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Object가 속한 Project를 활성화해야 합니다.")
    if dataset_version_id and event_id and runtime_detail is not None:
        try:
            canonical = runtime_detail.latest_detail_view(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                asset_id=asset_id,
                dataset_version_id=dataset_version_id,
                event_id=event_id,
                history_window=history_window,
            )
            try:
                supplemental = _runtime_asset_detail_view_model(
                    asset_id=asset_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    dataset_version_id=dataset_version_id,
                    selected_event_id=event_id,
                    history_window=history_window,
                    principal=principal,
                    runtime_service=get_predictive_maintenance_runtime_service(),
                )
                return _merge_runtime_detail_supplemental(canonical, supplemental)
            except Exception:
                return canonical
        except KeyError as exc:
            raise EventNotFound(event_id) from exc
    if event_id:
        try:
            return _runtime_asset_detail_view_model(
                asset_id=asset_id,
                project_id=project_id,
                workspace_id=workspace_id,
                dataset_version_id=dataset_version_id,
                selected_event_id=event_id,
                history_window=history_window,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
        except EventNotFound:
            pass
    try:
        return service.asset_detail_view_model(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
    except EventNotFound:
        return _runtime_asset_detail_view_model(
            asset_id=asset_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
            selected_event_id=event_id,
            history_window=history_window,
            principal=principal,
            runtime_service=get_predictive_maintenance_runtime_service(),
        )


@router.get("/objects/{asset_id}/agent-review-packet")
def get_agent_review_packet(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    dataset_version_id: str | None = Query(default=None, max_length=160),
    event_id: str | None = Query(default=None, max_length=240),
    history_window: Literal["24h", "7d", "30d"] = Query(default="24h"),
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Object 범위를 벗어난 Agent Review Packet입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Object가 속한 Project를 활성화해야 합니다.")
    if event_id:
        try:
            return _runtime_agent_review_packet(
                asset_id=asset_id,
                project_id=project_id,
                workspace_id=MANUFACTURING_WORKSPACE,
                dataset_version_id=dataset_version_id,
                selected_event_id=event_id,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
        except EventNotFound:
            pass
    try:
        return service.agent_review_packet(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
    except EventNotFound:
        return _runtime_agent_review_packet(
            asset_id=asset_id,
            project_id=project_id,
            workspace_id=MANUFACTURING_WORKSPACE,
            dataset_version_id=dataset_version_id,
            principal=principal,
            runtime_service=get_predictive_maintenance_runtime_service(),
        )


def _authorize_agent_review_summary(
    *,
    principal: Principal,
    project_id: str,
) -> None:
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Object 범위를 벗어난 Agent Review Summary입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Object가 속한 Project를 활성화해야 합니다.")
    if not principal.is_admin and MANUFACTURING_WORKSPACE not in principal.workspace_scopes:
        raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 Agent Review Summary입니다.")


@router.get("/objects/{asset_id}/agent-review-summary")
def get_agent_review_summary(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    dataset_version_id: str | None = Query(default=None, max_length=160),
    event_id: str | None = Query(default=None, max_length=240),
    history_window: Literal["24h", "7d", "30d"] = Query(default="24h"),
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _authorize_agent_review_summary(principal=principal, project_id=project_id)
    if event_id:
        try:
            _runtime_agent_review_packet(
                asset_id=asset_id,
                project_id=project_id,
                workspace_id=MANUFACTURING_WORKSPACE,
                dataset_version_id=dataset_version_id,
                selected_event_id=event_id,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
            return JSONResponse(
                status_code=202,
                content={
                    "summary": None,
                    "trace": {
                        "provider": "runtime-product-result",
                        "fallback": False,
                        "reason": "runtime_packet_not_materialized_yet",
                        "validation_errors": [],
                        "materialization": {
                            "summary_id": None,
                            "summary_key": f"runtime:{event_id}",
                            "workflow_run_id": None,
                            "status": "pending",
                            "reused": False,
                            "source_sha256": "runtime-packet",
                            "context_sha256": None,
                            "prompt_version": "agent-review-summary-prompt-v1.0",
                            "model_version": "runtime-product-result",
                            "generated_at": None,
                            "created_at": None,
                            "updated_at": None,
                        },
                    },
                },
            )
        except EventNotFound:
            pass
    try:
        summary, trace = service.cached_agent_review_summary(
            asset_id,
            project_id,
            organization_id=principal.organization_id,
            workspace_id=MANUFACTURING_WORKSPACE,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
    except EventNotFound:
        _runtime_agent_review_packet(
            asset_id=asset_id,
            project_id=project_id,
            workspace_id=MANUFACTURING_WORKSPACE,
            dataset_version_id=dataset_version_id,
            principal=principal,
            runtime_service=get_predictive_maintenance_runtime_service(),
        )
        summary, trace = None, {
            "provider": "runtime-product-result",
            "fallback": False,
            "reason": "runtime_packet_not_materialized_yet",
            "validation_errors": [],
            "materialization": {
                "summary_id": None,
                "summary_key": f"runtime:{asset_id}",
                "workflow_run_id": None,
                "status": "pending",
                "reused": False,
                "source_sha256": "runtime-packet",
                "context_sha256": None,
                "prompt_version": "agent-review-summary-prompt-v1.0",
                "model_version": "runtime-product-result",
                "generated_at": None,
                "created_at": None,
                "updated_at": None,
            },
        }
    status_code = 200 if summary is not None else 202
    return JSONResponse(
        status_code=status_code,
        content={"summary": summary, "trace": trace},
    )


@router.post("/objects/{asset_id}/agent-review-summary")
def create_agent_review_summary(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    dataset_version_id: str | None = Query(default=None, max_length=160),
    event_id: str | None = Query(default=None, max_length=240),
    history_window: Literal["24h", "7d", "30d"] = Query(default="24h"),
    trigger: Literal["manual_materialization", "ui_manual_regeneration"] = Query(
        default="manual_materialization"
    ),
    principal: Principal = Depends(require_permission("agent.review.materialize")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    _authorize_agent_review_summary(principal=principal, project_id=project_id)
    limiter.check(
        bucket="agent-review-summary.materialize",
        subject=rate_limit_subject(
            principal.user_id,
            project_id,
            asset_id,
            event_id or "no-event",
            history_window,
            trigger,
        ),
        rule=AGENT_REVIEW_SUMMARY_MATERIALIZE_RATE,
    )
    if event_id:
        try:
            packet = _runtime_agent_review_packet(
                asset_id=asset_id,
                project_id=project_id,
                workspace_id=MANUFACTURING_WORKSPACE,
                dataset_version_id=dataset_version_id,
                selected_event_id=event_id,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
            summary, trace = _dynamic_summary_from_packet(service=service, packet=packet)
            return {"summary": summary, "trace": trace}
        except EventNotFound:
            pass
    try:
        summary, trace = service.agent_review_summary(
            asset_id,
            project_id,
            organization_id=principal.organization_id,
            workspace_id=MANUFACTURING_WORKSPACE,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
            trigger=trigger,
        )
    except EventNotFound:
        packet = _runtime_agent_review_packet(
            asset_id=asset_id,
            project_id=project_id,
            workspace_id=MANUFACTURING_WORKSPACE,
            dataset_version_id=dataset_version_id,
            principal=principal,
            runtime_service=get_predictive_maintenance_runtime_service(),
        )
        summary, trace = _dynamic_summary_from_packet(service=service, packet=packet)
    return {"summary": summary, "trace": trace}


def _decision_support_identity(
    *,
    principal: Principal,
    project_id: str,
    workspace_id: str,
    asset_id: str,
    evidence_snapshot_id: str,
    decision_as_of: datetime,
) -> OperationalRequestIdentity:
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 판단 지원 요청입니다.")
    if not principal.is_admin and workspace_id not in principal.workspace_scopes:
        raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 판단 지원 요청입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 요청 Project를 활성화해야 합니다.")
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise HTTPException(status_code=422, detail="decision_as_of must include timezone")
    if decision_as_of > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="decision_as_of cannot be in the future")
    return OperationalRequestIdentity(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        evidence_snapshot_id=evidence_snapshot_id,
        decision_as_of=decision_as_of,
    )


@router.get("/objects/{asset_id}/decision-support-brief")
def get_decision_support_brief(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    workspace_id: str = Query(default=MANUFACTURING_WORKSPACE, max_length=160),
    evidence_snapshot_id: str = Query(min_length=1, max_length=240),
    decision_as_of: datetime = Query(),
    role: DecisionBriefRole = Query(default=DecisionBriefRole.PROCESS_ENGINEER),
    principal: Principal = Depends(require_permission("events.read")),
    decision_support: OperationalDecisionSupportService = Depends(get_operational_decision_support_service),
):
    identity = _decision_support_identity(
        principal=principal,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        evidence_snapshot_id=evidence_snapshot_id,
        decision_as_of=decision_as_of,
    )
    brief, trace = decision_support.cached_brief(identity=identity, actor_role=role)
    return JSONResponse(
        status_code=200 if brief is not None else 202,
        content={
            "brief": brief.model_dump(mode="json") if brief is not None else None,
            "trace": asdict(trace),
        },
    )


@router.post("/objects/{asset_id}/decision-support-brief")
def create_decision_support_brief(
    asset_id: str,
    project_id: str = Query(default="manufacturing-demo-project"),
    workspace_id: str = Query(default=MANUFACTURING_WORKSPACE, max_length=160),
    evidence_snapshot_id: str = Query(min_length=1, max_length=240),
    decision_as_of: datetime = Query(),
    role: DecisionBriefRole = Query(default=DecisionBriefRole.PROCESS_MANAGER),
    risk_status: str = Query(default="critical", min_length=1, max_length=80),
    trigger: Literal["manual_materialization", "ui_manual_regeneration"] = Query(default="manual_materialization"),
    principal: Principal = Depends(require_permission("agent.review.materialize")),
    _: None = Depends(require_csrf),
    decision_support: OperationalDecisionSupportService = Depends(get_operational_decision_support_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    identity = _decision_support_identity(
        principal=principal,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        evidence_snapshot_id=evidence_snapshot_id,
        decision_as_of=decision_as_of,
    )
    limiter.check(
        bucket="decision-support-brief.materialize",
        subject=rate_limit_subject(
            principal.user_id,
            project_id,
            workspace_id,
            asset_id,
            evidence_snapshot_id,
            role.value,
            trigger,
        ),
        rule=DECISION_SUPPORT_MATERIALIZE_RATE,
    )
    try:
        brief, trace = decision_support.materialize(
            identity=identity,
            actor_role=role,
            risk_status=risk_status,
            trigger=trigger,
        )
    except (ValueError, DecisionSupportMaterializationInProgress) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"brief": brief.model_dump(mode="json"), "trace": asdict(trace)}


@router.get("/projects/{project_id}/decision-support-workflow-runs")
def list_decision_support_workflow_runs(
    project_id: str,
    asset_id: str | None = Query(default=None, max_length=160),
    status: Literal["running", "completed", "partial", "failed"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_permission("admin.audit.read")),
    decision_support: OperationalDecisionSupportService = Depends(get_operational_decision_support_service),
):
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 평가 이력입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 요청 Project를 활성화해야 합니다.")
    return {
        "items": decision_support.workflow_runs(
            organization_id=principal.organization_id,
            project_id=project_id,
            asset_id=asset_id,
            status=status,
            limit=limit,
        )
    }


@router.get("/projects/{project_id}/agent-review-workflow-runs")
def list_agent_review_workflow_runs(
    project_id: str,
    asset_id: str | None = Query(default=None, max_length=160),
    event_id: str | None = Query(default=None, max_length=160),
    dataset_version_id: str | None = Query(default=None, max_length=160),
    status: Literal["running", "completed", "partial", "failed"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_permission("admin.audit.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _authorize_agent_review_summary(principal=principal, project_id=project_id)
    return service.agent_review_workflow_runs(
        project_id,
        organization_id=principal.organization_id,
        workspace_id=MANUFACTURING_WORKSPACE,
        asset_id=asset_id,
        event_id=event_id,
        dataset_version_id=dataset_version_id,
        status=status,
        limit=limit,
    )


@router.post("/agent/query")
def run_agent_query(
    request: AgentQueryRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    """Read-only grounded Operations assistant query."""

    if not principal.is_admin and request.project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 Agent Query입니다.")
    if principal.active_project_id != request.project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Project를 활성화해야 합니다.")
    if not principal.is_admin and request.workspace_id not in principal.workspace_scopes:
        raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 Agent Query입니다.")

    now = _utc_now()
    run_id = f"agent-{uuid.uuid4()}"
    route = "hybrid" if request.route == "auto" else request.route

    if not request.object_id:
        state = {
            "run_id": run_id,
            "organization_id": principal.organization_id,
            "project_id": request.project_id,
            "workspace_id": request.workspace_id,
            "user_id": principal.user_id,
            "question": request.question,
            "route": "relational" if request.route == "auto" else request.route,
            "status": "failed",
            "object_type": request.object_type,
            "object_id": None,
            "evidence": [],
            "claims": [],
            "steps": [{
                "name": "select_object",
                "store": None,
                "status": "failed",
                "latency_ms": None,
                "detail": "object_id is required for grounded Operations assistant answers",
            }],
            "answer": "먼저 설비나 이벤트를 선택해야 정본 근거 기반 답변을 만들 수 있습니다.",
            "caveats": ["No object was selected."],
            "error": "object_id_required",
            "checkpoint_sequence": 1,
        }
        return {"state": state, "traces": [{
            "id": f"trace-{uuid.uuid4()}",
            "run_id": run_id,
            "step_name": "select_object",
            "store_kind": None,
            "status": "failed",
            "input": request.model_dump(mode="json"),
            "output": {"error": "object_id_required"},
            "latency_ms": None,
            "created_at": now,
        }]}

    packet = None
    packet_source = "fixture-agent-review"
    if request.event_id:
        try:
            packet = _runtime_agent_review_packet(
                asset_id=request.object_id,
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                dataset_version_id=None,
                selected_event_id=request.event_id,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
            packet_source = "runtime-product-result"
        except EventNotFound:
            packet = None
    if packet is None:
        try:
            packet = service.agent_review_packet(
                request.object_id,
                request.project_id,
                history_window="24h",
            )
            packet_source = "fixture-agent-review"
        except EventNotFound:
            packet = _runtime_agent_review_packet(
                asset_id=request.object_id,
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                dataset_version_id=None,
                selected_event_id=request.event_id,
                principal=principal,
                runtime_service=get_predictive_maintenance_runtime_service(),
            )
            packet_source = "runtime-product-result"
    evidence = _packet_evidence(
        packet,
        service=service,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        question=request.question,
        roles=principal.roles,
        top_k=request.top_k,
    )
    try:
        tool_result = run_read_only_tool_pipeline(packet)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        tool_result = {"terminal_status": "failed", "error": f"{type(exc).__name__}: {exc}", "steps": []}

    summary: dict[str, Any] | None = None
    summary_trace: dict[str, Any] = {}
    if principal.is_admin or "agent.review.materialize" in principal.permissions:
        try:
            if packet_source == "runtime-product-result":
                summary, summary_trace = _dynamic_summary_from_packet(service=service, packet=packet)
            else:
                summary, summary_trace = service.agent_review_summary(
                    request.object_id,
                    request.project_id,
                    organization_id=principal.organization_id,
                    workspace_id=request.workspace_id,
                    history_window="24h",
                    trigger="manual_materialization",
                )
        except Exception as exc:  # keep the assistant read path available
            summary_trace = {
                "fallback": "summary_materialization_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

    baseline_answer = _answer_from_packet(request.question, packet, evidence, summary, request.audience)
    answer = baseline_answer
    answer_citations: list[str] = []
    answer_caveats: list[str] = []
    answer_trace = {
        "mode": "deterministic_fallback",
        "provider": "none",
        "reason": "provider_unavailable",
    }
    if service.agent_answer_provider is not None:
        answer, answer_citations, answer_caveats, answer_trace = service.agent_answer_provider.generate(
            question=request.question,
            audience=request.audience,
            packet=packet,
            evidence=evidence,
            baseline_answer=baseline_answer,
            summary=summary,
        )
    claim_ids = answer_citations or [item["evidence_id"] for item in evidence[:4]]
    steps = [
        {
            "name": "agent_review_packet",
            "store": "postgresql",
            "status": "succeeded",
            "latency_ms": None,
            "detail": f"Composed live Agent Review Packet for the selected Operations object via {packet_source}.",
        },
        {
            "name": "read_only_tool_pipeline",
            "store": "postgresql",
            "status": "succeeded" if not (tool_result.get("validation_errors") or tool_result.get("error")) else "failed",
            "latency_ms": None,
            "detail": str(tool_result.get("terminal_status") or "completed"),
        },
        {
            "name": "agent_review_summary",
            "store": "postgresql",
            "status": "succeeded" if summary else "skipped",
            "latency_ms": None,
            "detail": str((summary_trace.get("materialization") or {}).get("status") or summary_trace.get("fallback") or "packet answer"),
        },
        {
            "name": "grounded_answer",
            "store": "company_context+postgresql",
            "status": "succeeded",
            "latency_ms": None,
            "detail": f"{answer_trace.get('mode')} via {answer_trace.get('provider')}",
        },
    ]
    state = {
        "run_id": run_id,
        "organization_id": principal.organization_id,
        "project_id": request.project_id,
        "workspace_id": request.workspace_id,
        "user_id": principal.user_id,
        "question": request.question,
        "route": route,
        "status": "succeeded",
        "object_type": request.object_type or "asset",
        "object_id": request.object_id,
        "evidence": evidence,
        "claims": [{
            "claim_id": "claim-grounded-answer",
            "text": answer,
            "evidence_ids": claim_ids,
            "confidence": "high" if claim_ids else "medium",
            "validated": True,
        }],
        "steps": steps,
        "answer": answer,
        "caveats": [
            "Read-only Operations assistant: no workflow approval, execution, or state mutation was performed.",
            *answer_caveats,
        ],
        "error": None,
        "checkpoint_sequence": 1,
    }
    traces = [
        {
            "id": f"trace-{uuid.uuid4()}",
            "run_id": run_id,
            "step_name": step["name"],
            "store_kind": step["store"],
            "status": step["status"],
            "input": {"question": request.question, "object_id": request.object_id} if step["name"] == "agent_review_packet" else {},
            "output": {"detail": step["detail"]},
            "latency_ms": step["latency_ms"],
            "created_at": now,
        }
        for step in steps
    ]
    return {"state": state, "traces": traces}


@router.get("/events/{event_id}/evidence")
def get_evidence(
    event_id: str,
    view: Literal["legacy", "canonical"] = Query(default="legacy"),
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    return service.evidence(event_id, view=view)


@router.post("/events/{event_id}/report")
def create_report(
    event_id: str,
    request: ReportRequest,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.report_role(principal, request.role)
    report, trace = service.report(
        event_id,
        ReportRequest(role=role, report_type=request.report_type, locale=request.locale, use_llm=request.use_llm),
    )
    return {"report": report.model_dump(mode="json"), "trace": trace}


@router.post("/events/{event_id}/layout")
def create_layout(
    event_id: str,
    request: LayoutRequest,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.legacy_dashboard_role(principal, request.role)
    layout, trace = service.layout(
        event_id,
        LayoutRequest(role=role, locale=request.locale, intent=request.intent, use_llm=request.use_llm),
    )
    return {"layout": layout.model_dump(mode="json"), "trace": trace}


@router.post("/events/{event_id}/decision")
def record_decision(
    event_id: str,
    request: DecisionRequest,
    principal: Principal = Depends(require_permission("events.decision")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    project_id = _require_active_event_project(principal, service, event_id)
    _require_configured_action_project(project_id)
    execution = ontology.invoke(
        ActionInvocation(
            action_type="record_operational_decision",
            object_id=risk_event_object_id(event_id),
            workspace_id=MANUFACTURING_WORKSPACE,
            parameters={"decision": request.decision, "note": request.note},
            idempotency_key=f"legacy-decision:{uuid.uuid4()}",
        ),
        principal,
    )
    return execution.result


@router.post("/events/{event_id}/notes")
def add_note(
    event_id: str,
    request: NoteRequest,
    principal: Principal = Depends(require_permission("events.note")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    project_id = _require_active_event_project(principal, service, event_id)
    _require_configured_action_project(project_id)
    execution = ontology.invoke(
        ActionInvocation(
            action_type="record_inspection_note",
            object_id=inspection_object_id(event_id),
            workspace_id=MANUFACTURING_WORKSPACE,
            parameters={"body": request.body},
            idempotency_key=f"legacy-note:{uuid.uuid4()}",
        ),
        principal,
    )
    return execution.result


@router.post("/events/{event_id}/follow-up")
def follow_up(
    event_id: str,
    request: FollowUpRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.legacy_dashboard_role(principal, request.role)
    safe_request = FollowUpRequest(role=role, locale=request.locale, question=request.question)
    return service.follow_up(event_id, safe_request).model_dump(mode="json")


@router.get("/events/{event_id}/activity")
def event_activity(
    event_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    service.event(event_id)
    return service.repository.event_activity(event_id)
