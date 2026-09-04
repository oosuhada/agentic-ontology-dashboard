import type { AuthUser } from "../../../types";
import type { OperationsView } from "../../operations/api/operationsContracts";

export type ReliabilityExperienceKind = "executive" | "operations" | "engineering" | "maintenance";

export type ReliabilityFocusIntent = "continuity" | "decision" | "investigation" | "execution";
export type ReliabilityPrimarySurface = "executive_brief" | "decision_workspace" | "monitoring_workspace" | "maintenance_workspace";

export interface ReliabilityLocalizedCopy {
  ko: string;
  en: string;
}

export interface ReliabilityPageCopy {
  eyebrow: ReliabilityLocalizedCopy;
  title: ReliabilityLocalizedCopy;
  detail: ReliabilityLocalizedCopy;
}

export interface ReliabilityNavigationItem {
  view: OperationsView;
  label: ReliabilityLocalizedCopy;
  detail: ReliabilityLocalizedCopy;
  page: ReliabilityPageCopy;
}

export interface ReliabilityRoleExperience {
  kind: ReliabilityExperienceKind;
  label: ReliabilityLocalizedCopy;
  defaultView: OperationsView;
  primarySurface: ReliabilityPrimarySurface;
  primaryQuestion: ReliabilityLocalizedCopy;
  focusIntent: ReliabilityFocusIntent;
  firstScreenIntent: ReliabilityLocalizedCopy;
  operationalFocusHint: ReliabilityLocalizedCopy;
  navigation: [ReliabilityNavigationItem, ...ReliabilityNavigationItem[]];
}

function copy(ko: string, en: string): ReliabilityLocalizedCopy {
  return { ko, en };
}

function page(
  eyebrowKo: string,
  eyebrowEn: string,
  titleKo: string,
  titleEn: string,
  detailKo: string,
  detailEn: string,
): ReliabilityPageCopy {
  return {
    eyebrow: copy(eyebrowKo, eyebrowEn),
    title: copy(titleKo, titleEn),
    detail: copy(detailKo, detailEn),
  };
}

