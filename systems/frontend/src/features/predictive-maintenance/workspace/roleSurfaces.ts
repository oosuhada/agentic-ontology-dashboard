import type { OperationsView } from "../../operations/api/operationsContracts";
import type {
  ReliabilityExperienceKind,
  ReliabilityLocalizedCopy,
  ReliabilityPageCopy,
} from "./roleExperience";

export type ReliabilitySurfaceId =
  | "factory-status"
  | "executive-brief"
  | "operational-risk"
  | "executive-kpi"
  | "executive-reports"
  | "decision-bottleneck"
  | "maintenance-effect"
  | "roadmap"
  | "operations-status"
  | "pending-decisions"
  | "decision-case"
  | "production-impact"
  | "maintenance-approval"
  | "backlog"
  | "report-draft"
  | "monitoring"
  | "assets"
  | "sensor-features"
  | "inspection"
  | "maintenance-history"
  | "field-notes"
  | "my-work"
  | "work-targets"
  | "field-status"
  | "work-history";

export interface ReliabilitySurface {
  id: ReliabilitySurfaceId;
  view: OperationsView;
  label: ReliabilityLocalizedCopy;
  detail: ReliabilityLocalizedCopy;
  page: ReliabilityPageCopy;
}

export interface ReliabilitySurfaceGroup {
  id: string;
  label: ReliabilityLocalizedCopy;
  surfaces: ReliabilitySurface[];
}

function copy(ko: string, en: string): ReliabilityLocalizedCopy { return { ko, en }; }
function page(eyebrow: string, title: string, detail: string, eyebrowEn: string, titleEn: string, detailEn: string): ReliabilityPageCopy {
  return { eyebrow: copy(eyebrow, eyebrowEn), title: copy(title, titleEn), detail: copy(detail, detailEn) };
}

