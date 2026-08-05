import { Database, ExternalLink, PlugZap, Rows3 } from "lucide-react";
import type { EventSummary } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { DashboardParameterDefinition, SavedView } from "./types";
import type { PredictiveMaintenanceDashboardDataSource } from "../predictive-maintenance/types";

export interface DashboardDataConnection {
  loading: boolean;
  datasetCount: number;
  recordCount: number;
  relationalReadyCount: number;
  sourceTypes: string[];
  datasetNames: string[];
  sourceVersions: string[];
  externalConnection: boolean;
  error: string | null;
  activeSource?: PredictiveMaintenanceDashboardDataSource | null;
  fallbackReason?: string;
}

interface ContextPanelProps {
  events: EventSummary[];
  selectedEventId: string;
  parameterState: Record<string, unknown>;
  parameterDefinitions: DashboardParameterDefinition[];
  affectedCount: number;
  savedViews: SavedView[];
  selectedSavedViewId: string;
  activeSelectionCount: number;
  dataConnection: DashboardDataConnection;
  onSelectEvent: (eventId: string) => void;
  onOpenDatasets: () => void;
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
  dataConnection,
  onSelectEvent,
  onOpenDatasets,
  onClearSelections,
  onParameterChange,
  onSelectSavedView,
  onApplySavedView,
  onDeleteSavedView,
}: ContextPanelProps) {
  const { t } = useI18n();
  const selected = events.find((event) => event.event_id === selectedEventId);
  const statusDefinition = parameterDefinitions.find((item) => item.id === "status_filter");
  const intentDefinition = parameterDefinitions.find((item) => item.id === "intent");
  const filteredEvents = events.filter((event) => {
    const filter = parameterState.status_filter;
    return !filter || filter === "all" || event.status === filter;
  });
  const activeSource = dataConnection.activeSource;

  return (
    <aside className="dashboard-context-panel">
      <section className="dashboard-data-connections">
        <div className="context-section-heading">
          <span className="section-label">Connected Resources</span>
          <strong className={activeSource || dataConnection.externalConnection ? "is-live" : "is-local"}>
            {dataConnection.loading && !activeSource
              ? "checking"
              : activeSource
                ? "PostgreSQL"
                : dataConnection.error
                  ? "degraded"
                  : "local fixture"}
          </strong>
        </div>
        <div className="dashboard-connection-grid">
          <article>
            <span><PlugZap size={12} /> Events API</span>
            <strong>{events.length.toLocaleString()}</strong>
            <small>workspace-scoped objects</small>
          </article>
          <article>
            <span><Database size={12} /> Datasets</span>
            <strong>{dataConnection.loading ? "—" : dataConnection.datasetCount.toLocaleString()}</strong>
            <small>{dataConnection.recordCount.toLocaleString()} versioned rows</small>
          </article>
          <article>
            <span><Rows3 size={12} /> Relational</span>
            <strong>{dataConnection.loading ? "—" : `${dataConnection.relationalReadyCount}/${dataConnection.datasetCount}`}</strong>
            <small>ready projections</small>
          </article>
        </div>
        <div className={`dashboard-source-disclosure ${dataConnection.error && !activeSource ? "has-error" : ""}`}>
          <div>
            <strong>{activeSource?.dataset_name ?? "Manufacturing Gold Fixture Demo"}</strong>
            <small>
              {activeSource
                ? `${activeSource.source_version} · ${activeSource.dataset_status === "published" ? "Published" : activeSource.dataset_status} · ${activeSource.release_ready ? "release ready" : "release checks pending"} · PostgreSQL Result Artifact · ${activeSource.result_artifact_count.toLocaleString()} artifacts · ${activeSource.prediction_timeline_count.toLocaleString()} timeline rows · relational ${activeSource.relational_status} · graph ${activeSource.graph.status} · ${activeSource.model_version ?? "model unavailable"} · ${activeSource.selection_reason.replaceAll("_", " ")}`
                : dataConnection.error
                  ? dataConnection.error
                  : `${dataConnection.datasetNames.join(" + ") || "Manufacturing Equipment Registry + Manufacturing Risk Events"} · ${dataConnection.sourceVersions.join(", ") || "gold-fixtures-2026-08-01"} · legacy/offline fallback${dataConnection.fallbackReason ? ` · ${dataConnection.fallbackReason}` : ""}`}
            </small>
          </div>
          <button type="button" onClick={onOpenDatasets}>{t("common.inspect")} <ExternalLink size={11} /></button>
        </div>
      </section>

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
        <div className="fd-filter-chips" role="group" aria-label="상태 필터 바로가기">
          {(statusDefinition?.options ?? ["all"]).map((option) => {
            const value = String(option);
            return (
              <button
                type="button"
                key={value}
                className={String(parameterState.status_filter ?? "all") === value ? "active" : ""}
                onClick={() => onParameterChange("status_filter", value)}
              >
                {value}
              </button>
            );
          })}
        </div>
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
            <button type="button" onClick={onClearSelections}>{t("common.clear")}</button>
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
          <option value="">{t("dashboard.saveView")}</option>
          {savedViews.map((view) => <option key={view.id} value={view.id}>{view.name}</option>)}
        </select>
        <div className="button-row compact-row">
          <button type="button" className="secondary" disabled={!selectedSavedViewId} onClick={onApplySavedView}>{t("common.apply")}</button>
          <button type="button" className="secondary" disabled={!selectedSavedViewId} onClick={onDeleteSavedView}>{t("common.delete")}</button>
        </div>
      </section>
    </aside>
  );
}
