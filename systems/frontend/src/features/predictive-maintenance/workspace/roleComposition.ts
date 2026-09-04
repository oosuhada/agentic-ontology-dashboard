import type { OperationsView } from "../../operations/api/operationsContracts";
import type { ReliabilityExperienceKind } from "./roleExperience";
import type { ReliabilitySurfaceId } from "./roleSurfaces";

export type ReliabilityBlockId =
  | "risk-metrics"
  | "factory-map"
  | "business-kpis"
  | "operational-kpis"
  | "risk-portfolio"
  | "line-risk"
  | "risk-queue"
  | "asset-brief"
  | "production-exposure"
  | "decision-queue"
  | "decision-bottleneck"
  | "workflow-lifecycle"
  | "case-lineage"
  | "workflow-actions"
  | "sensor-signals"
  | "feature-trend"
  | "evidence-factors"
  | "inspection-targets"
  | "maintenance-history"
  | "maintenance-effect"
  | "material-context"
  | "decision-history"
  | "report-summary"
  | "context-evidence"
  | "data-quality";

export interface ReliabilityCompositionSignals {
  hasCriticalRisk: boolean;
  hasDataQualityHold: boolean;
  hasOpenWorkflow: boolean;
  hasMaterialConstraint: boolean;
  hasDecisionBacklog: boolean;
  hasHighProductionExposure: boolean;
  hasMaintenanceOutcome: boolean;
}

const COMPOSITIONS: Record<ReliabilityExperienceKind, Record<Exclude<OperationsView, "system">, ReliabilityBlockId[]>> = {
  executive: {
    reports: ["risk-metrics", "operational-kpis", "report-summary", "production-exposure", "decision-queue", "case-lineage", "business-kpis", "risk-portfolio", "context-evidence"],
    operations: ["operational-kpis", "decision-queue", "production-exposure", "case-lineage", "workflow-lifecycle", "business-kpis", "risk-queue", "context-evidence"],
    overview: ["risk-metrics", "factory-map", "operational-kpis", "risk-portfolio", "business-kpis", "line-risk", "risk-queue", "context-evidence"],
    objects: ["asset-brief", "production-exposure", "case-lineage", "maintenance-effect", "maintenance-history", "material-context", "evidence-factors"],
  },
  operations: {
    operations: ["risk-metrics", "operational-kpis", "decision-queue", "production-exposure", "case-lineage", "workflow-lifecycle", "workflow-actions", "material-context", "context-evidence"],
    overview: ["risk-metrics", "factory-map", "operational-kpis", "risk-portfolio", "line-risk", "risk-queue", "decision-queue", "business-kpis"],
    objects: ["asset-brief", "production-exposure", "case-lineage", "maintenance-history", "maintenance-effect", "material-context", "evidence-factors", "context-evidence"],
    reports: ["report-summary", "operational-kpis", "production-exposure", "case-lineage", "decision-history", "business-kpis", "context-evidence"],
  },
  engineering: {
    overview: ["risk-metrics", "factory-map", "risk-queue", "feature-trend", "sensor-signals", "evidence-factors", "case-lineage", "inspection-targets", "maintenance-history"],
    objects: ["asset-brief", "feature-trend", "sensor-signals", "evidence-factors", "case-lineage", "maintenance-history", "maintenance-effect", "material-context", "context-evidence"],
    operations: ["inspection-targets", "case-lineage", "workflow-lifecycle", "workflow-actions", "maintenance-history", "decision-history", "evidence-factors"],
    reports: ["report-summary", "evidence-factors", "maintenance-history", "context-evidence"],
  },
  maintenance: {
    operations: ["risk-metrics", "case-lineage", "workflow-lifecycle", "workflow-actions", "inspection-targets", "asset-brief", "material-context", "maintenance-history", "maintenance-effect"],
    objects: ["asset-brief", "inspection-targets", "sensor-signals", "case-lineage", "maintenance-history", "maintenance-effect", "material-context"],
    overview: ["risk-metrics", "factory-map", "case-lineage", "workflow-lifecycle", "risk-queue", "material-context", "maintenance-history"],
    reports: ["maintenance-effect", "maintenance-history", "decision-history", "report-summary", "context-evidence"],
  },
};

