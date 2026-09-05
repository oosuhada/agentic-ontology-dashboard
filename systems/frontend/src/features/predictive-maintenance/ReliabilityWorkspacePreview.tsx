import {
  ChevronsLeft,
  ChevronsRight,
  Focus,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Settings2,
  UserRound,
} from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  createOperationsAgentReviewSummary,
  getOperationsAgentReviewPacket,
  getOperationsAgentReviewSummary,
  runAgentQuery,
} from "../../api";
import type { AuthUser } from "../../types";
import { displayPreset, useDisplayPreferences } from "../../ui/foundry/displayPreferences";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { HanbitLogo } from "../../ui/foundry/HanbitLogo";
import type {
  OperationsClosedLoopLifecycleStep,
  OperationsAgentReviewPacket,
  OperationsAgentReviewSummaryResponse,
  OperationsBootstrapModel,
  OperationsContextModel,
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsView,
} from "../operations/api/operationsContracts";
import { displayAssetName, displayExplanationMethod, displayLineLabel, displaySensorFactorLabel, fieldFactorItem } from "../operations/displayLabels";
import "./reliability-workspace-preview.css";
import { ContextAssistantDrawer } from "./workspace/ContextAssistantDrawer";
import { ReliabilityCommandPalette, type ReliabilitySearchEntity } from "./workspace/ReliabilityCommandPalette";
import { LifecycleInstrument } from "./workspace/LifecycleInstrument";
import { OperationalFocus } from "./workspace/OperationalFocus";
import {
  groundedReliabilityAssistantAnswer,
  type ReliabilityAssistantContext,
  type ReliabilityAssistantMessage,
} from "./workspace/assistantContext";
import { resolveReliabilityRoleExperience } from "./workspace/roleExperience";
import { reliabilitySurfaceGroups, reliabilitySurfaces, resolveReliabilitySurface } from "./workspace/roleSurfaces";

const ImmersiveRiskWorkbench = lazy(() =>
  import("./workspace/ImmersiveRiskWorkbench").then((module) => ({
    default: module.ImmersiveRiskWorkbench,
  })),
);

const RELIABILITY_LOCALE_STORAGE_KEY = "ontology-dashboard:reliability-locale";

function initialReliabilityLocale(): "ko-KR" | "en-US" {
  const saved = window.localStorage.getItem(RELIABILITY_LOCALE_STORAGE_KEY);
  return saved === "en-US" ? "en-US" : "ko-KR";
}

function probability(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function displayDateTime(value: string | null | undefined, english: boolean) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(english ? "en-US" : "ko-KR", { dateStyle: "short", timeStyle: "short" });
}

function assistantActivityStepLabel(name: string, english: boolean) {
  const normalized = name.trim().toLowerCase();
  const labels: Record<string, [string, string]> = {
    route: ["질의 경로 결정", "Resolve query route"],
    routing: ["질의 경로 결정", "Resolve query route"],
    relational: ["운영 데이터 조회", "Query operational data"],
    relational_retrieval: ["운영 데이터 조회", "Query operational data"],
    graph: ["Ontology 관계 탐색", "Traverse ontology relations"],
    graph_retrieval: ["Ontology 관계 탐색", "Traverse ontology relations"],
    vector: ["RAG 문서 검색", "Search RAG documents"],
    vector_retrieval: ["RAG 문서 검색", "Search RAG documents"],
    retrieve: ["연결 근거 검색", "Retrieve connected evidence"],
    retrieval: ["연결 근거 검색", "Retrieve connected evidence"],
    ground: ["근거 연결 검증", "Validate evidence grounding"],
    grounding: ["근거 연결 검증", "Validate evidence grounding"],
    compose: ["근거 기반 답변 구성", "Compose grounded answer"],
    answer: ["근거 기반 답변 구성", "Compose grounded answer"],
  };
  if (labels[normalized]) return labels[normalized][english ? 1 : 0];
  const matched = Object.entries(labels).find(([key]) => normalized.includes(key));
  if (matched) return matched[1][english ? 1 : 0];
  return name.replaceAll("_", " ").replaceAll(".", " › ");
}

function assistantActivityStoreLabel(store: string | null | undefined) {
  if (!store) return null;
  const labels: Record<string, string> = {
    postgresql: "PostgreSQL",
    neo4j: "Ontology Graph",
    pgvector: "pgvector",
    project3_rag: "Knowledge RAG",
  };
  return labels[store] ?? store;
}

const OPERATIONAL_FOCUS_SURFACES = new Set([
  "decision-case",
  "maintenance-approval",
  "inspection",
  "my-work",
  "work-targets",
  "factory-status",
]);

const IMMERSIVE_RISK_SURFACES = new Set([
  "factory-status",
  "monitoring",
  "operational-risk",
  "operations-overview",
  "assets",
  "production-impact",
]);

function shouldShowOperationalFocus(surfaceId: string) {
  return OPERATIONAL_FOCUS_SURFACES.has(surfaceId);
}

const LIFECYCLE_LABELS: Record<OperationsClosedLoopLifecycleStep, [string, string]> = {
  prediction: ["예측", "Prediction"],
  evidence: ["근거 확인", "Evidence review"],
  decision: ["운영 판단", "Decision"],
  inspection_requested: ["점검 요청", "Inspection requested"],
  inspection_approved: ["점검 승인", "Inspection approved"],
  inspection_in_progress: ["점검 중", "Inspection in progress"],
  inspection_completed: ["점검 완료", "Inspection completed"],
  recommendation_proposed: ["정비안 제안", "Recommendation proposed"],
  maintenance_requested: ["정비 요청", "Maintenance requested"],
  maintenance_approved: ["정비 승인", "Maintenance approved"],
  maintenance_in_progress: ["정비 중", "Maintenance in progress"],
  maintenance_completed: ["정비 완료", "Maintenance completed"],
  post_maintenance_observation_pending: ["정비 후 관측 대기", "Post-maintenance observation pending"],
  ready_for_reprediction: ["재예측 가능", "Ready for re-prediction"],
};

function lifecycleLabel(step: OperationsClosedLoopLifecycleStep | null | undefined, english: boolean) {
  if (!step) return null;
  return LIFECYCLE_LABELS[step][english ? 1 : 0];
}

const CLOSED_LOOP_ACTION_LABELS: Record<string, [string, string]> = {
  create_inspection_work_order: ["점검 작업요청 생성", "Create inspection work request"],
  request_inspection_work_order: ["점검 작업요청 생성", "Create inspection work request"],
  request_inspection: ["점검 요청", "Request inspection"],
  approve_inspection_work_order: ["점검 승인", "Approve inspection work request"],
  start_inspection_work_order: ["점검 시작", "Start inspection"],
  start_inspection: ["점검 시작", "Start inspection"],
  complete_inspection_work_order: ["점검 결과 기록·완료", "Record and complete inspection"],
  complete_inspection: ["점검 결과 기록·완료", "Record and complete inspection"],
  calculate_maintenance_cost: ["정비 비용 분석", "Run maintenance cost analysis"],
  create_operations_manual_recommendation: ["정비안 생성", "Create maintenance recommendation"],
  decide_operations_manual_recommendation: ["정비안 판단", "Review maintenance recommendation"],
  approve_maintenance_work_order: ["정비 WorkOrder 승인", "Approve maintenance WorkOrder"],
  start_maintenance_action: ["정비 시작", "Start maintenance"],
  complete_maintenance_action: ["정비 완료", "Complete maintenance"],
  request_maintenance_replay: ["정비 후 관측 재개", "Resume post-maintenance observation"],
};

