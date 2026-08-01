import type { DashboardBoard, DashboardBoardLayout } from "./types";

const DEFAULT_HEIGHT_BY_RENDERER: Record<string, number> = {
  OperationsKpi: 1,
  RiskTrendWorkbench: 4,
  EventDataGrid: 5,
  OntologyRelationship: 4,
  ActivityStream: 4,
  PlannerAssistant: 6,
  ConversationThread: 5,
  SensorLineChart: 4,
};

export function legacyBoardToGridLayout(
  board: DashboardBoard,
  index: number,
  renderer?: string,
): DashboardBoardLayout {
  if (board.layout) {
    return {
      x: Math.max(0, Math.min(11, board.layout.x)),
      y: Math.max(0, board.layout.y),
      w: Math.max(1, Math.min(12, board.layout.w)),
      h: Math.max(1, Math.min(12, board.layout.h)),
      min_w: board.layout.min_w ?? undefined,
      min_h: board.layout.min_h ?? undefined,
      max_w: board.layout.max_w ?? undefined,
      max_h: board.layout.max_h ?? undefined,
    };
  }

  const width = Math.max(1, Math.min(12, board.width || 6));
  const columnsPerRow = Math.max(1, Math.floor(12 / width));
  const settingsHeight = Number(board.settings.height_units ?? 0);
  return {
    x: (index % columnsPerRow) * width,
    y: Math.floor(index / columnsPerRow) * 2,
    w: width,
    h: Math.max(1, settingsHeight || DEFAULT_HEIGHT_BY_RENDERER[renderer ?? ""] || 2),
    min_w: 2,
    min_h: 1,
    max_w: 12,
    max_h: 12,
  };
}

export function backfillGridLayouts(
  boards: DashboardBoard[],
  rendererByDefinition?: Map<string, string>,
): DashboardBoard[] {
  let x = 0;
  let y = 0;
  let rowHeight = 0;

  return [...boards]
    .sort((left, right) => left.order - right.order)
    .map((board, index) => {
      if (board.layout) return { ...board, layout: legacyBoardToGridLayout(board, index, rendererByDefinition?.get(board.definition_id)) };
      const layout = legacyBoardToGridLayout(board, index, rendererByDefinition?.get(board.definition_id));
      if (x + layout.w > 12) {
        x = 0;
        y += Math.max(1, rowHeight);
        rowHeight = 0;
      }
      const placed = { ...layout, x, y };
      x += layout.w;
      rowHeight = Math.max(rowHeight, layout.h);
      if (x >= 12) {
        x = 0;
        y += rowHeight;
        rowHeight = 0;
      }
      return {
        ...board,
        width: placed.w,
        layout: placed,
        settings: { ...board.settings, height_units: String(placed.h) },
      };
    });
}

export function applyGridLayoutItem(
  board: DashboardBoard,
  layout: { x: number; y: number; w: number; h: number },
): DashboardBoard {
  return {
    ...board,
    width: layout.w,
    layout: {
      ...(board.layout ?? {}),
      x: layout.x,
      y: layout.y,
      w: layout.w,
      h: layout.h,
    },
    settings: { ...board.settings, height_units: String(layout.h) },
  };
}
