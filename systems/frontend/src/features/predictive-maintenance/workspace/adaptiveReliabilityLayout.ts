import type { BlockType, Intent } from "../../../types";
import type { ReliabilityBlockId } from "./roleComposition";

export interface AdaptiveReliabilityCardSignals {
  declaredSpan: 6 | 12;
  empty: boolean;
  actionHero: boolean;
  textLength: number;
  controlCount: number;
  hasWideVisualization: boolean;
}

export const RELIABILITY_MASONRY_ROW_HEIGHT = 8;

const PLANNER_BLOCK_MAP: Record<BlockType, ReliabilityBlockId[]> = {
  StatusSummary: ["risk-metrics", "asset-brief"],
  RiskKpi: ["risk-metrics", "operational-kpis"],
  PriorityList: ["risk-queue", "decision-queue", "risk-portfolio"],
  ImpactSummary: ["production-exposure", "business-kpis"],
  ManagerDecisionCard: ["decision-queue", "decision-bottleneck", "workflow-actions"],
  SensorLineChart: ["feature-trend", "sensor-signals"],
  AnomalyTimeline: ["feature-trend", "maintenance-history"],
  FactorContribution: ["evidence-factors"],
  EvidenceTable: ["case-lineage", "decision-history", "context-evidence"],
  RecommendedActions: ["workflow-actions", "material-context"],
  EngineerChecklist: ["inspection-targets", "workflow-actions"],
  DataQualityWarning: ["data-quality"],
  ModelDetails: ["evidence-factors", "sensor-signals"],
  ConversationThread: ["decision-history", "context-evidence"],
};

export function reliabilityLayoutIntent(surfaceId: string | null): Intent {
  if (surfaceId === "assets" || surfaceId === "monitoring") return "explain-risk";
  if (surfaceId === "inspection" || surfaceId === "maintenance-approval") return "recommend-check";
  if (surfaceId === "maintenance-effect") return "compare";
  if (surfaceId === "executive-brief" || surfaceId === "executive-reports" || surfaceId === "report-draft") {
    return "summarize-manager";
  }
  if (surfaceId === "sensor-features" || surfaceId === "maintenance-history" || surfaceId === "work-targets") {
    return "detail-engineer";
  }
  return "overview";
}

function governedPrefixLength(blocks: ReliabilityBlockId[]) {
  const workflowActionIndex = blocks.indexOf("workflow-actions");
  if (workflowActionIndex >= 0) return workflowActionIndex + 1;
  if (blocks[0] === "data-quality") return 1;
  return 0;
}

export function applyReliabilityPlannerOrder(
  blocks: ReliabilityBlockId[],
  plannerTypes: BlockType[] | null | undefined,
) {
  if (!plannerTypes?.length) return blocks;
  const prefixLength = governedPrefixLength(blocks);
  const prefix = blocks.slice(0, prefixLength);
  const candidates = blocks.slice(prefixLength);
  const candidateSet = new Set(candidates);
  const ranked: ReliabilityBlockId[] = [];
  for (const type of plannerTypes) {
    for (const blockId of PLANNER_BLOCK_MAP[type]) {
      if (!candidateSet.has(blockId) || ranked.includes(blockId)) continue;
      ranked.push(blockId);
    }
  }
  for (const blockId of candidates) {
    if (!ranked.includes(blockId)) ranked.push(blockId);
  }
  return [...prefix, ...ranked];
}

/**
 * Reliability layout has two layers:
 * - semantic ordering is owned by role/runtime composition (and can be fed by
 *   an LLM planner),
 * - pixel geometry stays deterministic so a refresh never makes the UI jump
 *   unpredictably for the same content.
 *
 * The geometry layer may shrink genuinely compact cards, widen dense cards,
 * and lets empty states occupy one half-row so later cards can pack beside
 * them instead of inheriting a tall sibling's row height.
 */
export function preferredAdaptiveReliabilitySpan(
  signals: AdaptiveReliabilityCardSignals,
): 4 | 6 | 8 | 12 {
  if (signals.actionHero) return 12;
  if (signals.empty) return 6;
  if (signals.declaredSpan === 12) return 12;
  if (signals.hasWideVisualization) return 6;
  if (signals.controlCount >= 6 || signals.textLength >= 1600) return 8;
  if (signals.controlCount <= 1 && signals.textLength > 0 && signals.textLength <= 260) return 4;
  return 6;
}

export function adaptiveReliabilityRowSpan(
  contentHeight: number,
  rowGap: number,
  rowHeight = RELIABILITY_MASONRY_ROW_HEIGHT,
) {
  if (!Number.isFinite(contentHeight) || contentHeight <= 0) return 1;
  return Math.max(1, Math.ceil((contentHeight + rowGap) / (rowHeight + rowGap)));
}