function closedLoopActionLabel(actionId: string | null | undefined, fallback: string | null | undefined, english: boolean) {
  if (!actionId) return fallback ?? null;
  return CLOSED_LOOP_ACTION_LABELS[actionId]?.[english ? 1 : 0]
    ?? (english ? actionId.replaceAll("_", " ") : fallback ?? actionId);
}

function closedLoopOwnerLabel(
  role: "process_manager" | "process_engineer" | "maintenance_technician" | "unassigned" | null | undefined,
  fallback: string | null | undefined,
  english: boolean,
) {
  if (!english) return fallback ?? null;
  if (role === "process_manager") return "Operations manager";
  if (role === "process_engineer") return "Field engineer";
  if (role === "maintenance_technician") return "Maintenance technician";
  if (role === "unassigned") return "Unassigned";
  return fallback ?? null;
}

const CLOSED_LOOP_ACTIVITY_LABELS: Record<string, [string, string]> = {
  "work_order.requested": ["작업요청 생성", "Work request created"],
  "work_order.approved": ["작업요청 승인", "Work request approved"],
  "work_order.started": ["작업 시작", "Work started"],
  "work_order.completed": ["작업 완료", "Work completed"],
  "inspection.completed": ["점검 결과 기록", "Inspection result recorded"],
  "recommendation.proposed": ["정비안 제안", "Maintenance recommendation proposed"],
  "recommendation.decided": ["정비안 판단", "Maintenance recommendation decided"],
  "maintenance.started": ["정비 시작", "Maintenance started"],
  "maintenance.completed": ["정비 완료", "Maintenance completed"],
  "maintenance.replay_requested": ["재평가 요청", "Re-evaluation requested"],
};

function closedLoopActivityLabel(eventType: string, fallback: string, english: boolean) {
  return CLOSED_LOOP_ACTIVITY_LABELS[eventType]?.[english ? 1 : 0]
    ?? (english ? eventType.replaceAll("_", " ").replaceAll(".", " ") : fallback);
}

const ENGLISH_FACTOR_LABELS: Record<string, string> = {
  rotation_raw: "Rotation average",
  vibration_raw: "Vibration average",
  pressure_raw: "Pressure average",
  voltage_raw: "Voltage",
  current_raw: "Current",
  relative_vibration_z: "Vibration anomaly",
  spindle_vibration: "Spindle vibration",
  air_pressure: "Air pressure",
  flow_rate: "Flow rate",
  air_temperature_k: "Intake air temperature",
  process_temperature_k: "Process temperature",
  rotational_speed_rpm: "Spindle speed",
  torque_nm: "Torque",
  tool_wear_min: "Tool wear",
  mechanical_power_w: "Motor power",
  power_w: "Motor power",
  overstrain_index: "Overstrain index",
  overstrain_load: "Overstrain index",
  temperature_difference_k: "Process-air temperature gap",
  temperature_gap_k: "Process-air temperature gap",
  generator_failure_score: "Model risk score",
  model_selected_threshold: "Risk decision threshold",
  asset_criticality_adjustment: "Asset criticality adjustment",
  generator_model_artifact_manifest: "Applied model release",
};

function englishFactorLabel(key: string) {
  const base = key
    .replace(/_(1h|6h|12h|24h|7d|30d)_(max_abs|abs_max|abs_mean|change|max|min|mean|std|last)$/, "")
    .replace(/_(abs_current|current)$/, "");
  return ENGLISH_FACTOR_LABELS[key] ?? ENGLISH_FACTOR_LABELS[base] ?? base.replaceAll("_", " ");
}

function factorExplanationLabel(value: string | null | undefined, english: boolean) {
  if (!english) return displayExplanationMethod(value);
  if (!value) return null;
  if (value.includes("proxy_attribution") || value.includes("attribution")) return "Model contribution analysis";
  if (value.includes("shap")) return "Model impact analysis";
  return null;
}

function riskStatusLabel(status: OperationsEvent["status"] | null | undefined, english: boolean) {
  const labels: Record<NonNullable<OperationsEvent["status"]>, [string, string]> = {
    normal: ["정상", "Normal"],
    attention: ["주의", "Attention"],
    warning: ["경고", "Warning"],
    critical: ["고위험", "Critical"],
    data_quality_hold: ["데이터 확인 필요", "Data quality hold"],
  };
  return status ? labels[status][english ? 1 : 0] : (english ? "No selection" : "선택 없음");
}

function riskTone(status: OperationsEvent["status"] | null | undefined) {
  if (status === "critical") return "critical" as const;
  if (status === "warning") return "warning" as const;
  if (status === "attention" || status === "data_quality_hold") return "attention" as const;
  if (status === "normal") return "normal" as const;
  return "neutral" as const;
}

function recommendedDecisionLabel(value: OperationsEvent["recommendedDecision"] | null | undefined, english: boolean) {
  if (!value) return null;
  const labels: Record<OperationsEvent["recommendedDecision"], [string, string]> = {
    continue_monitoring: ["계속 관찰", "Continue monitoring"],
    request_inspection: ["현장 점검 요청", "Request inspection"],
    review_shutdown: ["정지 검토 요청", "Review shutdown"],
    hold_for_data_check: ["데이터 확인 보류", "Hold for data check"],
  };
  return labels[value][english ? 1 : 0];
}

function operationalImpactLabel(detail: OperationsEventDetailModel | null, english: boolean) {
  const estimatedLostUnits = detail?.operationContext?.eventImpact?.estimatedLostUnits;
  if (typeof estimatedLostUnits === "number") {
    return english
      ? `Estimated ${estimatedLostUnits.toLocaleString()} units at risk`
      : `계획 생산량 약 ${estimatedLostUnits.toLocaleString()}개 영향 추정`;
  }
  const impact = detail?.operationContext?.productionImpact;
  const labels = {
    none: ["현재 생산 영향 없음", "No current production impact"],
    low: ["낮은 생산 영향", "Low production impact"],
    medium: ["중간 생산 영향", "Medium production impact"],
    high: ["높은 생산 영향", "High production impact"],
  } as const;
  return impact ? labels[impact][english ? 1 : 0] : (english ? "Production impact not available" : "생산 영향 미제공");
}

function factorValue(value: number | null, unit: string | null, english = false) {
  if (value === null) return null;
  return `${value.toLocaleString(english ? "en-US" : "ko-KR")}${unit ? ` ${unit}` : ""}`;
}

function evidenceItemLabel(
  item: OperationsAgentReviewPacket["model_expression_context"]["top_factors"][number],
  english: boolean,
) {
  const rawValue = item.value === null || item.value === undefined
    ? null
    : typeof item.value === "number"
      ? item.value.toLocaleString(english ? "en-US" : "ko-KR", { maximumFractionDigits: 3 })
      : String(item.value);
  const unit = item.unit && item.unit !== "model unit" ? ` ${item.unit}` : "";
  const label = english
    ? englishFactorLabel(item.feature)
    : displaySensorFactorLabel(item.feature, item.display_name);
  return `${label}${rawValue ? ` ${rawValue}${unit}` : ""}`;
}

