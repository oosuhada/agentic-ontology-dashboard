import type { AppRole, DomainPack, Project } from "../../types";
import type { BoardCatalogDefinition, DashboardBoard, DashboardTab, ResolvedDashboard } from "../dashboard/types";
import type { DatasetCatalogDetail, DatasetCatalogItem, DatasetProjectionItem } from "../datasets/types";

export type AdaptiveProfileId = "factory-reliability" | "fleet-maintenance" | "compressor-monitoring" | "generic-operations";

export interface DatasetSemanticSignals {
  fields: string[];
  temporalFields: string[];
  quantitativeFields: string[];
  categoricalFields: string[];
  identifierFields: string[];
  geoFields: string[];
  textFields: string[];
  sourceTypes: string[];
  graphReady: boolean;
  vectorReady: boolean;
  relationalReady: boolean;
  hasQualityIssues: boolean;
  hasPredictionSignal: boolean;
  hasAnomalySignal: boolean;
}

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
  signals: DatasetSemanticSignals;
  compositionRevision: string;
}

const PROFILES: Record<AdaptiveProfileId, Omit<AdaptiveExperienceProfile, "datasetSummary" | "signals" | "compositionRevision">> = {
  "factory-reliability": {
    id: "factory-reliability",
    label: "Factory Reliability Command",
    eyebrow: "EQUIPMENT · LINE · FAILURE RISK",
    description: "설비 위험, 생산 라인 영향, 고장 유형과 점검 결정을 중심으로 화면을 자동 구성합니다.",
    primaryEntity: "Equipment",
    primaryMetric: "Failure probability",
    visualLanguage: "위험 추세 + 원인 기여 + 설비 관계 + 점검 조치",
    reportSections: ["운영 위험", "생산 영향", "점검 결정"],
  },
  "fleet-maintenance": {
    id: "fleet-maintenance",
    label: "Fleet Maintenance Briefing",
    eyebrow: "VEHICLE · SERVICE · ROUTE IMPACT",
    description: "차량 정비 우선순위, 서비스 지연, 운행 영향과 정비 백로그 중심으로 화면을 자동 구성합니다.",
    primaryEntity: "Vehicle",
    primaryMetric: "Service risk",
    visualLanguage: "Fleet KPI + 운행 영향 + 정비 큐 + 활동 스트림",
    reportSections: ["Fleet 상태", "운행 영향", "정비 우선순위"],
  },
  "compressor-monitoring": {
    id: "compressor-monitoring",
    label: "Compressor Condition Monitor",
    eyebrow: "TELEMETRY · PRESSURE · ANOMALY WINDOW",
    description: "연속 센서 추세, 이상 구간, 모델 상태와 예방 정비 중심으로 화면을 자동 구성합니다.",
    primaryEntity: "Compressor",
    primaryMetric: "Condition score",
    visualLanguage: "대형 시계열 + 이상 타임라인 + 모델 근거 + 품질 경고",
    reportSections: ["상태 추세", "이상 구간", "예방 정비"],
  },
  "generic-operations": {
    id: "generic-operations",
    label: "Adaptive Operations Workspace",
    eyebrow: "SCHEMA · SEMANTICS · DECISION",
    description: "Dataset schema의 시간·수치·범주·관계·문서 신호를 분석해 화면 종류와 정보 구조를 자동 구성합니다.",
    primaryEntity: "Object",
    primaryMetric: "Operational signal",
    visualLanguage: "Schema-driven KPI + 추세/비교 + 관계 + 상세 근거",
    reportSections: ["상태 요약", "주요 변화", "권고 조치"],
  },
};

interface SchemaColumn {
  name: string;
  type: string;
}

function schemaColumns(schema: Record<string, unknown>): SchemaColumn[] {
  const columns = Array.isArray(schema.columns) ? schema.columns : [];
  const fromColumns = columns.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    const name = String(value.name ?? value.id ?? "").trim();
    if (!name) return [];
    return [{ name, type: String(value.value_type ?? value.type ?? value.physical_type ?? "unknown").toLowerCase() }];
  });
  const properties = schema.properties && typeof schema.properties === "object" ? schema.properties as Record<string, unknown> : {};
  const fromProperties = Object.entries(properties).map(([name, definition]) => ({
    name,
    type: definition && typeof definition === "object"
      ? String((definition as Record<string, unknown>).type ?? "unknown").toLowerCase()
      : "unknown",
  }));
  return [...fromColumns, ...fromProperties];
}