export const RELIABILITY_ROLE_EXPERIENCES: Record<ReliabilityExperienceKind, ReliabilityRoleExperience> = {
  executive: {
    kind: "executive",
    label: copy("경영진", "Executive"),
    defaultView: "reports",
    primarySurface: "executive_brief",
    primaryQuestion: copy(
      "현재 전체 운영 위험과 생산 영향은 무엇인가?",
      "What are the current operational risks and production impacts?",
    ),
    focusIntent: "continuity",
    firstScreenIntent: copy(
      "전체 위험, 생산 연속성, 중요한 미결 판단을 먼저 요약합니다.",
      "Lead with portfolio risk, production continuity, and important open decisions.",
    ),
    operationalFocusHint: copy(
      "설비별 원시 지표보다 전체 위험과 생산 영향, 미결 판단을 우선하고 필요할 때만 상세 근거로 내려갑니다.",
      "Prioritize portfolio risk, production impact, and open decisions before drilling into asset-level evidence.",
    ),
    navigation: [
      {
        view: "overview",
        label: copy("운영 리스크", "Operational risk"),
        detail: copy("KPI · 생산 연속성", "KPI · production continuity"),
        page: page(
          "브리핑",
          "BRIEFING",
          "생산 안정성과 의사결정",
          "Production continuity and decisions",
          "설비 수치보다 전체 운영 영향과 경영진이 판단해야 할 요청을 우선합니다.",
          "Prioritize business impact and executive decision requests over raw equipment metrics.",
        ),
      },
      {
        view: "operations",
        label: copy("의사결정 병목", "Decision bottlenecks"),
        detail: copy("Decision Case · Backlog", "Decision cases · backlog"),
        page: page(
          "의사결정 병목",
          "DECISION BOTTLENECKS",
          "지연 중인 핵심 의사결정",
          "Delayed critical decisions",
          "판단이 지연되는 주요 Decision Case와 다음 책임자를 경영 관점에서 확인합니다.",
          "Review delayed Decision Cases and accountable next owners from an executive perspective.",
        ),
      },
      {
        view: "reports",
        label: copy("Executive Brief", "Executive Brief"),
        detail: copy("AS-OF · 경영 보고", "AS-OF · executive reporting"),
        page: page(
          "보고서",
          "REPORTS",
          "경영 상황 보고",
          "Executive situation report",
          "핵심 결론과 생산 영향을 먼저 보고 필요한 근거만 확인합니다.",
          "Start with conclusions and production impact, then drill into evidence only when needed.",
        ),
      },
      {
        view: "objects",
        label: copy("정비 효과", "Maintenance effect"),
        detail: copy("Before-after · 주요 설비", "Before-after · key assets"),
        page: page(
          "상세 근거",
          "EVIDENCE",
          "설비 단위 근거 확인",
          "Asset-level evidence",
          "브리핑의 결론과 생산 영향 판단을 검증할 때 사용하는 상세 화면입니다.",
          "Use this view to validate conclusions and production-impact decisions from the briefing.",
        ),
      },
    ],
  },
  operations: {
    kind: "operations",
    label: copy("생산 운영", "Production operations"),
    defaultView: "operations",
    primarySurface: "decision_workspace",
    primaryQuestion: copy(
      "지금 내가 판단하거나 승인해야 하는 건 무엇인가?",
      "What do I need to decide or approve now?",
    ),
    focusIntent: "decision",
    firstScreenIntent: copy(
      "생산 영향, 대기 중인 판단, 업무 단계와 다음 행동을 연결합니다.",
      "Connect production impact, pending decisions, workflow stage, and the next action.",
    ),
    operationalFocusHint: copy(
      "생산 영향이 큰 항목부터 대기 중인 판단, 점검·정비 진행 상태와 다음 행동을 함께 보여줍니다.",
      "Lead with high-impact items, pending decisions, inspection or maintenance progress, and the next action.",
    ),
    navigation: [
      {
        view: "overview",
        label: copy("운영 현황", "Operations"),
        detail: copy("라인 위험 · 생산 영향", "Line risk · production impact"),
        page: page(
          "운영 현황",
          "OPERATIONS",
          "생산 리스크와 조치 현황",
          "Production risk and response status",
          "어느 라인이 영향을 받고 무엇을 판단해야 하는지부터 확인합니다.",
          "See which lines are exposed and what decisions are required first.",
        ),
      },
      {
        view: "operations",
        label: copy("판단 대기", "Pending decisions"),
        detail: copy("Decision Case · 정비 승인", "Decision cases · maintenance approval"),
        page: page(
          "판단 및 작업",
          "DECISIONS & WORK",
          "판단이 필요한 작업",
          "Work requiring a decision",
          "현장 점검 결과와 생산 영향, 현재 업무 단계와 다음 운영 판단을 연결합니다.",
          "Connect field findings, production impact, the current workflow stage, and the next operational decision.",
        ),
      },
      {
        view: "objects",
        label: copy("생산 영향", "Production impact"),
        detail: copy("설비 · 비용 근거", "Assets · cost evidence"),
        page: page(
          "설비",
          "ASSETS",
          "설비별 위험과 생산 영향",
          "Asset risk and production impact",
          "위험 신호가 실제 생산과 운영 판단에 미치는 영향을 설비 단위로 확인합니다.",
          "Review how asset risk signals translate into production impact and operational decisions.",
        ),
      },
      {
        view: "reports",
        label: copy("보고 초안", "Report draft"),
        detail: copy("경영진 보고로 전환", "Convert to executive brief"),
        page: page(
          "보고",
          "REPORTS",
          "운영 판단과 조치 보고",
          "Operational decisions and response report",
          "생산 영향, 판단 결과와 후속 조치 상태를 한 흐름으로 정리합니다.",
          "Summarize production impact, decisions, and follow-up response status in one flow.",
        ),
      },
    ],
  },
  engineering: {
    kind: "engineering",
    label: copy("신뢰성 분석", "Reliability analysis"),
    defaultView: "overview",
    primarySurface: "monitoring_workspace",
    primaryQuestion: copy(
      "어떤 설비를 조사해야 하고 근거는 무엇인가?",
      "Which equipment should I investigate, and what evidence supports it?",
    ),
    focusIntent: "investigation",
    firstScreenIntent: copy(
      "이상 설비와 센서·예측 신호를 먼저 찾고 조사 근거와 점검 필요성을 좁혀갑니다.",
      "Find abnormal assets and sensor or prediction signals first, then narrow the evidence and inspection need.",
    ),
    operationalFocusHint: copy(
      "이상 설비를 중심으로 센서·예측·원인 근거와 점검 필요성을 한 흐름으로 보여줍니다.",
      "Center abnormal assets, sensor and prediction evidence, causal support, and inspection need in one investigation flow.",
    ),
    navigation: [
      {
        view: "overview",
        label: copy("모니터링", "Monitoring"),
        detail: copy("설비 상태맵 · 위험 알림", "Asset map · risk alerts"),
        page: page(
          "진단 현황",
          "DIAGNOSTICS",
          "조사가 필요한 설비와 이상 신호",
          "Assets requiring investigation",
          "수치와 센서 변화부터 탐색해 조사 우선순위와 원인 후보를 좁혀갑니다.",
          "Start from measurements and sensor changes to narrow investigation priority and suspected causes.",
        ),
      },
      {
        view: "objects",
        label: copy("설비 · 센서 피쳐", "Assets · sensor features"),
        detail: copy("실시간 피쳐 · 이상 센서", "Live features · abnormal sensors"),
        page: page(
          "설비 진단",
          "ASSET ANALYSIS",
          "설비 신호와 원인 근거",
          "Equipment signals and causal evidence",
          "센서, 예측, 원인 기여와 이력을 한 흐름에서 분석합니다.",
          "Analyze sensors, predictions, contribution factors, and history in one flow.",
        ),
      },
      {
        view: "operations",
        label: copy("점검 · 정비 이력", "Inspection · maintenance"),
        detail: copy("점검 실행 · 조치 결과", "Inspection · action results"),
        page: page(
          "점검 기록",
          "INSPECTION RECORD",
          "점검 결과와 분석 이력",
          "Inspection findings and analysis history",
          "현장 점검 결과를 기존 신호와 근거에 연결해 다음 조사 필요성을 확인합니다.",
          "Connect field findings to prior signals and evidence to determine what investigation is still needed.",
        ),
      },
      {
        view: "reports",
        label: copy("현장 메모 · 분석 보고", "Field notes · analysis report"),
        detail: copy("근거 정리 · 공유", "Evidence summary · sharing"),
        page: page(
          "분석 보고",
          "ANALYSIS REPORT",
          "근거 기반 분석 보고",
          "Evidence-based analysis report",
          "확인된 신호, 근거와 남은 불확실성을 구분해 조사 결과를 정리합니다.",
          "Separate confirmed signals, supporting evidence, and remaining uncertainty in the investigation report.",
        ),
      },
    ],
  },
  maintenance: {
    kind: "maintenance",
    label: copy("정비 실행", "Maintenance execution"),
    defaultView: "operations",
    primarySurface: "maintenance_workspace",
    primaryQuestion: copy(
      "지금 수행해야 할 승인된 작업은 무엇인가?",
      "What approved work do I need to perform now?",
    ),
    focusIntent: "execution",
    firstScreenIntent: copy(
      "승인·배정된 작업과 대상 위치, 현재 작업 단계와 실행 상태를 먼저 보여줍니다.",
      "Lead with approved or assigned work, target location, current work step, and execution status.",
    ),
    operationalFocusHint: copy(
      "승인·배정된 작업을 중심으로 대상 설비, 위치와 현장 문맥, 현재 작업 단계와 실행 상태를 보여줍니다.",
      "Center approved or assigned work with the target asset, location and field context, current work step, and execution status.",
    ),
    navigation: [
      {
        view: "operations",
        label: copy("내 작업", "My work"),
        detail: copy("승인 작업 · 진행 상태", "Approved work · progress"),
        page: page(
          "내 작업",
          "MY WORK",
          "승인된 정비 작업",
          "Approved maintenance work",
          "어디에서 무엇을 해야 하는지와 현재 작업 순서를 먼저 확인합니다.",
          "Start with where to go, what to do, and the current work sequence.",
        ),
      },
      {
        view: "objects",
        label: copy("작업 대상", "Work targets"),
        detail: copy("위치 · 상태 · 근거", "Location · condition · evidence"),
        page: page(
          "작업 대상",
          "WORK TARGETS",
          "작업 대상 위치와 현장 근거",
          "Work target location and field evidence",
          "승인된 작업을 수행하는 데 필요한 설비 위치, 상태와 근거를 확인합니다.",
          "Review the equipment location, condition, and evidence needed to perform approved work.",
        ),
      },
      {
        view: "overview",
        label: copy("현장 현황", "Field status"),
        detail: copy("점검 · 정비 진행 상황", "Inspection · maintenance progress"),
        page: page(
          "현장 현황",
          "FIELD STATUS",
          "현장 작업 진행 상태",
          "Field work status",
          "승인된 점검과 정비가 현재 어느 단계에 있고 무엇이 남았는지 확인합니다.",
          "See the current step of approved inspection and maintenance work and what remains.",
        ),
      },
      {
        view: "reports",
        label: copy("작업 이력", "Work history"),
        detail: copy("완료 결과 · 기록", "Completion results · record"),
        page: page(
          "작업 이력",
          "WORK HISTORY",
          "완료 작업과 실행 이력",
          "Completed work and execution history",
          "완료 결과와 현장 기록을 확인해 작업 이력을 추적합니다.",
          "Trace completed work through completion results and field records.",
        ),
      },
    ],
  },
};

