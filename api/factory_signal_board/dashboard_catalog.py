from __future__ import annotations

from datetime import datetime, timezone

from .dashboard_models import (
    BoardCatalogDefinition,
    DashboardBoard,
    DashboardBoardLayout,
    DashboardParameterDefinition,
    DashboardTab,
    DashboardTemplateSnapshot,
)

ALL_ROLES = [
    "tenant_admin",
    "executive_viewer",
    "process_manager",
    "process_engineer",
    "maintenance_technician",
    "quality_auditor",
    "ml_validator",
    "fde",
]

PARAMETER_DEFINITIONS = [
    DashboardParameterDefinition(
        id="selected_event_id",
        display_name="선택 Risk Event",
        value_type="string",
        default_value="",
        description="Risk Event 선택을 downstream board에 전달합니다.",
    ),
    DashboardParameterDefinition(
        id="selected_equipment_id",
        display_name="선택 Equipment",
        value_type="string",
        default_value="",
        description="Equipment context를 전달합니다.",
    ),
    DashboardParameterDefinition(
        id="status_filter",
        display_name="상태 필터",
        value_type="string",
        default_value="all",
        options=["all", "critical", "warning", "attention", "data_quality_hold", "normal"],
    ),
    DashboardParameterDefinition(
        id="intent",
        display_name="화면 관점",
        value_type="string",
        default_value="overview",
        options=[
            "overview",
            "explain-risk",
            "compare",
            "summarize-manager",
            "detail-engineer",
            "recommend-check",
            "show-model-details",
        ],
    ),
]


def _definition(
    *,
    id: str,
    display_name: str,
    description: str,
    category: str,
    renderer: str,
    allowed_roles: list[str] | None = None,
    object_types: list[str] | None = None,
    emits: list[str] | None = None,
    accepts: list[str] | None = None,
    default_width: int = 6,
    minimum_width: int = 4,
    maximum_width: int = 12,
    allow_multiple: bool = False,
    default_settings: dict | None = None,
    default_data_binding: dict | None = None,
    default_render_spec: dict | None = None,
) -> BoardCatalogDefinition:
    accepted = accepts or []
    return BoardCatalogDefinition(
        id=id,
        display_name=display_name,
        description=description,
        category=category,
        renderer=renderer,
        allowed_roles=allowed_roles or ALL_ROLES,
        object_types=object_types or [],
        emits=emits or [],
        accepts=accepted,
        binding_schema={parameter_id: "string" for parameter_id in accepted},
        default_width=default_width,
        minimum_width=minimum_width,
        maximum_width=maximum_width,
        allow_multiple=allow_multiple,
        default_settings=default_settings or {},
        default_data_binding=default_data_binding,
        default_render_spec=default_render_spec,
    )


