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
  const categories = Object.keys(CATEGORY_LABELS) as BoardCategory[];
  const filtered = items.filter((item) => {
    const categoryMatches = category === "all" || item.category === category;
    const needle = search.trim().toLowerCase();
    const searchMatches = !needle || `${item.display_name} ${item.description} ${item.id}`.toLowerCase().includes(needle);
    return categoryMatches && searchMatches;
  });

  return (
    <div className="board-catalog-overlay" role="dialog" aria-modal="true" aria-label="Board Catalog">
      <section className="board-catalog-panel">
        <header>
          <div><span className="eyebrow">BOARD CATALOG</span><h2>역할에 허용된 Board 추가</h2></div>
          <button type="button" className="secondary" onClick={onClose}>닫기</button>
        </header>

        <div className="catalog-toolbar">
          <label>
            검색
            <input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="board 이름 또는 목적" />
          </label>
          <label>
            추가할 탭
            <select value={targetTabId} onChange={(event) => onTargetTabChange(event.target.value)}>
              {tabs.map((tab) => <option key={tab.id} value={tab.id}>{tab.title}</option>)}
            </select>
          </label>
          <button type="button" className="secondary" onClick={onCreateTab}>새 탭 생성</button>
        </div>

        <nav className="catalog-categories" aria-label="Board categories">
          <button type="button" className={category === "all" ? "active" : ""} onClick={() => onCategoryChange("all")}>전체</button>
          {categories.map((item) => (
            <button key={item} type="button" className={category === item ? "active" : ""} onClick={() => onCategoryChange(item)}>
              {CATEGORY_LABELS[item]}
            </button>
          ))}
        </nav>

        <div className="catalog-grid">
          {filtered.map((definition) => (
            <article key={definition.id} className="catalog-card">
              <div className="catalog-card-meta"><span>{CATEGORY_LABELS[definition.category]}</span><code>{definition.default_width}/12</code></div>
              <h3>{definition.display_name}</h3>
              <p>{definition.description}</p>
              <div className="catalog-binding-list">
                {definition.accepts.length ? <small>Accepts: {definition.accepts.join(", ")}</small> : <small>독립 board</small>}
                {definition.emits.length ? <small>Emits: {definition.emits.join(", ")}</small> : null}
              </div>
              <button type="button" className="primary" onClick={() => onAddBoard(definition, targetTabId)}>이 탭에 추가</button>
            </article>
          ))}
          {filtered.length === 0 ? <div className="empty-state">검색 조건에 맞는 허용 board가 없습니다.</div> : null}
        </div>
      </section>
    </div>
  );
}
