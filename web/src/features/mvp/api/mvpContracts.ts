export type MvpView = "overview" | "objects" | "operations" | "executive-report";
export type MvpRoleLens = "process_manager" | "field_operator";
export type MvpRiskStatus = "normal" | "attention" | "warning" | "critical" | "data_quality_hold";
export type MvpConfidence = "high" | "medium" | "low" | "unavailable";
export type MvpDecision =
  | "continue_monitoring"
  | "request_inspection"
  | "review_shutdown"
  | "hold_for_data_check";

export type MvpSourceMode = "canonical-runtime" | "gold-fixture-fallback";

export interface MvpProvenance {
  datasetId: string | null;
  datasetVersionId: string;
  datasetLabel: string;
  sourceVersion: string | null;
  modelVersion: string | null;
  policyVersion: string | null;
  schemaVersion: string | null;
  promptVersion: string | null;
  sourceRefs: string[];
}

export interface MvpFactor {
  id: string;
  feature: string;
  label: string;
  value: number | null;
  unit: string | null;
  contribution: number;
  direction: "risk_up" | "risk_down";
  explanationMethod: string | null;
}

export interface MvpAsset {
  assetId: string;
  displayName: string;
  assetType: string;
  site: string;
  line: string;
  cell: string;
  status: MvpRiskStatus;
  failureProbability: number | null;
  confidence: MvpConfidence;
  confidenceScore: number | null;
  criticality: "low" | "medium" | "high";
  assignedEngineer: string | null;
  estimatedDowntimeMinutes: number;
  sparePartAvailable: boolean | null;
  predictedFailureType: string;
  recommendedDecision: MvpDecision;
  observedAt: string | null;
  eventId: string | null;
  topFactors: MvpFactor[];
  provenance: MvpProvenance;
}

export interface MvpEvent {
  eventId: string;
  scenarioId: string;
  assetId: string;
  assetName: string;
  line: string;
  status: MvpRiskStatus;
  failureProbability: number | null;
  confidence: MvpConfidence;
  predictedFailureType: string;
  recommendedDecision: MvpDecision;
  criticality: "low" | "medium" | "high";
  assignedEngineer: string | null;
  estimatedDowntimeMinutes: number;
  sparePartAvailable: boolean | null;
  observedAt: string | null;
  datasetVersionId: string;
  ontologyObjectId: string | null;
}

export interface MvpMetrics {
  totalAssets: number;
  normal: number;
  attention: number;
  warning: number;
  critical: number;
  dataQualityHold: number;
  averageRisk: number | null;
  estimatedDowntimeMinutes: number;
  pendingDecisions: number;
}

export interface MvpLineRisk {
  line: string;
  total: number;
  critical: number;
  warning: number;
  attention: number;
  dataQualityHold: number;
  averageRisk: number | null;
}

export interface MvpContextModel {
  projectId: string;
  projectName: string;
  workspaceId: string;
  workspaceName: string;
  datasetVersionId: string;
  datasetLabel: string;
  sourceVersion: string | null;
  modelVersion: string | null;
  schemaVersion: string | null;
  sourceMode: MvpSourceMode;
  sourceStatus: string;
  refreshedAt: string;
  observedAt: string | null;
  stale: boolean;
  warnings: string[];
}

export interface MvpBootstrapModel {
  context: MvpContextModel;
  assets: MvpAsset[];
  events: MvpEvent[];
  metrics: MvpMetrics;
  lineRisk: MvpLineRisk[];
}

export interface MvpSensorValue {
  id: string;
  label: string;
  value: number | string | boolean | null;
  unit: string | null;
}

export interface MvpActivityItem {
  id: string;
  kind: "decision" | "note" | "conversation" | "system";
  title: string;
  detail: string;
  actor: string;
  createdAt: string;
  decision: MvpDecision | null;
}

export interface MvpReportSection {
  id: string;
  title: string;
  body: string;
  evidenceFieldIds: string[];
}

export interface MvpReportModel {
  reportId: string;
  revision: number;
  mode: "llm" | "deterministic-fallback" | "template-fallback";
  headline: string;
  summary: string;
  sections: MvpReportSection[];
  actions: string[];
  limitations: string[];
  generatedAt: string;
  promptVersion: string | null;
}

export interface MvpEventDetailModel {
  event: MvpEvent;
  sensors: MvpSensorValue[];
  topFactors: MvpFactor[];
  threshold: number | null;
  dataQualityWarnings: Array<{ code: string; field: string; message: string; severity: string }>;
  activity: MvpActivityItem[];
  report: MvpReportModel;
  provenance: MvpProvenance;
  loadedSources: {
    evidence: boolean;
    report: boolean;
    activity: boolean;
  };
  warnings: string[];
}

export interface MvpSelection {
  view: MvpView;
  projectId: string;
  workspaceId: string | null;
  assetId: string | null;
  eventId: string | null;
  role: MvpRoleLens;
}
