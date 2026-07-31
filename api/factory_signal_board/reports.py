from __future__ import annotations

from typing import Any

from .contracts import GroundedReport, ReportAction, ReportSection, Role

STATUS_LABELS = {
    "normal": "정상",
    "attention": "관심",
    "warning": "경고",
    "critical": "긴급 검토",
    "data_quality_hold": "데이터 확인 필요",
}
DECISION_LABELS = {
    "continue_monitoring": "계속 운전하며 모니터링",
    "request_inspection": "현장 점검 요청",
    "review_shutdown": "사람의 판단으로 정지 검토",
    "hold_for_data_check": "데이터 확인 전 판단 보류",
}
FAILURE_LABELS = {
    "none": "특정 고장 유형 없음",
    "tool_wear_failure": "공구 마모 위험",
    "heat_dissipation_failure": "열 방출 이상 가능성",
    "power_or_overstrain_failure": "동력·과부하 이상 가능성",
    "multi_factor_risk": "복합 이상 가능성",
    "uncertain": "고장 유형 불확실",
    "unavailable": "판단 불가",
}


def _probability_text(evidence: dict[str, Any]) -> str:
    value = evidence["failure_probability"]
    return "산출하지 않음" if value is None else f"{value * 100:.1f}%"


def _factor_sentence(factor: dict[str, Any]) -> str:
    return (
        f"{factor['display_name']} {factor['value']:,.2f}{factor['unit']}"
        f"(참고 범위 {factor['normal_range']})가 위험도를 "
        f"{'높이는' if factor['direction'] == 'risk_up' else '낮추는'} 방향으로 계산됐습니다."
    )


def _actions(evidence: dict[str, Any]) -> list[ReportAction]:
    decision = evidence["recommended_decision"]
    kind = {
        "continue_monitoring": "monitor",
        "request_inspection": "inspect",
        "review_shutdown": "review_shutdown",
        "hold_for_data_check": "verify_data",
    }[decision]
    source_refs = evidence["maintenance_context"]["source_refs"]
    actions = [
        ReportAction(
            action_id=f"action.{index + 1}",
            label=label,
            kind=kind if index == 0 else ("inspect" if decision != "hold_for_data_check" else "verify_data"),
            requires_human_approval=True,
            source_refs=source_refs,
        )
        for index, label in enumerate(evidence["maintenance_context"]["recommended_actions"])
    ]
    if not actions:
        actions.append(
            ReportAction(
                action_id="action.1",
                label=DECISION_LABELS[decision],
                kind=kind,
                requires_human_approval=True,
                source_refs=[],
            )
        )
    return actions


