from __future__ import annotations

from typing import Any

from .report_schema import AppLocale, GroundedReport, ReportAction, ReportSection, ReportType, Role

STATUS_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "normal": "정상",
        "attention": "관찰",
        "warning": "경고",
        "critical": "긴급 검토",
        "data_quality_hold": "데이터 확인 필요",
    },
    "en-US": {
        "normal": "Normal",
        "attention": "Attention",
        "warning": "Warning",
        "critical": "Critical review",
        "data_quality_hold": "Data quality review required",
    },
}

DECISION_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "continue_monitoring": "계속 운전하며 모니터링",
        "request_inspection": "현장 점검 요청",
        "review_shutdown": "사람의 판단으로 정지 검토",
        "hold_for_data_check": "데이터 확인 전 판단 보류",
    },
    "en-US": {
        "continue_monitoring": "Continue operation and monitor",
        "request_inspection": "Request a field inspection",
        "review_shutdown": "Review a shutdown with an authorized operator",
        "hold_for_data_check": "Hold the decision until data is verified",
    },
}

FAILURE_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "none": "특정 고장 유형 없음",
        "tool_wear_failure": "공구 마모 위험",
        "heat_dissipation_failure": "열 방출 이상 가능성",
        "power_or_overstrain_failure": "동력·과부하 이상 가능성",
        "multi_factor_risk": "복합 이상 가능성",
        "failure_risk": "고장 위험",
        "no_significant_risk": "유의한 고장 위험 없음",
        "uncertain": "고장 유형 불확실",
        "unavailable": "판단 불가",
    },
    "en-US": {
        "none": "No specific failure type",
        "tool_wear_failure": "Tool-wear risk",
        "heat_dissipation_failure": "Possible heat-dissipation issue",
        "power_or_overstrain_failure": "Possible power or overstrain issue",
        "multi_factor_risk": "Multi-factor risk",
        "failure_risk": "Failure risk",
        "no_significant_risk": "No significant failure risk",
        "uncertain": "Uncertain failure type",
        "unavailable": "Unavailable",
    },
}

FEATURE_LABELS_EN = {
    "air_temperature_k": "Air temperature",
    "process_temperature_k": "Process temperature",
    "rotational_speed_rpm": "Rotational speed",
    "torque_nm": "Torque",
    "tool_wear_min": "Tool wear",
    "power_w": "Mechanical power",
    "temperature_gap_k": "Process-to-air temperature gap",
    "overstrain_load": "Tool-wear torque load",
    "rotation_raw_6h_mean": "6-hour rotational-speed mean",
    "rotation_raw_6h_abs_mean": "6-hour rotational-speed absolute mean",
    "rotation_raw_6h_std": "6-hour rotational-speed standard deviation",
}



def _equipment_name(value: str, locale: AppLocale) -> str:
    if locale == "ko-KR":
        return value
    replacements = {
        "절삭 설비": "Cutting Machine",
        "성형 설비": "Forming Machine",
        "프레스 설비": "Press Machine",
        "복합 가공 설비": "Multi-process Machine",
        "조립 설비": "Assembly Machine",
        "검사 설비": "Inspection Machine",
    }
    translated = value
    for source, target in replacements.items():
        translated = translated.replace(source, target)
    return translated


def _probability_text(evidence: dict[str, Any], locale: AppLocale) -> str:
    value = evidence["failure_probability"]
    if value is None:
        return "산출하지 않음" if locale == "ko-KR" else "Not calculated"
    return f"{value * 100:.1f}%"


def _factor_name(factor: dict[str, Any], locale: AppLocale) -> str:
    if locale == "ko-KR":
        return str(factor["display_name"])
    field_id = str(factor.get("evidence_field_id") or "").removeprefix("factor:")
    return FEATURE_LABELS_EN.get(field_id, str(factor.get("feature") or factor["display_name"]).replace("_", " ").title())


