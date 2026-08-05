import { ChevronDown, ChevronRight, Copy, Eye, EyeOff, GripVertical, Maximize2, Minimize2, MoreHorizontal, Star, Trash2 } from "lucide-react";
import { forwardRef, type CSSProperties, type ReactNode } from "react";
import type { DashboardBoard, DashboardMode } from "../../features/dashboard/types";
import { localizedBoardTitle } from "../../features/dashboard/dashboardLocalization";
import { useI18n } from "../i18n/I18nProvider";

interface BoardFrameProps {
  board: DashboardBoard;
  mode: DashboardMode;
  selected: boolean;
  affected: boolean;
  fullscreen: boolean;
  favorite: boolean;
  collapsed?: boolean;
  resizeLabel?: string | null;
  headerActions?: ReactNode;
  children: ReactNode;
  onSelect: () => void;
  onToggleHidden: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onToggleFavorite: () => void;
  onToggleCollapsed?: () => void;
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
  collapsed = false,
  resizeLabel,
  headerActions,
  children,
  onSelect,
  onToggleHidden,
  onDuplicate,
  onRemove,
  onToggleFavorite,
  onToggleCollapsed,
  onFullscreen,
  className = "",
  style,
}, ref) {
  const { t } = useI18n();
  const layoutMode = typeof board.settings.layout_mode === "string" ? board.settings.layout_mode : "manual";
  const title = localizedBoardTitle(board, t);
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
      data-definition-id={board.definition_id}
      data-favorite={favorite ? "true" : "false"}
      data-layout-mode={layoutMode}
      className={[
        "dashboard-board-frame",
        "fd-board-frame",
        board.hidden ? "is-hidden" : "",
        selected ? "is-selected" : "",
        affected ? "is-affected" : "",
        favorite ? "is-favorite" : "",
        mode === "edit" ? "is-arranging" : "",
        fullscreen ? "is-fullscreen" : "",
        collapsed ? "is-collapsed" : "",
        className,
      ].filter(Boolean).join(" ")}
      onClick={onSelect}
    >
      <header className="dashboard-board-header fd-board-frame__header">
        <button
          type="button"
          className="dashboard-board-drag-handle"
          aria-label={`${title} ${t("dashboard.moveBoard")}`}
          title={mode === "edit" ? t("dashboard.dragToMove") : t("dashboard.viewMode")}
          disabled={mode !== "edit"}
        >
          <GripVertical size={14} />
        </button>
        <div className="dashboard-board-title fd-board-frame__title">
          <span>{board.custom ? t("dashboard.personalBoard").toUpperCase() : t("dashboard.governedBoard").toUpperCase()}</span>
          <strong>{title}</strong>
        </div>
        <div className="dashboard-board-actions fd-board-frame__actions">
          {mode === "edit" ? <span className={`layout-mode-chip mode-${layoutMode}`}>{layoutMode === "ai" ? t("dashboard.layoutModeAi") : layoutMode === "auto" ? t("dashboard.layoutModeAuto") : t("dashboard.layoutModeManual")}</span> : null}
          {affected ? <span className="affected-chip">{t("dashboard.filterApplied")}</span> : null}
          {headerActions}
          {mode === "view" && onToggleCollapsed ? (
            <button
              type="button"
              aria-label={collapsed ? `${title} ${t("dashboard.expandBoard")}` : `${title} ${t("dashboard.collapseBoard")}`}
              aria-expanded={!collapsed}
              title={collapsed ? t("dashboard.expandBoard") : t("dashboard.collapseBoard")}
              onClick={(event) => { event.stopPropagation(); onToggleCollapsed(); }}
            >
              {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
            </button>
          ) : null}
          {mode === "view" ? (
            <button
              type="button"
              className={`dashboard-board-favorite ${favorite ? "active" : ""}`}
              aria-label={favorite ? `${title} ${t("dashboard.unfavorite")}` : `${title} ${t("dashboard.favorite")}`}
              aria-pressed={favorite}
              title={favorite ? t("dashboard.unfavorite") : t("dashboard.favorite")}
              onClick={(event) => {
                event.stopPropagation();
                onToggleFavorite();
              }}
            >
              <Star size={13} fill={favorite ? "currentColor" : "none"} />
            </button>
          ) : null}
          <button
            type="button"
            aria-label={fullscreen ? t("dashboard.closeFullscreen") : `${title} ${t("dashboard.fullscreen")}`}
            title={fullscreen ? t("dashboard.closeFullscreen") : t("dashboard.fullscreen")}
            onClick={(event) => {
              event.stopPropagation();
              onFullscreen();
            }}
          >
            {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
          {mode === "edit" ? (
            <details className="dashboard-board-more" onClick={(event) => event.stopPropagation()}>
              <summary aria-label={`${title} ${t("dashboard.moreActions")}`} title={t("dashboard.moreActions")}><MoreHorizontal size={14} /></summary>
              <div role="menu" aria-label={`${title} ${t("dashboard.moreActions")}`}>
                <button type="button" role="menuitem" onClick={(event) => { onToggleFavorite(); event.currentTarget.closest("details")?.removeAttribute("open"); }}><Star size={13} fill={favorite ? "currentColor" : "none"} />{favorite ? t("dashboard.unfavorite") : t("dashboard.favorite")}</button>
                <button type="button" role="menuitem" onClick={(event) => { onToggleHidden(); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{board.hidden ? <Eye size={13} /> : <EyeOff size={13} />}{board.hidden ? t("common.show") : t("common.hide")}</button>
                <button type="button" role="menuitem" onClick={(event) => { onDuplicate(); event.currentTarget.closest("details")?.removeAttribute("open"); }}><Copy size={13} />{t("common.duplicate")}</button>
                <button type="button" role="menuitem" className="intent-danger" disabled={board.mandatory} title={board.mandatory ? t("dashboard.requiredBoardDelete") : t("common.delete")} onClick={(event) => { onRemove(); event.currentTarget.closest("details")?.removeAttribute("open"); }}><Trash2 size={13} />{t("common.delete")}</button>
              </div>
            </details>
          ) : null}
        </div>
      </header>
      {board.hidden && mode === "edit" ? <div className="hidden-board-label">{t("dashboard.hiddenInView")}</div> : null}
      {resizeLabel ? <output className="dashboard-board-resize-label">{resizeLabel}</output> : null}
      {!collapsed ? <div className="dashboard-board-content fd-board-frame__content">{children}</div> : null}
    </article>
  );
});
