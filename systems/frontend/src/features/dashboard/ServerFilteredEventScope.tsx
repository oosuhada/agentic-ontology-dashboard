import { useEffect, useMemo, useState, type ReactNode } from "react";
import { queryDashboardBoard } from "../../api";
import type { EventSummary } from "../../types";
import { filterEventsBySelection } from "./cross-filter-engine";
import type { SelectionFilter } from "./types";

interface ServerFilteredEventScopeProps {
  boardId: string;
  dashboardId: string;
  workspaceId: string;
  events: EventSummary[];
  parameterState: Record<string, unknown>;
  selectionFilters: SelectionFilter[];
  children: (events: EventSummary[]) => ReactNode;
}

function normalizeEventId(value: string) {
  return value.startsWith("risk_event:") ? value.slice("risk_event:".length) : value;
}

export function ServerFilteredEventScope({
  boardId,
  dashboardId,
  workspaceId,
  events,
  parameterState,
  selectionFilters,
  children,
}: ServerFilteredEventScopeProps) {
  const [serverEvents, setServerEvents] = useState<EventSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const parameterSignature = JSON.stringify(parameterState);
  const filterSignature = JSON.stringify(selectionFilters);
  const fallbackEvents = useMemo(
    () => filterEventsBySelection(events, selectionFilters),
    [events, filterSignature],
  );

  useEffect(() => {
    let active = true;
    if (!selectionFilters.length) {
      setServerEvents(null);
      setLoading(false);
      setError("");
      return () => { active = false; };
    }

    setLoading(true);
    setError("");
    queryDashboardBoard({
      dashboard_id: dashboardId,
      board_id: boardId,
      workspace_id: workspaceId,
      parameter_state: parameterState,
      selection_filters: selectionFilters,
      offset: 0,
      limit: 500,
    })
      .then((payload) => {
        if (!active) return;
        const matchingIds = new Set(payload.matching_object_ids.map(normalizeEventId));
        setServerEvents(events.filter((event) => matchingIds.has(event.event_id)));
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setServerEvents(null);
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [boardId, dashboardId, events, parameterSignature, filterSignature, workspaceId]);

  const scopedEvents = selectionFilters.length
    ? serverEvents ?? fallbackEvents
    : events;

  return (
    <div className="server-filtered-event-scope">
      {selectionFilters.length ? (
        <div
          className={`dashboard-cross-filter-runtime ${error ? "fallback" : loading ? "loading" : "server"}`}
          role="status"
        >
          <strong>{error ? "Client fallback" : loading ? "Server cross-filter" : "Server filtered"}</strong>
          <span>
            {error
              ? `${fallbackEvents.length} objects · ${error}`
              : loading
                ? `${selectionFilters.length} filter${selectionFilters.length > 1 ? "s" : ""}`
                : `${scopedEvents.length} objects`}
          </span>
        </div>
      ) : null}
      {children(scopedEvents)}
    </div>
  );
}