def _factor_sentence(factor: dict[str, Any], locale: AppLocale) -> str:
    name = _factor_name(factor, locale)
    value = f"{factor['value']:,.2f}{factor['unit']}"
    if locale == "ko-KR":
        return (
            f"{name} {value}(참고 범위 {factor['normal_range']})가 위험도를 "
            f"{'높이는' if factor['direction'] == 'risk_up' else '낮추는'} 방향으로 계산됐습니다."
        )
    direction = "increased" if factor["direction"] == "risk_up" else "reduced"
    return (
        f"{name} was {value}; the model calculated that it {direction} risk. "
        f"The governed reference range is {factor['normal_range']}."
    )


def _data_quality_text(evidence: dict[str, Any], locale: AppLocale) -> str:
    warnings = evidence["data_quality_warnings"]
    if locale == "ko-KR":
        return " ".join(str(item["message"]) for item in warnings)
    if not warnings:
        return "The required sensor values did not pass the governed data-quality checks."
    return " ".join(
        f"{item.get('field', 'sensor data')}: {item.get('code', 'quality check failed')}."
        for item in warnings
    )


def _actions(evidence: dict[str, Any], locale: AppLocale) -> list[ReportAction]:
    decision = evidence["recommended_decision"]
    kind = {
        "continue_monitoring": "monitor",
        "request_inspection": "inspect",
        "review_shutdown": "review_shutdown",
        "hold_for_data_check": "verify_data",
    }[decision]
    source_refs = evidence["maintenance_context"]["source_refs"]
    source_actions = evidence["maintenance_context"]["recommended_actions"]
    labels = source_actions if locale == "ko-KR" else [DECISION_LABELS[locale][decision]]
    actions = [
        ReportAction(
            action_id=f"action.{index + 1}",
            label=label,
            kind=kind if index == 0 else ("inspect" if decision != "hold_for_data_check" else "verify_data"),
            requires_human_approval=True,
            source_refs=source_refs,
        )
        for index, label in enumerate(labels)
    ]
    if not actions:
        actions.append(
            ReportAction(
                action_id="action.1",
                label=DECISION_LABELS[locale][decision],
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
    locale: AppLocale = "ko-KR",
    mode: str = "deterministic",
    report_type: ReportType | None = None,
) -> GroundedReport:
    resolved_report_type: ReportType = report_type or (
        "executive-brief" if role == "executive" else "inspection-summary" if role == "engineer" else "operations-decision"
    )
    equipment = evidence["equipment"]
    equipment_name = _equipment_name(str(equipment["display_name"]), locale)
    status = evidence["status"]
    status_label = STATUS_LABELS[locale][status]
    decision_label = DECISION_LABELS[locale][evidence["recommended_decision"]]
    failure_label = FAILURE_LABELS[locale].get(
        evidence["predicted_failure_type"],
        str(evidence["predicted_failure_type"]).replace("_", " "),
    )
    factor_ids = [factor["evidence_field_id"] for factor in evidence["top_factors"]]
    primary_factors = evidence["top_factors"][:3]
    factor_text = " ".join(_factor_sentence(factor, locale) for factor in primary_factors)
    citations = ["status", "recommended_decision", "confidence", "failure_probability", *factor_ids]

    limitations = (
        [
            "예측 고장 유형은 현장 점검으로 확정된 근본 원인이 아닙니다.",
            "추천 조치는 자동 실행되지 않으며 권한 있는 사람이 검토해야 합니다.",
        ]
        if locale == "ko-KR"
        else [
            "The predicted failure type is not a root cause confirmed by a field inspection.",
            "Recommended actions are not executed automatically and require review by an authorized person.",
        ]
    )

    if status == "data_quality_hold":
        warnings = _data_quality_text(evidence, locale)
        if locale == "ko-KR":
            headline = f"{equipment_name} 데이터 확인이 필요합니다"
            summary = f"센서 데이터 품질 문제로 고장 위험을 판단하지 않았습니다. {warnings}"
            section_titles = ("판단 보류 사유", "권장 결정")
            limitations.append("유효한 센서 값으로 다시 검증하기 전 정상 또는 고장으로 단정할 수 없습니다.")
        else:
            headline = f"{equipment_name} requires a data-quality review"
            summary = f"Failure risk was not assessed because the sensor data did not pass validation. {warnings}"
            section_titles = ("Reason for holding the decision", "Recommended decision")
            limitations.append("The asset must not be classified as normal or failed until valid sensor values are verified.")
        sections = [
            ReportSection(
                section_id="data-quality",
                title=section_titles[0],
                body=warnings,
                evidence_field_ids=[f"data_quality_warnings.{index}" for index, _ in enumerate(evidence["data_quality_warnings"])],
            ),
            ReportSection(
                section_id="decision",
                title=section_titles[1],
                body=decision_label,
                evidence_field_ids=["recommended_decision"],
            ),
        ]
    elif role == "executive":
        criticality_label = {
            "high": "높음" if locale == "ko-KR" else "high",
            "medium": "중간" if locale == "ko-KR" else "medium",
            "low": "낮음" if locale == "ko-KR" else "low",
        }.get(str(equipment.get("criticality")), "확인 필요" if locale == "ko-KR" else "not provided")
        if locale == "ko-KR":
            if resolved_report_type == "inspection-summary":
                headline = f"{equipment_name} · 현장 확인 필요"
                summary = f"현재 위험도는 {_probability_text(evidence, locale)}이며 {failure_label} 가능성이 있습니다. 현장 점검으로 원인을 확인하기 전 고장으로 확정하지 않습니다."
                sections = [
                    ReportSection(section_id="executive-inspection", title="확인이 필요한 사항", body=decision_label, evidence_field_ids=["recommended_decision"]),
                    ReportSection(section_id="executive-inspection-impact", title="운영 영향", body=f"예상 정지 노출은 {equipment['estimated_downtime_minutes']}분입니다.", evidence_field_ids=["equipment.estimated_downtime_minutes"]),
                ]
            elif resolved_report_type == "maintenance-effect":
                headline = f"{equipment_name} · 정비 효과 확인 대기"
                summary = "현재 Event 근거에는 이 Case와 인과적으로 연결된 완료 정비 후 관측이 포함되지 않았습니다. 정비 완료와 후속 관측이 연결된 뒤 효과를 판단해야 합니다."
                sections = [
                    ReportSection(section_id="executive-maintenance-state", title="현재 상태", body="완료 정비 결과가 연결되기 전에는 before/after 성과를 확정하지 않습니다.", evidence_field_ids=["status"]),
                    ReportSection(section_id="executive-maintenance-next", title="다음 확인", body=decision_label, evidence_field_ids=["recommended_decision"]),
                ]
            elif resolved_report_type == "weekly-risk":
                headline = f"주간 리스크 참고 · {equipment_name}"
                summary = f"선택 Case 기준 위험도 {_probability_text(evidence, locale)}, 상태 {status_label}, 권장 판단은 '{decision_label}'입니다. 이 보고서는 선택 Case snapshot이며 전체 주간 포트폴리오 집계가 아닙니다."
                sections = [
                    ReportSection(section_id="executive-weekly-risk", title="선택 Case 리스크", body=summary, evidence_field_ids=["status", "failure_probability", "recommended_decision"]),
                    ReportSection(section_id="executive-weekly-limitation", title="집계 범위", body="전체 포트폴리오 추세는 별도 운영 KPI에서 확인해야 합니다.", evidence_field_ids=[]),
                ]
            elif resolved_report_type == "operations-decision":
                headline = f"{equipment_name} · 경영 의사결정 요청"
                summary = f"현재 {status_label} 상태이며 위험도는 {_probability_text(evidence, locale)}입니다. 예상 정지 노출은 {equipment['estimated_downtime_minutes']}분이고, 현재 요청된 판단은 '{decision_label}'입니다."
                sections = [
                    ReportSection(section_id="executive-decision-request", title="의사결정 요청", body=decision_label, evidence_field_ids=["recommended_decision"]),
                    ReportSection(section_id="executive-decision-impact", title="운영 노출", body=f"예상 정지 노출 {equipment['estimated_downtime_minutes']}분 · 설비 중요도 {criticality_label}", evidence_field_ids=["equipment.estimated_downtime_minutes", "equipment.criticality"]),
                ]
            else:
                headline = f"Executive Brief · {equipment_name}"
                summary = f"현재 {status_label} 상태이며 위험도는 {_probability_text(evidence, locale)}입니다. {failure_label}은 점검 전 가설이며, 경영 관점의 현재 판단 요청은 '{decision_label}'입니다."
                sections = [
                    ReportSection(section_id="executive-status", title="경영 판단 요약", body=summary, evidence_field_ids=["status", "failure_probability", "predicted_failure_type", "recommended_decision"]),
                    ReportSection(section_id="executive-impact", title="운영 노출", body=f"예상 정지 노출은 {equipment['estimated_downtime_minutes']}분이며 설비 중요도는 {criticality_label}입니다.", evidence_field_ids=["equipment.estimated_downtime_minutes", "equipment.criticality"]),
                    ReportSection(section_id="executive-request", title="결정 요청", body=decision_label, evidence_field_ids=["recommended_decision"]),
                ]
        else:
            headline = f"Executive Brief · {equipment_name}"
            summary = f"Current status is {status_label} with {_probability_text(evidence, locale)} estimated risk. The current decision request is '{decision_label}'."
            sections = [
                ReportSection(section_id="executive-status", title="Executive assessment", body=summary, evidence_field_ids=["status", "failure_probability", "recommended_decision"]),
                ReportSection(section_id="executive-impact", title="Operational exposure", body=f"Estimated downtime exposure is {equipment['estimated_downtime_minutes']} minutes.", evidence_field_ids=["equipment.estimated_downtime_minutes"]),
            ]
    elif role == "manager":
        if locale == "ko-KR":
            headline = f"{equipment_name} · {status_label} · {decision_label}"
            summary = (
                f"고장 위험도는 {_probability_text(evidence, locale)}이며 {failure_label}이 추정됩니다. "
                f"예상 정지 영향은 {equipment['estimated_downtime_minutes']}분입니다. "
                f"권장 결정은 '{decision_label}'입니다."
            )
            sections = [
                ReportSection(section_id="manager-status", title="현재 판단", body=summary, evidence_field_ids=["status", "failure_probability", "predicted_failure_type", "recommended_decision"]),
                ReportSection(
                    section_id="manager-impact",
                    title="운영 영향",
                    body=(
                        f"설비 중요도는 {equipment['criticality']}이며, fixture 기준 예상 정지 영향은 "
                        f"{equipment['estimated_downtime_minutes']}분입니다. 이 값은 실제 생산 손실이 아닌 데모 추정치입니다."
                    ),
                    evidence_field_ids=["equipment.criticality", "equipment.estimated_downtime_minutes"],
                ),
                ReportSection(section_id="manager-evidence", title="핵심 근거", body=factor_text or "현재 위험을 뒷받침하는 유효한 요인이 없습니다.", evidence_field_ids=factor_ids[:3]),
            ]
        else:
            headline = f"{equipment_name} · {status_label} · {decision_label}"
            summary = (
                f"The estimated failure risk is {_probability_text(evidence, locale)}, with {failure_label.lower()}. "
                f"The estimated downtime exposure is {equipment['estimated_downtime_minutes']} minutes. "
                f"The recommended decision is '{decision_label}'."
            )
            sections = [
                ReportSection(section_id="manager-status", title="Current assessment", body=summary, evidence_field_ids=["status", "failure_probability", "predicted_failure_type", "recommended_decision"]),
                ReportSection(
                    section_id="manager-impact",
                    title="Operational impact",
                    body=(
                        f"Asset criticality is {equipment['criticality']}. The fixture-based estimated downtime exposure is "
                        f"{equipment['estimated_downtime_minutes']} minutes; this is a demo estimate, not measured production loss."
                    ),
                    evidence_field_ids=["equipment.criticality", "equipment.estimated_downtime_minutes"],
                ),
                ReportSection(section_id="manager-evidence", title="Key evidence", body=factor_text or "No validated factor currently supports an elevated risk assessment.", evidence_field_ids=factor_ids[:3]),
            ]
    else:
        interval = evidence["detected_interval"]
        if locale == "ko-KR":
            headline = f"{equipment_name} 근거 분석 · {status_label}"
            summary = (
                f"{interval['start']}부터 {interval['end']}까지의 관측에서 {failure_label}이 추정됐습니다. "
                f"고장 위험도는 {_probability_text(evidence, locale)}, 신뢰도는 {evidence['confidence']}입니다."
            )
            checklist = " / ".join(evidence["maintenance_context"]["checklist"])
            sections = [
                ReportSection(section_id="engineer-interval", title="이상 구간", body=summary, evidence_field_ids=["detected_interval.start", "detected_interval.end", "failure_probability", "confidence"]),
                ReportSection(section_id="engineer-factors", title="센서·파생변수 근거", body=factor_text or "품질 검증을 통과한 위험 요인이 없습니다.", evidence_field_ids=factor_ids),
                ReportSection(section_id="engineer-checklist", title="점검 체크리스트", body=checklist, evidence_field_ids=[*evidence["maintenance_context"]["source_refs"]]),
                ReportSection(section_id="engineer-manager-summary", title="매니저 보고용 요약", body=f"{status_label} 상태로 분류됐으며 권장 결정은 '{decision_label}'입니다. 현장 점검으로 원인을 확인해야 합니다.", evidence_field_ids=["status", "recommended_decision"]),
            ]
        else:
            headline = f"{equipment_name} evidence analysis · {status_label}"
            summary = (
                f"Observations from {interval['start']} to {interval['end']} indicate {failure_label.lower()}. "
                f"The estimated failure risk is {_probability_text(evidence, locale)} with {evidence['confidence']} confidence."
            )
            checklist = " / ".join([
                "Review the governed top factors",
                "Confirm the latest sensor window",
                "Check maintenance evidence before approval",
            ])
            sections = [
                ReportSection(section_id="engineer-interval", title="Anomaly interval", body=summary, evidence_field_ids=["detected_interval.start", "detected_interval.end", "failure_probability", "confidence"]),
                ReportSection(section_id="engineer-factors", title="Sensor and derived-variable evidence", body=factor_text or "No risk factor passed the governed quality checks.", evidence_field_ids=factor_ids),
                ReportSection(section_id="engineer-checklist", title="Inspection checklist", body=checklist, evidence_field_ids=[*evidence["maintenance_context"]["source_refs"]]),
                ReportSection(section_id="engineer-manager-summary", title="Manager briefing", body=f"The asset is classified as {status_label.lower()}, and the recommended decision is '{decision_label}'. A field inspection is required to confirm the cause.", evidence_field_ids=["status", "recommended_decision"]),
            ]

    return GroundedReport(
        report_id=f"RPT-{evidence['event_id']}-{role}-{resolved_report_type}-{locale}",
        event_id=evidence["event_id"],
        role=role,
        report_type=resolved_report_type,
        locale=locale,
        mode=mode,  # type: ignore[arg-type]
        headline=headline,
        summary=summary,
        status=status,
        confidence=evidence["confidence"],
        recommended_decision=evidence["recommended_decision"],
        sections=sections,
        actions=_actions(evidence, locale),
        citations=sorted(set(citations)),
        limitations=limitations,
        generated_at=evidence["generated_at"],
    )