def render_report(
    evidence: dict[str, Any],
    role: Role,
    *,
    mode: str = "deterministic",
) -> GroundedReport:
    equipment = evidence["equipment"]
    status = evidence["status"]
    status_label = STATUS_LABELS[status]
    decision_label = DECISION_LABELS[evidence["recommended_decision"]]
    failure_label = FAILURE_LABELS.get(evidence["predicted_failure_type"], evidence["predicted_failure_type"])
    factor_ids = [factor["evidence_field_id"] for factor in evidence["top_factors"]]
    primary_factors = evidence["top_factors"][:3]
    factor_text = " ".join(_factor_sentence(factor) for factor in primary_factors)
    citations = ["status", "recommended_decision", "confidence", "failure_probability", *factor_ids]

    limitations = [
        "예측 고장 유형은 현장 점검으로 확정된 근본 원인이 아닙니다.",
        "추천 조치는 자동 실행되지 않으며 권한 있는 사람이 검토해야 합니다.",
    ]

    if status == "data_quality_hold":
        warnings = " ".join(item["message"] for item in evidence["data_quality_warnings"])
        headline = f"{equipment['display_name']} 데이터 확인이 필요합니다"
        summary = f"센서 데이터 품질 문제로 고장 위험을 판단하지 않았습니다. {warnings}"
        sections = [
            ReportSection(
                section_id="data-quality",
                title="판단 보류 사유",
                body=warnings,
                evidence_field_ids=[f"data_quality_warnings.{index}" for index, _ in enumerate(evidence["data_quality_warnings"])],
            ),
            ReportSection(
                section_id="decision",
                title="권장 결정",
                body=decision_label,
                evidence_field_ids=["recommended_decision"],
            ),
        ]
        limitations.append("유효한 센서 값으로 다시 검증하기 전 정상 또는 고장으로 단정할 수 없습니다.")
    elif role == "manager":
        headline = f"{equipment['display_name']} · {status_label} · {decision_label}"
        summary = (
            f"고장 위험도는 {_probability_text(evidence)}이며 {failure_label}이 추정됩니다. "
            f"예상 정지 영향은 {equipment['estimated_downtime_minutes']}분입니다. "
            f"권장 결정은 '{decision_label}'입니다."
        )
        sections = [
            ReportSection(
                section_id="manager-status",
                title="현재 판단",
                body=summary,
                evidence_field_ids=["status", "failure_probability", "predicted_failure_type", "recommended_decision"],
            ),
            ReportSection(
                section_id="manager-impact",
                title="운영 영향",
                body=(
                    f"설비 중요도는 {equipment['criticality']}이며, fixture 기준 예상 정지 영향은 "
                    f"{equipment['estimated_downtime_minutes']}분입니다. 이 값은 실제 생산 손실이 아닌 데모 추정치입니다."
                ),
                evidence_field_ids=["equipment.criticality", "equipment.estimated_downtime_minutes"],
            ),
            ReportSection(
                section_id="manager-evidence",
                title="핵심 근거",
                body=factor_text or "현재 위험을 뒷받침하는 유효한 요인이 없습니다.",
                evidence_field_ids=factor_ids[:3],
            ),
        ]
    else:
        headline = f"{equipment['display_name']} 근거 분석 · {status_label}"
        interval = evidence["detected_interval"]
        summary = (
            f"{interval['start']}부터 {interval['end']}까지의 관측에서 {failure_label}이 추정됐습니다. "
            f"고장 위험도는 {_probability_text(evidence)}, 신뢰도는 {evidence['confidence']}입니다."
        )
        checklist = " / ".join(evidence["maintenance_context"]["checklist"])
        sections = [
            ReportSection(
                section_id="engineer-interval",
                title="이상 구간",
                body=summary,
                evidence_field_ids=["detected_interval.start", "detected_interval.end", "failure_probability", "confidence"],
            ),
            ReportSection(
                section_id="engineer-factors",
                title="센서·파생변수 근거",
                body=factor_text or "품질 검증을 통과한 위험 요인이 없습니다.",
                evidence_field_ids=factor_ids,
            ),
            ReportSection(
                section_id="engineer-checklist",
                title="점검 체크리스트",
                body=checklist,
                evidence_field_ids=[*evidence["maintenance_context"]["source_refs"]],
            ),
            ReportSection(
                section_id="engineer-manager-summary",
                title="매니저 보고용 요약",
                body=f"{status_label} 상태로 분류됐으며 권장 결정은 '{decision_label}'입니다. 현장 점검으로 원인을 확인해야 합니다.",
                evidence_field_ids=["status", "recommended_decision"],
            ),
        ]

    report = GroundedReport(
        report_id=f"RPT-{evidence['event_id']}-{role}",
        event_id=evidence["event_id"],
        role=role,
        mode=mode,  # type: ignore[arg-type]
        headline=headline,
        summary=summary,
        status=status,
        confidence=evidence["confidence"],
        recommended_decision=evidence["recommended_decision"],
        sections=sections,
        actions=_actions(evidence),
        citations=sorted(set(citations)),
        limitations=limitations,
        generated_at=evidence["generated_at"],
    )
    return report
