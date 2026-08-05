import { ListFilter, Rows3, Star } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BoardFrame } from "../../ui/foundry/BoardFrame";
import { useI18n } from "../../ui/i18n/I18nProvider";
import {
  ResponsiveGridLayout,
  useContainerWidth,
  type Layout,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout";
import type { DashboardBoard, DashboardMode, DashboardTab } from "./types";
import { useDashboardArrangeMode } from "./dashboardArrange";
import { legacyBoardToGridLayout } from "./gridLayout";
import { localizedBoardTitle } from "./dashboardLocalization";
import type { BoardContentMetric } from "./layoutOptimizer";

export interface DashboardGridCanvasProps {
  tab: DashboardTab | null;
  mode: DashboardMode;
  selectedBoardId: string | null;
  fullscreenBoardId: string | null;
  affectedBoardIds: string[];
  renderBoard: (board: DashboardBoard) => ReactNode;
  renderBoardHeader?: (board: DashboardBoard) => ReactNode;
  onSelectBoard: (boardId: string) => void;
  onLayoutChange: (tabId: string, layout: Layout) => void;
  onMoveBoard: (boardId: string, targetTabId: string, targetBoardId?: string) => void;
  onDuplicateBoard: (boardId: string) => void;
  onRemoveBoard: (boardId: string) => void;
  onToggleHidden: (boardId: string, hidden: boolean) => void;
  onFullscreen: (boardId: string | null) => void;
  onEnterArrange: () => void;
  onToggleFavorite: (boardId: string) => void;
  onContentMetricsChange?: (metrics: BoardContentMetric[]) => void;
  saving?: boolean;
}

const BREAKPOINTS = { lg: 500, md: 480, sm: 0 } as const;
const COLS = { lg: 12, md: 8, sm: 1 } as const;
const MIN_HEIGHT_UNITS_BY_DEFINITION: Record<string, number> = {
  "operations-kpi": 2,
  "fde-workspace-overview": 5,
  "fde-ontology-registry": 3,
  "fde-deployment-checklist": 5,
  "fde-diagnostic-events": 4,
};

function mergeChangedItem(layout: Layout, changedItem: LayoutItem | null): Layout {
  if (!changedItem) return layout;
  let found = false;
  const merged = layout.map((item) => {
    if (item.i !== changedItem.i) return item;
    found = true;
    return { ...item, ...changedItem };
  });
  return found ? merged : [...merged, changedItem];
}

function responsiveLayouts(boards: DashboardBoard[]): ResponsiveLayouts<"lg" | "md" | "sm"> {
  const lg: Layout = boards.map((board, index) => {
    const layout = legacyBoardToGridLayout(board, index);
    const minimumHeight = Math.max(
      layout.min_h ?? 1,
      MIN_HEIGHT_UNITS_BY_DEFINITION[board.definition_id] ?? 1,
    );
    return {
      i: board.id,
      x: layout.x,
      y: layout.y,
      w: layout.w,
      h: Math.max(layout.h, minimumHeight),
      minW: layout.min_w ?? 2,
      minH: minimumHeight,
      maxW: layout.max_w ?? 12,
      maxH: layout.max_h ?? 12,
      static: false,
    };
  });
  const md: Layout = lg.map((item, index) => ({
    ...item,
    x: item.w >= 8 ? 0 : (index % 2) * 4,
    y: Math.floor(index / 2) * Math.max(2, item.h),
    w: item.w >= 8 ? 8 : 4,
    maxW: 8,
  }));
  const sm: Layout = lg.map((item, index) => ({
    ...item,
    x: 0,
    y: index * Math.max(2, item.h),
    w: 1,
    minW: 1,
    maxW: 1,
  }));
  return { lg, md, sm };
}

export function DashboardGridCanvas({
  tab,
  mode,
  selectedBoardId,
  fullscreenBoardId,
  affectedBoardIds,
  renderBoard,
  renderBoardHeader,
  onSelectBoard,
  onLayoutChange,
  onDuplicateBoard,
  onRemoveBoard,
  onToggleHidden,
  onFullscreen,
  onEnterArrange,
  onToggleFavorite,
  onContentMetricsChange,
  saving = false,
}: DashboardGridCanvasProps) {
  const { t } = useI18n();
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1180 });
  const canvasRef = useRef<HTMLElement | null>(null);
  const [focusMode, setFocusMode] = useState<"all" | "focus" | "favorites" | "details">("all");
  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({});
  const availableBoards = useMemo(() => tab?.boards.filter((board) => mode === "edit" || !board.hidden) ?? [], [mode, tab]);
  const collapsedBoardIds = useMemo(() => {
    const next = new Set(tab?.boards.filter((board) => board.settings.collapsed_default === true).map((board) => board.id) ?? []);
    for (const [boardId, collapsed] of Object.entries(collapseOverrides)) {
      if (collapsed) next.add(boardId); else next.delete(boardId);
    }
    return next;
  }, [collapseOverrides, tab]);
  const visibleBoards = useMemo(() => {
    if (mode === "edit" || focusMode === "all") return availableBoards;
    if (focusMode === "favorites") return availableBoards.filter((board) => board.settings.favorite === true);
    if (focusMode === "focus") return availableBoards.filter((board) => board.settings.information_section === "focus" || (!board.settings.information_section && (board.mandatory || board.order < 3)));
    return availableBoards.filter((board) => board.settings.information_section !== "focus" && (!board.mandatory || board.order >= 3));
  }, [availableBoards, focusMode, mode]);
  const collapsedBoards = useMemo(() => visibleBoards.filter((board) => collapsedBoardIds.has(board.id)), [collapsedBoardIds, visibleBoards]);
  const gridBoards = useMemo(() => visibleBoards.filter((board) => !collapsedBoardIds.has(board.id)), [collapsedBoardIds, visibleBoards]);
  const layouts = useMemo(() => responsiveLayouts(gridBoards), [gridBoards]);
  const [resizePreview, setResizePreview] = useState<{ boardId: string; width: number; height: number } | null>(null);
  const { phase, dispatch, longPressHandlers } = useDashboardArrangeMode({ mode, onEnter: onEnterArrange });

  const assignCanvasRef = useCallback((node: HTMLElement | null) => {
    canvasRef.current = node;
    containerRef.current = node as HTMLDivElement | null;
  }, [containerRef]);

  const reportContentMetrics = useCallback(() => {
    if (!canvasRef.current || !onContentMetricsChange) return;
    const metrics = Array.from(canvasRef.current.querySelectorAll<HTMLElement>(".dashboard-board-frame"))
      .map((frame) => {
        const content = frame.querySelector<HTMLElement>(".dashboard-board-content") ?? frame;
        return {
          boardId: frame.dataset.boardId ?? "",
          contentHeight: Math.max(content.scrollHeight, content.getBoundingClientRect().height),
          contentWidth: Math.max(content.scrollWidth, content.getBoundingClientRect().width),
          viewportHeight: content.getBoundingClientRect().height,
        };
      })
      .filter((metric) => metric.boardId);
    onContentMetricsChange(metrics);
  }, [onContentMetricsChange]);

  useEffect(() => {
    dispatch({ type: saving ? "SAVE_START" : "SAVE_END" });
  }, [dispatch, saving]);

  useEffect(() => {
    setFocusMode("all");
    setCollapseOverrides({});
  }, [tab?.id]);

  useEffect(() => {
    if (!canvasRef.current || !onContentMetricsChange || typeof ResizeObserver === "undefined") return undefined;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(reportContentMetrics);
    });
    observer.observe(canvasRef.current);
    canvasRef.current.querySelectorAll(".dashboard-board-content").forEach((element) => observer.observe(element));
    frame = requestAnimationFrame(reportContentMetrics);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [gridBoards, onContentMetricsChange, reportContentMetrics]);

  function toggleCollapsed(boardId: string) {
    setCollapseOverrides((current) => ({ ...current, [boardId]: !collapsedBoardIds.has(boardId) }));
  }

  if (!tab) return <div className="dashboard-empty-canvas">{t("dashboard.emptyTabs")}</div>;

  return (
    <section
      ref={assignCanvasRef}
      className={`dashboard-board-canvas rgl-canvas mode-${mode} arrange-${phase}`}
      data-arrange-state={phase}
      aria-label={`${tab.title} board canvas`}
      {...longPressHandlers}
    >
      {mode === "view" && availableBoards.length ? (
        <div className="dashboard-focus-toolbar" role="toolbar" aria-label="Dashboard focus view">
          <div className="dashboard-focus-segments" role="group" aria-label="Board visibility">
            <button type="button" className={focusMode === "all" ? "active" : ""} onClick={() => setFocusMode("all")}><Rows3 size={12} />{t("dashboard.focus.all")}</button>
            <button type="button" className={focusMode === "focus" ? "active" : ""} onClick={() => setFocusMode("focus")}><ListFilter size={12} />{t("dashboard.focus.focus")}</button>
            <button type="button" className={focusMode === "favorites" ? "active" : ""} onClick={() => setFocusMode("favorites")}><Star size={12} />{t("dashboard.focus.favorites")}</button>
            <button type="button" className={focusMode === "details" ? "active" : ""} onClick={() => setFocusMode("details")}>{t("dashboard.focus.details")}</button>
          </div>
          <label>{t("dashboard.focus.jump")}
            <select defaultValue="" onChange={(event) => {
              const boardId = event.target.value;
              if (!boardId) return;
              document.querySelector<HTMLElement>(`[data-board-id="${CSS.escape(boardId)}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
              event.target.value = "";
            }}>
              <option value="">—</option>
              {visibleBoards.map((board) => <option key={board.id} value={board.id}>{localizedBoardTitle(board, t)}</option>)}
            </select>
          </label>
        </div>
      ) : null}
      {mode === "edit" ? <div className="dashboard-arrange-hint" role="status">{t("dashboard.arrangeHint")}</div> : null}
      {visibleBoards.length === 0 ? (
        <div className="dashboard-empty-canvas">
          <strong>{t("dashboard.focus.noBoards")}</strong>
          <button type="button" className="secondary" onClick={() => setFocusMode("all")}>{t("dashboard.focus.showAll")}</button>
        </div>
      ) : null}

      {collapsedBoards.length ? (
        <div className="dashboard-collapsed-board-tray" aria-label={t("dashboard.collapsedBoards")}>
          {collapsedBoards.map((board) => (
            <BoardFrame
              key={board.id}
              board={board}
              mode={mode}
              selected={selectedBoardId === board.id}
              affected={affectedBoardIds.includes(board.id)}
              fullscreen={false}
              favorite={board.settings.favorite === true}
              collapsed
              headerActions={renderBoardHeader?.(board)}
              onSelect={() => onSelectBoard(board.id)}
              onToggleHidden={() => onToggleHidden(board.id, !board.hidden)}
              onDuplicate={() => onDuplicateBoard(board.id)}
              onRemove={() => onRemoveBoard(board.id)}
              onToggleFavorite={() => onToggleFavorite(board.id)}
              onToggleCollapsed={() => toggleCollapsed(board.id)}
              onFullscreen={() => onFullscreen(board.id)}
            >
              {null}
            </BoardFrame>
          ))}
        </div>
      ) : null}

      {mounted && gridBoards.length ? (
        <ResponsiveGridLayout<"lg" | "md" | "sm">
          width={width}
          breakpoint={mode === "edit" ? "lg" : undefined}
          breakpoints={BREAKPOINTS}
          cols={COLS}
          layouts={layouts}
          rowHeight={82}
          margin={{ lg: [12, 12], md: [10, 10], sm: [8, 8] }}
          containerPadding={{ lg: [0, 0], md: [0, 0], sm: [0, 0] }}
          dragConfig={{
            enabled: mode === "edit",
            bounded: true,
            handle: ".dashboard-board-drag-handle",
            cancel: "button,input,select,textarea,a,[role='button']",
            threshold: 3,
          }}
          resizeConfig={{ enabled: mode === "edit", handles: ["n", "s", "e", "w", "ne", "nw", "se", "sw"] }}
          onDragStart={() => dispatch({ type: "DRAG_START" })}
          onDragStop={(layout, _oldItem, newItem) => {
            dispatch({ type: "DRAG_STOP" });
            if (mode === "edit") onLayoutChange(tab.id, mergeChangedItem(layout, newItem));
          }}
          onResizeStart={(_layout, _oldItem, newItem) => {
            dispatch({ type: "RESIZE_START" });
            if (!newItem) return;
            setResizePreview({ boardId: newItem.i, width: newItem.w, height: newItem.h });
          }}
          onResize={(_layout, _oldItem, newItem) => {
            if (!newItem) return;
            setResizePreview({ boardId: newItem.i, width: newItem.w, height: newItem.h });
          }}
          onResizeStop={(layout, _oldItem, newItem) => {
            dispatch({ type: "RESIZE_STOP" });
            setResizePreview(null);
            if (mode === "edit") onLayoutChange(tab.id, mergeChangedItem(layout, newItem));
          }}
        >
          {gridBoards.map((board) => {
            const fullscreen = fullscreenBoardId === board.id;
            const selected = selectedBoardId === board.id;
            const affected = affectedBoardIds.includes(board.id);
            return (
              <BoardFrame
                key={board.id}
                board={board}
                mode={mode}
                selected={selected}
                affected={affected}
                fullscreen={fullscreen}
                favorite={board.settings.favorite === true}
                collapsed={collapsedBoardIds.has(board.id)}
                headerActions={renderBoardHeader?.(board)}
                resizeLabel={resizePreview?.boardId === board.id ? `${resizePreview.width} columns × ${resizePreview.height} rows` : null}
                onSelect={() => onSelectBoard(board.id)}
                onToggleHidden={() => onToggleHidden(board.id, !board.hidden)}
                onDuplicate={() => onDuplicateBoard(board.id)}
                onRemove={() => onRemoveBoard(board.id)}
                onToggleFavorite={() => onToggleFavorite(board.id)}
                onToggleCollapsed={() => toggleCollapsed(board.id)}
                onFullscreen={() => onFullscreen(fullscreen ? null : board.id)}
              >
                {renderBoard(board)}
              </BoardFrame>
            );
          })}
        </ResponsiveGridLayout>
      ) : null}
    </section>
  );
}
