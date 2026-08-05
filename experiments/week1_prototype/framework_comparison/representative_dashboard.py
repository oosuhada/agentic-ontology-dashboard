"""Shared manufacturing-dashboard contract used by both framework adapters.

The benchmark deliberately keeps data loading and business aggregation in one
shared module. FastAPI and Flask therefore receive the same fixture records and
execute the same Python function; only request parsing, response validation and
HTTP serialization belong to the framework adapters.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = PROJECT_ROOT / "data" / "fixtures"


# Generated from ManufacturingPredictiveMaintenanceService.list_events() using
# the same GS-001..GS-008 fixtures on 2026-08-05. Keeping the evaluated risk
# output beside the raw fixtures makes this benchmark runnable in the small
# Week 1 comparison environment without importing the entire product backend.
PRODUCT_RISK_SNAPSHOT = {
    "EVT-GS-001": {
        "status": "normal",
        "failure_probability": 0.116074,
        "confidence": "high",
        "predicted_failure_type": "none",
        "recommended_decision": "continue_monitoring",
    },
    "EVT-GS-002": {
        "status": "warning",
        "failure_probability": 0.824583,
        "confidence": "high",
        "predicted_failure_type": "tool_wear_failure",
        "recommended_decision": "request_inspection",
    },
    "EVT-GS-003": {
        "status": "warning",
        "failure_probability": 0.602318,
        "confidence": "high",
        "predicted_failure_type": "heat_dissipation_failure",
        "recommended_decision": "request_inspection",
    },
    "EVT-GS-004": {
        "status": "critical",
        "failure_probability": 0.908411,
        "confidence": "high",
        "predicted_failure_type": "power_or_overstrain_failure",
        "recommended_decision": "review_shutdown",
    },
    "EVT-GS-005": {
        "status": "warning",
        "failure_probability": 0.771832,
        "confidence": "medium",
        "predicted_failure_type": "multi_factor_risk",
        "recommended_decision": "request_inspection",
    },
    "EVT-GS-006": {
        "status": "attention",
        "failure_probability": 0.294766,
        "confidence": "low",
        "predicted_failure_type": "uncertain",
        "recommended_decision": "request_inspection",
    },
    "EVT-GS-007": {
        "status": "data_quality_hold",
        "failure_probability": None,
        "confidence": "unavailable",
        "predicted_failure_type": "unavailable",
        "recommended_decision": "hold_for_data_check",
    },
    "EVT-GS-008": {
        "status": "warning",
        "failure_probability": 0.824583,
        "confidence": "high",
        "predicted_failure_type": "tool_wear_failure",
        "recommended_decision": "request_inspection",
    },
}


class DashboardSummary(BaseModel):
    total_assets: int
    visible_events: int
    critical_events: int
    warning_events: int
    data_quality_holds: int
    average_failure_probability: float | None
    estimated_downtime_minutes: int


class RiskEvent(BaseModel):
    event_id: str
    equipment_id: str
    equipment_name: str
    line: str
    criticality: str
    assigned_engineer: str
    status: str
    failure_probability: float | None
    confidence: str
    predicted_failure_type: str
    recommended_decision: str
    spare_part_available: bool
    estimated_downtime_minutes: int
    observation_timestamp: str


class LineRisk(BaseModel):
    line: str
    event_count: int
    critical_or_warning_count: int
    average_failure_probability: float | None


class SensorPoint(BaseModel):
    event_id: str
    equipment_id: str
    timestamp: str
    rotational_speed_rpm: float | None
    torque_nm: float | None
    tool_wear_min: float | None
    air_temperature_k: float | None
    process_temperature_k: float | None


class DecisionCount(BaseModel):
    decision: str
    count: int


class ManufacturingDashboardResponse(BaseModel):
    contract_version: Literal["manufacturing-dashboard-benchmark-v1"]
    project_id: Literal["manufacturing-demo-project"]
    workspace_id: Literal["manufacturing-demo"]
    source: Literal["product-gs-fixtures-and-risk-snapshot"]
    filters: dict[str, str | int | float | None]
    summary: DashboardSummary
    risk_events: list[RiskEvent]
    risk_by_line: list[LineRisk]
    sensor_series: list[SensorPoint]
    recommended_decisions: list[DecisionCount]
    generated_from_event_count: int = Field(ge=1)


RiskStatus = Literal[
    "critical",
    "warning",
    "attention",
    "data_quality_hold",
    "normal",
]
RiskSort = Literal[
    "probability_desc",
    "probability_asc",
    "event_id_asc",
    "line_asc",
]
OperatorRole = Literal[
    "process_manager",
    "process_engineer",
    "maintenance_engineer",
    "executive",
]


class RiskEventSearchResponse(BaseModel):
    contract_version: Literal["risk-event-search-benchmark-v1"]
    project_id: Literal["manufacturing-demo-project"]
    source: Literal["product-gs-fixtures-and-risk-snapshot"]
    filters: dict[str, str | int | float | None]
    total_matching: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[RiskEvent]


class MaintenanceRecommendationRequest(BaseModel):
    event_id: str = Field(min_length=1)
    operator_role: OperatorRole
    include_evidence: bool = True


class RecommendationEvidence(BaseModel):
    key: str
    label: str
    value: str | int | float | bool | None


class MaintenanceRecommendationResponse(BaseModel):
    contract_version: Literal["maintenance-recommendation-benchmark-v1"]
    project_id: Literal["manufacturing-demo-project"]
    event_id: str
    equipment_id: str
    equipment_name: str
    operator_role: OperatorRole
    priority: RiskStatus
    recommended_decision: str
    requires_shutdown_review: bool
    estimated_downtime_minutes: int = Field(ge=0)
    spare_part_available: bool
    confidence: str
    predicted_failure_type: str
    reasons: list[str]
    recommended_actions: list[str]
    evidence: list[RecommendationEvidence]
    generated_from_shared_rule: Literal[True]


class RepresentativeEventNotFound(KeyError):
    """Raised when the benchmark request references an unknown event."""


RISK_PRIORITY = {
    "critical": 0,
    "warning": 1,
    "attention": 2,
    "data_quality_hold": 3,
    "normal": 4,
}


@lru_cache(maxsize=1)
def _fixture_records() -> tuple[dict, ...]:
    records: list[dict] = []
    for path in sorted(FIXTURE_ROOT.glob("GS-*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        event_id = fixture["event_id"]
        risk = PRODUCT_RISK_SNAPSHOT[event_id]
        records.append({**fixture, "risk": risk})
    if len(records) != len(PRODUCT_RISK_SNAPSHOT):
        raise RuntimeError(
            f"Expected {len(PRODUCT_RISK_SNAPSHOT)} GS fixtures, found {len(records)}"
        )
    return tuple(records)


def build_manufacturing_dashboard(
    *,
    risk_threshold: float = 0.0,
    limit: int = 8,
    line: str | None = None,
) -> ManufacturingDashboardResponse:
    """Build one representative first-page dashboard response."""

    source_records = _fixture_records()
    event_rows: list[dict] = []
    sensor_series: list[SensorPoint] = []

    for fixture in source_records:
        equipment = fixture["equipment"]
        risk = fixture["risk"]
        probability = risk["failure_probability"]
        if line and equipment["line"] != line:
            continue
        if probability is not None and probability < risk_threshold:
            continue
        if probability is None and risk_threshold > 0:
            continue

        event_rows.append(
            {
                "event_id": fixture["event_id"],
                "equipment_id": equipment["equipment_id"],
                "equipment_name": equipment["display_name"],
                "line": equipment["line"],
                "criticality": equipment["criticality"],
                "assigned_engineer": equipment["assigned_engineer"],
                "status": risk["status"],
                "failure_probability": probability,
                "confidence": risk["confidence"],
                "predicted_failure_type": risk["predicted_failure_type"],
                "recommended_decision": risk["recommended_decision"],
                "spare_part_available": equipment["spare_part_available"],
                "estimated_downtime_minutes": equipment[
                    "estimated_downtime_minutes"
                ],
                "observation_timestamp": fixture["observation"]["timestamp"],
            }
        )
        for point in fixture["history"]:
            sensor_series.append(
                SensorPoint(
                    event_id=fixture["event_id"],
                    equipment_id=equipment["equipment_id"],
                    timestamp=point["timestamp"],
                    rotational_speed_rpm=point.get("rotational_speed_rpm"),
                    torque_nm=point.get("torque_nm"),
                    tool_wear_min=point.get("tool_wear_min"),
                    air_temperature_k=point.get("air_temperature_k"),
                    process_temperature_k=point.get("process_temperature_k"),
                )
            )

    event_rows.sort(
        key=lambda row: (
            RISK_PRIORITY[row["status"]],
            -(row["failure_probability"] or 0.0),
            row["event_id"],
        )
    )
    visible_rows = event_rows[:limit]
    visible_ids = {row["event_id"] for row in visible_rows}
    visible_series = [
        point for point in sensor_series if point.event_id in visible_ids
    ]

    probabilities = [
        row["failure_probability"]
        for row in visible_rows
        if row["failure_probability"] is not None
    ]
    by_line: dict[str, list[dict]] = defaultdict(list)
    for row in visible_rows:
        by_line[row["line"]].append(row)

    line_rows: list[LineRisk] = []
    for line_name, rows in sorted(by_line.items()):
        line_probabilities = [
            row["failure_probability"]
            for row in rows
            if row["failure_probability"] is not None
        ]
        line_rows.append(
            LineRisk(
                line=line_name,
                event_count=len(rows),
                critical_or_warning_count=sum(
                    row["status"] in {"critical", "warning"} for row in rows
                ),
                average_failure_probability=(
                    round(sum(line_probabilities) / len(line_probabilities), 6)
                    if line_probabilities
                    else None
                ),
            )
        )

    decision_counts = Counter(
        row["recommended_decision"] for row in visible_rows
    )
    response = ManufacturingDashboardResponse(
        contract_version="manufacturing-dashboard-benchmark-v1",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        source="product-gs-fixtures-and-risk-snapshot",
        filters={
            "risk_threshold": risk_threshold,
            "limit": limit,
            "line": line,
        },
        summary=DashboardSummary(
            total_assets=len({row["equipment_id"] for row in visible_rows}),
            visible_events=len(visible_rows),
            critical_events=sum(row["status"] == "critical" for row in visible_rows),
            warning_events=sum(row["status"] == "warning" for row in visible_rows),
            data_quality_holds=sum(
                row["status"] == "data_quality_hold" for row in visible_rows
            ),
            average_failure_probability=(
                round(sum(probabilities) / len(probabilities), 6)
                if probabilities
                else None
            ),
            estimated_downtime_minutes=sum(
                row["estimated_downtime_minutes"] for row in visible_rows
            ),
        ),
        risk_events=[RiskEvent(**row) for row in visible_rows],
        risk_by_line=line_rows,
        sensor_series=visible_series,
        recommended_decisions=[
            DecisionCount(decision=decision, count=count)
            for decision, count in sorted(decision_counts.items())
        ],
        generated_from_event_count=len(source_records),
    )
    return response


def _risk_event_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fixture in _fixture_records():
        equipment = fixture["equipment"]
        risk = fixture["risk"]
        rows.append(
            {
                "event_id": fixture["event_id"],
                "equipment_id": equipment["equipment_id"],
                "equipment_name": equipment["display_name"],
                "line": equipment["line"],
                "criticality": equipment["criticality"],
                "assigned_engineer": equipment["assigned_engineer"],
                "status": risk["status"],
                "failure_probability": risk["failure_probability"],
                "confidence": risk["confidence"],
                "predicted_failure_type": risk["predicted_failure_type"],
                "recommended_decision": risk["recommended_decision"],
                "spare_part_available": equipment["spare_part_available"],
                "estimated_downtime_minutes": equipment[
                    "estimated_downtime_minutes"
                ],
                "observation_timestamp": fixture["observation"]["timestamp"],
            }
        )
    return rows


def build_risk_event_search(
    *,
    risk_threshold: float = 0.0,
    status: RiskStatus | None = None,
    failure_type: str | None = None,
    line: str | None = None,
    sort: RiskSort = "probability_desc",
    limit: int = 5,
    offset: int = 0,
) -> RiskEventSearchResponse:
    """Filter, sort and paginate the same product risk-event snapshot."""

    rows = []
    for row in _risk_event_rows():
        probability = row["failure_probability"]
        if probability is None and risk_threshold > 0:
            continue
        if probability is not None and probability < risk_threshold:
            continue
        if status and row["status"] != status:
            continue
        if failure_type and row["predicted_failure_type"] != failure_type:
            continue
        if line and row["line"] != line:
            continue
        rows.append(row)

    if sort == "probability_desc":
        rows.sort(
            key=lambda item: (
                item["failure_probability"] is None,
                -(item["failure_probability"] or 0.0),
                item["event_id"],
            )
        )
    elif sort == "probability_asc":
        rows.sort(
            key=lambda item: (
                item["failure_probability"] is None,
                item["failure_probability"] or 0.0,
                item["event_id"],
            )
        )
    elif sort == "line_asc":
        rows.sort(key=lambda item: (item["line"], item["event_id"]))
    else:
        rows.sort(key=lambda item: item["event_id"])

    total_matching = len(rows)
    page = rows[offset : offset + limit]
    return RiskEventSearchResponse(
        contract_version="risk-event-search-benchmark-v1",
        project_id="manufacturing-demo-project",
        source="product-gs-fixtures-and-risk-snapshot",
        filters={
            "risk_threshold": risk_threshold,
            "status": status,
            "failure_type": failure_type,
            "line": line,
            "sort": sort,
        },
        total_matching=total_matching,
        offset=offset,
        limit=limit,
        items=[RiskEvent(**row) for row in page],
    )


def build_maintenance_recommendation(
    request: MaintenanceRecommendationRequest,
) -> MaintenanceRecommendationResponse:
    """Apply one deterministic maintenance-decision rule to a product event."""

    fixture = next(
        (
            item
            for item in _fixture_records()
            if item["event_id"] == request.event_id
        ),
        None,
    )
    if fixture is None:
        raise RepresentativeEventNotFound(request.event_id)

    equipment = fixture["equipment"]
    observation = fixture["observation"]
    risk = fixture["risk"]
    probability = risk["failure_probability"]
    reasons = [
        f"위험 상태가 {risk['status']}입니다.",
        (
            f"고장 확률이 {probability:.1%}입니다."
            if probability is not None
            else "신뢰 가능한 고장 확률을 계산할 수 없습니다."
        ),
        f"예측 고장 유형은 {risk['predicted_failure_type']}입니다.",
        f"설비 중요도는 {equipment['criticality']}입니다.",
    ]
    if risk["confidence"] in {"low", "unavailable"}:
        reasons.append(f"예측 신뢰도가 {risk['confidence']}이므로 추가 확인이 필요합니다.")
    if not equipment["spare_part_available"]:
        reasons.append("즉시 사용할 수 있는 대체 부품이 없습니다.")

    decision = risk["recommended_decision"]
    if decision == "review_shutdown":
        actions = ["운영 매니저의 설비 정지 검토", "담당 엔지니어 현장 점검"]
    elif decision == "request_inspection":
        actions = ["담당 엔지니어 점검 요청", "센서와 정비 이력 재확인"]
    elif decision == "hold_for_data_check":
        actions = ["센서 데이터 품질 확인", "검증 완료 전 자동 의사결정 보류"]
    else:
        actions = ["현재 운전 유지", "다음 관측 주기까지 위험 추세 모니터링"]
    if not equipment["spare_part_available"]:
        actions.append("대체 부품 확보 가능 시점 확인")

    evidence: list[RecommendationEvidence] = []
    if request.include_evidence:
        evidence = [
            RecommendationEvidence(
                key="failure_probability",
                label="고장 확률",
                value=probability,
            ),
            RecommendationEvidence(
                key="rotational_speed_rpm",
                label="회전 속도",
                value=observation.get("rotational_speed_rpm"),
            ),
            RecommendationEvidence(
                key="torque_nm",
                label="토크",
                value=observation.get("torque_nm"),
            ),
            RecommendationEvidence(
                key="tool_wear_min",
                label="공구 마모",
                value=observation.get("tool_wear_min"),
            ),
            RecommendationEvidence(
                key="spare_part_available",
                label="대체 부품 확보",
                value=equipment["spare_part_available"],
            ),
        ]

    return MaintenanceRecommendationResponse(
        contract_version="maintenance-recommendation-benchmark-v1",
        project_id="manufacturing-demo-project",
        event_id=fixture["event_id"],
        equipment_id=equipment["equipment_id"],
        equipment_name=equipment["display_name"],
        operator_role=request.operator_role,
        priority=risk["status"],
        recommended_decision=decision,
        requires_shutdown_review=decision == "review_shutdown",
        estimated_downtime_minutes=equipment["estimated_downtime_minutes"],
        spare_part_available=equipment["spare_part_available"],
        confidence=risk["confidence"],
        predicted_failure_type=risk["predicted_failure_type"],
        reasons=reasons,
        recommended_actions=actions,
        evidence=evidence,
        generated_from_shared_rule=True,
    )

