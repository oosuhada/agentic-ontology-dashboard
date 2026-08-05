import type { BoardCatalogDefinition, BoardVisualizationRuntime, BoardWidth, DashboardBoard, DashboardTab } from "./types";
import { VisualizationInspector } from "./visualization/VisualizationInspector";
import { useI18n } from "../../ui/i18n/I18nProvider";

interface BoardInspectorProps {
  board: DashboardBoard | null;
  definition: BoardCatalogDefinition | null;
  tabs: DashboardTab[];
  currentTabId: string | null;
  visualizationRuntime?: BoardVisualizationRuntime | null;
  workspaceId: string;
  dashboardId: string;
  onUpdate: (update: Partial<DashboardBoard>) => void;
  onMove: (targetTabId: string) => void;
  onClose: () => void;
}

export function BoardInspector({
  board,
  definition,
  tabs,
  currentTabId,
  visualizationRuntime = null,
  workspaceId,
  dashboardId,
  onUpdate,
  onMove,
  onClose,
}: BoardInspectorProps) {
  const { t } = useI18n();
  if (!board || !definition) {
    return (
      <aside className="dashboard-inspector">
        <span className="section-label">{t("inspector.title")}</span>
        <div className="inspector-empty">
          <strong>{t("inspector.selectBoard")}</strong>
          <p>{t("inspector.selectBoardDetail")}</p>
        </div>
      </aside>
    );
  }

  const widthOptions = Array.from(
    { length: definition.maximum_width - definition.minimum_width + 1 },
    (_, index) => definition.minimum_width + index,
  ) as BoardWidth[];
  const layout = board.layout ?? { x: 0, y: board.order * 2, w: board.width, h: Number(board.settings.height_units ?? 2) };

  return (
    <aside className="dashboard-inspector">
      <header className="inspector-header">
        <div><span className="section-label">{t("inspector.resource").toUpperCase()}</span><strong>{definition.display_name}</strong><small>{currentTabId ?? "dashboard"} / {board.id}</small></div>
        <button type="button" onClick={onClose}>{t("common.close")}</button>
      </header>

      <nav className="dashboard-inspector-nav" aria-label="Board inspector sections">
        <a href="#board-configuration">{t("inspector.configuration")}</a><a href="#board-layout">{t("inspector.layout")}</a>{visualizationRuntime ? <a href="#board-visualization">{t("inspector.visualization")}</a> : null}<a href="#board-contract">{t("inspector.dataContract")}</a><a href="#board-runtime">{t("inspector.runtime")}</a>
      </nav>

      <div className="inspector-definition" id="board-configuration">
        <span>{definition.category.toUpperCase()}</span>
        <p>{definition.description}</p>
        <code>{definition.id}</code>
      </div>

      <label className="context-field" id="board-layout">
        {t("inspector.boardTitle")}
        <input value={board.title} onChange={(event) => onUpdate({ title: event.target.value })} />
      </label>

      <label className="context-field">
        {t("inspector.layoutWidth")}
        <select
          value={layout.w}
          onChange={(event) => {
            const width = Number(event.target.value) as BoardWidth;
            onUpdate({ width, layout: { ...layout, w: width, x: Math.min(layout.x, 12 - width) }, settings: { ...board.settings, layout_mode: "manual", layout_lock: true } });
          }}
        >
          {widthOptions.map((width) => (
            <option key={width} value={width}>{width} / 12 {width === 12 ? "· Full" : width === 8 ? "· 2/3" : width === 6 ? "· Half" : width === 4 ? "· Third" : ""}</option>
          ))}
        </select>
      </label>

      <label className="context-field">
        {t("inspector.boardHeight")}
        <select
          value={String(layout.h)}
          onChange={(event) => {
            const height = Number(event.target.value);
            onUpdate({ layout: { ...layout, h: height }, settings: { ...board.settings, height_units: String(height), layout_mode: "manual", layout_lock: true } });
          }}
        >
          <option value="1">Compact · 1 row</option>
          <option value="2">Standard · 2 rows</option>
          <option value="3">Tall · 3 rows</option>
          <option value="4">Analysis · 4 rows</option>
          <option value="5">Data grid · 5 rows</option>
          <option value="6">Deep workbench · 6 rows</option>
          <option value="7">Extended · 7 rows</option>
          <option value="8">Maximum preset · 8 rows</option>
        </select>
      </label>

      <label className="context-field">
        {t("inspector.layoutMode")}
        <select
          value={board.settings.layout_lock === true || board.settings.layout_mode === "manual" ? "manual" : "auto"}
          onChange={(event) => onUpdate({
            settings: {
              ...board.settings,
              layout_mode: event.target.value,
              layout_lock: event.target.value === "manual",
            },
          })}
        >
          <option value="auto">{t("inspector.layoutAuto")}</option>
          <option value="manual">{t("inspector.layoutManual")}</option>
        </select>
      </label>

      <div className="inspector-layout-grid">
        <label className="context-field">X<input type="number" min={0} max={Math.max(0, 12 - layout.w)} value={layout.x} onChange={(event) => onUpdate({ layout: { ...layout, x: Math.max(0, Math.min(12 - layout.w, Number(event.target.value))) }, settings: { ...board.settings, layout_mode: "manual", layout_lock: true } })} /></label>
        <label className="context-field">Y<input type="number" min={0} value={layout.y} onChange={(event) => onUpdate({ layout: { ...layout, y: Math.max(0, Number(event.target.value)) }, settings: { ...board.settings, layout_mode: "manual", layout_lock: true } })} /></label>
        <label className="context-field">W<input type="number" min={definition.minimum_width} max={definition.maximum_width} value={layout.w} onChange={(event) => { const width = Math.max(definition.minimum_width, Math.min(definition.maximum_width, Number(event.target.value))); onUpdate({ width, layout: { ...layout, w: width, x: Math.min(layout.x, 12 - width) }, settings: { ...board.settings, layout_mode: "manual", layout_lock: true } }); }} /></label>
        <label className="context-field">H<input type="number" min={1} max={12} value={layout.h} onChange={(event) => { const height = Math.max(1, Math.min(12, Number(event.target.value))); onUpdate({ layout: { ...layout, h: height }, settings: { ...board.settings, height_units: String(height), layout_mode: "manual", layout_lock: true } }); }} /></label>
      </div>

      <label className="context-field">
        {t("inspector.placementTab")}
        <select value={currentTabId ?? ""} onChange={(event) => onMove(event.target.value)}>
          {tabs.map((tab) => <option key={tab.id} value={tab.id}>{tab.title}</option>)}
        </select>
      </label>

      <label className="inspector-checkbox">
        <input
          type="checkbox"
          checked={board.hidden}
          disabled={board.mandatory}
          onChange={(event) => onUpdate({ hidden: event.target.checked })}
        />
        {t("inspector.hideInView")}
      </label>
      {board.mandatory ? <small className="mandatory-note">{t("inspector.requiredBoard")}</small> : null}

      {Object.keys(definition.binding_schema).length ? (
        <section className="inspector-section" id="board-contract">
          <span className="section-label">Bindings</span>
          {Object.entries(definition.binding_schema).map(([bindingId, valueType]) => (
            <label key={bindingId} className="context-field">
              {bindingId} <small>{valueType}</small>
              <input
                value={String(board.bindings[bindingId] ?? "")}
                onChange={(event) => onUpdate({ bindings: { ...board.bindings, [bindingId]: event.target.value } })}
                placeholder={t("inspector.fixedOrEmpty")}
              />
            </label>
          ))}
        </section>
      ) : null}

      {board.source?.kind === "analysis_board" ? (
        <section className="inspector-section">
          <span className="section-label">Analysis Source</span>
          <label className="context-field">Analysis ID<input value={board.source.analysis_id} readOnly /></label>
          <label className="context-field">Node ID<input value={board.source.analysis_node_id} readOnly /></label>
          <label className="context-field">
            Version policy
            <select value={board.source.version_policy} onChange={(event) => onUpdate({ source: { ...board.source!, version_policy: event.target.value as "pinned" | "latest_published", version: event.target.value === "latest_published" ? null : board.source?.version ?? 1 } })}>
              <option value="pinned">Pinned revision</option>
              <option value="latest_published">Latest published</option>
            </select>
          </label>
          {board.source.version_policy === "pinned" ? <label className="context-field">Pinned version<input type="number" min={1} value={board.source.version ?? 1} onChange={(event) => onUpdate({ source: { ...board.source!, version: Math.max(1, Number(event.target.value)) } })} /></label> : null}
        </section>
      ) : null}

      {board.definition_id === "text-board" ? (
        <label className="context-field">
          Plain text
          <textarea
            value={String(board.settings.text ?? "")}
            onChange={(event) => onUpdate({ settings: { ...board.settings, text: event.target.value } })}
            placeholder="HTML과 script는 저장할 수 없습니다."
          />
        </label>
      ) : null}

      {visualizationRuntime ? (
        <VisualizationInspector
          board={board}
          runtime={visualizationRuntime}
          workspaceId={workspaceId}
          dashboardId={dashboardId}
          onUpdate={(visualization) => onUpdate({ settings: { ...board.settings, visualization } })}
        />
      ) : null}

      <section className="inspector-section" id="board-runtime">
        <span className="section-label">Runtime</span>
        <div className="inspector-contract">
          <span>Renderer</span><code>{definition.renderer}</code>
          <span>Objects</span><code>{definition.object_types.join(", ") || "-"}</code>
          <span>Layout</span><code>x{layout.x} · y{layout.y} · {layout.w}×{layout.h}</code>
          <span>Instance</span><code>{board.custom ? "personal" : "template"}</code>
        </div>
      </section>

      <section className="inspector-section">
        <span className="section-label">Cross-filter Contract</span>
        <div className="inspector-contract">
          <span>Accepts</span><code>{definition.accepts.join(", ") || "-"}</code>
          <span>Emits</span><code>{definition.emits.join(", ") || "-"}</code>
        </div>
      </section>
    </aside>
  );
}