function operationalFocusCopy(input: {
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  lifecycleCurrentLabel: string | null;
  lifecycleNextLabel: string | null;
  primaryActionLabel: string | null;
  roleHeadline: string;
  roleDetail: string;
  english: boolean;
}) {
  if (!input.selectedEvent) {
    return { headline: input.roleHeadline, detail: input.roleDetail };
  }

  const event = input.selectedEvent;
  const eventAssetName = input.english
    ? (event.assetName || event.assetId)
    : displayAssetName({ assetId: event.assetId, displayName: event.assetName });
  const risk = probability(event.failureProbability);
  const impact = operationalImpactLabel(input.detail, input.english);
  const action = input.primaryActionLabel;
  const current = input.lifecycleCurrentLabel;
  const next = input.lifecycleNextLabel;
  const headline = action
    ? `${eventAssetName} · ${action}`
    : current
      ? `${eventAssetName} · ${current}`
      : `${eventAssetName} · ${riskStatusLabel(event.status, input.english)} ${risk}`;

  const facts = [
    input.english ? `Failure risk ${risk}` : `고장 위험 ${risk}`,
    impact,
    current ? (input.english ? `Current ${current}` : `현재 ${current}`) : null,
    next ? (input.english ? `Next ${next}` : `다음 ${next}`) : null,
    action ? (input.english ? `Action ${action}` : `행동 ${action}`) : null,
  ].filter((value): value is string => Boolean(value));

  return { headline, detail: facts.join(" · ") };
}

export function reliabilityWorkspacePreviewEnabled() {
  const queryEnabled = new URLSearchParams(window.location.search).get("workspace_shell") === "reliability";
  if (queryEnabled) return true;
  const basePath = import.meta.env.BASE_URL.replace(/\/+$/, "");
  const pathname = window.location.pathname;
  if (basePath === "") {
    return /^\/app\/projects\/[^/]+\/operations/.test(pathname);
  }
  const previewBaseEnabled = basePath === "/reliability-preview"
    && (pathname === basePath || pathname.startsWith(`${basePath}/`));
  return previewBaseEnabled;
}

export function ReliabilityWorkspaceLoadingPlaceholder() {
  const locale = initialReliabilityLocale();
  const english = locale === "en-US";

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return (
    <main
      className="rw-preview-shell rw-preview-loading-placeholder left-open assistant-closed"
      aria-busy="true"
      aria-label={english ? "Reliability workspace loading" : "Reliability workspace 불러오는 중"}
    >
      <header className="rw-preview-topbar">
        <div className="rw-preview-topbar-left">
          <div className="rw-preview-brand"><span><HanbitLogo /></span><div><strong>Hanbit Tech</strong><small>Reliability Operations</small></div></div>
          <div className="rw-preview-loading-line is-breadcrumb" />
        </div>
        <div className="rw-preview-loading-line is-user" />
      </header>

      <div className="rw-preview-body">
        <aside className="rw-preview-left rw-preview-loading-left" aria-hidden="true">
          <div className="rw-preview-loading-line is-eyebrow" />
          <div className="rw-preview-loading-line is-nav" />
          <div className="rw-preview-loading-line is-nav" />
          <div className="rw-preview-loading-line is-nav" />
          <div className="rw-preview-loading-line is-scope" />
        </aside>

        <section className="rw-preview-main">
          <header className="rw-preview-page-heading">
            <span>{english ? "RELIABILITY OPERATIONS" : "RELIABILITY OPERATIONS"}</span>
            <h1>{english ? "Preparing the operational workspace" : "운영 워크스페이스를 준비하고 있습니다"}</h1>
            <p>{english ? "Connecting risk, evidence, lifecycle, and the next action." : "위험, 근거, lifecycle, 다음 행동을 연결하고 있습니다."}</p>
          </header>

          <div className="rw-preview-loading-content" aria-hidden="true">
            <section className="rw-preview-loading-card is-focus">
              <div className="rw-preview-loading-line is-kicker" />
              <div className="rw-preview-loading-line is-title" />
              <div className="rw-preview-loading-line is-copy" />
              <div className="rw-preview-loading-metrics">
                <span /><span /><span /><span />
              </div>
            </section>
            <section className="rw-preview-loading-card-grid">
              <div className="rw-preview-loading-card"><div className="rw-preview-loading-line is-title" /><div className="rw-preview-loading-line is-copy" /><div className="rw-preview-loading-line is-copy short" /></div>
              <div className="rw-preview-loading-card"><div className="rw-preview-loading-line is-title" /><div className="rw-preview-loading-line is-copy" /><div className="rw-preview-loading-line is-copy short" /></div>
            </section>
          </div>
        </section>
      </div>

      <footer className="rw-preview-bottom" aria-hidden="true">
        <div className="rw-preview-loading-lifecycle">
          <span /><span /><span /><span /><span />
        </div>
      </footer>
    </main>
  );
}

