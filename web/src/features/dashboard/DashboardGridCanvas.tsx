import { useMemo, type ReactNode } from "react";
import { Copy, Eye, EyeOff, GripVertical, Maximize2, Minimize2, Trash2 } from "lucide-react";
import {
  ResponsiveGridLayout,
  useContainerWidth,
  type Layout,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import type { DashboardBoard, DashboardMode, DashboardTab } from "./types";
import { legacyBoardToGridLayout } from "./gridLayout";

export interface DashboardGridCanvasProps {
  tab: DashboardTab | null;
  mode: DashboardMode;
  selectedBoardId: string | null;
  fullscreenBoardId: string | null;
  affectedBoardIds: string[];
  renderBoard: (board: DashboardBoard) => ReactNode;
  onSelectBoard: (boardId: string) => void;
  onLayoutChange: (tabId: string, layout: Layout) => void;
  onMoveBoard: (boardId: string, targetTabId: string, targetBoardId?: string) => void;
  onDuplicateBoard: (boardId: string) => void;
  onRemoveBoard: (boardId: string) => void;
  onToggleHidden: (boardId: string, hidden: boolean) => void;
  onFullscreen: (boardId: string | null) => void;
}

const BREAKPOINTS = { lg: 500, md: 480, sm: 0 } as const;
const COLS = { lg: 12, md: 8, sm: 1 } as const;

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
    return {
      i: board.id,
      x: layout.x,
      y: layout.y,
      w: layout.w,
      h: layout.h,
      minW: layout.min_w ?? 2,
      minH: layout.min_h ?? 1,
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
  onSelectBoard,
  onLayoutChange,
  onDuplicateBoard,
  onRemoveBoard,
  onToggleHidden,
  onFullscreen,
}: DashboardGridCanvasProps) {
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1180 });
  const visibleBoards = useMemo(
    () => tab?.boards.filter((board) => mode === "edit" || !board.hidden) ?? [],
    [mode, tab],
  );
  const layouts = useMemo(() => responsiveLayouts(visibleBoards), [visibleBoards]);

  if (!tab) return <div className="dashboard-empty-canvas">표시할 Dashboard 탭이 없습니다.</div>;

  return (
    <section ref={containerRef} className={`dashboard-board-canvas rgl-canvas mode-${mode}`} aria-label={`${tab.title} board canvas`}>
      {visibleBoards.length === 0 ? (
        <div className="dashboard-empty-canvas">
          <strong>이 탭에 표시할 board가 없습니다.</strong>
          <p>편집 모드에서 Board Catalog를 열어 board를 추가하세요.</p>
        </div>
      ) : null}

      {mounted && visibleBoards.length ? (
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
          resizeConfig={{ enabled: mode === "edit", handles: ["se", "e", "s"] }}
          onDragStop={(layout, _oldItem, newItem) => mode === "edit" && onLayoutChange(tab.id, mergeChangedItem(layout, newItem))}
          onResizeStop={(layout, _oldItem, newItem) => mode === "edit" && onLayoutChange(tab.id, mergeChangedItem(layout, newItem))}
        >
          {visibleBoards.map((board) => {
            const fullscreen = fullscreenBoardId === board.id;
            const selected = selectedBoardId === board.id;
            const affected = affectedBoardIds.includes(board.id);
            return (
              <article
                key={board.id}
                data-grid-x={board.layout?.x ?? ""}
                data-grid-y={board.layout?.y ?? ""}
                data-grid-w={board.layout?.w ?? board.width}
                data-grid-h={board.layout?.h ?? ""}
                className={[
                  "dashboard-board-frame",
                  board.hidden ? "is-hidden" : "",
                  selected ? "is-selected" : "",
                  affected ? "is-affected" : "",
                  fullscreen ? "is-fullscreen" : "",
                ].filter(Boolean).join(" ")}
                onClick={() => onSelectBoard(board.id)}
              >
                <header className="dashboard-board-header">
                  <button
                    type="button"
                    className="dashboard-board-drag-handle"
                    aria-label={`${board.title} 이동`}
                    title={mode === "edit" ? "드래그하여 이동" : "View mode"}
                    disabled={mode !== "edit"}
                  >
                    <GripVertical size={14} />
                  </button>
                  <div className="dashboard-board-title">
                    <span>{board.custom ? "PERSONAL BOARD" : "GOVERNED BOARD"}</span>
                    <strong>{board.title}</strong>
                  </div>
                  <div className="dashboard-board-actions">
                    {affected ? <span className="affected-chip">필터 반영</span> : null}
                    <button
                      type="button"
                      aria-label={fullscreen ? "전체 화면 닫기" : `${board.title} 전체 화면`}
                      title={fullscreen ? "전체 화면 닫기" : "전체 화면"}
                      onClick={(event) => {
                        event.stopPropagation();
                        onFullscreen(fullscreen ? null : board.id);
                      }}
                    >
                      {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                    </button>
                    {mode === "edit" ? (
                      <>
                        <button
                          type="button"
                          aria-label={board.hidden ? "표시" : "숨김"}
                          title={board.hidden ? "Board 표시" : "Board 숨김"}
                          onClick={(event) => {
                            event.stopPropagation();
                            onToggleHidden(board.id, !board.hidden);
                          }}
                        >
                          {board.hidden ? <Eye size={13} /> : <EyeOff size={13} />}
                        </button>
                        <button
                          type="button"
                          aria-label="복제"
                          title="Board 복제"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDuplicateBoard(board.id);
                          }}
                        >
                          <Copy size={13} />
                        </button>
                        <button
                          type="button"
                          aria-label="삭제"
                          disabled={board.mandatory}
                          title={board.mandatory ? "필수 board는 삭제할 수 없습니다." : "Board 삭제"}
                          onClick={(event) => {
                            event.stopPropagation();
                            onRemoveBoard(board.id);
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    ) : null}
                  </div>
                </header>
                {board.hidden && mode === "edit" ? <div className="hidden-board-label">View 모드에서는 숨겨집니다.</div> : null}
                <div className="dashboard-board-content">{renderBoard(board)}</div>
              </article>
            );
          })}
        </ResponsiveGridLayout>
      ) : null}
    </section>
  );
}