function projectionReady(projections: DatasetProjectionItem[], kind: "relational" | "graph" | "vector") {
  return projections.some((projection) => projection.store_kind === kind && projection.status === "ready");
}

function deriveSignals(datasets: DatasetCatalogItem[], details: DatasetCatalogDetail[]): DatasetSemanticSignals {
  const columns = details.flatMap((detail) => schemaColumns(detail.versions[0]?.schema ?? {}));
  const fields = [...new Set(columns.map((column) => column.name))].sort();
  const fieldType = new Map(columns.map((column) => [column.name, column.type]));
  const matches = (field: string, pattern: RegExp) => pattern.test(field.toLowerCase());
  const temporalFields = fields.filter((field) => matches(field, /(time|timestamp|date|datetime|created|updated|detected|window)/) || /(date|time)/.test(fieldType.get(field) ?? ""));
  const identifierFields = fields.filter((field) => matches(field, /(^id$|_id$|uuid|serial|vin|key|code$)/));
  const geoFields = fields.filter((field) => matches(field, /(lat|lon|lng|latitude|longitude|geo|location|region|route)/));
  const textFields = fields.filter((field) => matches(field, /(description|summary|note|body|text|comment|document|content|message)/));
  const quantitativeFields = fields.filter((field) => {
    const type = fieldType.get(field) ?? "";
    return /(number|integer|float|double|decimal)/.test(type) && !identifierFields.includes(field);
  });
  const categoricalFields = fields.filter((field) => {
    const type = fieldType.get(field) ?? "";
    return matches(field, /(status|type|category|class|line|criticality|severity|confidence|decision|owner|engineer|group)/)
      || (/(string|boolean)/.test(type) && !identifierFields.includes(field) && !textFields.includes(field));
  });
  const allProjections = details.flatMap((detail) => detail.projections);
  const sourceTypes = [...new Set(datasets.map((dataset) => dataset.source_type))].sort();
  const corpus = `${fields.join(" ")} ${datasets.flatMap((dataset) => [dataset.display_name, dataset.description, dataset.source_type]).join(" ")}`.toLowerCase();
  return {
    fields,
    temporalFields,
    quantitativeFields,
    categoricalFields,
    identifierFields,
    geoFields,
    textFields,
    sourceTypes,
    graphReady: projectionReady(allProjections, "graph"),
    vectorReady: projectionReady(allProjections, "vector") || sourceTypes.some((source) => /(document|pdf|text|vector)/i.test(source)),
    relationalReady: projectionReady(allProjections, "relational") || datasets.some((dataset) => dataset.projection_health.relational === "ready"),
    hasQualityIssues: details.some((detail) => detail.quarantine_records.length > 0 || detail.ingestion_runs.some((run) => run.status === "failed")),
    hasPredictionSignal: /(risk|probability|score|prediction|failure|confidence|threshold|model)/.test(corpus),
    hasAnomalySignal: /(anomaly|abnormal|outlier|alarm|alert|failure|fault)/.test(corpus),
  };
}

function profileId(projectId: string, project: Project | undefined, domainPack: DomainPack | undefined, datasets: DatasetCatalogItem[], signals: DatasetSemanticSignals): AdaptiveProfileId {
  const corpus = [projectId, project?.display_name, project?.description, domainPack?.display_name, ...datasets.flatMap((item) => [item.display_name, item.description]), ...signals.fields].filter(Boolean).join(" ").toLowerCase();
  if (/(vehicle|fleet|vin|mileage|odometer|route|service interval)/.test(corpus)) return "fleet-maintenance";
  if (/(compressor|pressure|metropt|air leak|air_leak)/.test(corpus)) return "compressor-monitoring";
  if (/(manufactur|factory|equipment|production line|tool_wear|torque|failure_probability)/.test(corpus)) return "factory-reliability";
  return "generic-operations";
}

