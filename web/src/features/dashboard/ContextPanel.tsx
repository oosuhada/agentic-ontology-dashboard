import type { EventSummary } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import type { DashboardParameterDefinition, SavedView } from "./types";

interface ContextPanelProps {
  events: EventSummary[];
  selectedEventId: string;
  parameterState: Record<string, unknown>;
  parameterDefinitions: DashboardParameterDefinition[];
  affectedCount: number;
  savedViews: SavedView[];
  selectedSavedViewId: string;
  activeSelectionCount: number;
  onSelectEvent: (eventId: string) => void;
  onClearSelections: () => void;
  onParameterChange: (parameterId: string, value: unknown) => void;
  onSelectSavedView: (viewId: string) => void;
  onApplySavedView: () => void;
  onDeleteSavedView: () => void;
}

export function ContextPanel({
  events,
  selectedEventId,
  parameterState,
  parameterDefinitions,
  affectedCount,
  savedViews,
  selectedSavedViewId,
  activeSelectionCount,
  onSelectEvent,
  onClearSelections,
  onParameterChange,
  onSelectSavedView,
  onApplySavedView,
  onDeleteSavedView,
}: ContextPanelProps) {
  const selected = events.find((event) => event.event_id === selectedEventId);
  const statusDefinition = parameterDefinitions.find((item) => item.id === "status_filter");
  const intentDefinition = parameterDefinitions.find((item) => item.id === "intent");
  const filteredEvents = events.filter((event) => {
    const filter = parameterState.status_filter;
    return !filter || filter === "all" || event.status === filter;
  });

  return (
    <aside className="dashboard-context-panel">
      <section>
        <span className="section-label">Object Context</span>
        {selected ? (
          <div className="context-object-card">
            <div><strong>{selected.equipment.display_name}</strong><StatusBadge status={selected.status} /></div>
            <small>{selected.scenario_id} · {selected.equipment.line}</small>
            <dl>
              <dt>Equipment</dt><dd>{selected.equipment.equipment_id}</dd>
              <dt>Risk Event</dt><dd>{selected.event_id}</dd>
              <dt>담당</dt><dd>{selected.equipment.assigned_engineer}</dd>
            </dl>
          </div>
        ) : <p className="context-empty">Risk Event를 선택하세요.</p>}
      </section>

      <section>
        <div className="context-section-heading">
          <span className="section-label">Parameters & Filters</span>
          <strong>{affectedCount} boards affected</strong>
        </div>
        <label className="context-field">
          상태 필터
          <select
            value={String(parameterState.status_filter ?? "all")}
            onChange={(event) => onParameterChange("status_filter", event.target.value)}
          >
            {(statusDefinition?.options ?? ["all"]).map((option) => (
              <option key={String(option)} value={String(option)}>{String(option)}</option>
            ))}
          </select>
        </label>
        <label className="context-field">
          화면 관점
          <select
            value={String(parameterState.intent ?? "overview")}
            onChange={(event) => onParameterChange("intent", event.target.value)}
          >
            {(intentDefinition?.options ?? ["overview"]).map((option) => (
              <option key={String(option)} value={String(option)}>{String(option)}</option>
            ))}
          </select>
        </label>
        {activeSelectionCount ? (
          <div className="cross-filter-summary">
            <span><strong>{activeSelectionCount}</strong> active cross-filter{activeSelectionCount > 1 ? "s" : ""}</span>
            <button type="button" onClick={onClearSelections}>Clear</button>
          </div>
        ) : null}
        <div className="parameter-state-list">
          {parameterDefinitions.map((definition) => (
            <div key={definition.id}>
              <span>{definition.display_name}</span>
              <code>{String(parameterState[definition.id] ?? definition.default_value ?? "-")}</code>
            </div>
          ))}
        </div>
      </section>

      <section className="context-event-section">
        <span className="section-label">Risk Event Objects</span>
        <div className="event-nav context-event-nav">
          {filteredEvents.map((event) => (
            <button
              key={event.event_id}
              type="button"
              className={selectedEventId === event.event_id ? "active" : ""}
              onClick={() => onSelectEvent(event.event_id)}
            >
              <span><strong>{event.equipment.display_name}</strong><small>{event.scenario_id} · {event.equipment.line}</small></span>
              <StatusBadge status={event.status} />
            </button>
          ))}
        </div>
      </section>

      <section>
        <span className="section-label">Saved Views</span>
        <select
          className="saved-view-select"
          value={selectedSavedViewId}
          onChange={(event) => onSelectSavedView(event.target.value)}
        >
          <option value="">저장된 View 선택</option>
          {savedViews.map((view) => <option key={view.id} value={view.id}>{view.name}</option>)}
        </select>
        <div className="button-row compact-row">
          <button type="button" className="secondary" disabled={!selectedSavedViewId} onClick={onApplySavedView}>적용</button>
          <button type="button" className="secondary" disabled={!selectedSavedViewId} onClick={onDeleteSavedView}>삭제</button>
        </div>
      </section>
    </aside>
  );
}
