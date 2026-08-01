import type { BoardCatalogDefinition, BoardWidth, DashboardBoard, DashboardTab } from "./types";

interface BoardInspectorProps {
  board: DashboardBoard | null;
  definition: BoardCatalogDefinition | null;
  tabs: DashboardTab[];
  currentTabId: string | null;
  onUpdate: (update: Partial<DashboardBoard>) => void;
  onMove: (targetTabId: string) => void;
  onClose: () => void;
}

export function BoardInspector({
  board,
  definition,
  tabs,
  currentTabId,
  onUpdate,
  onMove,
  onClose,
}: BoardInspectorProps) {
  if (!board || !definition) {
    return (
      <aside className="dashboard-inspector">
        <span className="section-label">Inspector</span>
        <div className="inspector-empty">
          <strong>Board를 선택하세요.</strong>
          <p>편집 모드에서 제목, 폭, 표시 여부, binding과 text 내용을 수정할 수 있습니다.</p>
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
        <div><span className="section-label">Board Inspector</span><strong>{definition.display_name}</strong></div>
        <button type="button" onClick={onClose}>닫기</button>
      </header>

      <div className="inspector-definition">
        <span>{definition.category.toUpperCase()}</span>
        <p>{definition.description}</p>
        <code>{definition.id}</code>
      </div>

      <label className="context-field">
        Board 제목
        <input value={board.title} onChange={(event) => onUpdate({ title: event.target.value })} />
      </label>

      <label className="context-field">
        Layout 폭
        <select
          value={layout.w}
          onChange={(event) => {
            const width = Number(event.target.value) as BoardWidth;
            onUpdate({ width, layout: { ...layout, w: width, x: Math.min(layout.x, 12 - width) } });
          }}
        >
          {widthOptions.map((width) => (
            <option key={width} value={width}>{width} / 12 {width === 12 ? "· Full" : width === 8 ? "· 2/3" : width === 6 ? "· Half" : width === 4 ? "· Third" : ""}</option>
          ))}
        </select>
      </label>

      <label className="context-field">
        Board 높이
        <select
          value={String(layout.h)}
          onChange={(event) => {
            const height = Number(event.target.value);
            onUpdate({ layout: { ...layout, h: height }, settings: { ...board.settings, height_units: String(height) } });
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

      <div className="inspector-layout-grid">
        <label className="context-field">X<input type="number" min={0} max={Math.max(0, 12 - layout.w)} value={layout.x} onChange={(event) => onUpdate({ layout: { ...layout, x: Math.max(0, Math.min(12 - layout.w, Number(event.target.value))) } })} /></label>
        <label className="context-field">Y<input type="number" min={0} value={layout.y} onChange={(event) => onUpdate({ layout: { ...layout, y: Math.max(0, Number(event.target.value)) } })} /></label>
        <label className="context-field">W<input type="number" min={definition.minimum_width} max={definition.maximum_width} value={layout.w} onChange={(event) => { const width = Math.max(definition.minimum_width, Math.min(definition.maximum_width, Number(event.target.value))); onUpdate({ width, layout: { ...layout, w: width, x: Math.min(layout.x, 12 - width) } }); }} /></label>
        <label className="context-field">H<input type="number" min={1} max={12} value={layout.h} onChange={(event) => { const height = Math.max(1, Math.min(12, Number(event.target.value))); onUpdate({ layout: { ...layout, h: height }, settings: { ...board.settings, height_units: String(height) } }); }} /></label>
      </div>

      <label className="context-field">
        배치 탭
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
        View 모드에서 숨김
      </label>
      {board.mandatory ? <small className="mandatory-note">필수 board는 숨기거나 삭제할 수 없습니다.</small> : null}

      {Object.keys(definition.binding_schema).length ? (
        <section className="inspector-section">
          <span className="section-label">Bindings</span>
          {Object.entries(definition.binding_schema).map(([bindingId, valueType]) => (
            <label key={bindingId} className="context-field">
              {bindingId} <small>{valueType}</small>
              <input
                value={String(board.bindings[bindingId] ?? "")}
                onChange={(event) => onUpdate({ bindings: { ...board.bindings, [bindingId]: event.target.value } })}
                placeholder="고정 값 또는 비워두기"
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

      <section className="inspector-section">
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