export const RELIABILITY_SURFACES: Record<ReliabilityExperienceKind, ReliabilitySurface[]> = {
  executive: [
    { id: "executive-brief", view: "reports", label: copy("Executive Brief", "Executive Brief"), detail: copy("경영 요약 · 보고 준비", "Executive summary · reporting"), page: page("경영 브리핑", "운영 리스크와 경영 보고", "실시간 공장 현황 위에 생산 영향, KPI, 핵심 Decision Case와 보고 초안을 연결합니다.", "EXECUTIVE BRIEF", "Operational risk and executive reporting", "Connect live factory status to production impact, KPI, critical Decision Cases, and reporting." ) },
    { id: "decision-bottleneck", view: "operations", label: copy("의사결정 병목", "Decision bottlenecks"), detail: copy("지연 · Owner · Backlog", "Delay · owner · backlog"), page: page("의사결정 병목", "지연 중인 핵심 판단", "판단이 지연된 Case와 다음 책임자, 생산 영향의 크기를 함께 봅니다.", "DECISION BOTTLENECKS", "Delayed critical decisions", "Review delayed cases, accountable owners, and production impact together." ) },
    { id: "operational-risk", view: "overview", label: copy("운영 리스크", "Operational risk"), detail: copy("공장 · 라인 · 위험", "Plant · line · risk"), page: page("운영 리스크", "생산 연속성 위험", "공장과 라인 단위의 위험 분포와 우선 대응 대상을 확인합니다.", "OPERATIONAL RISK", "Production continuity risk", "Review plant and line risk distribution and the highest-priority exposures." ) },
    { id: "maintenance-effect", view: "objects", label: copy("정비 효과", "Maintenance effect"), detail: copy("Before-after · 재발", "Before-after · recurrence"), page: page("정비 효과", "정비 이후 위험 변화", "과거 정비와 현재 위험을 연결해 before-after와 재발 여부를 확인합니다.", "MAINTENANCE EFFECT", "Risk after maintenance", "Connect maintenance history to current risk for before-after and recurrence review." ) },
  ],
  operations: [
    { id: "pending-decisions", view: "operations", label: copy("판단 대기", "Pending decisions"), detail: copy("우선순위 · SLA", "Priority · SLA"), page: page("판단 대기", "지금 판단해야 할 항목", "생산 영향이 큰 항목부터 다음 운영 판단과 Owner를 확인합니다.", "PENDING DECISIONS", "Decisions required now", "Prioritize high-impact cases and review the next operational decision and owner." ) },
    { id: "operations-status", view: "overview", label: copy("운영 현황", "Operations status"), detail: copy("실시간 KPI · 상태맵", "Live KPI · factory map"), page: page("운영 현황", "생산 리스크와 조치 현황", "실시간 공장 상태와 판단 대기 항목을 함께 확인합니다.", "OPERATIONS STATUS", "Production risk and response", "Review live factory status together with work requiring decisions." ) },
    { id: "production-impact", view: "objects", label: copy("생산 영향", "Production impact"), detail: copy("수량 · 비용 · 제품", "Units · cost · product"), page: page("생산 영향", "설비 위험의 운영 영향", "예상 정지, 계획 손실 수량, 제품 경제성과 자재 제약을 연결합니다.", "PRODUCTION IMPACT", "Operational impact of asset risk", "Connect downtime, planned unit loss, product economics, and material constraints." ) },
    { id: "report-draft", view: "reports", label: copy("보고", "Reports"), detail: copy("초안 · 검토 대기 · Archive", "Drafts · review queue · archive"), page: page("보고", "Case에서 이어지는 보고 산출물", "Decision Case에서 생성된 보고 초안과 검토 대기, 완료된 snapshot 산출물을 한곳에서 확인합니다.", "REPORTS", "Reporting artifacts from Decision Cases", "Review report drafts, review queues, and completed snapshot artifacts produced from Decision Cases." ) },
  ],
  engineering: [
    { id: "monitoring", view: "overview", label: copy("모니터링", "Monitoring"), detail: copy("상태맵 · 위험 알림", "Factory map · risk alerts"), page: page("모니터링", "조사가 필요한 설비", "실시간 상태맵과 이상 신호에서 조사 우선순위를 좁혀갑니다.", "MONITORING", "Assets requiring investigation", "Narrow investigation priority from live factory state and abnormal signals." ) },
    { id: "assets", view: "objects", label: copy("원인 분석", "Root-cause analysis"), detail: copy("센서 추세 · 기여도 · 이력", "Signals · contribution · history"), page: page("원인 분석", "설비 신호와 원인 근거", "선택 설비의 센서 추세, 모델 기여와 정비 이력을 함께 분석해 원인 후보를 좁힙니다.", "ROOT-CAUSE ANALYSIS", "Equipment signals and causal evidence", "Analyze sensor trends, model contribution, and maintenance history to narrow causal candidates." ) },
    { id: "inspection", view: "operations", label: copy("점검", "Inspection"), detail: copy("점검 대상 · Checklist · 실행", "Targets · checklist · execution"), page: page("점검", "근거 기반 점검 실행", "근거에 연결된 점검 위치와 checklist를 확인하고 현장 실행 단계로 이어갑니다.", "INSPECTION", "Evidence-based inspection", "Review grounded inspection targets and checklists, then continue into field execution." ) },
    { id: "field-notes", view: "reports", label: copy("현장 기록", "Field records"), detail: copy("관측 · 불확실성 · Handoff", "Observation · uncertainty · handoff"), page: page("현장 기록", "근거 기반 현장 기록", "현장 관측, 남은 불확실성과 handoff 내용을 Evidence와 연결해 정리합니다.", "FIELD RECORDS", "Evidence-based field record", "Connect field observations, uncertainty, and handoff notes to evidence." ) },
  ],
  maintenance: [
    { id: "my-work", view: "operations", label: copy("내 작업", "My work"), detail: copy("승인 작업 · 진행 상태", "Approved work · progress"), page: page("내 작업", "승인된 현장 작업", "어디에서 무엇을 해야 하는지와 현재 작업 순서를 먼저 확인합니다.", "MY WORK", "Approved field work", "Start with where to go, what to do, and the current work sequence." ) },
    { id: "work-targets", view: "objects", label: copy("작업 대상", "Work targets"), detail: copy("위치 · 상태 · 근거", "Location · condition · evidence"), page: page("작업 대상", "설비 위치와 현장 근거", "승인된 작업에 필요한 설비 위치, 상태, 점검 근거와 자재를 확인합니다.", "WORK TARGETS", "Asset location and field evidence", "Review asset location, condition, inspection evidence, and materials needed for approved work." ) },
    { id: "field-status", view: "overview", label: copy("현장 현황", "Field status"), detail: copy("점검 · 정비 진행", "Inspection · maintenance progress"), page: page("현장 현황", "현장 작업 진행 상태", "현재 점검과 정비가 어느 단계에 있고 무엇이 남았는지 확인합니다.", "FIELD STATUS", "Field work status", "See the current stage of inspection and maintenance work and what remains." ) },
    { id: "work-history", view: "reports", label: copy("작업 이력", "Work history"), detail: copy("완료 결과 · 기록", "Completion · records"), page: page("작업 이력", "완료 작업과 실행 이력", "완료 결과와 현장 기록을 통해 작업 이력을 추적합니다.", "WORK HISTORY", "Completed work and execution history", "Trace work through completion results and field records." ) },
  ],
};