export function deriveAdaptiveExperience(
  projectId: string,
  project: Project | undefined,
  domainPack: DomainPack | undefined,
  datasets: DatasetCatalogItem[],
  details: DatasetCatalogDetail[] = [],
): AdaptiveExperienceProfile {
  const signals = deriveSignals(datasets, details);
  const id = profileId(projectId, project, domainPack, datasets, signals);
  const totalRecords = datasets.reduce((sum, item) => sum + item.record_count, 0);
  const datasetSummary = datasets.length
    ? `${datasets.length} datasets · ${totalRecords.toLocaleString()} records · ${signals.fields.length} fields · ${signals.sourceTypes.join(", ") || "unknown source"}`
    : "Dataset profile is being resolved";
  const revisionCorpus = [id, ...signals.fields, ...signals.sourceTypes, String(signals.graphReady), String(signals.vectorReady)].join("|");
  let hash = 0;
  for (const character of revisionCorpus) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return { ...PROFILES[id], datasetSummary, signals, compositionRevision: `schema-${Math.abs(hash).toString(36)}` };
}

const PROFILE_PLANS: Record<AdaptiveProfileId, string[]> = {
  "factory-reliability": ["operations-kpi", "risk-trend-workbench", "factor-contribution", "priority-list", "event-data-grid", "ontology-relationship", "recommended-actions", "activity-stream", "data-quality-warning", "planner-assistant"],
  "fleet-maintenance": ["operations-kpi", "impact-summary", "priority-list", "activity-stream", "event-data-grid", "ontology-relationship", "recommended-actions", "planner-assistant", "data-quality-warning", "risk-trend-workbench"],
  "compressor-monitoring": ["sensor-line-chart", "anomaly-timeline", "risk-trend-workbench", "model-details", "evidence-table", "data-quality-warning", "recommended-actions", "activity-stream", "factor-contribution", "planner-assistant"],
  "generic-operations": ["operations-kpi", "risk-trend-workbench", "event-data-grid", "ontology-relationship", "activity-stream", "data-quality-warning", "planner-assistant", "recommended-actions"],
};

const ROLE_PLANS: Record<string, string[]> = {
  executive_viewer: ["executive-portfolio", "executive-business-impact", "executive-risk-trend", "executive-unresolved", "priority-list", "activity-stream", "planner-assistant"],
  process_manager: ["operations-kpi", "priority-list", "impact-summary", "manager-decision", "recommended-actions", "activity-stream", "risk-trend-workbench", "ontology-relationship"],
  process_engineer: ["status-summary", "sensor-line-chart", "anomaly-timeline", "factor-contribution", "evidence-table", "engineer-checklist", "ontology-relationship", "recommended-actions", "data-quality-warning"],
  maintenance_technician: ["field-task", "field-safety-location", "field-measurements", "field-task-actions", "recommended-actions", "evidence-table", "sensor-line-chart"],
  quality_auditor: ["audit-reconstruction", "audit-version-snapshot", "audit-evidence-trace", "audit-action-history", "data-quality-warning", "audit-export-checkpoint", "ontology-relationship"],
  ml_validator: ["ml-version-matrix", "ml-threshold-cost", "ml-slice-error", "ml-drift-schema", "ml-gold-regression", "ml-release-candidate", "data-quality-warning", "model-details"],
  fde: ["fde-workspace-overview", "integration-health", "fde-ontology-registry", "fde-diagnostic-events", "planner-assistant", "fde-deployment-checklist", "fde-approval-queue"],
  tenant_admin: ["operations-kpi", "priority-list", "ontology-relationship", "activity-stream", "integration-health", "audit-trace", "planner-assistant", "data-quality-warning"],
};

function signalBoards(profile: AdaptiveExperienceProfile) {
  const signals = profile.signals;
  const boards: string[] = [];
  if (signals.temporalFields.length && signals.quantitativeFields.length) boards.push("sensor-line-chart", "risk-trend-workbench", "anomaly-timeline");
  if (signals.graphReady) boards.push("ontology-relationship");
  if (signals.vectorReady || signals.textFields.length) boards.push("planner-assistant", "evidence-table");
  if (signals.hasPredictionSignal) boards.push("factor-contribution", "model-details");
  if (signals.hasQualityIssues) boards.push("data-quality-warning");
  if (signals.geoFields.length) boards.push("impact-summary", "activity-stream");
  return boards;
}

