import type {
  BoardCatalogDefinition,
  DashboardBoard,
  DashboardTab,
  DependencyEdge,
  ResolvedDashboard,
} from "./types";
import { applyGridLayoutItem, backfillGridLayouts, legacyBoardToGridLayout } from "./gridLayout";

export function cloneDashboard(dashboard: ResolvedDashboard): ResolvedDashboard {
  return structuredClone(dashboard);
}

export const deriveBoardLayout = legacyBoardToGridLayout;
export const withBoardLayouts = backfillGridLayouts;

export function applyBoardLayouts(
  tabs: DashboardTab[],
  tabId: string,
  layouts: ReadonlyArray<{ i: string; x: number; y: number; w: number; h: number }>,
): DashboardTab[] {
  const layoutById = new Map(layouts.map((layout) => [layout.i, layout]));
  return tabs.map((tab) => {
    if (tab.id !== tabId) return tab;
    const boards = tab.boards.map((board) => {
      const layout = layoutById.get(board.id);
      if (!layout) return board;
      return applyGridLayoutItem(board, layout);
    });
    return { ...tab, boards };
  });
}

export function normalizeTabs(tabs: DashboardTab[]): DashboardTab[] {
  return tabs
    .map((tab) => ({
      ...tab,
      boards: [...tab.boards]
        .sort((a, b) => a.order - b.order)
        .map((board, index) => ({ ...board, order: index })),
    }))
    .sort((a, b) => a.order - b.order)
    .map((tab, index) => ({ ...tab, order: index }));
}

export function reorderTabs(tabs: DashboardTab[], sourceId: string, targetId: string): DashboardTab[] {
  if (sourceId === targetId) return tabs;
  const ordered = [...tabs].sort((a, b) => a.order - b.order);
  const sourceIndex = ordered.findIndex((tab) => tab.id === sourceId);
  const targetIndex = ordered.findIndex((tab) => tab.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0) return tabs;
  const [source] = ordered.splice(sourceIndex, 1);
  ordered.splice(targetIndex, 0, source);
  return normalizeTabs(ordered);
}

export function moveBoard(
  tabs: DashboardTab[],
  boardId: string,
  targetTabId: string,
  targetBoardId?: string,
): DashboardTab[] {
  let moving: DashboardBoard | null = null;
  const without = tabs.map((tab) => ({
    ...tab,
    boards: tab.boards.filter((board) => {
      if (board.id !== boardId) return true;
      moving = board;
      return false;
    }),
  }));
  if (!moving) return tabs;
  return normalizeTabs(
    without.map((tab) => {
      if (tab.id !== targetTabId) return tab;
      const boards = [...tab.boards];
      const targetIndex = targetBoardId ? boards.findIndex((board) => board.id === targetBoardId) : -1;
      if (targetIndex >= 0) boards.splice(targetIndex, 0, moving as DashboardBoard);
      else boards.push(moving as DashboardBoard);
      return { ...tab, boards };
    }),
  );
}

export function updateBoard(
  tabs: DashboardTab[],
  boardId: string,
  update: Partial<DashboardBoard>,
): DashboardTab[] {
  return tabs.map((tab) => ({
    ...tab,
    boards: tab.boards.map((board) => board.id === boardId ? { ...board, ...update } : board),
  }));
}

export function removeBoard(tabs: DashboardTab[], boardId: string): DashboardTab[] {
  const board = tabs.flatMap((tab) => tab.boards).find((item) => item.id === boardId);
  if (board?.mandatory) throw new Error("필수 board는 삭제할 수 없습니다.");
  return normalizeTabs(tabs.map((tab) => ({ ...tab, boards: tab.boards.filter((item) => item.id !== boardId) })));
}

export function duplicateBoard(tabs: DashboardTab[], boardId: string): { tabs: DashboardTab[]; boardId: string } {
  const sourceTab = tabs.find((tab) => tab.boards.some((board) => board.id === boardId));
  const source = sourceTab?.boards.find((board) => board.id === boardId);
  if (!sourceTab || !source) return { tabs, boardId };
  const nextId = `custom:${source.definition_id}:${crypto.randomUUID()}`;
  const sourceLayout = deriveBoardLayout(source, source.order);
  const duplicate: DashboardBoard = {
    ...structuredClone(source),
    id: nextId,
    title: `${source.title} 복사본`,
    order: source.order + 1,
    layout: { ...sourceLayout, x: Math.min(11, sourceLayout.x + 1), y: sourceLayout.y + 1 },
    mandatory: false,
    custom: true,
  };
  const nextTabs = tabs.map((tab) => {
    if (tab.id !== sourceTab.id) return tab;
    const boards = [...tab.boards];
    boards.splice(source.order + 1, 0, duplicate);
    return { ...tab, boards };
  });
  return { tabs: normalizeTabs(nextTabs), boardId: nextId };
}

export function addCatalogBoard(
  tabs: DashboardTab[],
  tabId: string,
  definition: BoardCatalogDefinition,
): { tabs: DashboardTab[]; boardId: string } {
  const boardId = `custom:${definition.id}:${crypto.randomUUID()}`;
  const next = tabs.map((tab) => {
    if (tab.id !== tabId) return tab;
    const board: DashboardBoard = {
      id: boardId,
      definition_id: definition.id,
      title: definition.display_name,
      width: definition.default_width,
      order: tab.boards.length,
      layout: {
        x: 0,
        y: tab.boards.length * 2,
        w: definition.default_width,
        h: Math.max(1, Number(definition.default_settings.height_units ?? 2)),
        min_w: definition.minimum_width,
        min_h: 1,
        max_w: definition.maximum_width,
        max_h: 12,
      },
      hidden: false,
      mandatory: false,
      custom: true,
      bindings: structuredClone(definition.default_bindings),
      settings: structuredClone(definition.default_settings),
    };
    return { ...tab, boards: [...tab.boards, board] };
  });
  return { tabs: normalizeTabs(next), boardId };
}

export function addCustomTab(tabs: DashboardTab[], title = "새 탭"): { tabs: DashboardTab[]; tabId: string } {
  const tabId = `custom:tab:${crypto.randomUUID()}`;
  return {
    tabId,
    tabs: normalizeTabs([
      ...tabs,
      {
        id: tabId,
        title,
        order: tabs.length,
        hidden: false,
        custom: true,
        parameter_ids: ["selected_event_id", "selected_equipment_id", "status_filter", "intent"],
        boards: [],
      },
    ]),
  };
}

export function affectedBoardIds(
  graph: DependencyEdge[],
  sourceBoardId: string,
  parameterId: string,
): string[] {
  return graph
    .filter((edge) => edge.source_board_id === sourceBoardId && edge.parameter_ids.includes(parameterId))
    .map((edge) => edge.target_board_id);
}
