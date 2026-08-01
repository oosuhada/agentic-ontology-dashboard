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


class DomainPackDefinition(BaseModel):
    id: str
    display_name: str
    description: str
    workspace_ids: list[str]
    object_type_ids: list[str]
    link_type_ids: list[str]
    action_type_ids: list[str]
    status: Literal["active", "draft", "disabled"] = "active"


OBJECT_TYPES: tuple[ObjectTypeDefinition, ...] = (
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
        id="inspection",
        display_name="Inspection",
        description="점검 요청, 체크리스트와 현장 결과를 연결하는 업무 객체입니다.",
        domain_pack="manufacturing-predictive-maintenance",
        interfaces=["task", "auditable"],
        properties=[
            OntologyProperty(id="status", display_name="점검 상태", value_type="string", required=True),
            OntologyProperty(id="assignee", display_name="담당자", value_type="string"),
            OntologyProperty(id="due_at", display_name="기한", value_type="datetime"),
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
)

LINK_TYPES: tuple[LinkTypeDefinition, ...] = (
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
        id="risk_event_requires_inspection",
        display_name="Risk Event requires Inspection",
        source_type="risk_event",
        target_type="inspection",
        cardinality="one-to-many",
        domain_pack="manufacturing-predictive-maintenance",
    ),
    LinkTypeDefinition(
        id="inspection_records_action",
        display_name="Inspection records Maintenance Action",
        source_type="inspection",
        target_type="maintenance_action",
        cardinality="one-to-many",
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


MANUFACTURING_PACK = DomainPackDefinition(
    id="manufacturing-predictive-maintenance",
    display_name="Manufacturing Predictive Maintenance Pack",
    description="초기 제조 예지보전 vertical slice를 유지하는 Ontology Dashboard의 첫 domain pack입니다.",
    workspace_ids=["manufacturing-demo"],
    object_type_ids=[item.id for item in OBJECT_TYPES],
    link_type_ids=[item.id for item in LINK_TYPES],
    action_type_ids=[item.id for item in ACTION_TYPES],
)


def registry_payload() -> dict[str, Any]:
    return {
        "domain_packs": [MANUFACTURING_PACK.model_dump(mode="json")],
        "object_types": [item.model_dump(mode="json") for item in OBJECT_TYPES],
        "link_types": [item.model_dump(mode="json") for item in LINK_TYPES],
        "action_types": [item.model_dump(mode="json") for item in ACTION_TYPES],
    }
