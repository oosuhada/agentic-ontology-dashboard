import { Copy, Eye, EyeOff, GripVertical, Maximize2, Minimize2, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import type { DashboardBoard, DashboardMode } from "../../features/dashboard/types";

interface BoardFrameProps {
  board: DashboardBoard;
  mode: DashboardMode;
  selected: boolean;
  affected: boolean;
  fullscreen: boolean;
  children: ReactNode;
  onSelect: () => void;
  onToggleHidden: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onFullscreen: () => void;
}

export function BoardFrame({
  board,
  mode,
  selected,
  affected,
  fullscreen,
  children,
  onSelect,
  onToggleHidden,
  onDuplicate,
  onRemove,
  onFullscreen,
}: BoardFrameProps) {
  return (
    <article
      data-grid-x={board.layout?.x ?? ""}
      data-grid-y={board.layout?.y ?? ""}
      data-grid-w={board.layout?.w ?? board.width}
      data-grid-h={board.layout?.h ?? ""}
      className={[
        "dashboard-board-frame",
        "fd-board-frame",
        board.hidden ? "is-hidden" : "",
        selected ? "is-selected" : "",
        affected ? "is-affected" : "",
        fullscreen ? "is-fullscreen" : "",
      ].filter(Boolean).join(" ")}
      onClick={onSelect}
    >
      <header className="dashboard-board-header fd-board-frame__header">
        <button
          type="button"
          className="dashboard-board-drag-handle"
          aria-label={`${board.title} 이동`}
          title={mode === "edit" ? "드래그하여 이동" : "View mode"}
          disabled={mode !== "edit"}
        >
          <GripVertical size={14} />
        </button>
        <div className="dashboard-board-title fd-board-frame__title">
          <span>{board.custom ? "PERSONAL BOARD" : "GOVERNED BOARD"}</span>
          <strong>{board.title}</strong>
        </div>
        <div className="dashboard-board-actions fd-board-frame__actions">
          {affected ? <span className="affected-chip">필터 반영</span> : null}
          <button
            type="button"
            aria-label={fullscreen ? "전체 화면 닫기" : `${board.title} 전체 화면`}
            title={fullscreen ? "전체 화면 닫기" : "전체 화면"}
            onClick={(event) => {
              event.stopPropagation();
              onFullscreen();
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
                  onToggleHidden();
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
                  onDuplicate();
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
                  onRemove();
                }}
              >
                <Trash2 size={13} />
              </button>
            </>
          ) : null}
        </div>
      </header>
      {board.hidden && mode === "edit" ? <div className="hidden-board-label">View 모드에서는 숨겨집니다.</div> : null}
      <div className="dashboard-board-content fd-board-frame__content">{children}</div>
    </article>
  );
}
