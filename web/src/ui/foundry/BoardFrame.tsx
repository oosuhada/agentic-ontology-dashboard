import { Copy, Eye, EyeOff, GripVertical, Maximize2, Minimize2, Star, Trash2 } from "lucide-react";
import { forwardRef, type CSSProperties, type ReactNode } from "react";
import type { DashboardBoard, DashboardMode } from "../../features/dashboard/types";

interface BoardFrameProps {
  board: DashboardBoard;
  mode: DashboardMode;
  selected: boolean;
  affected: boolean;
  fullscreen: boolean;
  favorite: boolean;
  resizeLabel?: string | null;
  headerActions?: ReactNode;
  children: ReactNode;
  onSelect: () => void;
  onToggleHidden: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onToggleFavorite: () => void;
  onFullscreen: () => void;
  className?: string;
  style?: CSSProperties;
}

export const BoardFrame = forwardRef<HTMLElement, BoardFrameProps>(function BoardFrame({
  board,
  mode,
  selected,
  affected,
  fullscreen,
  favorite,
  resizeLabel,
  headerActions,
  children,
  onSelect,
  onToggleHidden,
  onDuplicate,
  onRemove,
  onToggleFavorite,
  onFullscreen,
  className = "",
  style,
}, ref) {
  return (
    <article
      ref={ref}
      style={style}
      data-grid-x={board.layout?.x ?? ""}
      data-grid-y={board.layout?.y ?? ""}
      data-grid-w={board.layout?.w ?? board.width}
      data-grid-h={board.layout?.h ?? ""}
      data-grid-min-w={board.layout?.min_w ?? 1}
      data-grid-min-h={board.layout?.min_h ?? 1}
      data-grid-max-w={board.layout?.max_w ?? 12}
      data-grid-max-h={board.layout?.max_h ?? 12}
      data-board-id={board.id}
      data-favorite={favorite ? "true" : "false"}
      className={[
        "dashboard-board-frame",
        "fd-board-frame",
        board.hidden ? "is-hidden" : "",
        selected ? "is-selected" : "",
        affected ? "is-affected" : "",
        favorite ? "is-favorite" : "",
        mode === "edit" ? "is-arranging" : "",
        fullscreen ? "is-fullscreen" : "",
        className,
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
          {headerActions}
          <button
            type="button"
            className={`dashboard-board-favorite ${favorite ? "active" : ""}`}
            aria-label={favorite ? `${board.title} 즐겨찾기 해제` : `${board.title} 즐겨찾기`}
            aria-pressed={favorite}
            title={favorite ? "즐겨찾기 해제" : "즐겨찾기"}
            onClick={(event) => {
              event.stopPropagation();
              onToggleFavorite();
            }}
          >
            <Star size={13} fill={favorite ? "currentColor" : "none"} />
          </button>
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
      {resizeLabel ? <output className="dashboard-board-resize-label">{resizeLabel}</output> : null}
      <div className="dashboard-board-content fd-board-frame__content">{children}</div>
    </article>
  );
});