function boardPlan(profile: AdaptiveExperienceProfile, roleCode: AppRole, catalog: BoardCatalogDefinition[], count: number) {
  const byId = new Map(catalog.map((definition) => [definition.id, definition]));
  const ordered = [...signalBoards(profile), ...PROFILE_PLANS[profile.id], ...(ROLE_PLANS[roleCode] ?? [])];
  const unique = [...new Set(ordered)].filter((id) => byId.get(id)?.allowed_roles.includes(roleCode));
  const fallbacks = catalog.filter((definition) => definition.allowed_roles.includes(roleCode)).map((definition) => definition.id);
  return [...unique, ...fallbacks.filter((id) => !unique.includes(id))].slice(0, Math.max(1, count));
}

const LAYOUTS: Record<AdaptiveProfileId, Array<[number, number]>> = {
  "factory-reliability": [[7, 4], [5, 4], [4, 3], [4, 3], [4, 3], [6, 4], [6, 4], [12, 3]],
  "fleet-maintenance": [[12, 4], [4, 3], [4, 3], [4, 3], [8, 4], [4, 4], [6, 3], [6, 3]],
  "compressor-monitoring": [[8, 5], [4, 5], [12, 4], [6, 4], [6, 4], [12, 3], [6, 3], [6, 3]],
  "generic-operations": [[12, 3], [6, 4], [6, 4], [4, 3], [4, 3], [4, 3], [12, 3]],
};

function placeBoards(boards: DashboardBoard[], profile: AdaptiveExperienceProfile, definitions: BoardCatalogDefinition[]) {
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  return boards.map((board, index) => {
    const definition = definitions[index];
    const [desiredWidth, height] = LAYOUTS[profile.id][index % LAYOUTS[profile.id].length];
    const width = Math.max(definition.minimum_width, Math.min(definition.maximum_width, desiredWidth));
    if (x + width > 12) {
      y += rowHeight;
      x = 0;
      rowHeight = 0;
    }
    const next: DashboardBoard = {
      ...board,
      definition_id: definition.id,
      title: `${profile.primaryEntity} · ${definition.display_name}`,
      width,
      layout: { x, y, w: width, h: height, min_w: definition.minimum_width, min_h: 1, max_w: definition.maximum_width, max_h: 12 },
      source: null,
      bindings: { ...definition.default_bindings },
      settings: { ...definition.default_settings, adaptive_profile: profile.id, schema_revision: profile.compositionRevision },
      hidden: false,
    };
    x += width;
    rowHeight = Math.max(rowHeight, height);
    return next;
  });
}

function adaptiveTabTitle(profile: AdaptiveExperienceProfile, index: number) {
  const titles: Record<AdaptiveProfileId, string[]> = {
    "factory-reliability": ["Reliability Command", "Evidence & Maintenance"],
    "fleet-maintenance": ["Fleet Briefing", "Service & Route Impact"],
    "compressor-monitoring": ["Condition Monitoring", "Anomaly & Prevention"],
    "generic-operations": ["Adaptive Overview", "Data Evidence"],
  };
  return titles[profile.id][index] ?? `${profile.label} ${index + 1}`;
}

export function applyAdaptiveDashboardProfile(
  dashboard: ResolvedDashboard,
  profile: AdaptiveExperienceProfile,
  catalog: BoardCatalogDefinition[],
): ResolvedDashboard {
  if (dashboard.preference_revision > 0 || !catalog.length) return dashboard;
  const flatBoards = dashboard.tabs.flatMap((tab) => tab.boards);
  const ids = boardPlan(profile, dashboard.role_code, catalog, flatBoards.length);
  const byId = new Map(catalog.map((definition) => [definition.id, definition]));
  const definitions = flatBoards.map((board, index) => byId.get(ids[index]) ?? byId.get(board.definition_id)).filter(Boolean) as BoardCatalogDefinition[];
  if (definitions.length !== flatBoards.length) return dashboard;
  let cursor = 0;
  const tabs: DashboardTab[] = dashboard.tabs.map((tab, tabIndex) => {
    const tabDefinitions = definitions.slice(cursor, cursor + tab.boards.length);
    cursor += tab.boards.length;
    return {
      ...tab,
      title: adaptiveTabTitle(profile, tabIndex),
      boards: placeBoards(tab.boards, profile, tabDefinitions),
    };
  });
  return {
    ...dashboard,
    display_name: `${profile.label} · ${dashboard.display_name}`,
    tabs,
    merge_notices: [...dashboard.merge_notices, `${profile.label} ${profile.compositionRevision}: Dataset schema가 Board 종류와 구성을 자동 선택했습니다.`],
  };
}
