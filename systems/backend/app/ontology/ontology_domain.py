from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OntologyProperty(BaseModel):
    id: str
    display_name: str
    value_type: Literal["string", "number", "integer", "boolean", "datetime", "object", "array"]
    required: bool = False
    unit: str | None = None
    description: str | None = None


class ObjectTypeDefinition(BaseModel):
    id: str
    display_name: str
    description: str
    properties: list[OntologyProperty] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    domain_pack: str


class ObjectRecord(BaseModel):
    id: str
    object_type: str
    workspace_id: str
    properties: dict[str, Any]
    source_refs: list[str] = Field(default_factory=list)
    version: int = 1


class LinkTypeDefinition(BaseModel):
    id: str
    display_name: str
    source_type: str
    target_type: str
    cardinality: Literal["one-to-one", "one-to-many", "many-to-one", "many-to-many"]
    domain_pack: str


class LinkRecord(BaseModel):
    id: str
    link_type: str
    source_object_id: str
    target_object_id: str
    workspace_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    version: int = 1


class ActionParameter(BaseModel):
    id: str
    display_name: str
    value_type: Literal["string", "number", "integer", "boolean", "datetime", "object", "array"]
    required: bool = True


class ActionTypeDefinition(BaseModel):
    id: str
    display_name: str
    description: str
    object_type: str
    parameters: list[ActionParameter] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True
    domain_pack: str


class ActionInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1, max_length=120)
    object_id: str = Field(min_length=3, max_length=240)
    workspace_id: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=200)


class ActionExecutionResult(BaseModel):
    invocation_id: str
    action_type: str
    object_id: str
    workspace_id: str
    state: Literal["succeeded"] = "succeeded"
    replayed: bool = False
    result: dict[str, Any]
    audit_id: str
    created_at: str
    completed_at: str


class OntologyTraversal(BaseModel):
    root: ObjectRecord
    nodes: list[ObjectRecord]
    edges: list[LinkRecord]
    direction: Literal["outgoing", "incoming", "both"]
    depth: int


class EvidenceReference(BaseModel):
    id: str
    evidence_type: str
    object_id: str
    source_refs: list[str]
    generated_at: str
    version: int = 1


class BoardDefinition(BaseModel):
    id: str
    display_name: str
    category: Literal["suggested", "observe", "explore", "explain", "act", "audit", "build"]
    object_types: list[str]
    emits: list[str] = Field(default_factory=list)
    accepts: list[str] = Field(default_factory=list)
    allowed_roles: list[str]
    minimum_width: int = 3
    maximum_width: int = 12


class DashboardDefinition(BaseModel):
    id: str
    display_name: str
    workspace_id: str
    role_code: str
    tabs: list[str]
    mandatory_board_ids: list[str] = Field(default_factory=list)
    version: int = 1


