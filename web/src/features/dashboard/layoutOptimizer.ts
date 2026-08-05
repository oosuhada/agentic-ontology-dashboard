import type { DashboardBoard, DashboardBoardLayout } from "./types";

export type DashboardLayoutStrategy = "content-fit" | "ai-recommendation";

export interface BoardContentMetric {
  boardId: string;
  contentHeight: number;
  contentWidth: number;
  viewportHeight: number;
}

export const DEFAULT_ROW_HEIGHT = 82;
const BOARD_CHROME_HEIGHT = 72;

const WIDTH_HINTS: Record<string, number> = {
  OperationsKpi: 12,
  StatusSummary: 12,
  RiskTrendWorkbench: 8,
  SensorLineChart: 8,
  EventDataGrid: 8,
  EvidenceTable: 8,
  GenericDataBoard: 8,
  AnalysisReference: 8,
  OntologyRelationship: 4,
  FactorContribution: 4,
  RecommendedActions: 4,
  ActivityStream: 4,
  PlannerAssistant: 8,
  ConversationThread: 6,
  DataQualityWarning: 12,
  PriorityList: 6,
  ImpactSummary: 6,
  ManagerDecisionCard: 4,
  EngineerChecklist: 4,
  ModelDetails: 8,
};

const HEIGHT_HINTS: Record<string, number> = {
  OperationsKpi: 2,
  StatusSummary: 2,
  RiskTrendWorkbench: 4,
  SensorLineChart: 4,
  EventDataGrid: 5,
  EvidenceTable: 5,
  GenericDataBoard: 5,
  AnalysisReference: 4,
  OntologyRelationship: 4,
  FactorContribution: 4,
  RecommendedActions: 3,
  ActivityStream: 4,
  PlannerAssistant: 6,
  ConversationThread: 5,
  DataQualityWarning: 3,
  PriorityList: 4,
  ImpactSummary: 3,
  ManagerDecisionCard: 4,
  EngineerChecklist: 4,
  ModelDetails: 5,
};

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function rendererName(board: DashboardBoard, rendererByDefinition?: Map<string, string>) {
  return String(
    rendererByDefinition?.get(board.definition_id)
      ?? board.settings.renderer
      ?? board.settings.renderer_name
      ?? board.definition_id
      ?? "",
  );
}

function isLocked(board: DashboardBoard) {
  return board.settings.layout_lock === true || board.settings.layout_mode === "manual";
}

function contentHeightUnits(metric: BoardContentMetric | undefined, layout: DashboardBoardLayout, semanticHint: number) {
  if (!metric || metric.contentHeight <= 0) return layout.h;
  if (metric.contentHeight <= metric.viewportHeight + 12) return semanticHint;
  const measured = Math.ceil((metric.contentHeight + BOARD_CHROME_HEIGHT) / DEFAULT_ROW_HEIGHT);
  return clamp(measured, layout.min_h ?? 1, layout.max_h ?? 12);
}

function preferredWidth(board: DashboardBoard, viewportWidth: number, rendererByDefinition?: Map<string, string>) {
  const renderer = rendererName(board, rendererByDefinition);
  const current = board.layout?.w ?? board.width ?? 6;
  const hinted = WIDTH_HINTS[renderer] ?? current;
  const viewportAdjusted = viewportWidth < 900 ? 12 : viewportWidth < 1180 ? Math.max(6, hinted) : hinted;
  return clamp(viewportAdjusted, board.layout?.min_w ?? 2, board.layout?.max_w ?? 12);
}

function preferredHeight(board: DashboardBoard, metric: BoardContentMetric | undefined, rendererByDefinition?: Map<string, string>) {
  const current = board.layout ?? { x: 0, y: 0, w: board.width || 6, h: 3 };
  const renderer = rendererName(board, rendererByDefinition);
  const semanticHint = HEIGHT_HINTS[renderer] ?? current.h;
  return Math.max(semanticHint, contentHeightUnits(metric, current, semanticHint));
}

function packBoards(boards: DashboardBoard[]): DashboardBoard[] {
  const occupied = new Set<string>();
  const placed = new Map<string, DashboardBoardLayout>();
  const occupy = (layout: DashboardBoardLayout) => {
    for (let y = layout.y; y < layout.y + layout.h; y += 1) {
      for (let x = layout.x; x < layout.x + layout.w; x += 1) occupied.add(`${x}:${y}`);
    }
  };
  const fits = (x: number, y: number, width: number, height: number) => {
    if (x + width > 12) return false;
    for (let row = y; row < y + height; row += 1) {
      for (let column = x; column < x + width; column += 1) {
        if (occupied.has(`${column}:${row}`)) return false;
      }
    }
    return true;
  };

  for (const board of boards) {
    if (!isLocked(board) || !board.layout) continue;
    const locked = {
      ...board.layout,
      x: clamp(board.layout.x, 0, Math.max(0, 12 - board.layout.w)),
    };
    placed.set(board.id, locked);
    occupy(locked);
  }

  for (const board of boards) {
    if (placed.has(board.id)) continue;
    const layout = board.layout ?? { x: 0, y: 0, w: board.width || 6, h: 3 };
    let position = { x: 0, y: 0 };
    let found = false;
    for (let y = 0; y < 120 && !found; y += 1) {
      for (let x = 0; x <= 12 - layout.w; x += 1) {
        if (!fits(x, y, layout.w, layout.h)) continue;
        position = { x, y };
        found = true;
        break;
      }
    }
    const nextLayout = { ...layout, ...position };
    placed.set(board.id, nextLayout);
    occupy(nextLayout);
  }

  return boards.map((board) => {
    const layout = placed.get(board.id) ?? board.layout ?? { x: 0, y: 0, w: board.width || 6, h: 3 };
    return { ...board, width: layout.w, layout };
  });
}

export function optimizeDashboardLayout(
  boards: DashboardBoard[],
  metrics: BoardContentMetric[],
  strategy: DashboardLayoutStrategy,
  viewportWidth: number,
  rendererByDefinition?: Map<string, string>,
) {
  const metricById = new Map(metrics.map((metric) => [metric.boardId, metric]));
  const updated = boards.map((board) => {
    if (isLocked(board)) return board;
    const layout = board.layout ?? { x: 0, y: 0, w: board.width || 6, h: 3, min_w: 2, min_h: 1, max_w: 12, max_h: 12 };
    const nextHeight = preferredHeight(board, metricById.get(board.id), rendererByDefinition);
    const nextWidth = strategy === "content-fit" ? layout.w : preferredWidth(board, viewportWidth, rendererByDefinition);
    return {
      ...board,
      width: nextWidth,
      layout: { ...layout, w: nextWidth, h: nextHeight },
      settings: {
        ...board.settings,
        height_units: String(nextHeight),
        layout_mode: strategy === "content-fit" ? "auto" : "ai",
        preferred_width: nextWidth,
      },
    };
  });
  return packBoards(updated);
}
