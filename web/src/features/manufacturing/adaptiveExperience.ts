import type { DomainPack, Project } from "../../types";
import type { DatasetCatalogItem } from "../datasets/types";
import type { DashboardBoard, DashboardTab, ResolvedDashboard, VisualizationKind } from "../dashboard/types";

export type AdaptiveProfileId = "factory-reliability" | "fleet-maintenance" | "compressor-monitoring" | "generic-operations";

export interface AdaptiveExperienceProfile {
  id: AdaptiveProfileId;
  label: string;
  eyebrow: string;
  description: string;
  primaryEntity: string;
  primaryMetric: string;
  visualLanguage: string;
  reportSections: string[];
  datasetSummary: string;
}

const PROFILES: Record<AdaptiveProfileId, Omit<AdaptiveExperienceProfile, "datasetSummary">> = {
  "factory-reliability": {
    id: "factory-reliability",
    label: "Factory Reliability Command",
    eyebrow: "EQUIPMENT · LINE · FAILURE RISK",
    description: "설비 위험, 생산 라인 영향, 고장 유형과 점검 결정을 중심으로 화면을 구성합니다.",
    primaryEntity: "Equipment",
    primaryMetric: "Failure probability",
    visualLanguage: "위험 분포 + 라인 비교 + 이벤트 테이블",
    reportSections: ["운영 위험", "생산 영향", "점검 결정"],
  },
  "fleet-maintenance": {
    id: "fleet-maintenance",
    label: "Fleet Maintenance Briefing",
    eyebrow: "VEHICLE · SERVICE · ROUTE IMPACT",
    description: "차량별 정비 우선순위, 서비스 지연과 운행 영향이 먼저 보이도록 화면을 구성합니다.",
    primaryEntity: "Vehicle",
    primaryMetric: "Service risk",
    visualLanguage: "전사 요약 + 차량군 비교 + 정비 백로그",
    reportSections: ["Fleet 상태", "운행 영향", "정비 우선순위"],
  },
  "compressor-monitoring": {
    id: "compressor-monitoring",
    label: "Compressor Condition Monitor",
    eyebrow: "TELEMETRY · PRESSURE · ANOMALY WINDOW",
    description: "연속 센서 추세, 이상 구간과 압축기 상태 변화를 중심으로 화면을 구성합니다.",
    primaryEntity: "Compressor",
    primaryMetric: "Condition score",
    visualLanguage: "대형 시계열 + 상태 카드 + 이상 이벤트",
    reportSections: ["상태 추세", "이상 구간", "예방 정비"],
  },
  "generic-operations": {
    id: "generic-operations",
    label: "Adaptive Operations Workspace",
    eyebrow: "DATASET · OBJECT · DECISION",
    description: "연결된 데이터셋의 개체, 시간 필드와 측정값을 기준으로 화면을 자동 구성합니다.",
    primaryEntity: "Object",
    primaryMetric: "Operational signal",
    visualLanguage: "요약 + 비교 + 상세 테이블",
    reportSections: ["상태 요약", "주요 변화", "권고 조치"],
  },
};

export function deriveAdaptiveExperience(
  projectId: string,
  project: Project | undefined,
  domainPack: DomainPack | undefined,
  datasets: DatasetCatalogItem[],
): AdaptiveExperienceProfile {
  const corpus = [
    projectId,
    project?.display_name,
    domainPack?.display_name,
    ...datasets.flatMap((item) => [item.display_name, item.description, item.source_type]),
  ].filter(Boolean).join(" ").toLowerCase();
  const id: AdaptiveProfileId = corpus.includes("azure") || corpus.includes("fleet") || corpus.includes("vehicle")
    ? "fleet-maintenance"
    : corpus.includes("metropt") || corpus.includes("compressor") || corpus.includes("pressure")
      ? "compressor-monitoring"
      : corpus.includes("manufactur") || corpus.includes("equipment") || corpus.includes("factory")
        ? "factory-reliability"
        : "generic-operations";
  const totalRecords = datasets.reduce((sum, item) => sum + item.record_count, 0);
  const datasetSummary = datasets.length
    ? `${datasets.length} datasets · ${totalRecords.toLocaleString()} records · ${[...new Set(datasets.map((item) => item.source_type))].join(", ")}`
    : "Dataset profile is being resolved";
  return { ...PROFILES[id], datasetSummary };
}

function preferredKind(board: DashboardBoard, profile: AdaptiveExperienceProfile): VisualizationKind | undefined {
  const name = `${board.definition_id} ${board.title}`.toLowerCase();
  if (name.includes("table") || name.includes("event") || name.includes("queue") || name.includes("checklist")) return "table";
  if (name.includes("metric") || name.includes("summary") || name.includes("score") || name.includes("impact")) return "metric";
  if (profile.id === "compressor-monitoring") {
    if (name.includes("factor") || name.includes("distribution")) return "bar";
    return "line";
  }
  if (profile.id === "fleet-maintenance") {
    if (name.includes("status") || name.includes("composition")) return "stacked_bar";
    if (name.includes("trend") || name.includes("history")) return "area";
    return "bar";
  }
  if (name.includes("trend") || name.includes("history") || name.includes("sensor")) return "line";
  if (name.includes("distribution") || name.includes("factor")) return "bar";
  return undefined;
}

function layoutTab(tab: DashboardTab, profile: AdaptiveExperienceProfile): DashboardTab {
  let y = 0;
  let x = 0;
  let rowHeight = 0;
  const patterns: Record<AdaptiveProfileId, Array<[number, number]>> = {
    "factory-reliability": [[7, 4], [5, 4], [4, 3], [4, 3], [4, 3], [6, 3], [6, 3]],
    "fleet-maintenance": [[12, 4], [4, 3], [4, 3], [4, 3], [8, 4], [4, 4], [6, 3], [6, 3]],
    "compressor-monitoring": [[8, 5], [4, 5], [12, 3], [6, 4], [6, 4], [12, 3]],
    "generic-operations": [[12, 3], [6, 4], [6, 4], [4, 3], [4, 3], [4, 3]],
  };
  const boards = tab.boards.map((board, index) => {
    const [w, h] = patterns[profile.id][index % patterns[profile.id].length];
    if (x + w > 12) {
      y += rowHeight;
      x = 0;
      rowHeight = 0;
    }
    const kind = preferredKind(board, profile);
    const next = {
      ...board,
      width: w,
      layout: {
        ...(board.layout ?? {}),
        x,
        y,
        w,
        h,
        min_w: Math.min(board.layout?.min_w ?? 1, w),
        min_h: Math.min(board.layout?.min_h ?? 1, h),
        max_w: Math.max(board.layout?.max_w ?? 12, w),
        max_h: Math.max(board.layout?.max_h ?? 12, h),
      },
      settings: kind
        ? { ...board.settings, visualization: { version: 1, mode: "manual", kind, color_strategy: "semantic" } }
        : board.settings,
    };
    x += w;
    rowHeight = Math.max(rowHeight, h);
    return next;
  });
  return { ...tab, boards };
}

export function applyAdaptiveDashboardProfile(
  dashboard: ResolvedDashboard,
  profile: AdaptiveExperienceProfile,
): ResolvedDashboard {
  if (dashboard.preference_revision > 0) return dashboard;
  return {
    ...dashboard,
    display_name: `${profile.label} · ${dashboard.display_name}`,
    tabs: dashboard.tabs.map((tab) => layoutTab(tab, profile)),
    merge_notices: [...dashboard.merge_notices, `${profile.label} dataset profile applied to the default composition.`],
  };
}
