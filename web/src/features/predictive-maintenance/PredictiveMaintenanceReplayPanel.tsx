import { useEffect, useMemo, useState } from "react";
import {
  controlPredictiveMaintenanceReplay,
  getPredictiveMaintenanceLatestResults,
  getPredictiveMaintenanceRuntimeContext,
  predictiveMaintenanceReplayEventsUrl,
  startPredictiveMaintenanceReplay,
} from "../../api";
import type {
  PredictiveMaintenanceRuntimeContext,
  ProductResultPage,
  ReplaySessionSnapshot,
} from "./types";

interface PredictiveMaintenanceReplayPanelProps {
  projectId: string;
  workspaceId: string;
}

function timeLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function graphStatusLabel(context: PredictiveMaintenanceRuntimeContext): string {
  if (context.graph.status === "ready") return "Graph ready";
  if (context.graph.status === "failed") return "Graph degraded · PostgreSQL replay available";
  return `Graph ${context.graph.status} · PostgreSQL replay available`;
}

export function PredictiveMaintenanceReplayPanel({
  projectId,
  workspaceId,
}: PredictiveMaintenanceReplayPanelProps) {
  const [context, setContext] = useState<PredictiveMaintenanceRuntimeContext | null>(null);
  const [results, setResults] = useState<ProductResultPage | null>(null);
  const [replay, setReplay] = useState<ReplaySessionSnapshot | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId || !workspaceId) return;
    const controller = new AbortController();
    setUnsupported(false);
    setError("");
    Promise.all([
      getPredictiveMaintenanceRuntimeContext(projectId, workspaceId, controller.signal),
      getPredictiveMaintenanceLatestResults(projectId, workspaceId, 3, controller.signal),
    ])
      .then(([nextContext, nextResults]) => {
        setContext(nextContext);
        setResults(nextResults);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        const status = typeof reason === "object" && reason !== null && "status" in reason
          ? Number((reason as { status: number }).status)
          : 0;
        if (status === 404 || status === 409) {
          setUnsupported(true);
          return;
        }
        setError(reason instanceof Error ? reason.message : "Prediction runtime을 불러오지 못했습니다.");
      });
    return () => controller.abort();
  }, [projectId, workspaceId]);

  useEffect(() => {
    if (!replay?.cursor.session_id) return;
    const source = new EventSource(
      predictiveMaintenanceReplayEventsUrl(projectId, workspaceId, replay.cursor.session_id),
      { withCredentials: true },
    );
    source.addEventListener("replay", (event) => {
      setReplay(JSON.parse((event as MessageEvent<string>).data) as ReplaySessionSnapshot);
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [projectId, replay?.cursor.session_id, workspaceId]);

  const criticalCount = useMemo(
    () => results?.items.filter((item) => item.status_grade === "critical").length ?? 0,
    [results],
  );

  async function startReplay() {
    setBusy(true);
    setError("");
    try {
      setReplay(await startPredictiveMaintenanceReplay(projectId, workspaceId, {
        dataset_version_id: context?.dataset_version_id,
        speed_minutes_per_second: 60,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Replay를 시작하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function control(action: "pause" | "resume" | "reset", payload: Record<string, never> = {}) {
    if (!replay) return;
    setBusy(true);
    try {
      setReplay(await controlPredictiveMaintenanceReplay(
        projectId,
        workspaceId,
        replay.cursor.session_id,
        action,
        payload,
      ));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Replay 상태를 변경하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (unsupported) return null;

  return (
    <section className="pm-replay-panel" aria-label="Predictive maintenance replay">
      <header>
        <div>
          <span className="eyebrow">Result Artifact · Replay</span>
          <strong>V3.1 prediction runtime</strong>
        </div>
        <span className={`pm-replay-graph status-${context?.graph.status ?? "loading"}`}>
          {context ? graphStatusLabel(context) : "Resolving Dataset Version"}
        </span>
      </header>

      {context ? (
        <div className="pm-replay-summary">
          <span><small>Dataset Version</small>{context.dataset_version_id}</span>
          <span><small>Latest results</small>{results?.total ?? 0} assets</span>
          <span><small>Critical</small>{criticalCount}</span>
          <span><small>Contract</small>{results?.latest_product_contract ?? "—"}</span>
        </div>
      ) : null}

      {results?.items.length ? (
        <div className="pm-replay-results">
          {results.items.map((item) => (
            <div key={item.asset_id}>
              <strong>{item.asset_id}</strong>
              <span>{item.status_grade} · {(item.failure_probability * 100).toFixed(1)}%</span>
              <small>{item.recommended_action?.action ?? "Snapshot compatibility"}</small>
            </div>
          ))}
        </div>
      ) : null}

      <div className="pm-replay-cursor">
        <span><small>Simulation time</small>{timeLabel(replay?.cursor.simulation_time)}</span>
        <span><small>Source freshness</small>{timeLabel(replay?.cursor.source_freshness_at)}</span>
        <span><small>Nearest prediction</small>{timeLabel(replay?.nearest_prediction_time)}</span>
        <span><small>State</small>{replay?.cursor.state ?? "not started"}</span>
      </div>

      <div className="button-row">
        {!replay ? (
          <button type="button" className="primary" disabled={!context || busy} onClick={() => void startReplay()}>
            Start replay
          </button>
        ) : (
          <>
            {replay.cursor.state === "running" ? (
              <button type="button" disabled={busy} onClick={() => void control("pause")}>Pause</button>
            ) : (
              <button type="button" disabled={busy || replay.cursor.state === "completed"} onClick={() => void control("resume")}>Resume</button>
            )}
            <button type="button" disabled={busy} onClick={() => void control("reset")}>Reset</button>
          </>
        )}
      </div>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </section>
  );
}