export function resolveReliabilityRoleExperience(user: AuthUser): ReliabilityRoleExperience {
  const roles = user.active_project_roles.length ? user.active_project_roles : user.roles;
  if (roles.includes("executive_viewer")) return RELIABILITY_ROLE_EXPERIENCES.executive;
  if (roles.includes("process_manager") || user.is_admin) return RELIABILITY_ROLE_EXPERIENCES.operations;
  if (roles.includes("maintenance_technician")) return RELIABILITY_ROLE_EXPERIENCES.maintenance;
  return RELIABILITY_ROLE_EXPERIENCES.engineering;
}

export function reliabilityNavigation(experience: ReliabilityRoleExperience): ReliabilityNavigationItem[] {
  const order: Record<ReliabilityExperienceKind, OperationsView[]> = {
    executive: ["reports", "operations", "overview", "objects"],
    operations: ["operations", "overview", "objects", "reports"],
    engineering: ["overview", "objects", "operations", "reports"],
    maintenance: ["operations", "objects", "overview", "reports"],
  };
  const items = new Map(experience.navigation.map((item) => [item.view, item]));
  return order[experience.kind]
    .map((view) => items.get(view))
    .filter((item): item is ReliabilityNavigationItem => Boolean(item));
}

export function reliabilityPageCopy(
  experience: ReliabilityRoleExperience,
  view: OperationsView,
): ReliabilityPageCopy {
  const activeItem = experience.navigation.find((item) => item.view === view);
  const defaultItem = experience.navigation.find((item) => item.view === experience.defaultView);
  return activeItem?.page ?? defaultItem?.page ?? experience.navigation[0].page;
}
