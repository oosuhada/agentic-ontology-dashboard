import { Database, ExternalLink, PlugZap, Rows3 } from "lucide-react";
import { useState } from "react";
import type { EventSummary } from "../../types";
import { StatusBadge } from "../../components/StatusBadge";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { MessageKey } from "../../ui/i18n/messages";
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

const STATUS_OPTION_KEYS: Record<string, MessageKey> = {
  all: "status.all",
  critical: "status.critical",
  warning: "status.warning",
  attention: "status.attention",
  data_quality_hold: "status.dataQualityHold",
  normal: "status.normal",
};

const INTENT_OPTION_KEYS: Record<string, MessageKey> = {
  overview: "intent.overview",
  "explain-risk": "intent.explainRisk",
  compare: "intent.compare",
  "summarize-manager": "intent.summarizeManager",
  "detail-engineer": "intent.detailEngineer",
  "recommend-check": "intent.recommendCheck",
  "show-model-details": "intent.showModelDetails",
};

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
  const { t, locale } = useI18n();
  const [activeSection, setActiveSection] = useState<"context" | "filters" | "events">("context");
  const optionLabel = (value: string) => {
    const key = STATUS_OPTION_KEYS[value] ?? INTENT_OPTION_KEYS[value];
    return key ? t(key) : value;
  };
  const selected = events.find((event) => event.event_id === selectedEventId);
  const statusDefinition = parameterDefinitions.find((item) => item.id === "status_filter");
  const intentDefinition = parameterDefinitions.find((item) => item.id === "intent");
  const filteredEvents = events.filter((event) => {
    const filter = parameterState.status_filter;
    return !filter || filter === "all" || event.status === filter;
  });
  const activeSource = dataConnection.activeSource;
  const sourceDetail = activeSource
    ? `${activeSource.source_version} · ${activeSource.dataset_status === "published" ? t("dashboard.sourcePublished") : activeSource.dataset_status} · ${activeSource.release_ready ? "release ready" : "release checks pending"} · PostgreSQL Result Artifact · ${activeSource.result_artifact_count.toLocaleString(locale)} artifacts · ${activeSource.prediction_timeline_count.toLocaleString(locale)} timeline rows · relational ${activeSource.relational_status} · graph ${activeSource.graph.status} · ${activeSource.model_version ?? t("dashboard.sourceModelUnavailable")} · ${activeSource.selection_reason.replaceAll("_", " ")}`
    : dataConnection.error
      ? dataConnection.error
      : `${dataConnection.datasetNames.join(" + ") || "Manufacturing Equipment Registry + Manufacturing Risk Events"} · ${dataConnection.sourceVersions.join(", ") || "gold-fixtures-2026-08-01"} · legacy/offline fallback${dataConnection.fallbackReason ? ` · ${dataConnection.fallbackReason}` : ""}`;
  const sourceSummary = activeSource
    ? `${activeSource.source_version} · ${activeSource.dataset_status === "published" ? t("dashboard.sourcePublished") : activeSource.dataset_status} · ${activeSource.result_artifact_count.toLocaleString(locale)} ${t("dashboard.sourceArtifacts")} · ${activeSource.model_version ?? t("dashboard.sourceModelUnavailable")}`
    : sourceDetail;

  return (
    <aside className="dashboard-context-panel">
      <nav className="dashboard-context-tabs" aria-label={locale === "ko-KR" ? "Dashboard 상황 패널" : "Dashboard context sections"}>
        <button type="button" className={activeSection === "context" ? "active" : ""} onClick={() => setActiveSection("context")}>{locale === "ko-KR" ? "상황" : "Context"}</button>
        <button type="button" className={activeSection === "filters" ? "active" : ""} onClick={() => setActiveSection("filters")}>{locale === "ko-KR" ? "필터" : "Filters"}{affectedCount ? <small>{affectedCount}</small> : null}</button>
        <button type="button" className={activeSection === "events" ? "active" : ""} onClick={() => setActiveSection("events")}>Event<small>{filteredEvents.length}</small></button>
      </nav>

      {activeSection === "context" ? <>
      <section className="dashboard-data-connections">
        <div className="context-section-heading">
          <span className="section-label">{t("dashboard.connectedResources")}</span>
          <strong className={activeSource || dataConnection.externalConnection ? "is-live" : "is-local"}>
            {dataConnection.loading && !activeSource
              ? t("dashboard.checking")
              : activeSource
                ? "PostgreSQL"
                : dataConnection.error
                  ? t("dashboard.degraded")
                  : t("dashboard.localFixture")}
          </strong>
        </div>
        <div className="dashboard-connection-grid">
          <article>
            <span><PlugZap size={12} /> {t("dashboard.eventsApi")}</span>
            <strong>{events.length.toLocaleString(locale)}</strong>
            <small>{t("dashboard.workspaceObjects")}</small>
          </article>
          <article>
            <span><Database size={12} /> {t("dashboard.datasetsLabel")}</span>
            <strong>{dataConnection.loading ? "—" : dataConnection.datasetCount.toLocaleString(locale)}</strong>
            <small>{dataConnection.recordCount.toLocaleString(locale)} {t("dashboard.versionedRows")}</small>
          </article>
          <article>
            <span><Rows3 size={12} /> {t("dashboard.relational")}</span>
            <strong>{dataConnection.loading ? "—" : `${dataConnection.relationalReadyCount}/${dataConnection.datasetCount}`}</strong>
            <small>{t("dashboard.readyProjections")}</small>
          </article>
        </div>
        <div className={`dashboard-source-disclosure ${dataConnection.error && !activeSource ? "has-error" : ""}`}>
          <div>
            <strong>{activeSource?.dataset_name ?? "Manufacturing Gold Fixture Demo"}</strong>
            <small title={sourceDetail}>{sourceSummary}</small>
          </div>
          <button type="button" onClick={onOpenDatasets}>{t("common.inspect")} <ExternalLink size={11} /></button>
        </div>
      </section>

      <section>
        <span className="section-label">{t("dashboard.objectContext")}</span>
        {selected ? (
          <div className="context-object-card">
            <div><strong>{selected.equipment.display_name}</strong><StatusBadge status={selected.status} /></div>
            <small>{selected.scenario_id} · {selected.equipment.line}</small>
            <dl>
              <dt>{t("dashboard.equipment")}</dt><dd>{selected.equipment.equipment_id}</dd>
              <dt>{t("dashboard.riskEvent")}</dt><dd>{selected.event_id}</dd>
              <dt>{t("dashboard.assignee")}</dt><dd>{selected.equipment.assigned_engineer}</dd>
            </dl>
          </div>
        ) : <p className="context-empty">{t("dashboard.selectRiskEvent")}</p>}
      </section>

      <section>
        <span className="section-label">{t("dashboard.savedViews")}</span>
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
      </> : null}

      {activeSection === "filters" ? <section>
        <div className="context-section-heading">
          <span className="section-label">{t("dashboard.parametersFilters")}</span>
          <strong>{t("dashboard.boardsAffected", { count: affectedCount })}</strong>
        </div>
        <label className="context-field">
          {t("dashboard.statusFilter")}
          <select
            value={String(parameterState.status_filter ?? "all")}
            onChange={(event) => onParameterChange("status_filter", event.target.value)}
          >
            {(statusDefinition?.options ?? ["all"]).map((option) => (
              <option key={String(option)} value={String(option)}>{optionLabel(String(option))}</option>
            ))}
          </select>
        </label>
        <div className="fd-filter-chips" role="group" aria-label={t("dashboard.statusFilterShortcuts")}>
          {(statusDefinition?.options ?? ["all"]).map((option) => {
            const value = String(option);
            return (
              <button
                type="button"
                key={value}
                className={String(parameterState.status_filter ?? "all") === value ? "active" : ""}
                onClick={() => onParameterChange("status_filter", value)}
              >
                {optionLabel(value)}
              </button>
            );
          })}
        </div>
        <label className="context-field">
          {t("dashboard.viewIntent")}
          <select
            value={String(parameterState.intent ?? "overview")}
            onChange={(event) => onParameterChange("intent", event.target.value)}
          >
            {(intentDefinition?.options ?? ["overview"]).map((option) => (
              <option key={String(option)} value={String(option)}>{optionLabel(String(option))}</option>
            ))}
          </select>
        </label>
        {activeSelectionCount ? (
          <div className="cross-filter-summary">
            <span>{t("dashboard.activeCrossFilters", { count: activeSelectionCount })}</span>
            <button type="button" onClick={onClearSelections}>{t("common.clear")}</button>
          </div>
        ) : null}
        <div className="parameter-state-list">
          {parameterDefinitions.map((definition) => (
            <div key={definition.id}>
              <span>{definition.display_name}</span>
              <code>{optionLabel(String(parameterState[definition.id] ?? definition.default_value ?? "-"))}</code>
            </div>
          ))}
        </div>
      </section> : null}

      {activeSection === "events" ? <section className="context-event-section">
        <span className="section-label">{t("dashboard.riskEvents")}</span>
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
      </section> : null}
    </aside>
  );
}