BOARD_CATALOG: tuple[BoardCatalogDefinition, ...] = (
    _definition(
        id="object-context",
        display_name="Object Context",
        description="현재 선택한 Equipment와 Risk Event context를 표시합니다.",
        category="suggested",
        renderer="ObjectContext",
        object_types=["equipment", "risk_event"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["status_filter"],
        default_width=4,
        allow_multiple=True,
    ),
    _definition(
        id="operations-kpi",
        display_name="Operations KPI Strip",
        description="현재 parameter scope의 사건 수, critical 상태, 평균 위험과 downtime exposure를 고밀도 KPI로 표시합니다.",
        category="observe",
        renderer="OperationsKpi",
        object_types=["risk_event", "equipment"],
        accepts=["status_filter"],
        default_width=12,
        allow_multiple=True,
        default_settings={"height_units": "1"},
    ),
    _definition(
        id="risk-trend-workbench",
        display_name="Interactive Risk Trend",
        description="Risk와 downtime 지표를 전환하고 chart 선택을 Object Context로 전파합니다.",
        category="explore",
        renderer="RiskTrendWorkbench",
        object_types=["risk_event", "equipment"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["status_filter"],
        default_width=6,
        allow_multiple=True,
        default_settings={"height_units": "4"},
    ),
    _definition(
        id="risk-by-status-generic",
        display_name="Risk by Status (RenderSpec)",
        description="DataBinding과 RenderSpec만으로 실행되는 신규 generic chart board입니다.",
        category="explore",
        renderer="GenericDataBoard",
        object_types=["risk_event"],
        emits=["status_filter"],
        accepts=["status_filter"],
        default_width=6,
        allow_multiple=True,
        default_settings={"height_units": "4"},
        default_data_binding={
            "source": "object_set",
            "object_type": "risk_event",
            "fields": ["status", "failure_probability"],
        },
        default_render_spec={
            "kind": "bar",
            "x_field": "status",
            "y_field": "risk",
            "aggregation": "avg",
            "selectable": True,
            "brushable": True,
        },
    ),
    _definition(
        id="event-data-grid",
        display_name="Risk Event Data Grid",
        description="검색, 정렬, row limit과 object drill-down을 제공하는 고밀도 결과 테이블입니다.",
        category="explore",
        renderer="EventDataGrid",
        object_types=["risk_event", "equipment"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["status_filter"],
        default_width=12,
        allow_multiple=True,
        default_settings={"height_units": "5"},
    ),
    _definition(
        id="ontology-relationship",
        display_name="Ontology Relationship Graph",
        description="Equipment → Risk Event → Evidence → Action 관계와 같은 line의 연결 object를 탐색합니다.",
        category="explain",
        renderer="OntologyRelationship",
        object_types=["equipment", "risk_event", "evidence_package", "maintenance_action"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["selected_event_id"],
        default_width=6,
        allow_multiple=True,
        default_settings={"height_units": "4"},
    ),
    _definition(
        id="activity-stream",
        display_name="Operational Activity Stream",
        description="Evidence, report, signal과 object 변경을 시간순 운영 스트림으로 표시합니다.",
        category="audit",
        renderer="ActivityStream",
        object_types=["risk_event", "evidence_package", "maintenance_action"],
        emits=["selected_event_id"],
        accepts=["selected_event_id", "status_filter"],
        default_width=6,
        allow_multiple=True,
        default_settings={"height_units": "4"},
    ),
    _definition(
        id="analysis-result",
        display_name="Analysis Result Reference",
        description="Analysis Path의 특정 board revision을 값 복제 없이 참조합니다.",
        category="explore",
        renderer="AnalysisReference",
        object_types=["analysis", "analysis_board"],
        accepts=["selected_event_id", "status_filter"],
        default_width=8,
        minimum_width=4,
        allow_multiple=True,
        default_settings={"height_units": "3"},
    ),
    _definition(
        id="status-summary",
        display_name="Status Summary",
        description="현재 사건의 상태와 권장 판단을 요약합니다.",
        category="observe",
        renderer="StatusSummary",
        object_types=["risk_event"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="risk-kpi",
        display_name="Risk KPI",
        description="확률, threshold, 신뢰도와 상태를 비교합니다.",
        category="observe",
        renderer="RiskKpi",
        allowed_roles=["tenant_admin", "executive_viewer", "process_manager", "quality_auditor", "ml_validator", "fde"],
        object_types=["risk_event"],
        accepts=["selected_event_id", "status_filter"],
        default_width=6,
    ),
    _definition(
        id="priority-list",
        display_name="Risk Event Priority",
        description="위험 우선순위 사건 목록을 선택 가능한 board로 표시합니다.",
        category="observe",
        renderer="PriorityList",
        object_types=["risk_event", "equipment"],
        emits=["selected_event_id", "selected_equipment_id"],
        accepts=["status_filter"],
        default_width=12,
    ),
    _definition(
        id="impact-summary",
        display_name="Operational Impact",
        description="예상 downtime과 운영 영향 정보를 표시합니다.",
        category="explain",
        renderer="ImpactSummary",
        allowed_roles=["tenant_admin", "executive_viewer", "process_manager", "fde"],
        object_types=["equipment", "risk_event"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="manager-decision",
        display_name="Operational Decision",
        description="권장 판단을 검토하고 사람의 결정을 기록합니다.",
        category="act",
        renderer="ManagerDecisionCard",
        allowed_roles=["tenant_admin", "process_manager"],
        object_types=["risk_event"],
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="sensor-line-chart",
        display_name="Sensor Trend",
        description="선택 사건의 센서 시계열을 비교합니다.",
        category="explore",
        renderer="SensorLineChart",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician", "quality_auditor", "ml_validator", "fde"],
        object_types=["risk_event", "evidence_package"],
        accepts=["selected_event_id"],
        emits=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="anomaly-timeline",
        display_name="Anomaly Timeline",
        description="탐지 구간과 주요 시점을 확인합니다.",
        category="explore",
        renderer="AnomalyTimeline",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician", "quality_auditor", "ml_validator", "fde"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="factor-contribution",
        display_name="Factor Contribution",
        description="위험 판단에 기여한 주요 근거를 표시합니다.",
        category="explain",
        renderer="FactorContribution",
        allowed_roles=["tenant_admin", "process_engineer", "quality_auditor", "ml_validator", "fde", "process_manager"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="evidence-table",
        display_name="Evidence Table",
        description="관측·파생 근거와 lineage를 표로 검토합니다.",
        category="audit",
        renderer="EvidenceTable",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician", "quality_auditor", "ml_validator", "fde"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="recommended-actions",
        display_name="Recommended Actions",
        description="Evidence와 정책에 근거한 권장 조치를 표시합니다.",
        category="act",
        renderer="RecommendedActions",
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="engineer-checklist",
        display_name="Inspection Checklist",
        description="현장 점검 항목과 메모 Action을 제공합니다.",
        category="act",
        renderer="EngineerChecklist",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician", "fde"],
        object_types=["inspection"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="data-quality-warning",
        display_name="Data Quality Warning",
        description="입력 품질 문제와 판단 보류 조건을 표시합니다.",
        category="audit",
        renderer="DataQualityWarning",
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="model-details",
        display_name="Model & Policy Details",
        description="모델·정책 버전, threshold와 lineage를 확인합니다.",
        category="audit",
        renderer="ModelDetails",
        allowed_roles=["tenant_admin", "process_engineer", "quality_auditor", "ml_validator", "fde"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="conversation-thread",
        display_name="Grounded Follow-up",
        description="허용된 intent 범위에서 근거 기반 후속 질문을 수행합니다.",
        category="explain",
        renderer="ConversationThread",
        accepts=["selected_event_id", "intent"],
        emits=["intent"],
        default_width=12,
    ),
    _definition(
        id="audit-trace",
        display_name="Action Audit Trace",
        description="Object, Evidence와 사람의 Action 연결 상태를 표시합니다.",
        category="audit",
        renderer="AuditTrace",
        allowed_roles=["tenant_admin", "quality_auditor", "fde"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="integration-health",
        display_name="Integration Health",
        description="domain adapter와 provider 연결 상태를 진단합니다.",
        category="build",
        renderer="IntegrationHealth",
        allowed_roles=["tenant_admin", "fde"],
        default_width=6,
    ),
    _definition(
        id="model-health",
        display_name="Model Health",
        description="모델 버전, data-quality slice와 release 상태를 요약합니다.",
        category="build",
        renderer="ModelHealth",
        allowed_roles=["tenant_admin", "ml_validator", "fde"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="executive-portfolio",
        display_name="Executive Portfolio",
        description="조직·workspace 단위 위험, 설비 수와 영향 집계를 제공합니다.",
        category="observe",
        renderer="ExecutivePortfolio",
        allowed_roles=["tenant_admin", "executive_viewer"],
        object_types=["equipment", "risk_event"],
        emits=["selected_event_id", "selected_equipment_id"],
        default_width=12,
    ),
    _definition(
        id="executive-risk-trend",
        display_name="Risk & Impact Trend",
        description="세부 센서 대신 위험 점수와 운영 영향 추세를 표시합니다.",
        category="explore",
        renderer="ExecutiveRiskTrend",
        allowed_roles=["tenant_admin", "executive_viewer"],
        accepts=["status_filter"],
        emits=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="executive-unresolved",
        display_name="Unresolved Critical Events",
        description="아직 사람의 decision이 없는 중요 사건을 drill-down 목록으로 제공합니다.",
        category="act",
        renderer="ExecutiveUnresolved",
        allowed_roles=["tenant_admin", "executive_viewer"],
        accepts=["status_filter"],
        emits=["selected_event_id", "selected_equipment_id"],
        default_width=6,
    ),
    _definition(
        id="executive-business-impact",
        display_name="Business Impact Assumptions",
        description="정지 영향 추정값과 계산 가정을 함께 표시합니다.",
        category="explain",
        renderer="ExecutiveBusinessImpact",
        allowed_roles=["tenant_admin", "executive_viewer"],
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="audit-reconstruction",
        display_name="Event Reconstruction",
        description="입력 snapshot에서 Evidence와 판단까지 사건을 재구성합니다.",
        category="audit",
        renderer="AuditReconstruction",
        allowed_roles=["tenant_admin", "quality_auditor"],
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="audit-version-snapshot",
        display_name="Version Snapshot",
        description="input schema, model, policy, context, Evidence와 Report version을 고정해 보여줍니다.",
        category="audit",
        renderer="AuditVersionSnapshot",
        allowed_roles=["tenant_admin", "quality_auditor"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="audit-evidence-trace",
        display_name="Evidence → Report Trace",
        description="Report section을 원본 Evidence field ID까지 추적합니다.",
        category="audit",
        renderer="AuditEvidenceTrace",
        allowed_roles=["tenant_admin", "quality_auditor"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="audit-action-history",
        display_name="Action History",
        description="운영 decision, note, Ontology Action과 현장 상태 변경을 시간순으로 표시합니다.",
        category="audit",
        renderer="AuditActionHistory",
        allowed_roles=["tenant_admin", "quality_auditor"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="audit-export-checkpoint",
        display_name="Audit Export Checkpoint",
        description="현재 사건 snapshot의 hash와 export 목적을 감사 기록으로 남깁니다.",
        category="act",
        renderer="AuditExportCheckpoint",
        allowed_roles=["tenant_admin", "quality_auditor"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="field-task",
        display_name="Mobile Field Task",
        description="작은 화면에서 배정 작업, 우선순위와 현재 상태를 확인합니다.",
        category="act",
        renderer="FieldTask",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician"],
        accepts=["selected_event_id"],
        emits=["selected_event_id", "selected_equipment_id"],
        default_width=12,
    ),
    _definition(
        id="field-safety-location",
        display_name="Safety & Location",
        description="설비 위치와 작업 전 안전 확인 항목을 제공합니다.",
        category="act",
        renderer="FieldSafetyLocation",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="field-measurements",
        display_name="Measurement & Photo Metadata",
        description="현장 측정값과 사진 binary가 아닌 metadata를 입력합니다.",
        category="act",
        renderer="FieldMeasurements",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician"],
        accepts=["selected_event_id"],
        default_width=6,
    ),
    _definition(
        id="field-task-actions",
        display_name="Complete · Issue · Blocked",
        description="완료, 문제 발견, 작업 불가 Ontology Action과 엔지니어 handoff를 실행합니다.",
        category="act",
        renderer="FieldTaskActions",
        allowed_roles=["tenant_admin", "process_engineer", "maintenance_technician"],
        accepts=["selected_event_id"],
        default_width=12,
    ),
    _definition(
        id="fde-workspace-overview",
        display_name="Customer Workspace Overview",
        description="고객 workspace의 domain pack, object와 template 현황을 요약합니다.",
        category="build",
        renderer="FDEWorkspaceOverview",
        allowed_roles=["tenant_admin", "fde"],
        default_width=6,
    ),
    _definition(
        id="fde-ontology-registry",
        display_name="Ontology Registry Workbench",
        description="Object·Link·Action registry와 고객 workflow binding을 검토합니다.",
        category="build",
        renderer="FDEOntologyRegistry",
        allowed_roles=["tenant_admin", "fde"],
        default_width=6,
    ),
    _definition(
        id="fde-deployment-checklist",
        display_name="Deployment Checklist",
        description="배포 전 identity, ontology, provider, 승인과 secret 경계를 점검합니다.",
        category="build",
        renderer="FDEDeploymentChecklist",
        allowed_roles=["tenant_admin", "fde"],
        default_width=6,
    ),
    _definition(
        id="fde-diagnostic-events",
        display_name="Diagnostic Events",
        description="provider fallback과 data-quality diagnostic을 안전 경계와 함께 표시합니다.",
        category="build",
        renderer="FDEDiagnosticEvents",
        allowed_roles=["tenant_admin", "fde"],
        default_width=6,
    ),
    _definition(
        id="planner-assistant",
        display_name="Ontology Planner Assistant",
        description="자연어 Object query, 역할별 Board 추천, grounded narrative와 승인 전 Dashboard draft를 생성합니다.",
        category="suggested",
        renderer="PlannerAssistant",
        allowed_roles=ALL_ROLES,
        object_types=["equipment", "risk_event", "evidence_package", "inspection", "maintenance_action"],
        accepts=["selected_event_id", "selected_equipment_id"],
        default_width=12,
    ),
    _definition(
        id="fde-approval-queue",
        display_name="Template Approval Queue",
        description="FDE가 제출한 template 변경의 pending·approved·rejected 상태를 표시합니다.",
        category="build",
        renderer="FDEApprovalQueue",
        allowed_roles=["tenant_admin", "fde"],
        default_width=12,
    ),
    _definition(
        id="ml-version-matrix",
        display_name="Model & Dataset Versions",
        description="운영 Evidence의 model, dataset schema와 policy version을 분리해 표시합니다.",
        category="build",
        renderer="MLVersionMatrix",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=12,
    ),
    _definition(
        id="ml-threshold-cost",
        display_name="Operational Threshold Cost",
        description="운영 threshold별 개입 수와 예상 위험 누락 비용을 비교합니다.",
        category="explore",
        renderer="MLThresholdCost",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=6,
    ),
    _definition(
        id="ml-slice-error",
        display_name="Slice & Error Analysis",
        description="상태·중요도 slice와 Gold 실패 사례를 분석합니다.",
        category="explore",
        renderer="MLSliceError",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=6,
    ),
    _definition(
        id="ml-drift-schema",
        display_name="Drift & Schema Anomaly",
        description="schema version과 data-quality anomaly를 drift 후보로 분리해 표시합니다.",
        category="audit",
        renderer="MLDriftSchema",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=6,
    ),
    _definition(
        id="ml-gold-regression",
        display_name="Gold Regression",
        description="8개 accepted scenario의 상태·decision·confidence 회귀 결과를 표시합니다.",
        category="audit",
        renderer="MLGoldRegression",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=6,
    ),
    _definition(
        id="ml-release-candidate",
        display_name="Release Candidate Approval",
        description="model·dataset·policy snapshot을 승인 요청 Action으로 제출합니다.",
        category="act",
        renderer="MLReleaseCandidate",
        allowed_roles=["tenant_admin", "ml_validator"],
        default_width=12,
    ),
    _definition(
        id="parameter-summary",
        display_name="Parameter Summary",
        description="현재 dashboard parameter와 downstream 영향 범위를 표시합니다.",
        category="suggested",
        renderer="ParameterSummary",
        accepts=["selected_event_id", "selected_equipment_id", "status_filter", "intent"],
        default_width=4,
        allow_multiple=True,
    ),
    _definition(
        id="text-board",
        display_name="Text Board",
        description="스크립트나 HTML 없이 설명과 운영 메모를 표시합니다.",
        category="build",
        renderer="TextBoard",
        default_width=6,
        allow_multiple=True,
        default_settings={"text": "새 설명을 입력하세요."},
    ),
)

BOARD_DEFINITION_BY_ID = {item.id: item for item in BOARD_CATALOG}


def _board(
    role: str,
    tab: str,
    definition_id: str,
    title: str,
    order: int,
    *,
    width: int | None = None,
    mandatory: bool = False,
) -> DashboardBoard:
    definition = BOARD_DEFINITION_BY_ID[definition_id]
    return DashboardBoard(
        id=f"{role}:{tab}:{definition_id}",
        definition_id=definition_id,
        title=title,
        width=width or definition.default_width,
        order=order,
        mandatory=mandatory,
        bindings=dict(definition.default_bindings),
        settings=dict(definition.default_settings),
    )


def _tab(role: str, slug: str, title: str, order: int, boards: list[DashboardBoard]) -> DashboardTab:
    x = 0
    y = 0
    row_height = 0
    tall_renderers = {
        "RiskTrendWorkbench": 4,
        "EventDataGrid": 5,
        "OntologyRelationship": 4,
        "ActivityStream": 4,
        "PlannerAssistant": 6,
        "ConversationThread": 5,
        "SensorLineChart": 4,
    }
    for board in sorted(boards, key=lambda item: item.order):
        definition = BOARD_DEFINITION_BY_ID[board.definition_id]
        width = max(1, min(12, board.width))
        height = max(
            1,
            int(board.settings.get("height_units", tall_renderers.get(definition.renderer, 2))),
        )
        if x + width > 12:
            x = 0
            y += max(1, row_height)
            row_height = 0
        board.layout = DashboardBoardLayout(
            x=x,
            y=y,
            w=width,
            h=height,
            min_w=definition.minimum_width,
            min_h=1,
            max_w=definition.maximum_width,
            max_h=12,
        )
        board.settings["height_units"] = str(height)
        x += width
        row_height = max(row_height, height)
        if x >= 12:
            x = 0
            y += row_height
            row_height = 0
    return DashboardTab(
        id=f"{role}:{slug}",
        title=title,
        order=order,
        parameter_ids=["selected_event_id", "selected_equipment_id", "status_filter", "intent"],
        boards=boards,
    )


def _template_tabs(role: str) -> list[DashboardTab]:
    if role == "tenant_admin":
        return [
            _tab(role, "operations", "운영 Overview", 0, [
                _board(role, "operations", "status-summary", "현재 운영 상태", 0, width=12, mandatory=True),
                _board(role, "operations", "priority-list", "전체 위험 우선순위", 1, width=12, mandatory=True),
                _board(role, "operations", "impact-summary", "예상 운영 영향", 2),
                _board(role, "operations", "risk-kpi", "위험 KPI", 3),
                _board(role, "operations", "operations-kpi", "Operations KPI", 4, width=12),
                _board(role, "operations", "risk-trend-workbench", "Interactive Risk Trend", 5, width=6),
                _board(role, "operations", "activity-stream", "Operational Activity", 6, width=6),
                _board(role, "operations", "event-data-grid", "Risk Event Data Grid", 7, width=12),
            ]),
            _tab(role, "governance", "Governance", 1, [
                _board(role, "governance", "audit-trace", "Action 감사 추적", 0, mandatory=True),
                _board(role, "governance", "integration-health", "Integration 상태", 1),
                _board(role, "governance", "model-details", "모델·정책 정보", 2),
            ]),
        ]
    if role == "executive_viewer":
        return [
            _tab(role, "overview", "Executive Overview", 0, [
                _board(role, "overview", "executive-portfolio", "조직 위험 Portfolio", 0, width=12, mandatory=True),
                _board(role, "overview", "executive-risk-trend", "위험·영향 추세", 1, width=6, mandatory=True),
                _board(role, "overview", "executive-unresolved", "미조치 중요 사건", 2, width=6, mandatory=True),
                _board(role, "overview", "executive-business-impact", "사업 영향과 가정", 3, width=12),
                _board(role, "overview", "operations-kpi", "Portfolio KPI", 4, width=12),
                _board(role, "overview", "risk-trend-workbench", "Interactive Portfolio Trend", 5, width=6),
                _board(role, "overview", "activity-stream", "Decision Activity", 6, width=6),
            ]),
            _tab(role, "briefing", "보고 View", 1, [
                _board(role, "briefing", "status-summary", "선택 사건 요약", 0, width=12),
                _board(role, "briefing", "recommended-actions", "대응 상태", 1, width=6),
                _board(role, "briefing", "text-board", "임원 보고 메모", 2, width=6),
            ]),
        ]
    if role == "process_manager":
        return [
            _tab(role, "operations", "운영 판단", 0, [
                _board(role, "operations", "status-summary", "현재 사건 요약", 0, width=12, mandatory=True),
                _board(role, "operations", "priority-list", "설비 우선순위", 1, width=12, mandatory=True),
                _board(role, "operations", "impact-summary", "예상 운영 영향", 2),
                _board(role, "operations", "risk-kpi", "위험 지표", 3),
                _board(role, "operations", "manager-decision", "운영 판단 기록", 4, width=12, mandatory=True),
                _board(role, "operations", "data-quality-warning", "데이터 품질 경고", 5, width=12),
                _board(role, "operations", "operations-kpi", "Operations KPI", 6, width=12),
                _board(role, "operations", "risk-trend-workbench", "Risk & Downtime Explorer", 7, width=6),
                _board(role, "operations", "event-data-grid", "Risk Event Data Grid", 8, width=6),
            ]),
            _tab(role, "explain", "근거와 후속", 1, [
                _board(role, "explain", "factor-contribution", "주요 위험 근거", 0),
                _board(role, "explain", "recommended-actions", "권장 조치", 1),
                _board(role, "explain", "conversation-thread", "후속 질문", 2, width=12),
            ]),
        ]
    if role == "process_engineer":
        return [
            _tab(role, "evidence", "Evidence 분석", 0, [
                _board(role, "evidence", "sensor-line-chart", "센서 변화", 0, width=12, mandatory=True),
                _board(role, "evidence", "anomaly-timeline", "이상 구간", 1),
                _board(role, "evidence", "factor-contribution", "주요 위험 근거", 2, mandatory=True),
                _board(role, "evidence", "evidence-table", "근거 상세", 3),
                _board(role, "evidence", "model-details", "모델 상세", 4),
                _board(role, "evidence", "data-quality-warning", "데이터 품질 경고", 5, width=12),
                _board(role, "evidence", "conversation-thread", "후속 질문", 6, width=12),
                _board(role, "evidence", "event-data-grid", "Risk Event Data Grid", 7, width=12),
                _board(role, "evidence", "ontology-relationship", "Ontology Relationship", 8, width=6),
                _board(role, "evidence", "activity-stream", "Evidence Activity", 9, width=6),
            ]),
            _tab(role, "inspection", "점검 Workflow", 1, [
                _board(role, "inspection", "engineer-checklist", "점검 체크리스트", 0, mandatory=True),
                _board(role, "inspection", "recommended-actions", "권장 조치", 1),
                _board(role, "inspection", "conversation-thread", "후속 질문", 2, width=12),
            ]),
        ]
    if role == "maintenance_technician":
        return [
            _tab(role, "tasks", "Mobile Task", 0, [
                _board(role, "tasks", "field-task", "배정 현장 작업", 0, width=12, mandatory=True),
                _board(role, "tasks", "field-safety-location", "안전·위치", 1, width=6, mandatory=True),
                _board(role, "tasks", "engineer-checklist", "점검 체크리스트", 2, width=6, mandatory=True),
                _board(role, "tasks", "field-measurements", "측정값·사진 Metadata", 3, width=6),
                _board(role, "tasks", "field-task-actions", "완료·문제·작업 불가", 4, width=6, mandatory=True),
            ]),
            _tab(role, "handoff", "Engineer Handoff", 1, [
                _board(role, "handoff", "status-summary", "작업 대상 Evidence", 0, width=12),
                _board(role, "handoff", "recommended-actions", "권장 작업", 1, width=6),
                _board(role, "handoff", "sensor-line-chart", "최근 센서 변화", 2, width=6),
                _board(role, "handoff", "text-board", "교대 메모", 3, width=12),
                _board(role, "handoff", "ontology-relationship", "Equipment Relationship", 4, width=6),
                _board(role, "handoff", "activity-stream", "Task Activity", 5, width=6),
            ]),
        ]
    if role == "quality_auditor":
        return [
            _tab(role, "trace", "Event Reconstruction", 0, [
                _board(role, "trace", "audit-reconstruction", "사건 재구성", 0, width=12, mandatory=True),
                _board(role, "trace", "audit-version-snapshot", "Input·Model·Policy Version", 1, width=6, mandatory=True),
                _board(role, "trace", "audit-evidence-trace", "Evidence → Report Trace", 2, width=6, mandatory=True),
                _board(role, "trace", "ontology-relationship", "Ontology Relationship", 3, width=6),
                _board(role, "trace", "activity-stream", "Reconstruction Activity", 4, width=6),
            ]),
            _tab(role, "audit", "Action & Export", 1, [
                _board(role, "audit", "audit-action-history", "Action History", 0, width=6, mandatory=True),
                _board(role, "audit", "audit-export-checkpoint", "Export Checkpoint", 1, width=6, mandatory=True),
                _board(role, "audit", "data-quality-warning", "품질 경고", 2, width=12),
            ]),
        ]
    if role == "ml_validator":
        return [
            _tab(role, "model", "Model Console", 0, [
                _board(role, "model", "ml-version-matrix", "Model·Dataset·Policy Version", 0, width=12, mandatory=True),
                _board(role, "model", "ml-threshold-cost", "운영 Threshold Cost", 1, width=6, mandatory=True),
                _board(role, "model", "ml-slice-error", "Slice·Error Analysis", 2, width=6, mandatory=True),
            ]),
            _tab(role, "quality", "Drift & Regression", 1, [
                _board(role, "quality", "ml-drift-schema", "Drift·Schema Anomaly", 0, width=6, mandatory=True),
                _board(role, "quality", "ml-gold-regression", "Gold Regression", 1, width=6, mandatory=True),
                _board(role, "quality", "data-quality-warning", "선택 사건 품질 경고", 2, width=12),
                _board(role, "quality", "event-data-grid", "Validation Event Grid", 3, width=12),
                _board(role, "quality", "risk-trend-workbench", "Slice Risk Trend", 4, width=6),
                _board(role, "quality", "activity-stream", "Model Activity", 5, width=6),
            ]),
            _tab(role, "release", "Release Candidate", 2, [
                _board(role, "release", "ml-release-candidate", "Model Release 승인 요청", 0, width=12, mandatory=True),
                _board(role, "release", "model-details", "선택 사건 Model Snapshot", 1, width=6),
                _board(role, "release", "evidence-table", "Release Evidence", 2, width=6),
            ]),
        ]
    return [
        _tab(role, "workspace", "Customer Workspace", 0, [
            _board(role, "workspace", "fde-workspace-overview", "Customer Workspace Overview", 0, width=6, mandatory=True),
            _board(role, "workspace", "fde-ontology-registry", "Ontology Registry", 1, width=6, mandatory=True),
            _board(role, "workspace", "fde-deployment-checklist", "Deployment Checklist", 2, width=6, mandatory=True),
            _board(role, "workspace", "fde-diagnostic-events", "Diagnostic Events", 3, width=6, mandatory=True),
            _board(role, "workspace", "ontology-relationship", "Ontology Relationship", 4, width=6),
            _board(role, "workspace", "activity-stream", "Operational Activity", 5, width=6),
            _board(role, "workspace", "event-data-grid", "Workspace Event Grid", 6, width=12),
        ]),
        _tab(role, "builder", "Template Builder", 1, [
            _board(role, "builder", "parameter-summary", "Parameter Dependency", 0, width=4),
            _board(role, "builder", "object-context", "Ontology Object Context", 1, width=4),
            _board(role, "builder", "text-board", "Customer Workflow Notes", 2, width=4),
            _board(role, "builder", "planner-assistant", "Ontology Planner Assistant", 3, width=12, mandatory=True),
            _board(role, "builder", "fde-approval-queue", "Template Approval Queue", 4, width=12, mandatory=True),
        ]),
    ]


def _template_tabs_v4(role: str) -> list[DashboardTab]:
    """High-density role defaults for the Palantir-style workbench."""
    if role == "tenant_admin":
        return [
            _tab(role, "operations-v4", "Operations Command", 0, [
                _board(role, "operations-v4", "operations-kpi", "Operations KPI", 0, width=12, mandatory=True),
                _board(role, "operations-v4", "risk-trend-workbench", "Interactive Risk & Downtime", 1, width=8, mandatory=True),
                _board(role, "operations-v4", "activity-stream", "Operational Activity", 2, width=4),
                _board(role, "operations-v4", "event-data-grid", "Risk Event Data Grid", 3, width=12, mandatory=True),
                _board(role, "operations-v4", "status-summary", "Selected Event Status", 4, width=8, mandatory=True),
                _board(role, "operations-v4", "impact-summary", "Operational Impact", 5, width=4),
                _board(role, "operations-v4", "priority-list", "Governed Priority Queue", 6, width=12, mandatory=True),
            ]),
            _tab(role, "governance-v4", "Ontology & Governance", 1, [
                _board(role, "governance-v4", "ontology-relationship", "Ontology Relationship Graph", 0, width=8, mandatory=True),
                _board(role, "governance-v4", "audit-trace", "Action Audit Trace", 1, width=4, mandatory=True),
                _board(role, "governance-v4", "integration-health", "Integration Health", 2, width=4),
                _board(role, "governance-v4", "model-health", "Model Health", 3, width=4),
                _board(role, "governance-v4", "activity-stream", "Governance Activity", 4, width=4),
            ]),
        ]
    if role == "executive_viewer":
        return [
            _tab(role, "portfolio-v4", "Executive Overview", 0, [
                _board(role, "portfolio-v4", "operations-kpi", "Portfolio KPI", 0, width=12, mandatory=True),
                _board(role, "portfolio-v4", "risk-trend-workbench", "Risk & Downtime Portfolio", 1, width=8, mandatory=True),
                _board(role, "portfolio-v4", "executive-unresolved", "Unresolved Critical Events", 2, width=4, mandatory=True),
                _board(role, "portfolio-v4", "executive-portfolio", "조직 위험 Portfolio", 3, width=8, mandatory=True),
                _board(role, "portfolio-v4", "activity-stream", "Decision Activity", 4, width=4),
                _board(role, "portfolio-v4", "executive-business-impact", "Business Impact Assumptions", 5, width=12),
            ]),
            _tab(role, "briefing-v4", "Executive Briefing", 1, [
                _board(role, "briefing-v4", "status-summary", "Selected Event Brief", 0, width=8),
                _board(role, "briefing-v4", "recommended-actions", "Response Status", 1, width=4),
                _board(role, "briefing-v4", "text-board", "Executive Narrative", 2, width=12),
            ]),
        ]
    if role == "process_manager":
        return [
            _tab(role, "control-v4", "운영 판단", 0, [
                _board(role, "control-v4", "operations-kpi", "Operations KPI", 0, width=12, mandatory=True),
                _board(role, "control-v4", "risk-trend-workbench", "Risk & Downtime Explorer", 1, width=8, mandatory=True),
                _board(role, "control-v4", "manager-decision", "Operational Decision", 2, width=4, mandatory=True),
                _board(role, "control-v4", "event-data-grid", "Risk Event Data Grid", 3, width=12, mandatory=True),
                _board(role, "control-v4", "status-summary", "현재 사건 요약", 4, width=8, mandatory=True),
                _board(role, "control-v4", "impact-summary", "예상 운영 영향", 5, width=4),
                _board(role, "control-v4", "recommended-actions", "권장 조치", 6, width=4),
                _board(role, "control-v4", "data-quality-warning", "데이터 품질 경고", 7, width=8),
                _board(role, "control-v4", "priority-list", "Governed Priority Queue", 8, width=12, mandatory=True),
            ]),
            _tab(role, "explain-v4", "근거와 후속", 1, [
                _board(role, "explain-v4", "ontology-relationship", "Object Relationship", 0, width=8),
                _board(role, "explain-v4", "factor-contribution", "Risk Factors", 1, width=4),
                _board(role, "explain-v4", "recommended-actions", "Recommended Actions", 2, width=6),
                _board(role, "explain-v4", "activity-stream", "Operational Activity", 3, width=6),
                _board(role, "explain-v4", "conversation-thread", "Grounded Follow-up", 4, width=12),
            ]),
        ]
    if role == "process_engineer":
        return [
            _tab(role, "analysis-v4", "Evidence 분석", 0, [
                _board(role, "analysis-v4", "risk-trend-workbench", "Portfolio Signal Explorer", 0, width=8, mandatory=True),
                _board(role, "analysis-v4", "ontology-relationship", "Ontology Relationship", 1, width=4),
                _board(role, "analysis-v4", "event-data-grid", "Risk Event Data Grid", 2, width=12, mandatory=True),
                _board(role, "analysis-v4", "sensor-line-chart", "센서 변화", 3, width=12, mandatory=True),
                _board(role, "analysis-v4", "factor-contribution", "주요 위험 근거", 4, width=6, mandatory=True),
                _board(role, "analysis-v4", "evidence-table", "근거 상세", 5, width=6, mandatory=True),
                _board(role, "analysis-v4", "anomaly-timeline", "Anomaly Timeline", 6, width=6),
                _board(role, "analysis-v4", "model-details", "Model & Policy", 7, width=6),
                _board(role, "analysis-v4", "data-quality-warning", "Data Quality", 8, width=12),
                _board(role, "analysis-v4", "activity-stream", "Evidence Activity", 9, width=6),
                _board(role, "analysis-v4", "conversation-thread", "Grounded Follow-up", 10, width=6),
            ]),
            _tab(role, "workflow-v4", "점검 Workflow", 1, [
                _board(role, "workflow-v4", "engineer-checklist", "Inspection Checklist", 0, width=6, mandatory=True),
                _board(role, "workflow-v4", "recommended-actions", "Recommended Actions", 1, width=6),
                _board(role, "workflow-v4", "conversation-thread", "Grounded Follow-up", 2, width=12),
            ]),
        ]
    if role == "maintenance_technician":
        return [
            _tab(role, "field-v4", "Mobile Task", 0, [
                _board(role, "field-v4", "field-task", "배정 현장 작업", 0, width=12, mandatory=True),
                _board(role, "field-v4", "field-safety-location", "Safety & Location", 1, width=6, mandatory=True),
                _board(role, "field-v4", "engineer-checklist", "Inspection Checklist", 2, width=6, mandatory=True),
                _board(role, "field-v4", "field-measurements", "Measurements & Photos", 3, width=6),
                _board(role, "field-v4", "field-task-actions", "Complete · Issue · Blocked", 4, width=6, mandatory=True),
            ]),
            _tab(role, "handoff-v4", "Engineer Handoff", 1, [
                _board(role, "handoff-v4", "ontology-relationship", "Equipment Relationship", 0, width=6),
                _board(role, "handoff-v4", "sensor-line-chart", "Recent Sensor Change", 1, width=6),
                _board(role, "handoff-v4", "status-summary", "Task Evidence", 2, width=12),
                _board(role, "handoff-v4", "recommended-actions", "Recommended Work", 3, width=6),
                _board(role, "handoff-v4", "activity-stream", "Task Activity", 4, width=6),
                _board(role, "handoff-v4", "text-board", "Shift Notes", 5, width=12),
            ]),
        ]
    if role == "quality_auditor":
        return [
            _tab(role, "trace-v4", "Event Reconstruction", 0, [
                _board(role, "trace-v4", "ontology-relationship", "Ontology Relationship", 0, width=8, mandatory=True),
                _board(role, "trace-v4", "activity-stream", "Reconstruction Activity", 1, width=4, mandatory=True),
                _board(role, "trace-v4", "audit-reconstruction", "사건 재구성", 2, width=12, mandatory=True),
                _board(role, "trace-v4", "audit-version-snapshot", "Version Snapshot", 3, width=6, mandatory=True),
                _board(role, "trace-v4", "audit-evidence-trace", "Evidence → Report Trace", 4, width=6, mandatory=True),
            ]),
            _tab(role, "audit-v4", "Action & Export", 1, [
                _board(role, "audit-v4", "audit-action-history", "Action History", 0, width=6, mandatory=True),
                _board(role, "audit-v4", "audit-export-checkpoint", "Export Checkpoint", 1, width=6, mandatory=True),
                _board(role, "audit-v4", "data-quality-warning", "Quality Warnings", 2, width=12),
            ]),
        ]
    if role == "ml_validator":
        return [
            _tab(role, "model-v4", "Model Console", 0, [
                _board(role, "model-v4", "operations-kpi", "Validation KPI", 0, width=12),
                _board(role, "model-v4", "risk-trend-workbench", "Slice Risk Trend", 1, width=8, mandatory=True),
                _board(role, "model-v4", "activity-stream", "Model Activity", 2, width=4),
                _board(role, "model-v4", "ml-version-matrix", "Model · Dataset · Policy", 3, width=12, mandatory=True),
                _board(role, "model-v4", "ml-threshold-cost", "Operational Threshold Cost", 4, width=6, mandatory=True),
                _board(role, "model-v4", "ml-slice-error", "Slice & Error Analysis", 5, width=6, mandatory=True),
            ]),
            _tab(role, "quality-v4", "Drift & Regression", 1, [
                _board(role, "quality-v4", "event-data-grid", "Validation Event Grid", 0, width=12, mandatory=True),
                _board(role, "quality-v4", "ml-drift-schema", "Drift & Schema", 1, width=6, mandatory=True),
                _board(role, "quality-v4", "ml-gold-regression", "Gold Regression", 2, width=6, mandatory=True),
                _board(role, "quality-v4", "data-quality-warning", "Data Quality", 3, width=12),
            ]),
            _tab(role, "release-v4", "Release Candidate", 2, [
                _board(role, "release-v4", "ml-release-candidate", "Release Approval", 0, width=12, mandatory=True),
                _board(role, "release-v4", "model-details", "Model Snapshot", 1, width=6),
                _board(role, "release-v4", "evidence-table", "Release Evidence", 2, width=6),
            ]),
        ]
    return [
        _tab(role, "workspace-v4", "Customer Workspace", 0, [
            _board(role, "workspace-v4", "operations-kpi", "Workspace KPI", 0, width=12),
            _board(role, "workspace-v4", "ontology-relationship", "Ontology Relationship", 1, width=8, mandatory=True),
            _board(role, "workspace-v4", "activity-stream", "Operational Activity", 2, width=4),
            _board(role, "workspace-v4", "event-data-grid", "Workspace Event Grid", 3, width=12),
            _board(role, "workspace-v4", "fde-workspace-overview", "Customer Workspace Overview", 4, width=6, mandatory=True),
            _board(role, "workspace-v4", "fde-ontology-registry", "Ontology Registry", 5, width=6, mandatory=True),
            _board(role, "workspace-v4", "fde-deployment-checklist", "Deployment Checklist", 6, width=6, mandatory=True),
            _board(role, "workspace-v4", "fde-diagnostic-events", "Diagnostic Events", 7, width=6, mandatory=True),
        ]),
        _tab(role, "builder-v4", "Template Builder", 1, [
            _board(role, "builder-v4", "parameter-summary", "Parameter Dependency", 0, width=4),
            _board(role, "builder-v4", "object-context", "Object Context", 1, width=4),
            _board(role, "builder-v4", "text-board", "Customer Workflow Notes", 2, width=4),
            _board(role, "builder-v4", "planner-assistant", "Ontology Planner Assistant", 3, width=12, mandatory=True),
            _board(role, "builder-v4", "fde-approval-queue", "Template Approval Queue", 4, width=12, mandatory=True),
        ]),
    ]


def seed_templates() -> list[DashboardTemplateSnapshot]:
    created_at = datetime.now(timezone.utc).isoformat()
    templates: list[DashboardTemplateSnapshot] = []
    fixture_workspaces = (
        "manufacturing-demo",
        "azure-fleet-maintenance",
        "metropt-compressor-monitoring",
    )
    for workspace_id in fixture_workspaces:
        for role in ALL_ROLES:
            tabs = _template_tabs_v4(role)
            mandatory_board_ids = [
                board.id for tab in tabs for board in tab.boards if board.mandatory
            ]
            templates.append(
                DashboardTemplateSnapshot(
                    template_id=f"template:{workspace_id}:{role}",
                    workspace_id=workspace_id,
                    role_code=role,
                    display_name=f"{role.replace('_', ' ').title()} Default Dashboard",
                    version=4,
                    tabs=tabs,
                    mandatory_board_ids=mandatory_board_ids,
                    parameter_definitions=PARAMETER_DEFINITIONS,
                    created_by="system",
                    created_at=created_at,
                )
            )
    return templates