export function ReliabilityWorkspacePreview({
  model,
  context,
  activeView,
  activeSurface,
  user,
  selectedEvent,
  latestEventForSelectedAsset,
  detail,
  onSelectEvent,
  onNavigate,
  onRefresh,
  refreshing,
  onLogout,
  searchEntities = [],
  onSearchSelect,
  onFollowLatestEvent,
  backupMode = false,
  children,
}: {
  model: OperationsBootstrapModel;
  context: OperationsContextModel;
  activeView: OperationsView;
  activeSurface: string | null;
  user: AuthUser;
  selectedEvent: OperationsEvent | null;
  latestEventForSelectedAsset?: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  onSelectEvent: (event: OperationsEvent) => void;
  onNavigate: (surfaceId: string, view: OperationsView) => void;
  onRefresh: () => void;
  refreshing: boolean;
  onLogout: () => void | Promise<void>;
  searchEntities?: ReliabilitySearchEntity[];
  onSearchSelect?: (entity: ReliabilitySearchEntity) => void;
  onFollowLatestEvent?: () => void;
  backupMode?: boolean;
  children: ReactNode;
}) {
  const { setLocale } = useI18n();
  const { preferences, setPreset, setShowGuidance, setTheme } = useDisplayPreferences();
  const [locale, setReliabilityLocaleState] = useState<"ko-KR" | "en-US">(initialReliabilityLocale);
  const english = locale === "en-US";
  const experience = useMemo(() => resolveReliabilityRoleExperience(user), [user]);
  const navigation = useMemo(() => reliabilitySurfaces(experience.kind, backupMode), [backupMode, experience.kind]);
  const navigationGroups = useMemo(() => reliabilitySurfaceGroups(experience.kind, backupMode), [backupMode, experience.kind]);
  const preset = displayPreset(preferences);
  const activeNav = resolveReliabilitySurface(experience.kind, activeSurface, backupMode);
  const activePageCopy = activeNav.page;
  const eyebrow = english ? activePageCopy.eyebrow.en : activePageCopy.eyebrow.ko;
  const title = english ? activePageCopy.title.en : activePageCopy.title.ko;
  const detailCopy = english ? activePageCopy.detail.en : activePageCopy.detail.ko;
  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth > 860);
  const railCollapsedByViewportRef = useRef(window.innerWidth <= 860);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const settingsRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const [messages, setMessages] = useState<ReliabilityAssistantMessage[]>([]);
  const [agentPacket, setAgentPacket] = useState<OperationsAgentReviewPacket | null>(null);
  const [agentSummaryResponse, setAgentSummaryResponse] = useState<OperationsAgentReviewSummaryResponse | null>(null);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantQueryLoading, setAssistantQueryLoading] = useState(false);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [navPreview, setNavPreview] = useState<{
    id: string;
    label: string;
    detail: string;
    view: OperationsView;
    top: number;
    left: number;
  } | null>(null);

  useEffect(() => {
    function syncRailForViewport() {
      setNavPreview(null);
      if (window.innerWidth <= 860) {
        railCollapsedByViewportRef.current = true;
        setLeftOpen(false);
      } else if (railCollapsedByViewportRef.current) {
        railCollapsedByViewportRef.current = false;
        setLeftOpen(true);
      }
    }
    window.addEventListener("resize", syncRailForViewport);
    return () => window.removeEventListener("resize", syncRailForViewport);
  }, []);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [activeNav.id]);

  useEffect(() => {
    window.localStorage.setItem(RELIABILITY_LOCALE_STORAGE_KEY, locale);
    setLocale(locale);
  }, [locale, setLocale]);

  useEffect(() => {
    setMessages([]);
    setAgentPacket(null);
    setAgentSummaryResponse(null);
    setAssistantError(null);
  }, [selectedEvent?.eventId]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSettingsOpen(false);
        setSearchOpen(true);
      }
      if (event.key === "Escape" && settingsOpen) setSettingsOpen(false);
    }
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, [settingsOpen]);

  useEffect(() => {
    if (!settingsOpen) return;
    function handlePointerDown(event: PointerEvent) {
      if (!(event.target instanceof Node)) return;
      if (!settingsRef.current?.contains(event.target)) setSettingsOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [settingsOpen]);

  useEffect(() => {
    const assetId = selectedEvent?.assetId;
    if (!assistantOpen || !assetId) return;
    let cancelled = false;
    setAssistantLoading(true);
    setAssistantError(null);

    const request = {
      assetId,
      projectId: context.projectId,
      datasetVersionId: context.datasetVersionId,
      eventId: selectedEvent?.eventId ?? null,
      historyWindow: "24h" as const,
    };

    async function loadGroundedSummary() {
      const cached = await getOperationsAgentReviewSummary(request);
      if (cached.summary) return cached;
      return createOperationsAgentReviewSummary({ ...request, trigger: "ui_manual_regeneration" });
    }

    void Promise.allSettled([
      getOperationsAgentReviewPacket(request),
      loadGroundedSummary(),
    ]).then(([packetResult, summaryResult]) => {
      if (cancelled) return;
      if (packetResult.status === "fulfilled") setAgentPacket(packetResult.value);
      if (summaryResult.status === "fulfilled") setAgentSummaryResponse(summaryResult.value);
      if (packetResult.status === "rejected" && summaryResult.status === "rejected") {
        setAssistantError(english
          ? "Agent Review context is unavailable; using the selected event context only."
          : "Agent Review 문맥을 가져오지 못해 선택 이벤트 문맥만 사용합니다.");
      }
    }).finally(() => {
      if (!cancelled) setAssistantLoading(false);
    });

    return () => { cancelled = true; };
  }, [assistantOpen, context.datasetVersionId, context.projectId, selectedEvent?.assetId, selectedEvent?.eventId]);

  function setReliabilityLocale(nextLocale: "ko-KR" | "en-US") {
    setReliabilityLocaleState(nextLocale);
  }

  function showNavPreview(
    item: { id: string; label: { ko: string; en: string }; detail: { ko: string; en: string }; view: OperationsView },
    target: HTMLElement,
  ) {
    if (window.innerWidth <= 680) return;
    const rect = target.getBoundingClientRect();
    const panelWidth = 292;
    const panelHeight = 178;
    const gap = 10;
    const rightSide = rect.right + gap;
    const left = rightSide + panelWidth <= window.innerWidth - 10
      ? rightSide
      : Math.max(10, rect.left - panelWidth - gap);
    const top = Math.max(56, Math.min(rect.top - 8, window.innerHeight - panelHeight - 12));
    setNavPreview({
      id: item.id,
      label: english ? item.label.en : item.label.ko,
      detail: english ? item.detail.en : item.detail.ko,
      view: item.view,
      top,
      left,
    });
  }

  const workOrderCount = detail?.closedLoop?.workOrders.length ?? 0;
  const lifecycleSummary = detail?.closedLoop?.lifecycleSummary ?? null;
  const primaryAction = detail?.closedLoop?.primaryAction ?? null;
  const focusPrimaryAction = primaryAction
    ? {
      label: closedLoopActionLabel(primaryAction.actionId, primaryAction.label, english) ?? primaryAction.label,
      ownerLabel: closedLoopOwnerLabel(primaryAction.ownerRole, primaryAction.ownerLabel, english),
      disabled: false,
      disabledReason: null,
    }
    : selectedEvent
      ? {
        label: experience.kind === "operations"
          ? (english ? "Review inspection decision" : "점검 요청 판단하기")
          : experience.kind === "executive"
            ? (english ? "Open the current case report" : "현재 Case 보고 열기")
            : (english ? "Review evidence and start work" : "근거 확인 후 점검 시작하기"),
        ownerLabel: experience.kind === "operations"
          ? (english ? "Operations manager" : "운영 관리자")
          : experience.kind === "executive"
            ? (english ? "Executive reviewer" : "경영진 검토자")
            : (english ? "Field engineer" : "현장 엔지니어"),
        disabled: false,
        disabledReason: null,
      }
      : null;
  const lifecycleCompletedSteps = lifecycleSummary?.completedSteps.map((step) => ({
    id: step,
    label: lifecycleLabel(step, english) ?? step,
  })) ?? [];
  const lifecycleCurrent = lifecycleSummary
    ? {
      id: lifecycleSummary.currentStep,
      label: english
        ? (lifecycleLabel(lifecycleSummary.currentStep, true) || lifecycleSummary.currentStep)
        : (lifecycleSummary.currentStepLabel || lifecycleLabel(lifecycleSummary.currentStep, false) || lifecycleSummary.currentStep),
    }
    : null;
  const lifecycleNext = lifecycleSummary?.nextStep
    ? { id: lifecycleSummary.nextStep, label: lifecycleLabel(lifecycleSummary.nextStep, english) ?? lifecycleSummary.nextStep }
    : null;
  const fallbackLifecycleCurrent = selectedEvent
    ? {
      id: "decision_candidate",
      label: english ? "Decision candidate selected" : "판단 후보 추천됨",
    }
    : null;
  const fallbackLifecycleNext = selectedEvent
    ? {
      id: "review_next_action",
      label: experience.kind === "engineering"
        ? (english ? "Review evidence" : "근거 확인")
        : experience.kind === "executive"
          ? (english ? "Review brief" : "보고 검토")
          : (english ? "Review work request" : "작업 요청 검토"),
    }
    : null;
  const lifecycleCurrentForDisplay = lifecycleCurrent ?? fallbackLifecycleCurrent;
  const lifecycleNextForDisplay = lifecycleNext ?? fallbackLifecycleNext;
  const lifecycleTimeline = detail?.closedLoop?.timeline.map((item) => ({
    id: item.timelineId,
    label: closedLoopActivityLabel(item.eventType, item.label, english),
    status: item.status,
    actor: item.actorDisplayName,
    occurredAt: item.occurredAt,
  })) ?? [];
  const evidence = detail?.topFactors.slice(0, 4).map((factor) => ({
    id: factor.id,
    label: english ? englishFactorLabel(factor.feature) : fieldFactorItem(factor),
    value: factorValue(factor.value, factor.unit, english),
    detail: factorExplanationLabel(factor.explanationMethod, english),
  })) ?? [];
  const freshnessObservedAt = detail?.assetDetailStatus?.lastUpdatedAt
    ?? selectedEvent?.observedAt
    ?? context.observedAt
    ?? context.refreshedAt;
  const agentSummary = agentSummaryResponse?.summary ?? null;
  const roleSummary = agentSummary?.role_summaries.find((item) => (
    experience.kind === "operations"
      ? item.role === "process_manager"
      : experience.kind === "engineering" || experience.kind === "maintenance"
        ? item.role === "field_operator"
        : false
  ));
  const packetEvidenceItems = agentPacket?.model_expression_context.top_factors.slice(0, 4).map((item) => evidenceItemLabel(item, english)) ?? [];
  const assistantEvidenceItems = packetEvidenceItems.length
    ? packetEvidenceItems
    : evidence.map((item) => `${item.label}${item.value ? ` ${item.value}` : ""}`);
  const assistantHistoryItems = agentSummary?.history_summary.length
    ? agentSummary.history_summary
    : agentPacket?.review_draft.history_summary ?? [];
  const assistantContext: ReliabilityAssistantContext = {
    roleKind: experience.kind,
    assetId: selectedEvent?.assetId ?? null,
    assetName: selectedEvent?.assetName ?? null,
    eventId: selectedEvent?.eventId ?? null,
    failureProbability: selectedEvent?.failureProbability ?? null,
    statusLabel: riskStatusLabel(selectedEvent?.status, english),
    lineLabel: selectedEvent?.line ?? null,
    operationalImpact: operationalImpactLabel(detail, english),
    recommendedDecisionLabel: recommendedDecisionLabel(selectedEvent?.recommendedDecision, english),
    predictedFailureType: selectedEvent?.predictedFailureType ?? null,
    assignedEngineer: selectedEvent?.assignedEngineer ?? null,
    currentLifecycleLabel: lifecycleCurrentForDisplay?.label ?? null,
    nextLifecycleLabel: lifecycleNextForDisplay?.label ?? null,
    primaryActionLabel: focusPrimaryAction?.label ?? null,
    evidenceCount: evidence.length,
    evidenceSummary: assistantEvidenceItems.length
      ? assistantEvidenceItems.join(" · ")
      : null,
    workOrderCount,
    maintenanceState: lifecycleCurrentForDisplay?.label ?? null,
    observedAt: freshnessObservedAt,
    freshnessLabel: freshnessObservedAt ?? null,
    priorityReasons: agentPacket?.review_priority?.reasons ?? [],
    evidenceItems: assistantEvidenceItems,
    historyItems: assistantHistoryItems,
    workHistorySummary: assistantHistoryItems.length ? assistantHistoryItems.join(" · ") : null,
    aiSummary: experience.kind === "executive"
      ? agentSummary?.summary ?? agentPacket?.review_draft.summary ?? null
      : roleSummary?.quote ?? agentSummary?.summary ?? agentPacket?.review_draft.summary ?? null,
    aiSummaryMode: agentSummary?.mode ?? null,
    aiProvider: agentSummaryResponse?.trace.provider ?? null,
    retrievalProvider: agentPacket?.sop_retrieval.provider ?? null,
    retrievalCount: agentPacket?.sop_retrieval.returned_count ?? null,
  };
  const assistantActions = experience.kind === "engineering"
    ? [
      { id: "evidence", label: english ? "Open asset evidence" : "설비 근거 열기", detail: english ? "Sensors · factors · history" : "센서 · 기여도 · 이력", onClick: () => onNavigate("assets", "objects") },
      { id: "sensor", label: english ? "Analyze root cause" : "원인 분석 열기", detail: english ? "Signals · contribution · anomaly" : "센서 · 기여도 · 이상 구간", onClick: () => onNavigate("assets", "objects") },
      { id: "inspection", label: english ? "Open inspection case" : "점검 Case 열기", detail: english ? "Targets · workflow" : "점검 대상 · workflow", onClick: () => onNavigate("inspection", "operations") },
      { id: "history", label: english ? "Review maintenance history" : "정비 이력 보기", detail: english ? "Past work · before/after" : "과거 조치 · before/after", onClick: () => onNavigate("maintenance-history", "objects") },
    ]
    : experience.kind === "operations"
      ? [
        { id: "case", label: "Decision Case", detail: english ? "Evidence → action → outcome" : "근거 → 판단 → 조치 → 결과", onClick: () => onNavigate("decision-case", "operations") },
        { id: "impact", label: english ? "Open production impact" : "생산 영향 보기", detail: english ? "Units · cost · product" : "수량 · 비용 · 제품", onClick: () => onNavigate("production-impact", "objects") },
        { id: "approval", label: english ? "Open maintenance approval" : "정비 승인 보기", detail: english ? "Inspection · material · action" : "점검 · 자재 · 실행", onClick: () => onNavigate("maintenance-approval", "operations") },
        { id: "report", label: english ? "Open report artifact" : "보고 산출물 열기", detail: english ? "Current case snapshot" : "현재 Case snapshot", onClick: () => onNavigate("report-draft", "reports") },
      ]
      : experience.kind === "executive"
        ? [
          { id: "risk", label: english ? "Open operational risk" : "운영 리스크 보기", detail: english ? "Plant · line · exposure" : "공장 · 라인 · 노출", onClick: () => onNavigate("operational-risk", "overview") },
          { id: "kpi", label: english ? "Open operating KPI" : "운영 KPI 보기", detail: english ? "Lead time · backlog" : "Lead time · backlog", onClick: () => onNavigate("executive-kpi", "reports") },
          { id: "effect", label: english ? "Review maintenance effect" : "정비 효과 보기", detail: english ? "Before / after" : "Before / after", onClick: () => onNavigate("maintenance-effect", "objects") },
          { id: "factory", label: english ? "Inspect factory evidence" : "설비 상태 근거 보기", detail: english ? "Zone · cell · alerts" : "구역 · 셀 · 알림", onClick: () => onNavigate("factory-status", "overview") },
        ]
        : [
          { id: "work", label: english ? "Open my work" : "내 작업 열기", detail: english ? "Approved work · progress" : "승인 작업 · 진행 상태", onClick: () => onNavigate("my-work", "operations") },
          { id: "target", label: english ? "Open work target" : "작업 대상 보기", detail: english ? "Location · evidence · material" : "위치 · 근거 · 자재", onClick: () => onNavigate("work-targets", "objects") },
          { id: "history", label: english ? "Open work history" : "작업 이력 보기", detail: english ? "Completion · outcome" : "완료 · 결과", onClick: () => onNavigate("work-history", "reports") },
        ];
  const focusCopy = operationalFocusCopy({
    selectedEvent,
    detail,
    lifecycleCurrentLabel: lifecycleCurrentForDisplay?.label ?? null,
    lifecycleNextLabel: lifecycleNextForDisplay?.label ?? null,
    primaryActionLabel: focusPrimaryAction?.label ?? null,
    roleHeadline: english ? experience.primaryQuestion.en : experience.primaryQuestion.ko,
    roleDetail: english ? experience.operationalFocusHint.en : experience.operationalFocusHint.ko,
    english,
  });
  const showOperationalFocus = shouldShowOperationalFocus(activeNav.id);
  const showImmersiveRiskWorkbench = IMMERSIVE_RISK_SURFACES.has(activeNav.id);
  const lifecycleMode = activeNav.id === "decision-case" ? "full" : selectedEvent ? "compact" : "idle";
  const selectionTarget = experience.kind === "operations"
    ? { id: "decision-case", view: "operations" as const, label: english ? "Open Decision Case" : "Decision Case 열기" }
    : experience.kind === "engineering"
      ? { id: "assets", view: "objects" as const, label: english ? "Open root-cause analysis" : "원인 분석 열기" }
      : experience.kind === "executive"
        ? { id: "factory-status", view: "overview" as const, label: english ? "Open factory evidence" : "설비 상태 근거 열기" }
        : { id: "work-targets", view: "objects" as const, label: english ? "Open work target" : "작업 대상 열기" };
  const primaryActionTarget = experience.kind === "operations"
    ? { id: primaryAction?.actionId?.includes("maintenance") ? "maintenance-approval" : "inspection", view: "operations" as const }
    : experience.kind === "executive"
      ? { id: "report-draft", view: "reports" as const }
      : { id: "inspection", view: "operations" as const };

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const timestamp = Date.now();
    setMessages((current) => [...current, { id: `user-${timestamp}`, role: "user", text: trimmed }]);
    setAssistantQueryLoading(true);
    setAssistantError(null);

    try {
      const run = await Promise.race([
        runAgentQuery({
        project_id: context.projectId,
        workspace_id: context.workspaceId,
        question: trimmed,
        route: "auto",
        audience: experience.kind,
        object_type: "equipment",
        object_id: selectedEvent?.assetId ?? undefined,
        event_id: selectedEvent?.eventId ?? undefined,
        top_k: 8,
        }),
        new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("assistant_query_timeout")), 9_000)),
      ]);
      const evidenceStores = [...new Set(run.state.evidence.map((item) => item.store))];
      const hasGroundedEvidence = run.state.status === "succeeded" && run.state.evidence.length > 0;
      const answer = hasGroundedEvidence && run.state.answer.trim()
        ? run.state.answer.trim()
        : groundedReliabilityAssistantAnswer(assistantContext, trimmed, locale);
      const hintParts = [
        english ? "Connected evidence" : "연결 근거",
        english ? `${run.state.evidence.length} items` : `${run.state.evidence.length}건`,
        hasGroundedEvidence && evidenceStores.length ? evidenceStores.join(" + ") : null,
        !hasGroundedEvidence ? (english ? "current asset context used" : "현재 설비 문맥 사용") : null,
      ].filter((value): value is string => Boolean(value));
      const activitySteps = run.state.steps.map((step, index) => ({
        id: `${run.state.run_id}:${index}:${step.name}`,
        label: assistantActivityStepLabel(step.name, english),
        detail: step.detail || null,
        store: assistantActivityStoreLabel(step.store),
        status: step.status,
        latencyMs: step.latency_ms,
      }));
      setMessages((current) => [...current, {
        id: `assistant-${timestamp}`,
        role: "assistant",
        text: answer,
        contextHint: hintParts.join(" · "),
        activityTrace: {
          runId: run.state.run_id,
          route: run.state.route,
          status: run.state.status === "succeeded" ? "succeeded" : "failed",
          evidenceCount: run.state.evidence.length,
          claimCount: run.state.claims.length,
          checkpointSequence: run.state.checkpoint_sequence,
          durationMs: null,
          steps: activitySteps,
        },
      }]);
      if (!hasGroundedEvidence) {
        setAssistantError(english
          ? "No additional review evidence matched this question. The answer uses the currently selected asset context."
          : "추가 검토 근거가 일치하지 않아 현재 선택 설비의 연결 데이터를 기준으로 답변했습니다.");
      }
    } catch (reason) {
      const fallback = groundedReliabilityAssistantAnswer(assistantContext, trimmed, locale);
      setMessages((current) => [...current, {
        id: `assistant-${timestamp}`,
        role: "assistant",
        text: fallback,
        contextHint: english ? "Current asset context" : "현재 설비 문맥",
        activityTrace: {
          runId: null,
          route: null,
          status: "fallback",
          evidenceCount: 0,
          claimCount: 0,
          checkpointSequence: null,
          durationMs: null,
          steps: [
            {
              id: `fallback-${timestamp}-lookup`,
              label: english ? "Connected evidence lookup unavailable" : "연결 근거 조회 지연",
              detail: reason instanceof Error && reason.message === "assistant_query_timeout"
                ? (english ? "The retrieval window exceeded 9 seconds." : "근거 조회가 9초 제한을 초과했습니다.")
                : (english ? "The additional evidence lookup did not complete." : "추가 근거 조회가 완료되지 않았습니다."),
              store: null,
              status: "failed",
              latencyMs: null,
            },
            {
              id: `fallback-${timestamp}-context`,
              label: english ? "Use current case context" : "현재 Case 문맥 사용",
              detail: english ? "A deterministic grounded fallback was composed from the selected case." : "선택 Case의 검증된 문맥으로 결정론적 fallback 답변을 구성했습니다.",
              store: null,
              status: "fallback",
              latencyMs: null,
            },
          ],
        },
      }]);
      setAssistantError(reason instanceof Error
        ? (reason.message === "assistant_query_timeout"
          ? (english ? "Grounded evidence lookup exceeded 9 seconds. A deterministic answer from the current case context is shown instead." : "근거 조회가 9초를 넘겨 현재 Case 문맥의 결정론적 답변으로 전환했습니다.")
          : (english ? "Additional evidence lookup was unavailable, so the current asset context was used." : "추가 근거 조회가 지연되어 현재 선택 설비의 연결 데이터를 기준으로 답변했습니다."))
        : (english ? "The current asset context was used for this answer." : "현재 선택 설비의 연결 데이터를 기준으로 답변했습니다."));
    } finally {
      setAssistantQueryLoading(false);
    }
  }

  return (
    <main className={`rw-preview-shell role-${experience.kind} ${leftOpen ? "left-open" : "left-collapsed"} ${assistantOpen ? "assistant-open" : "assistant-closed"}`} data-primary-surface={experience.primarySurface} data-active-surface={activeNav.id} data-active-view={activeView}>
      <header className="rw-preview-topbar">
        <div className="rw-preview-topbar-left">
          <button type="button" className="rw-preview-icon-button" onClick={() => setLeftOpen((value) => !value)} aria-label={leftOpen ? "Collapse navigation" : "Open navigation"}>{leftOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}</button>
          <div className="rw-preview-brand"><span><HanbitLogo /></span><div><strong>Hanbit Tech</strong><small>Reliability Operations</small></div></div>
          <div className="rw-preview-breadcrumb"><span>{context.projectName}</span><i>/</i><strong>{english ? activeNav.label.en : activeNav.label.ko}</strong></div>
        </div>
        <div className="rw-preview-topbar-right">
          <button type="button" className="rw-preview-search" onClick={() => { setSettingsOpen(false); setSearchOpen(true); }} aria-label={english ? "Search Reliability Operations" : "Reliability Operations 검색"}><Search size={14} /><span>{english ? "Search" : "검색"}</span><kbd>⌘K</kbd></button>
          <button type="button" className={`rw-preview-assistant-toggle ${assistantOpen ? "is-active" : ""}`} aria-label={english ? "Reliability Assistant" : "Reliability Assistant 열기"} aria-expanded={assistantOpen} aria-pressed={assistantOpen} onClick={() => { setSettingsOpen(false); setAssistantOpen((value) => !value); }}>{assistantOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}<span>Assistant</span></button>
          <div className="rw-preview-user"><span><UserRound size={13} /></span><div><strong>{user.display_name}</strong><small>{english ? experience.label.en : experience.label.ko}</small></div></div>
        </div>
      </header>

      <div className="rw-preview-body">
        <aside className="rw-preview-left">
          <div className="rw-preview-left-heading"><span>{english ? experience.label.en : experience.label.ko}</span><strong>{english ? "Workspace" : "업무 공간"}</strong></div>
          <nav aria-label={english ? "Role workflow navigation" : "역할별 업무 단계 탐색"}>
            {navigationGroups.map((group) => (
              <section className="rw-preview-nav-group" key={group.id}>
                <header>{english ? group.label.en : group.label.ko}</header>
                <div>
                  {group.surfaces.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      className={activeNav.id === item.id ? "is-active" : ""}
                      aria-label={english ? item.label.en : item.label.ko}
                      aria-current={activeNav.id === item.id ? "page" : undefined}
                      onPointerEnter={(event) => showNavPreview(item, event.currentTarget)}
                      onPointerLeave={() => setNavPreview(null)}
                      onFocus={(event) => showNavPreview(item, event.currentTarget)}
                      onBlur={() => setNavPreview(null)}
                      onClick={() => { setNavPreview(null); setSettingsOpen(false); if (window.innerWidth <= 860) setLeftOpen(false); onNavigate(item.id, item.view); }}
                      title={!leftOpen ? (english ? item.label.en : item.label.ko) : undefined}
                    >
                      <span aria-hidden="true">•</span>
                      <div><strong>{english ? item.label.en : item.label.ko}</strong><small>{english ? item.detail.en : item.detail.ko}</small></div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </nav>
          <section className="rw-preview-scope"><span>{english ? "SCOPE" : "현재 범위"}</span><strong>{context.workspaceName}</strong><small>{context.sourceStatus}</small></section>
          <section ref={settingsRef} className={`rw-preview-settings ${settingsOpen ? "is-open" : ""}`}>
            <button type="button" className="rw-preview-settings-trigger" aria-label={english ? "Workspace settings" : "환경설정"} aria-expanded={settingsOpen && leftOpen} onClick={() => { if (!leftOpen) setLeftOpen(true); setSettingsOpen((value) => !value); }}><Settings2 size={14} /><span>{english ? "Settings" : "환경설정"}</span></button>
            {settingsOpen && leftOpen ? <div className="rw-preview-settings-panel">
              <header><strong>{english ? "Workspace settings" : "사용자 환경"}</strong><small>{user.display_name}</small></header>
              <div className="rw-preview-settings-group"><span>{english ? "Language" : "언어"}</span><div className="rw-preview-segmented two"><button type="button" className={!english ? "is-active" : ""} onClick={() => setReliabilityLocale("ko-KR")}>한국어</button><button type="button" className={english ? "is-active" : ""} onClick={() => setReliabilityLocale("en-US")}>English</button></div></div>
              <div className="rw-preview-settings-group"><span>{english ? "Theme" : "화면 테마"}</span><div className="rw-preview-segmented three">{(["light", "dark", "system"] as const).map((value) => <button type="button" key={value} className={preferences.theme === value ? "is-active" : ""} onClick={() => setTheme(value)}>{value === "light" ? (english ? "Light" : "라이트") : value === "dark" ? (english ? "Dark" : "다크") : (english ? "System" : "시스템")}</button>)}</div></div>
              <div className="rw-preview-settings-group"><span>{english ? "Display preset" : "화면 프리셋"}</span><div className="rw-preview-segmented four">{(["compact", "standard", "large", "accessible"] as const).map((value) => <button type="button" key={value} className={preset === value ? "is-active" : ""} onClick={() => setPreset(value)}>{value === "compact" ? (english ? "Report" : "보고/프린트") : value === "standard" ? (english ? "Desktop" : "데스크톱") : value === "large" ? (english ? "Large" : "큰 글씨") : (english ? "Presentation" : "발표/프로젝터")}</button>)}</div></div>
              <button type="button" className="rw-preview-settings-action" onClick={() => setShowGuidance(!preferences.showGuidance)}><span>{english ? "Screen guidance" : "화면 도움말"}</span><strong>{preferences.showGuidance ? (english ? "Shown" : "표시") : (english ? "Hidden" : "숨김")}</strong></button>
              <button type="button" className="rw-preview-settings-action" onClick={onRefresh} disabled={refreshing}><span><RefreshCw size={12} />{english ? "Refresh data" : "최신 데이터 다시 확인"}</span></button>
              <button type="button" className="rw-preview-settings-action" onClick={() => { setLeftOpen(false); setAssistantOpen(false); setSettingsOpen(false); }}><span><Focus size={12} />{english ? "Focus mode" : "집중 모드"}</span></button>
              <button type="button" className="rw-preview-settings-action is-danger" onClick={() => void onLogout()}><span><LogOut size={12} />{english ? "Switch account" : "계정 전환"}</span></button>
            </div> : null}
          </section>
          <button type="button" className="rw-preview-collapse" aria-label={leftOpen ? (english ? "Collapse navigation" : "탐색 메뉴 접기") : (english ? "Expand navigation" : "탐색 메뉴 펼치기")} aria-expanded={leftOpen} onClick={() => setLeftOpen((value) => !value)}>{leftOpen ? <><ChevronsLeft size={13} /><span>{english ? "Collapse" : "접기"}</span></> : <ChevronsRight size={13} />}</button>
        </aside>

        <section className="rw-preview-main" ref={mainRef}>
          {context.warnings.length ? <details className="rw-preview-warning"><summary>{english ? `${context.warnings.length} data notice(s)` : `데이터 참고사항 ${context.warnings.length}건`}</summary><ul>{context.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details> : null}
          <header className="rw-preview-page-heading"><span>{eyebrow}</span><h1>{title}</h1><p>{detailCopy}</p></header>
          {selectedEvent ? <section className={`rw-preview-selection-anchor tone-${riskTone(selectedEvent.status)}`} aria-label={english ? "Selected case context" : "현재 선택 Case 문맥"}>
            <div className="rw-preview-selection-anchor__path">
              <span>{english ? "SELECTED CASE" : "선택 Case"}</span>
              <strong>{english ? selectedEvent.line : displayLineLabel(selectedEvent.line)} <i>›</i> {english ? (selectedEvent.assetName || selectedEvent.assetId) : displayAssetName({ assetId: selectedEvent.assetId, displayName: selectedEvent.assetName })}</strong>
            </div>
            <div className="rw-preview-selection-anchor__facts">
              <span>{english ? "Observation" : "관측 기준"} {displayDateTime(selectedEvent.observedAt, english)}</span>
              <span className="rw-technical-metadata">{selectedEvent.eventId}</span>
              <b>{english ? "Risk" : "위험"} {probability(selectedEvent.failureProbability)}</b>
              <em>{riskStatusLabel(selectedEvent.status, english)}</em>
            </div>
            <button type="button" onClick={() => onNavigate(selectionTarget.id, selectionTarget.view)}>{selectionTarget.label}</button>
          </section> : null}
          {selectedEvent && latestEventForSelectedAsset ? <section className="rw-preview-new-observation" role="status" aria-label={english ? "New observation available" : "새 관측 도착"}>
            <div><strong>{english ? "New observation available" : "새 관측 도착"}</strong><span>{english ? "The selected Decision Case stays frozen until you explicitly follow the latest Event." : "현재 Decision Case는 선택 당시 근거로 고정됩니다. 최신 Event는 명시적으로 전환할 때만 열립니다."}</span></div>
            <small>{displayDateTime(latestEventForSelectedAsset.observedAt, english)} · {probability(latestEventForSelectedAsset.failureProbability)}</small>
            <button type="button" onClick={onFollowLatestEvent}>{english ? "Open latest Event" : "최신 Event 열기"}</button>
          </section> : null}
          {showImmersiveRiskWorkbench ? (
            <Suspense
              fallback={<div className="rw-preview-immersive-loading" aria-busy="true">{english ? "Preparing live risk workbench" : "실시간 위험 워크벤치 준비 중"}</div>}
            >
              <ImmersiveRiskWorkbench
                model={model}
                detail={detail}
                selectedEvent={selectedEvent}
                onSelectEvent={onSelectEvent}
                english={english}
              />
            </Suspense>
          ) : null}
          {showOperationalFocus ? <div className="rw-preview-operational-focus">
            <OperationalFocus
              asset={{
                id: selectedEvent?.assetId ?? context.workspaceId,
                name: selectedEvent ? (english ? (selectedEvent.assetName || selectedEvent.assetId) : displayAssetName({ assetId: selectedEvent.assetId, displayName: selectedEvent.assetName })) : (english ? "Select an asset" : "설비를 선택하세요"),
                contextLabel: selectedEvent ? (english ? selectedEvent.line : displayLineLabel(selectedEvent.line)) : context.workspaceName,
              }}
              situation={{
                statusLabel: riskStatusLabel(selectedEvent?.status, english),
                headline: focusCopy.headline,
                detail: focusCopy.detail,
                tone: riskTone(selectedEvent?.status),
                risk: {
                  label: english ? "Failure risk" : "고장 위험",
                  valueLabel: probability(selectedEvent?.failureProbability ?? null),
                },
                operationalImpact: operationalImpactLabel(detail, english),
              }}
              evidence={evidence}
              lifecycle={{
                currentLabel: lifecycleCurrentForDisplay?.label ?? (english ? "Current step is being confirmed" : "현재 처리 단계 확인 중"),
                nextLabel: lifecycleNextForDisplay?.label ?? null,
                ownerLabel: focusPrimaryAction?.ownerLabel ?? null,
              }}
              primaryAction={focusPrimaryAction}
              onPrimaryAction={focusPrimaryAction ? () => onNavigate(primaryActionTarget.id, primaryActionTarget.view) : undefined}
              freshness={{
                observedAt: freshnessObservedAt,
                label: freshnessObservedAt,
                sourceLabel: null,
              }}
              locale={locale}
              focusLabel={experience.kind === "operations"
                ? (english ? "NEXT DECISION" : "다음 판단")
                : experience.kind === "executive"
                  ? (english ? "REPORTING FOCUS" : "보고 포커스")
                  : (english ? "MY NEXT TASK" : "내 다음 작업")}
              actionLabel={experience.kind === "operations"
                ? (english ? "Decision entry" : "판단 진입")
                : experience.kind === "executive"
                  ? (english ? "Report entry" : "보고 진입")
                  : (english ? "Start next task" : "지금 할 일")}
            />
          </div> : null}
          <div className="rw-preview-content">{children}</div>
        </section>
      </div>

      <ReliabilityCommandPalette
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        navigation={navigation}
        entities={searchEntities}
        onNavigate={onNavigate}
        onSelectEntity={(entity) => onSearchSelect?.(entity)}
        english={english}
      />

      {navPreview && typeof document !== "undefined" ? createPortal(
        <aside
          className="rw-nav-context-popover"
          style={{ top: navPreview.top, left: navPreview.left }}
          role="status"
          aria-label={english ? `${navPreview.label} context preview` : `${navPreview.label} 문맥 미리보기`}
        >
          <header>
            <span>{navPreview.view.toUpperCase()}</span>
            <strong>{navPreview.label}</strong>
          </header>
          <p>{navPreview.detail}</p>
          <dl>
            <div><dt>{english ? "Selected" : "선택 Case"}</dt><dd>{selectedEvent ? (english ? (selectedEvent.assetName || selectedEvent.assetId) : displayAssetName({ assetId: selectedEvent.assetId, displayName: selectedEvent.assetName })) : (english ? "No case" : "미선택")}</dd></div>
            <div><dt>{english ? "Risk" : "위험"}</dt><dd>{probability(selectedEvent?.failureProbability ?? null)}</dd></div>
            <div><dt>{english ? "Source" : "데이터"}</dt><dd>{context.sourceStatus}</dd></div>
          </dl>
          <footer>
            <span>{activeNav.id === navPreview.id ? (english ? "Current view" : "현재 화면") : (english ? "Click to open" : "클릭하여 열기")}</span>
            {selectedEvent?.eventId ? <small className="rw-technical-metadata">{selectedEvent.eventId}</small> : null}
          </footer>
        </aside>,
        document.body,
      ) : null}

      <ContextAssistantDrawer
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        context={assistantContext}
        messages={messages}
        onSubmit={ask}
        loading={assistantLoading || assistantQueryLoading}
        submitting={assistantQueryLoading}
        error={assistantError}
        locale={locale}
        actions={assistantActions}
      />

      <footer className="rw-preview-bottom">
        <LifecycleInstrument
          title={selectedEvent?.assetName ?? (english ? "No case selected" : "Case 미선택")}
          completedSteps={lifecycleCompletedSteps}
          current={lifecycleCurrentForDisplay}
          next={lifecycleNextForDisplay}
          timeline={lifecycleTimeline}
          locale={locale}
          mode={lifecycleMode}
        />
      </footer>
    </main>
  );
}