OBJECT_TYPES: tuple[ObjectTypeDefinition, ...] = (
    ObjectTypeDefinition(
        id="telemetry_observation",
        display_name="Telemetry Observation",
        description=(
            "Adaptive Modeling과 semantic query가 사용하는 센서 관측 schema입니다. "
            "원본 관측 행은 PostgreSQL에 유지하며 기본 Ontology/Neo4j object로 물질화하지 않습니다."
        ),
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["observation", "versioned", "model-input"],
        properties=[
            OntologyProperty(id="equipment_id", display_name="설비 ID", value_type="string", required=True),
            OntologyProperty(id="observed_at", display_name="관측 시각", value_type="datetime", required=True),
            OntologyProperty(id="product_type", display_name="제품 유형", value_type="string"),
            OntologyProperty(id="equipment_age_years", display_name="설비 연령", value_type="number", unit="year"),
            OntologyProperty(id="voltage_v", display_name="전압", value_type="number", unit="V"),
            OntologyProperty(id="rotational_speed_rpm", display_name="회전 속도", value_type="number", unit="rpm"),
            OntologyProperty(id="pressure", display_name="압력", value_type="number"),
            OntologyProperty(id="vibration", display_name="진동", value_type="number"),
            OntologyProperty(id="air_temperature_k", display_name="공기 온도", value_type="number", unit="K"),
            OntologyProperty(id="process_temperature_k", display_name="공정 온도", value_type="number", unit="K"),
            OntologyProperty(id="torque_nm", display_name="토크", value_type="number", unit="N·m"),
            OntologyProperty(id="tool_wear_min", display_name="공구 마모", value_type="number", unit="minute"),
            OntologyProperty(id="machine_failure", display_name="고장 라벨", value_type="boolean"),
        ],
    ),
    ObjectTypeDefinition(
        id="site",
        display_name="Site",
        description="Dataset Version 안에서 설비와 생산 셀을 묶는 물리 사이트입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["location", "versioned"],
        properties=[
            OntologyProperty(id="display_name", display_name="사이트명", value_type="string", required=True),
            OntologyProperty(id="dataset_version_id", display_name="Dataset Version", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="production_cell",
        display_name="Production Cell",
        description="사이트 하위의 설비 운영 단위입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["location", "versioned"],
        properties=[
            OntologyProperty(id="display_name", display_name="생산 셀명", value_type="string", required=True),
            OntologyProperty(id="site_id", display_name="사이트 ID", value_type="string", required=True),
            OntologyProperty(id="dataset_version_id", display_name="Dataset Version", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="equipment",
        display_name="Equipment",
        description="운영 상태와 정비 이력을 가지는 제조 설비 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["asset", "maintainable"],
        properties=[
            OntologyProperty(id="display_name", display_name="설비명", value_type="string", required=True),
            OntologyProperty(id="line", display_name="라인", value_type="string", required=True),
            OntologyProperty(id="criticality", display_name="중요도", value_type="string", required=True),
            OntologyProperty(id="assigned_engineer", display_name="담당 엔지니어", value_type="string"),
        ],
    ),
    ObjectTypeDefinition(
        id="risk_event",
        display_name="Risk Event",
        description="모델 결과, 정책 판정과 운영 상태를 묶는 위험 사건 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["event", "evidence-bearing"],
        properties=[
            OntologyProperty(id="status", display_name="상태", value_type="string", required=True),
            OntologyProperty(id="failure_probability", display_name="고장 확률", value_type="number"),
            OntologyProperty(id="recommended_decision", display_name="권장 판단", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="prediction_result",
        display_name="Prediction Result",
        description="등록된 binary failure-within-horizon 예측 결과와 provenance입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["event", "evidence-bearing", "versioned"],
        properties=[
            OntologyProperty(id="prediction_task", display_name="예측 과업", value_type="string", required=True),
            OntologyProperty(id="failure_probability", display_name="고장 확률", value_type="number", required=True),
            OntologyProperty(id="predicted_failure_type", display_name="Binary 위험 클래스", value_type="string", required=True),
            OntologyProperty(id="observed_at", display_name="관측 시각", value_type="datetime", required=True),
            OntologyProperty(id="dataset_version_id", display_name="Dataset Version", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="production_cycle",
        display_name="Production Cycle",
        description="Ontology 탐색용으로 선별된 최신 생산 cycle입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["event", "versioned"],
        properties=[
            OntologyProperty(id="product_id", display_name="제품 ID", value_type="string", required=True),
            OntologyProperty(id="cycle_started_at", display_name="시작 시각", value_type="datetime", required=True),
            OntologyProperty(id="cycle_completed_at", display_name="완료 시각", value_type="datetime", required=True),
            OntologyProperty(id="dataset_version_id", display_name="Dataset Version", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="evidence_package",
        display_name="Evidence Package",
        description="입력, 모델, 정책, 설명과 lineage를 재구성할 수 있는 검증 근거입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["evidence-bearing", "versioned"],
        properties=[
            OntologyProperty(id="model_version", display_name="모델 버전", value_type="string", required=True),
            OntologyProperty(id="policy_version", display_name="정책 버전", value_type="string", required=True),
            OntologyProperty(id="generated_at", display_name="생성 시각", value_type="datetime", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="work_order",
        display_name="Work Order",
        description="설비 점검·정비 요청, 체크리스트, 담당자와 현장 결과를 연결하는 canonical 업무 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["task", "auditable", "maintainable"],
        properties=[
            OntologyProperty(id="status", display_name="작업 상태", value_type="string", required=True),
            OntologyProperty(id="assignee", display_name="담당자", value_type="string"),
            OntologyProperty(id="due_at", display_name="기한", value_type="datetime"),
            OntologyProperty(id="work_type", display_name="작업 유형", value_type="string"),
            OntologyProperty(id="event_id", display_name="연결 위험 사건", value_type="string"),
        ],
    ),
    ObjectTypeDefinition(
        id="inspection",
        display_name="Inspection (legacy alias)",
        description="기존 API 호환을 위한 deprecated alias입니다. 신규 구현은 work_order를 사용합니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["task", "auditable"],
        properties=[
            OntologyProperty(id="status", display_name="점검 상태", value_type="string", required=True),
            OntologyProperty(id="assignee", display_name="담당자", value_type="string"),
            OntologyProperty(id="due_at", display_name="기한", value_type="datetime"),
            OntologyProperty(id="canonical_work_order_id", display_name="Canonical Work Order ID", value_type="string"),
        ],
    ),
    ObjectTypeDefinition(
        id="maintenance_action",
        display_name="Maintenance Action",
        description="사람이 승인하고 기록한 정비 관련 행동입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["action-record", "auditable"],
        properties=[
            OntologyProperty(id="action", display_name="행동", value_type="string", required=True),
            OntologyProperty(id="actor", display_name="수행자", value_type="string", required=True),
            OntologyProperty(id="created_at", display_name="수행 시각", value_type="datetime", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="company",
        display_name="Company",
        description="조직·재무·운영 문맥의 최상위 회사 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["organization", "context"],
        properties=[
            OntologyProperty(id="name", display_name="회사명", value_type="string", required=True),
            OntologyProperty(id="industry", display_name="산업", value_type="string"),
            OntologyProperty(id="currency", display_name="기준 통화", value_type="string"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="organization_unit",
        display_name="Organization Unit",
        description="역할별 의사결정과 handoff 책임을 설명하는 데모 조직 단위입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["organization", "actor-context"],
        properties=[
            OntologyProperty(id="name", display_name="조직명", value_type="string", required=True),
            OntologyProperty(id="leader", display_name="책임자", value_type="string"),
            OntologyProperty(id="responsibilities", display_name="책임", value_type="array"),
            OntologyProperty(id="persona_roles", display_name="Persona 역할", value_type="array"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="product",
        display_name="Product",
        description="생산 영향과 경영 보고 환산에 쓰는 제품 경제성 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["business-context"],
        properties=[
            OntologyProperty(id="variant", display_name="제품 Variant", value_type="string", required=True),
            OntologyProperty(id="name", display_name="제품명", value_type="string", required=True),
            OntologyProperty(id="unit_sales_price_krw", display_name="단위 매출", value_type="number", unit="KRW"),
            OntologyProperty(id="unit_material_cost_krw", display_name="단위 재료비", value_type="number", unit="KRW"),
            OntologyProperty(id="unit_contribution_margin_krw", display_name="단위 공헌이익", value_type="number", unit="KRW"),
            OntologyProperty(id="daily_plan_units", display_name="일 계획 수량", value_type="integer", unit="unit"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="material",
        display_name="Material / Spare Part",
        description="정비와 생산 영향 판단에 쓰는 자재·예비품 master입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["inventory", "business-context"],
        properties=[
            OntologyProperty(id="name", display_name="자재명", value_type="string", required=True),
            OntologyProperty(id="category", display_name="분류", value_type="string"),
            OntologyProperty(id="unit_cost_krw", display_name="단가", value_type="number", unit="KRW"),
            OntologyProperty(id="on_hand_quantity", display_name="가용 재고", value_type="integer"),
            OntologyProperty(id="reorder_point", display_name="재주문점", value_type="integer"),
            OntologyProperty(id="lead_time_days", display_name="조달 리드타임", value_type="integer", unit="day"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="maintenance_history_record",
        display_name="Historical Maintenance Record",
        description="현재 closed-loop 상태와 연결해 비교할 수 있는 과거 정비 이력입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["history", "maintainable", "evidence-bearing"],
        properties=[
            OntologyProperty(id="asset_id", display_name="설비 ID", value_type="string", required=True),
            OntologyProperty(id="occurred_at", display_name="발생 시각", value_type="datetime", required=True),
            OntologyProperty(id="work_type", display_name="작업 유형", value_type="string"),
            OntologyProperty(id="component", display_name="대상 부품", value_type="string"),
            OntologyProperty(id="symptom", display_name="증상", value_type="string"),
            OntologyProperty(id="action", display_name="조치", value_type="string"),
            OntologyProperty(id="result", display_name="결과", value_type="string"),
            OntologyProperty(id="downtime_minutes", display_name="비가동 시간", value_type="integer", unit="minute"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="meeting_record",
        display_name="Meeting Record",
        description="과거 운영 판단의 배경을 RAG와 lineage에서 조회하기 위한 회의록입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["document", "decision-context"],
        properties=[
            OntologyProperty(id="title", display_name="회의명", value_type="string", required=True),
            OntologyProperty(id="occurred_at", display_name="회의 시각", value_type="datetime", required=True),
            OntologyProperty(id="attendees", display_name="참석 조직", value_type="array"),
            OntologyProperty(id="summary", display_name="회의 요약", value_type="string"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="decision_record",
        display_name="Decision Record",
        description="과거 운영·경영 의사결정을 현재 Decision Case의 참고 근거로 연결하는 기록입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["decision-context", "auditable"],
        properties=[
            OntologyProperty(id="title", display_name="판단 제목", value_type="string", required=True),
            OntologyProperty(id="decided_at", display_name="판단 시각", value_type="datetime", required=True),
            OntologyProperty(id="decision", display_name="판단 내용", value_type="string", required=True),
            OntologyProperty(id="owner_org_unit_id", display_name="책임 조직", value_type="string"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
    ObjectTypeDefinition(
        id="business_metric",
        display_name="Business Metric",
        description="경영진 보고의 KPI와 목표 문맥에 쓰는 business metric입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["metric", "business-context"],
        properties=[
            OntologyProperty(id="name", display_name="지표명", value_type="string", required=True),
            OntologyProperty(id="period", display_name="기간", value_type="string"),
            OntologyProperty(id="value", display_name="값", value_type="number"),
            OntologyProperty(id="unit", display_name="단위", value_type="string"),
            OntologyProperty(id="source_label", display_name="출처", value_type="string"),
            OntologyProperty(id="context_kind", display_name="문맥 구분", value_type="string", required=True),
        ],
    ),
)

LINK_TYPES: tuple[LinkTypeDefinition, ...] = (
    LinkTypeDefinition(
        id="site_contains_cell",
        display_name="Site contains Production Cell",
        source_type="site",
        target_type="production_cell",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="cell_contains_equipment",
        display_name="Production Cell contains Equipment",
        source_type="production_cell",
        target_type="equipment",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_supplies_air_to_equipment",
        display_name="Equipment supplies air to Equipment",
        source_type="equipment",
        target_type="equipment",
        cardinality="many-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_has_risk_event",
        display_name="Equipment has Risk Event",
        source_type="equipment",
        target_type="risk_event",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="risk_event_has_evidence",
        display_name="Risk Event has Evidence",
        source_type="risk_event",
        target_type="evidence_package",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_has_work_order",
        display_name="Equipment has Work Order",
        source_type="equipment",
        target_type="work_order",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_has_prediction_result",
        display_name="Equipment has Prediction Result",
        source_type="equipment",
        target_type="prediction_result",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="risk_event_supported_by_prediction_result",
        display_name="Risk Event supported by Prediction Result",
        source_type="risk_event",
        target_type="prediction_result",
        cardinality="many-to-one",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="risk_event_requires_work_order",
        display_name="Risk Event requires Work Order",
        source_type="risk_event",
        target_type="work_order",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="work_order_records_action",
        display_name="Work Order records Maintenance Action",
        source_type="work_order",
        target_type="maintenance_action",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="work_order_has_maintenance_action",
        display_name="Work Order has Maintenance Action",
        source_type="work_order",
        target_type="maintenance_action",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_completed_production_cycle",
        display_name="Equipment completed Production Cycle",
        source_type="equipment",
        target_type="production_cycle",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="risk_event_requires_inspection",
        display_name="Risk Event requires Inspection (legacy alias)",
        source_type="risk_event",
        target_type="inspection",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="inspection_records_action",
        display_name="Inspection records Maintenance Action (legacy alias)",
        source_type="inspection",
        target_type="maintenance_action",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="company_has_organization_unit",
        display_name="Company has Organization Unit",
        source_type="company",
        target_type="organization_unit",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="company_sells_product",
        display_name="Company sells Product",
        source_type="company",
        target_type="product",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="company_has_material",
        display_name="Company has Material",
        source_type="company",
        target_type="material",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="company_has_business_metric",
        display_name="Company has Business Metric",
        source_type="company",
        target_type="business_metric",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_uses_material",
        display_name="Equipment uses Material",
        source_type="equipment",
        target_type="material",
        cardinality="many-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="equipment_has_maintenance_history",
        display_name="Equipment has Historical Maintenance Record",
        source_type="equipment",
        target_type="maintenance_history_record",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="meeting_records_decision",
        display_name="Meeting records Decision",
        source_type="meeting_record",
        target_type="decision_record",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="organization_owns_decision",
        display_name="Organization Unit owns Decision",
        source_type="organization_unit",
        target_type="decision_record",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="decision_concerns_equipment",
        display_name="Decision concerns Equipment",
        source_type="decision_record",
        target_type="equipment",
        cardinality="many-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
)

ACTION_TYPES: tuple[ActionTypeDefinition, ...] = (
    ActionTypeDefinition(
        id="record_operational_decision",
        display_name="운영 판단 기록",
        description="사건에 대한 사람의 판단과 근거 메모를 감사 가능하게 기록합니다.",
        object_type="risk_event",
        parameters=[
            ActionParameter(id="decision", display_name="판단", value_type="string"),
            ActionParameter(id="note", display_name="근거 메모", value_type="string", required=False),
        ],
        required_permissions=["events.decision"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="record_work_order_note",
        display_name="Work Order 기록 추가",
        description="Canonical Work Order에 현장 점검 또는 handoff 메모를 기록합니다.",
        object_type="work_order",
        parameters=[ActionParameter(id="body", display_name="작업 기록", value_type="string")],
        required_permissions=["events.note"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="complete_work_order",
        display_name="Work Order 완료",
        description="체크리스트, 측정값, 사진 metadata와 handoff 메모를 포함해 Work Order를 완료합니다.",
        object_type="work_order",
        parameters=[
            ActionParameter(id="checklist", display_name="완료 체크리스트", value_type="array"),
            ActionParameter(id="measurements", display_name="측정값", value_type="object", required=False),
            ActionParameter(id="photo_metadata", display_name="사진 metadata", value_type="array", required=False),
            ActionParameter(id="note", display_name="Handoff 메모", value_type="string", required=False),
            ActionParameter(id="location", display_name="작업 위치", value_type="string", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="report_work_order_issue",
        display_name="Work Order 문제 발견",
        description="현장 문제, 측정값과 사진 metadata를 canonical Work Order에 기록합니다.",
        object_type="work_order",
        parameters=[
            ActionParameter(id="checklist", display_name="확인 체크리스트", value_type="array", required=False),
            ActionParameter(id="measurements", display_name="측정값", value_type="object", required=False),
            ActionParameter(id="photo_metadata", display_name="사진 metadata", value_type="array", required=False),
            ActionParameter(id="note", display_name="문제 설명", value_type="string"),
            ActionParameter(id="location", display_name="발견 위치", value_type="string", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="mark_work_order_blocked",
        display_name="Work Order 작업 불가",
        description="안전·접근·부품 문제로 Work Order를 수행할 수 없음을 기록합니다.",
        object_type="work_order",
        parameters=[
            ActionParameter(id="note", display_name="작업 불가 사유", value_type="string"),
            ActionParameter(id="location", display_name="작업 위치", value_type="string", required=False),
            ActionParameter(id="safety_risk", display_name="안전 위험", value_type="boolean", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="record_inspection_note",
        display_name="점검 기록 추가",
        description="현장 점검 또는 handoff 메모를 기록합니다.",
        object_type="inspection",
        parameters=[ActionParameter(id="body", display_name="점검 기록", value_type="string")],
        required_permissions=["events.note"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="complete_inspection",
        display_name="현장 작업 완료",
        description="체크리스트, 측정값, 사진 metadata와 handoff 메모를 포함해 점검을 완료합니다.",
        object_type="inspection",
        parameters=[
            ActionParameter(id="checklist", display_name="완료 체크리스트", value_type="array"),
            ActionParameter(id="measurements", display_name="측정값", value_type="object", required=False),
            ActionParameter(id="photo_metadata", display_name="사진 metadata", value_type="array", required=False),
            ActionParameter(id="note", display_name="Handoff 메모", value_type="string", required=False),
            ActionParameter(id="location", display_name="작업 위치", value_type="string", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="report_inspection_issue",
        display_name="문제 발견 기록",
        description="현장 문제, 측정값과 사진 metadata를 기록하고 엔지니어 handoff를 생성합니다.",
        object_type="inspection",
        parameters=[
            ActionParameter(id="checklist", display_name="확인 체크리스트", value_type="array", required=False),
            ActionParameter(id="measurements", display_name="측정값", value_type="object", required=False),
            ActionParameter(id="photo_metadata", display_name="사진 metadata", value_type="array", required=False),
            ActionParameter(id="note", display_name="문제 설명", value_type="string"),
            ActionParameter(id="location", display_name="발견 위치", value_type="string", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
    ActionTypeDefinition(
        id="mark_inspection_blocked",
        display_name="작업 불가 기록",
        description="안전·접근·부품 문제로 작업할 수 없음을 기록합니다.",
        object_type="inspection",
        parameters=[
            ActionParameter(id="note", display_name="작업 불가 사유", value_type="string"),
            ActionParameter(id="location", display_name="작업 위치", value_type="string", required=False),
            ActionParameter(id="safety_risk", display_name="안전 위험", value_type="boolean", required=False),
        ],
        required_permissions=["field.tasks.update"],
        domain_pack="manufacturing-predictive-maintenance",
    ),
)

OBJECT_TYPE_BY_ID = {item.id: item for item in OBJECT_TYPES}
LINK_TYPE_BY_ID = {item.id: item for item in LINK_TYPES}
ACTION_TYPE_BY_ID = {item.id: item for item in ACTION_TYPES}

PREDICTIVE_MAINTENANCE_ONTOLOGY_ID = "manufacturing-predictive-maintenance"


def registry_payload() -> dict[str, Any]:
    """Return the Ontology-owned Object/Link/Action registry.

    Generic domain-pack discovery and multi-pack selection were explicitly retired
    by the Phase 0.5 disposition.  The registry therefore exposes only Ontology
    concepts; PdM projection selection is a composition concern, not a registry.
    """
    return {
        "object_types": [item.model_dump(mode="json") for item in OBJECT_TYPES],
        "link_types": [item.model_dump(mode="json") for item in LINK_TYPES],
        "action_types": [item.model_dump(mode="json") for item in ACTION_TYPES],
    }