const FACTORY_STATUS_SURFACE: Record<Exclude<ReliabilityExperienceKind, "maintenance">, ReliabilitySurface> = {
  executive: {
    id: "factory-status",
    view: "overview",
    label: copy("설비 상태 근거", "Factory status evidence"),
    detail: copy("구역 · 셀 · 알림", "Zone · cell · alerts"),
    page: page(
      "설비 상태 근거",
      "공장 전체 설비 상태를 직접 확인",
      "경영 요약에서 더 깊게 확인할 필요가 있을 때 구역·셀 배치와 설비별 알림을 같은 실시간 근거로 확인합니다.",
      "FACTORY STATUS EVIDENCE",
      "Inspect plant-wide equipment status directly",
      "When executive summaries need deeper evidence, inspect zone, cell, and asset alerts from the same live operational state.",
    ),
  },
  operations: {
    id: "factory-status",
    view: "overview",
    label: copy("설비 현황", "Factory status"),
    detail: copy("구역 · 셀 · 실시간 알림", "Zone · cell · live alerts"),
    page: page(
      "실시간 설비 현황",
      "공장 전체 상태와 알림을 한눈에 확인",
      "구역과 셀 배치 위에서 주의·긴급 설비와 새 알림 수를 먼저 확인한 뒤 Decision Case로 내려갑니다.",
      "LIVE FACTORY STATUS",
      "See plant-wide status and alerts at a glance",
      "Start from zone and cell layout, identify warning and critical assets, then drill into the corresponding Decision Case.",
    ),
  },
  engineering: {
    id: "factory-status",
    view: "overview",
    label: copy("설비 현황", "Factory status"),
    detail: copy("셀 배치 · 위험 알림", "Cell layout · risk alerts"),
    page: page(
      "실시간 설비 현황",
      "조사할 설비를 위치와 알림으로 좁히기",
      "공장 배치에서 이상 알림이 발생한 셀과 설비를 먼저 찾고 센서·피쳐 근거로 이어갑니다.",
      "LIVE FACTORY STATUS",
      "Narrow investigation by location and alert",
      "Find the affected zone, cell, and asset first, then continue into sensor and feature evidence.",
    ),
  },
};

