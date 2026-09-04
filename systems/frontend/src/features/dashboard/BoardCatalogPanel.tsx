import { Activity, Boxes, Database, LayoutTemplate, Plus, Search, ShieldCheck, SlidersHorizontal, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { FoundryDialog } from "../../ui/foundry/FoundryDialog";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { BoardCatalogDefinition, BoardCategory, DashboardTab } from "./types";

const CATEGORY_LABELS: Record<BoardCategory, string> = {
  suggested: "Suggested",
  observe: "Observe",
  explore: "Explore",
  explain: "Explain",
  act: "Act",
  audit: "Audit",
  build: "Build",
};

const CATEGORY_ICONS = {
  suggested: LayoutTemplate,
  observe: Activity,
  explore: Search,
  explain: Database,
  act: Wrench,
  audit: ShieldCheck,
  build: Boxes,
} satisfies Record<BoardCategory, typeof Activity>;

interface BoardCatalogPanelProps {
  items: BoardCatalogDefinition[];
  tabs: DashboardTab[];
  targetTabId: string;
  search: string;
  category: BoardCategory | "all";
  onTargetTabChange: (tabId: string) => void;
  onSearchChange: (value: string) => void;
  onCategoryChange: (value: BoardCategory | "all") => void;
  onAddBoard: (definition: BoardCatalogDefinition, tabId: string) => void;
  onCreateTab: () => void;
  onClose: () => void;
}

export function BoardCatalogPanel({
  items,
  tabs,
  targetTabId,
  search,
  category,
  onTargetTabChange,
  onSearchChange,
  onCategoryChange,
  onAddBoard,
  onCreateTab,
  onClose,
}: BoardCatalogPanelProps) {
  const { t } = useI18n();
  const categories = Object.keys(CATEGORY_LABELS) as BoardCategory[];
  const filtered = useMemo(() => items.filter((item) => {
    const categoryMatches = category === "all" || item.category === category;
    const needle = search.trim().toLowerCase();
    const searchMatches = !needle || `${item.display_name} ${item.description} ${item.id}`.toLowerCase().includes(needle);
    return categoryMatches && searchMatches;
  }), [category, items, search]);
  const [selectedDefinitionId, setSelectedDefinitionId] = useState(filtered[0]?.id ?? "");
  useEffect(() => {
    if (!filtered.some((item) => item.id === selectedDefinitionId)) setSelectedDefinitionId(filtered[0]?.id ?? "");
  }, [filtered, selectedDefinitionId]);
  const selectedDefinition = filtered.find((item) => item.id === selectedDefinitionId) ?? filtered[0] ?? null;
  const categoryCounts = useMemo(() => Object.fromEntries(categories.map((item) => [item, items.filter((definition) => definition.category === item).length])), [categories, items]);

  return (
    <FoundryDialog ariaLabel={t("dialog.boardCatalog")} overlayClassName="board-catalog-overlay" dialogClassName="board-catalog-panel" onClose={onClose}>
        <header>
          <div><span className="eyebrow">CONTOUR RESOURCE BROWSER</span><h2>Board resource 추가</h2><p>현재 역할에 허용된 Board를 탐색하고 contract를 확인한 뒤 canvas에 배치합니다.</p></div>
          <button type="button" className="secondary" onClick={onClose}>{t("common.close")}</button>
        </header>

        <div className="catalog-toolbar">
          <label className="catalog-search-field">
            <Search size={13} />
            <input data-dialog-initial-focus aria-label="Board catalog search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search resources, renderers, object types…" />
          </label>
          <label>
            Target tab
            <select value={targetTabId} onChange={(event) => onTargetTabChange(event.target.value)}>
              {tabs.map((tab) => <option key={tab.id} value={tab.id}>{tab.title}</option>)}
            </select>
          </label>
          <button type="button" className="secondary" onClick={onCreateTab}><Plus size={12} /> {t("dashboard.newTab")}</button>
        </div>

        <div className="catalog-browser-layout">
          <nav className="catalog-resource-tree" aria-label="Board categories">
            <span className="section-label">RESOURCE TYPES</span>
            <button type="button" className={category === "all" ? "active" : ""} onClick={() => onCategoryChange("all")}><Boxes size={13} /><span><strong>All boards</strong><small>{items.length} resources</small></span></button>
            {categories.map((item) => {
              const Icon = CATEGORY_ICONS[item];
              return <button key={item} type="button" className={category === item ? "active" : ""} onClick={() => onCategoryChange(item)}><Icon size={13} /><span><strong>{CATEGORY_LABELS[item]}</strong><small>{categoryCounts[item]} resources</small></span></button>;
            })}
            <section><span className="section-label">ACTIVE TARGET</span><strong>{tabs.find((tab) => tab.id === targetTabId)?.title ?? "Dashboard"}</strong><small>Boards are appended to this governed tab.</small></section>
          </nav>

          <section className="catalog-resource-list" aria-label="Board palette">
            <header><div><span className="section-label">BOARD PALETTE</span><strong>{filtered.length} available resources</strong></div><SlidersHorizontal size={13} /></header>
            <div>
              {filtered.map((definition) => {
                const Icon = CATEGORY_ICONS[definition.category];
                return (
                  <button type="button" key={definition.id} className={`catalog-resource-row ${selectedDefinition?.id === definition.id ? "active" : ""}`} onClick={() => setSelectedDefinitionId(definition.id)} onDoubleClick={() => onAddBoard(definition, targetTabId)}>
                    <span><Icon size={14} /></span><div><strong>{definition.display_name}</strong><small>{definition.description}</small><code>{definition.renderer}</code></div><b>{definition.default_width}/12</b>
                  </button>
                );
              })}
              {filtered.length === 0 ? <div className="empty-state">검색 조건에 맞는 허용 board가 없습니다.</div> : null}
            </div>
          </section>

          <aside className="catalog-resource-preview">
            {selectedDefinition ? <>
              <header><span className="catalog-preview-icon">{(() => { const Icon = CATEGORY_ICONS[selectedDefinition.category]; return <Icon size={17} />; })()}</span><div><span className="section-label">BOARD RESOURCE</span><strong>{selectedDefinition.display_name}</strong><code>{selectedDefinition.id}</code></div></header>
              <p>{selectedDefinition.description}</p>
              <div className="catalog-preview-canvas"><span>{selectedDefinition.renderer}</span><div><i /><i /><i /></div><small>{selectedDefinition.default_width} / 12 default span</small></div>
              <dl>
                <div><dt>Category</dt><dd>{CATEGORY_LABELS[selectedDefinition.category]}</dd></div>
                <div><dt>Renderer</dt><dd><code>{selectedDefinition.renderer}</code></dd></div>
                <div><dt>Object types</dt><dd>{selectedDefinition.object_types.join(", ") || "Independent"}</dd></div>
                <div><dt>Width contract</dt><dd>{selectedDefinition.minimum_width}–{selectedDefinition.maximum_width} / 12</dd></div>
                <div><dt>Accepts</dt><dd>{selectedDefinition.accepts.join(", ") || "—"}</dd></div>
                <div><dt>Emits</dt><dd>{selectedDefinition.emits.join(", ") || "—"}</dd></div>
              </dl>
              <button type="button" className="primary catalog-add-selected" onClick={() => onAddBoard(selectedDefinition, targetTabId)}><Plus size={13} /> {t("common.apply")} · {tabs.find((tab) => tab.id === targetTabId)?.title ?? "tab"}</button>
              <small>Double-click a resource in the palette to add it immediately.</small>
            </> : <div className="empty-state">Select a Board resource.</div>}
          </aside>
        </div>
    </FoundryDialog>
  );
}