const SURFACE_COMPOSITIONS: Partial<Record<ReliabilitySurfaceId, ReliabilityBlockId[]>> = {
  "executive-brief": ["risk-metrics", "production-exposure", "decision-bottleneck", "report-summary", "operational-kpis"],
  "operational-risk": ["risk-metrics", "risk-portfolio", "production-exposure", "line-risk", "risk-queue"],
  "executive-kpi": ["operational-kpis", "risk-metrics", "business-kpis", "production-exposure"],
  "executive-reports": ["report-summary", "decision-bottleneck", "production-exposure", "operational-kpis"],
  "decision-bottleneck": ["decision-bottleneck", "workflow-lifecycle", "production-exposure", "operational-kpis"],
  "maintenance-effect": ["maintenance-effect", "maintenance-history", "production-exposure", "risk-portfolio"],
  roadmap: ["business-kpis", "decision-history", "maintenance-history", "material-context"],

  "operations-status": ["risk-metrics", "operational-kpis", "line-risk", "risk-queue", "decision-queue", "production-exposure"],
  "pending-decisions": ["decision-queue", "workflow-lifecycle", "production-exposure", "workflow-actions", "operational-kpis"],
  "decision-case": ["workflow-lifecycle", "decision-queue", "production-exposure", "workflow-actions", "case-lineage", "evidence-factors"],
  "production-impact": ["production-exposure", "business-kpis", "material-context", "risk-queue", "line-risk"],
  "maintenance-approval": ["case-lineage", "workflow-lifecycle", "workflow-actions", "inspection-targets", "material-context", "maintenance-history", "maintenance-effect"],
  backlog: ["decision-queue", "operational-kpis", "decision-history", "line-risk"],
  "report-draft": ["report-summary", "case-lineage", "production-exposure", "decision-history"],

  monitoring: ["risk-queue", "feature-trend", "sensor-signals", "evidence-factors", "case-lineage"],
  assets: ["evidence-factors", "inspection-targets", "sensor-signals", "feature-trend", "case-lineage"],
  "sensor-features": ["feature-trend", "sensor-signals", "evidence-factors", "maintenance-history"],
  inspection: ["inspection-targets", "workflow-actions", "workflow-lifecycle", "feature-trend", "evidence-factors", "case-lineage"],
  "maintenance-history": ["maintenance-history", "maintenance-effect", "decision-history", "evidence-factors"],
  "field-notes": ["decision-history", "inspection-targets", "report-summary"],

  "my-work": ["risk-metrics", "factory-map", "workflow-lifecycle", "workflow-actions", "inspection-targets", "material-context"],
  "work-targets": ["asset-brief", "inspection-targets", "material-context", "feature-trend", "maintenance-history"],
  "field-status": ["risk-metrics", "factory-map", "workflow-lifecycle", "risk-queue", "maintenance-history"],
  "work-history": ["maintenance-history", "decision-history", "report-summary", "context-evidence"],
};

function promote(blocks: ReliabilityBlockId[], id: ReliabilityBlockId, position = 0): ReliabilityBlockId[] {
  const next = blocks.filter((item) => item !== id);
  next.splice(Math.max(0, Math.min(position, next.length)), 0, id);
  return next;
}

function promoteAfterInvariant(blocks: ReliabilityBlockId[], id: ReliabilityBlockId, invariantCount: number, relativePosition = 0) {
  const currentIndex = blocks.indexOf(id);
  if (currentIndex >= 0 && currentIndex < invariantCount) return blocks;
  return promote(blocks, id, Math.min(blocks.length, invariantCount + relativePosition));
}

export function resolveReliabilityComposition(
  kind: ReliabilityExperienceKind,
  view: OperationsView,
  signals: ReliabilityCompositionSignals,
  surfaceId?: string | null,
): ReliabilityBlockId[] {
  if (view === "system") return [];
  const surfaceBlocks = surfaceId ? SURFACE_COMPOSITIONS[surfaceId as ReliabilitySurfaceId] : null;
  const roleSpecificSurfaceBlocks = kind === "engineering" && surfaceId === "maintenance-effect"
    ? ["maintenance-effect", "feature-trend", "sensor-signals", "maintenance-history", "evidence-factors"] satisfies ReliabilityBlockId[]
    : null;
  let blocks = [...(roleSpecificSurfaceBlocks ?? surfaceBlocks ?? COMPOSITIONS[kind][view])];
  const invariantCount = surfaceId === "executive-brief"
    ? Math.min(4, blocks.length)
    : surfaceBlocks || roleSpecificSurfaceBlocks
      ? Math.min(3, blocks.length)
      : 0;
  if (signals.hasDataQualityHold) {
    blocks = promoteAfterInvariant(blocks, "data-quality", invariantCount, 0);
  }
  if (signals.hasOpenWorkflow) {
    blocks = promoteAfterInvariant(blocks, "workflow-lifecycle", invariantCount, signals.hasDataQualityHold ? 1 : 0);
  }
  if (signals.hasDecisionBacklog && kind === "operations") {
    blocks = promoteAfterInvariant(blocks, "decision-queue", invariantCount, signals.hasDataQualityHold ? 1 : 0);
  }
  if (signals.hasCriticalRisk && kind === "engineering") {
    blocks = promoteAfterInvariant(blocks, "feature-trend", invariantCount, signals.hasDataQualityHold ? 1 : 0);
    blocks = promoteAfterInvariant(blocks, "evidence-factors", invariantCount, signals.hasDataQualityHold ? 2 : 1);
  }
  if (signals.hasHighProductionExposure && kind === "executive") {
    blocks = promoteAfterInvariant(blocks, "production-exposure", invariantCount, signals.hasDataQualityHold ? 1 : 0);
  }
  if (signals.hasMaintenanceOutcome) {
    blocks = promoteAfterInvariant(blocks, "maintenance-effect", invariantCount, signals.hasDataQualityHold ? 2 : 1);
  }
  if (signals.hasMaterialConstraint && (kind === "operations" || kind === "executive" || kind === "maintenance")) {
    blocks = promoteAfterInvariant(blocks, "material-context", invariantCount, 0);
  }
  if (signals.hasCriticalRisk && kind === "executive") {
    blocks = promoteAfterInvariant(blocks, "production-exposure", invariantCount, signals.hasDataQualityHold ? 1 : 0);
  }
  return blocks;
}

export function baseReliabilityComposition(
  kind: ReliabilityExperienceKind,
  view: Exclude<OperationsView, "system">,
): ReliabilityBlockId[] {
  return [...COMPOSITIONS[kind][view]];
}