const ROLE_DETAIL_SURFACES: Partial<Record<ReliabilityExperienceKind, ReliabilitySurface[]>> = {
  executive: [
    { id: "executive-kpi", view: "reports", label: copy("운영 KPI", "Operating KPI"), detail: copy("Lead time · 노출액 · Backlog", "Lead time · exposure · backlog"), page: page("운영 KPI", "판단 속도와 운영 노출을 함께 확인", "Decision Lead Time, Report Lead Time, backlog와 생산·재무 노출을 같은 Case 기준으로 봅니다.", "OPERATING KPI", "Decision speed and operating exposure", "Review decision lead time, reporting lead time, backlog, and production exposure from the same cases.") },
    { id: "executive-reports", view: "reports", label: copy("보고 산출물", "Report artifacts"), detail: copy("Snapshot · revision · 근거", "Snapshot · revision · evidence"), page: page("보고 산출물", "Case에서 생성된 경영 보고", "별도 문서가 아니라 Event와 Decision lineage에서 생성된 snapshot 보고 산출물을 확인합니다.", "REPORT ARTIFACTS", "Executive reports produced from cases", "Review snapshot reports produced from Event and Decision lineage rather than detached documents.") },
    { id: "roadmap", view: "objects", label: copy("개선 과제", "Improvement roadmap"), detail: copy("재발 · 병목 · 자재", "Recurrence · bottleneck · material"), page: page("개선 과제", "반복되는 운영 병목과 개선 후보", "재발 설비, 긴 조달 리드타임, 반복 의사결정 지연을 연결해 개선 과제를 찾습니다.", "IMPROVEMENT ROADMAP", "Recurring operational constraints", "Connect recurrent asset risk, long material lead times, and decision delays into improvement candidates.") },
  ],
  operations: [
    { id: "decision-case", view: "operations", label: copy("Decision Case", "Decision Case"), detail: copy("근거 · 판단 · Action · Outcome", "Evidence · decision · action · outcome"), page: page("Decision Case", "하나의 사건을 끝까지 추적", "Event에서 Evidence, 운영 판단, 작업, 정비 결과와 보고 산출물까지 하나의 lineage로 확인합니다.", "DECISION CASE", "Trace one event through outcome", "Trace Event, Evidence, decision, work, maintenance outcome, and report artifacts in one lineage.") },
    { id: "maintenance-approval", view: "operations", label: copy("정비 승인", "Maintenance approval"), detail: copy("점검 결과 · 자재 · 승인", "Inspection · material · approval"), page: page("정비 승인", "정비 실행 전 운영 조건 확인", "점검 결과와 자재 제약, 생산 영향을 함께 확인한 뒤 권한이 있는 사용자가 정비 단계를 진행합니다.", "MAINTENANCE APPROVAL", "Validate conditions before maintenance", "Review inspection results, material constraints, and production impact before authorized maintenance actions.") },
    { id: "backlog", view: "operations", label: copy("Backlog", "Backlog"), detail: copy("대기 · SLA · Owner", "Queue · SLA · owner"), page: page("운영 Backlog", "지연 중인 판단과 작업", "판단과 작업이 어느 단계에서 오래 머무는지 Owner와 함께 확인합니다.", "OPERATIONS BACKLOG", "Delayed decisions and work", "See where decisions and work remain delayed and who currently owns the next step.") },
  ],
  engineering: [
    { id: "sensor-features", view: "objects", label: copy("센서 피쳐", "Sensor features"), detail: copy("추세 · 기여도 · 이상 구간", "Trend · contribution · anomaly"), page: page("센서 피쳐", "이상 신호를 시계열로 분석", "선택 설비의 실제 관측 추세와 모델 기여 근거를 함께 비교합니다.", "SENSOR FEATURES", "Analyze abnormal signals over time", "Compare live observation trends and model contribution evidence for the selected asset.") },
    { id: "maintenance-effect", view: "objects", label: copy("정비 효과", "Maintenance effect"), detail: copy("Before/After · 재발 여부", "Before/after · recurrence"), page: page("정비 효과", "정비 전후 신호와 위험 변화", "정비 전후 위험과 핵심 센서 변화를 비교해 조치 효과와 재발 가능성을 확인합니다.", "MAINTENANCE EFFECT", "Risk and signal change after maintenance", "Compare risk and key signals before and after maintenance to assess effect and recurrence.") },
    { id: "maintenance-history", view: "objects", label: copy("정비 이력", "Maintenance history"), detail: copy("과거 조치 · Before/After", "Past work · before/after"), page: page("정비 이력", "과거 조치와 현재 이상을 연결", "같은 설비의 과거 정비와 현재 위험, 정비 전후 관측을 연결해 재발 여부를 확인합니다.", "MAINTENANCE HISTORY", "Connect past work to current risk", "Connect maintenance records, current risk, and before/after observations to review recurrence.") },
  ],
};

