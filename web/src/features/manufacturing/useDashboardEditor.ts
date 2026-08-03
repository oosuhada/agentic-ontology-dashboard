import type { Dispatch, SetStateAction } from "react";
import type { BoardCatalogDefinition, DashboardBoard, DashboardMode, ResolvedDashboard } from "../dashboard/types";
import { legacyBoardToGridLayout } from "../dashboard/gridLayout";
import {
  addCatalogBoard,
  addCustomTab,
  applyBoardLayouts,
  duplicateBoard,
  moveBoard,
  removeBoard,
  reorderTabs,
  updateBoard,
} from "../dashboard/utils";

interface DashboardEditorOptions {
  draftDashboard: ResolvedDashboard | null;
  selectedBoardId: string | null;
  selectedBoard: DashboardBoard | null;
  setDraftDashboard: Dispatch<SetStateAction<ResolvedDashboard | null>>;
  setSelectedBoardId: Dispatch<SetStateAction<string | null>>;
  setCatalogTargetTabId: Dispatch<SetStateAction<string>>;
  setMode: Dispatch<SetStateAction<DashboardMode>>;
  setDirty: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string>>;
  onBeforeChange: (current: ResolvedDashboard) => void;
}

export function useDashboardEditor({
  draftDashboard,
  selectedBoardId,
  selectedBoard,
  setDraftDashboard,
  setSelectedBoardId,
  setCatalogTargetTabId,
  setMode,
  setDirty,
  setError,
  onBeforeChange,
}: DashboardEditorOptions) {
  function updateDraft(
    updater: (current: ResolvedDashboard) => ResolvedDashboard,
    markDirty = true,
  ) {
    if (markDirty && draftDashboard) onBeforeChange(draftDashboard);
    setDraftDashboard((current) => current ? updater(current) : current);
    if (markDirty) setDirty(true);
  }

  function handleActiveTab(tabId: string) {
    updateDraft((current) => ({ ...current, active_tab_id: tabId }));
    setCatalogTargetTabId(tabId);
    setSelectedBoardId(null);
  }

  function handleReorderTabs(sourceId: string, targetId: string) {
    updateDraft((current) => ({ ...current, tabs: reorderTabs(current.tabs, sourceId, targetId) }));
  }

  function handleMoveBoard(boardId: string, targetTabId: string, targetBoardId?: string) {
    updateDraft((current) => ({
      ...current,
      tabs: moveBoard(current.tabs, boardId, targetTabId, targetBoardId),
      active_tab_id: targetTabId,
    }));
  }

  function handleLayoutChange(tabId: string, layouts: ReadonlyArray<{ i: string; x: number; y: number; w: number; h: number }>) {
    const tab = draftDashboard?.tabs.find((item) => item.id === tabId);
    if (!tab) return;
    const boardById = new Map(tab.boards.map((board, index) => [board.id, { board, index }]));
    const changed = layouts.some((layout) => {
      const current = boardById.get(layout.i);
      if (!current) return false;
      const position = legacyBoardToGridLayout(current.board, current.index);
      return position.x !== layout.x
        || position.y !== layout.y
        || position.w !== layout.w
        || position.h !== layout.h;
    });
    if (!changed) return;
    updateDraft((current) => ({
      ...current,
      tabs: applyBoardLayouts(current.tabs, tabId, layouts),
    }));
  }

  function handleUpdateBoard(update: Partial<DashboardBoard>) {
    if (!selectedBoardId) return;
    if (selectedBoard?.mandatory && update.hidden) {
      setError("필수 board는 숨길 수 없습니다.");
      return;
    }
    updateDraft((current) => ({
      ...current,
      tabs: updateBoard(current.tabs, selectedBoardId, update),
    }));
  }

  function handleRemoveBoard(boardId: string) {
    try {
      updateDraft((current) => ({ ...current, tabs: removeBoard(current.tabs, boardId) }));
      if (selectedBoardId === boardId) setSelectedBoardId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Board를 삭제하지 못했습니다.");
    }
  }

  function handleToggleHidden(boardId: string, hidden: boolean) {
    const board = draftDashboard?.tabs.flatMap((tab) => tab.boards).find((item) => item.id === boardId);
    if (board?.mandatory && hidden) {
      setError("필수 board는 숨길 수 없습니다.");
      return;
    }
    updateDraft((current) => ({
      ...current,
      tabs: updateBoard(current.tabs, boardId, { hidden }),
    }));
  }

  function handleToggleFavorite(boardId: string) {
    const board = draftDashboard?.tabs.flatMap((tab) => tab.boards).find((item) => item.id === boardId);
    if (!board) return;
    updateDraft((current) => ({
      ...current,
      tabs: updateBoard(current.tabs, boardId, {
        settings: { ...board.settings, favorite: board.settings.favorite !== true },
      }),
    }));
  }

  function handleDuplicateBoard(boardId: string) {
    updateDraft((current) => {
      const result = duplicateBoard(current.tabs, boardId);
      setSelectedBoardId(result.boardId);
      return { ...current, tabs: result.tabs };
    });
  }

  function handleAddTab() {
    if (!draftDashboard) return;
    const title = window.prompt("새 탭 이름", "새 분석 탭")?.trim();
    if (!title) return;
    updateDraft((current) => {
      const result = addCustomTab(current.tabs, title);
      setCatalogTargetTabId(result.tabId);
      return { ...current, tabs: result.tabs, active_tab_id: result.tabId };
    });
  }

  function handleAddBoard(definition: BoardCatalogDefinition, tabId: string) {
    updateDraft((current) => {
      const result = addCatalogBoard(current.tabs, tabId, definition);
      setSelectedBoardId(result.boardId);
      return { ...current, tabs: result.tabs, active_tab_id: tabId };
    });
    setMode("edit");
  }

  return {
    updateDraft,
    handleActiveTab,
    handleReorderTabs,
    handleMoveBoard,
    handleLayoutChange,
    handleUpdateBoard,
    handleRemoveBoard,
    handleToggleHidden,
    handleToggleFavorite,
    handleDuplicateBoard,
    handleAddTab,
    handleAddBoard,
  };
}