export function reliabilitySurfaces(kind: ReliabilityExperienceKind, backupMode = false): ReliabilitySurface[] {
  const baseline = RELIABILITY_SURFACES[kind];
  if (backupMode || kind === "maintenance") return baseline;
  const factoryStatus = FACTORY_STATUS_SURFACE[kind];
  const extras = ROLE_DETAIL_SURFACES[kind] ?? [];
  if (kind === "executive") {
    const [brief, bottleneck, operationalRisk, maintenanceEffect] = baseline;
    const [kpi, reports, roadmap] = extras;
    return [brief, operationalRisk, kpi, bottleneck, reports, maintenanceEffect, roadmap, factoryStatus].filter(Boolean);
  }
  if (kind === "operations") {
    const [pending, status, production, report] = baseline;
    const [decisionCase, maintenanceApproval, backlog] = extras;
    return [factoryStatus, status, pending, decisionCase, production, maintenanceApproval, backlog, report].filter(Boolean);
  }
  const [monitoring, assets, inspection, fieldNotes] = baseline;
  const [, maintenanceEffect, maintenanceHistory] = extras;
  return [factoryStatus, monitoring, assets, inspection, maintenanceEffect, maintenanceHistory, fieldNotes].filter(Boolean);
}

export function reliabilitySurfaceGroups(kind: ReliabilityExperienceKind, backupMode = false): ReliabilitySurfaceGroup[] {
  const surfaces = reliabilitySurfaces(kind, backupMode);
  if (backupMode) return [{ id: "workspace", label: copy("WORKSPACE", "WORKSPACE"), surfaces }];
  const group = (id: string, ko: string, en: string, ids: ReliabilitySurfaceId[]) => ({
    id,
    label: copy(ko, en),
    surfaces: ids.map((surfaceId) => surfaces.find((item) => item.id === surfaceId)).filter((item): item is ReliabilitySurface => Boolean(item)),
  });
  if (kind === "operations") return [
    group("observe", "OBSERVE · 감지", "OBSERVE", ["factory-status", "operations-status"]),
    group("decide", "DECIDE · 판단", "DECIDE", ["pending-decisions", "decision-case", "production-impact", "maintenance-approval"]),
    group("follow-up", "FOLLOW-UP · 후속", "FOLLOW-UP", ["backlog", "report-draft"]),
  ];
  if (kind === "executive") return [
    group("executive-primary", "PRIMARY · 경영 판단", "PRIMARY", ["executive-brief", "operational-risk", "executive-kpi", "decision-bottleneck", "executive-reports"]),
    group("executive-evidence", "EVIDENCE · 근거/상세", "EVIDENCE & DETAIL", ["maintenance-effect", "roadmap", "factory-status"]),
  ];
  if (kind === "engineering") return [
    group("observe", "OBSERVE · 감지", "OBSERVE", ["factory-status", "monitoring"]),
    group("diagnose", "DIAGNOSE · 진단", "DIAGNOSE", ["assets", "inspection", "maintenance-effect"]),
    group("learn", "LEARN · 이력", "LEARN", ["maintenance-history", "field-notes"]),
  ];
  return [
    group("execute", "EXECUTE · 현장", "EXECUTE", ["my-work", "work-targets", "field-status"]),
    group("history", "HISTORY · 이력", "HISTORY", ["work-history"]),
  ];
}

export function adaptiveReliabilityLandingSurface(
  kind: ReliabilityExperienceKind,
  metrics: { critical: number; pendingDecisions: number },
  backupMode = false,
): ReliabilitySurface {
  const surfaces = reliabilitySurfaces(kind, backupMode);
  if (backupMode || kind !== "operations") return defaultReliabilitySurface(kind, backupMode);
  const preferredId = metrics.critical > 0
    ? "factory-status"
    : metrics.pendingDecisions >= 3
      ? "pending-decisions"
      : "operations-status";
  return surfaces.find((item) => item.id === preferredId) ?? surfaces[0];
}

export function defaultReliabilitySurface(kind: ReliabilityExperienceKind, backupMode = false): ReliabilitySurface {
  return reliabilitySurfaces(kind, backupMode)[0];
}

export function resolveReliabilitySurface(kind: ReliabilityExperienceKind, surfaceId: string | null | undefined, backupMode = false): ReliabilitySurface {
  return reliabilitySurfaces(kind, backupMode).find((item) => item.id === surfaceId) ?? defaultReliabilitySurface(kind, backupMode);
}

export function reliabilitySurfaceForView(kind: ReliabilityExperienceKind, view: OperationsView, backupMode = false): ReliabilitySurface {
  return reliabilitySurfaces(kind, backupMode).find((item) => item.view === view) ?? defaultReliabilitySurface(kind, backupMode);
}
