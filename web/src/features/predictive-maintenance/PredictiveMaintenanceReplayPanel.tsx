import { useEffect, useMemo, useState } from "react";
import {
  controlPredictiveMaintenanceReplay,
  getPredictiveMaintenanceLatestResults,
  getPredictiveMaintenanceObservations,
  getPredictiveMaintenanceRuntimeContext,
  getPredictiveMaintenanceVersions,
  predictiveMaintenanceReplayEventsUrl,
  startPredictiveMaintenanceReplay,
} from "../../api";
import type { AppRole } from "../../types";
import type {
  GovernedProductResultSummary,
  PredictiveMaintenanceDatasetVersions,
  PredictiveMaintenanceObservationResponse,
  PredictiveMaintenanceRuntimeContext,
  ProductResultPage,
  ReplaySessionSnapshot,
} from "./types";

interface PredictiveMaintenanceReplayPanelProps {
  projectId: string;
  workspaceId: string;
  appRole?: AppRole;
}

type StatusGrade = GovernedProductResultSummary["status_grade"];

const STATUS_ORDER: StatusGrade[] = ["critical", "warning", "attention", "normal"];
export const AI4I_V3_1_DATASET_NAME = "UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1";
const AI4I_V2_DATASET_NAME = "UCI AI4I 2020 Manufacturing Predictive Maintenance — Canonical V2 compatibility snapshot";

function timeLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function compactChecksum(value: string | null | undefined): string {
  if (!value) return "—";
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

export function graphStatusLabel(context: PredictiveMaintenanceRuntimeContext): string {
  if (context.graph.status === "ready") return `Graph ready · ${context.graph.record_count.toLocaleString()} records`;
  if (context.graph.status === "failed") return "Graph degraded · PostgreSQL runtime available";
  return `Graph ${context.graph.status} · PostgreSQL runtime available`;
}

export function countStatusGrades(items: GovernedProductResultSummary[]): Record<StatusGrade, number> {
  const counts: Record<StatusGrade, number> = { critical: 0, warning: 0, attention: 0, normal: 0 };
  for (const item of items) counts[item.status_grade] += 1;
  return counts;
}

export function roleRuntimeMode(role: AppRole | undefined): "manager" | "engineer" | "model" | "governance" {
  if (role === "ml_validator") return "model";
  if (role === "tenant_admin" || role === "fde" || role === "quality_auditor") return "governance";
  if (role === "process_engineer" || role === "maintenance_technician") return "engineer";
  return "manager";
}

function resultWindow(result: GovernedProductResultSummary): { start: string; end: string } {
  const end = new Date(result.observed_at);
  const start = new Date(end.getTime() - 6 * 60 * 60 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

function selectedVersionLabel(versions: PredictiveMaintenanceDatasetVersions | null, id: string): string {
  const item = versions?.items.find((version) => version.dataset_version_id === id);
  if (!item) return id;
  const datasetName = item.is_v3_1
    ? AI4I_V3_1_DATASET_NAME
    : item.source_version.includes("ai4i")
      ? AI4I_V2_DATASET_NAME
      : item.dataset_name;
  return `${datasetName} · ${item.source_version} · v${item.version_number}${item.is_latest ? " · latest" : ""}`;
}

function recommendationSummary(items: GovernedProductResultSummary[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const item of items) {
    const recommendation = item.recommended_action;
    if (!recommendation) continue;
    const key = `${recommendation.priority} · ${recommendation.action}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 5);
}

export function PredictiveMaintenanceReplayPanel({
  projectId,
  workspaceId,
  appRole,
}: PredictiveMaintenanceReplayPanelProps) {
  const [versions, setVersions] = useState<PredictiveMaintenanceDatasetVersions | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [context, setContext] = useState<PredictiveMaintenanceRuntimeContext | null>(null);
  const [results, setResults] = useState<ProductResultPage | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [observations, setObservations] = useState<PredictiveMaintenanceObservationResponse | null>(null);
  const [replay, setReplay] = useState<ReplaySessionSnapshot | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [speed, setSpeed] = useState(60);
  const [seekTime, setSeekTime] = useState("");

  const runtimeMode = roleRuntimeMode(appRole);

  useEffect(() => {
    if (!projectId || !workspaceId) return;
    const controller = new AbortController();
    setUnsupported(false);
    setError("");
    getPredictiveMaintenanceVersions(projectId, workspaceId, controller.signal)
      .then((nextVersions) => {
        setVersions(nextVersions);
        setSelectedVersionId((current) => {
          if (current && nextVersions.items.some((item) => item.dataset_version_id === current)) return current;
          return nextVersions.default_dataset_version_id ?? "";
        });
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        const status = typeof reason === "object" && reason !== null && "status" in reason
          ? Number((reason as { status: number }).status)
          : 0;
        if (status === 404 || status === 409 || status === 503) {
          setUnsupported(true);
          return;
        }
        setError(reason instanceof Error ? reason.message : "Dataset Version 목록을 불러오지 못했습니다.");
      });
    return () => controller.abort();
  }, [projectId, workspaceId]);

  useEffect(() => {
    if (!projectId || !workspaceId || !selectedVersionId) return;
    const controller = new AbortController();
    setError("");
    setReplay(null);
    setObservations(null);
    Promise.all([
      getPredictiveMaintenanceRuntimeContext(projectId, workspaceId, controller.signal, selectedVersionId),
      getPredictiveMaintenanceLatestResults(projectId, workspaceId, 100, controller.signal, selectedVersionId),
    ])
      .then(([nextContext, nextResults]) => {
        setContext(nextContext);
        setResults(nextResults);
        setSelectedAssetId((current) => (
          current && nextResults.items.some((item) => item.asset_id === current)
            ? current
            : nextResults.items[0]?.asset_id ?? ""
        ));
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setContext(null);
        setResults(null);
        setError(reason instanceof Error ? reason.message : "Prediction runtime을 불러오지 못했습니다.");
      });
    return () => controller.abort();
  }, [projectId, selectedVersionId, workspaceId]);

  const selectedResult = useMemo(
    () => results?.items.find((item) => item.asset_id === selectedAssetId) ?? null,
    [results, selectedAssetId],
  );

  useEffect(() => {
    if (!selectedResult || !selectedVersionId || runtimeMode !== "engineer") {
      setObservations(null);
      return;
    }
    const controller = new AbortController();
    const window = resultWindow(selectedResult);
    getPredictiveMaintenanceObservations(projectId, workspaceId, {
      dataset_version_id: selectedVersionId,
      asset_id: selectedResult.asset_id,
      start: window.start,
      end: window.end,
      grain: "10m",
      derived_measures: ["power_w", "temperature_gap_k", "overstrain_load"],
      limit: 72,
    }, controller.signal)
      .then(setObservations)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Sensor window를 불러오지 못했습니다.");
        }
      });
    return () => controller.abort();
  }, [projectId, runtimeMode, selectedResult, selectedVersionId, workspaceId]);

  useEffect(() => {
    if (!replay?.cursor.session_id) return;
    const source = new EventSource(
      predictiveMaintenanceReplayEventsUrl(projectId, workspaceId, replay.cursor.session_id),
      { withCredentials: true },
    );
    source.addEventListener("replay", (event) => {
      const next = JSON.parse((event as MessageEvent<string>).data) as ReplaySessionSnapshot;
      setReplay(next);
      setSpeed(next.cursor.speed_minutes_per_second);
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [projectId, replay?.cursor.session_id, workspaceId]);

  const statusCounts = useMemo(() => countStatusGrades(results?.items ?? []), [results]);
  const actionSummary = useMemo(() => recommendationSummary(results?.items ?? []), [results]);
  const highRisk = useMemo(
    () => [...(results?.items ?? [])].sort((left, right) => right.failure_probability - left.failure_probability).slice(0, 5),
    [results],
  );
  const latestObservation = observations?.observations.at(-1) ?? null;

  async function startReplay() {
    setBusy(true);
    setError("");
    try {
      const next = await startPredictiveMaintenanceReplay(projectId, workspaceId, {
        dataset_version_id: selectedVersionId || context?.dataset_version_id,
        start_time: seekTime || undefined,
        speed_minutes_per_second: speed,
      });
      setReplay(next);
      setSeekTime(next.cursor.simulation_time.slice(0, 16));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Replay를 시작하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function control(
    action: "pause" | "resume" | "reset" | "seek" | "speed",
    payload: { time?: string; speed_minutes_per_second?: number } = {},
  ) {
    if (!replay) return;
    setBusy(true);
    setError("");
    try {
      const next = await controlPredictiveMaintenanceReplay(
        projectId,
        workspaceId,
        replay.cursor.session_id,
        action,
        payload,
      );
      setReplay(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Replay 상태를 변경하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  function changeDatasetVersion(nextVersionId: string) {
    setSelectedVersionId(nextVersionId);
    setSelectedAssetId("");
    setReplay(null);
    setObservations(null);
  }

  if (unsupported) return null;

  return (
    <section className={`pm-replay-panel pm-runtime-mode-${runtimeMode}`} aria-label="Predictive maintenance runtime">
      <header>
        <div>
          <span className="eyebrow">UCI AI4I 2020 · Dataset Version · Result Artifact · Replay</span>
          <strong>{AI4I_V3_1_DATASET_NAME}</strong>
        </div>
        <div className="pm-runtime-header-actions">
          <label>
            <span>Dataset Version</span>
            <select
              aria-label="Predictive maintenance Dataset Version"
              value={selectedVersionId}
              disabled={!versions?.items.length}
              onChange={(event) => changeDatasetVersion(event.target.value)}
            >
              {versions?.items.map((version) => (
                <option key={version.dataset_version_id} value={version.dataset_version_id}>
                  {selectedVersionLabel(versions, version.dataset_version_id)}
                </option>
              ))}
            </select>
          </label>
          <span className={`pm-replay-graph status-${context?.graph.status ?? "loading"}`}>
            {context ? graphStatusLabel(context) : "Resolving Dataset Version"}
          </span>
        </div>
      </header>

      {context ? (
        <>
          <div className="pm-replay-summary" aria-label="Dataset Version provenance">
            <span><small>Source version</small>{context.source_version}</span>
            <span><small>Bundle checksum</small><code title={context.bundle_checksum_sha256}>{compactChecksum(context.bundle_checksum_sha256)}</code></span>
            <span><small>Model</small>{context.model_version ?? "snapshot compatibility"}</span>
            <span><small>Task</small>{context.prediction_task ?? "legacy compatibility"}</span>
            <span><small>Result schema</small>{context.result_artifact_schema_version ?? "not available"}</span>
            <span><small>Latest results</small>{results?.total ?? 0} assets</span>
          </div>

          <div className="pm-status-grid" aria-label="Current risk status">
            {STATUS_ORDER.map((status) => (
              <article key={status} className={`status-${status}`}>
                <small>{status}</small>
                <strong>{statusCounts[status]}</strong>
                <span>assets</span>
              </article>
            ))}
          </div>

          <div className="pm-runtime-layout">
            <section className="pm-risk-list" aria-label="Highest risk assets">
              <header><strong>Highest current risk</strong><small>Result Artifact, not replay history</small></header>
              {highRisk.map((item) => (
                <button
                  key={item.asset_id}
                  type="button"
                  className={selectedAssetId === item.asset_id ? "active" : ""}
                  onClick={() => setSelectedAssetId(item.asset_id)}
                >
                  <span><strong>{item.asset_id}</strong><small>{item.site_id} · {item.cell_id}</small></span>
                  <span><b>{(item.failure_probability * 100).toFixed(1)}%</b><small>{item.status_grade}</small></span>
                </button>
              ))}
              {!highRisk.length ? <p className="pm-empty-state">이 Dataset Version에는 표시할 최신 결과가 없습니다.</p> : null}
            </section>

            <section className="pm-role-detail" aria-label={`${runtimeMode} predictive maintenance detail`}>
              {runtimeMode === "manager" ? (
                <>
                  <header><strong>Recommended review queue</strong><small>Recommendations are not approved or executed WorkOrders.</small></header>
                  <div className="pm-action-summary">
                    {actionSummary.map(([label, count]) => <span key={label}><strong>{count}</strong><small>{label}</small></span>)}
                    {!actionSummary.length ? <p className="pm-empty-state">추천 조치가 없습니다.</p> : null}
                  </div>
                </>
              ) : null}

              {runtimeMode === "engineer" ? (
                <>
                  <header><strong>{selectedResult?.asset_id ?? "Select equipment"} sensor and factor evidence</strong><small>Canonical observations · query-time derived measures</small></header>
                  <div className="pm-factor-list">
                    {selectedResult?.top_factors.map((factor) => (
                      <span key={`${selectedResult.asset_id}:${factor.rank}`}>
                        <strong>{factor.feature}</strong>
                        <small>{factor.direction} · contribution {factor.signed_contribution.toFixed(4)}</small>
                      </span>
                    ))}
                  </div>
                  <div className="pm-derived-grid">
                    {Object.entries(latestObservation?.derived_measures ?? {}).map(([key, value]) => (
                      <span key={key}><small>{key}</small><strong>{Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></span>
                    ))}
                    {!latestObservation ? <p className="pm-empty-state">선택 설비의 센서 구간을 준비하고 있습니다.</p> : null}
                  </div>
                </>
              ) : null}

              {runtimeMode === "model" ? (
                <>
                  <header><strong>Model validation scope</strong><small>Binary failure-within-horizon model</small></header>
                  <dl className="pm-contract-list">
                    <div><dt>Model version</dt><dd>{context.model_version ?? "—"}</dd></div>
                    <div><dt>Prediction task</dt><dd>{context.prediction_task ?? "—"}</dd></div>
                    <div><dt>Result schema</dt><dd>{context.result_artifact_schema_version ?? "—"}</dd></div>
                    <div><dt>Semantic catalog</dt><dd>{context.semantic_catalog_version}</dd></div>
                    <div><dt>Timeline rows</dt><dd>{(context.row_counts.prediction_timeline ?? 0).toLocaleString()}</dd></div>
                    <div><dt>Factor method</dt><dd>{selectedResult?.top_factors[0]?.explanation_method ?? "—"}</dd></div>
                  </dl>
                  <p className="pm-semantic-warning">PWF, HDF, OSF, TWF는 이 runtime 모델의 예측 class가 아닙니다.</p>
                </>
              ) : null}

              {runtimeMode === "governance" ? (
                <>
                  <header><strong>Release and projection evidence</strong><small>Safe aggregate gates only</small></header>
                  <dl className="pm-contract-list">
                    <div><dt>Dataset status</dt><dd>{context.dataset_status}</dd></div>
                    <div><dt>Immutable versions</dt><dd>{versions?.items.length ?? 0}</dd></div>
                    <div><dt>Rollback</dt><dd>{versions?.rollback_supported ? "available" : "not available"}</dd></div>
                    <div><dt>Graph attempts</dt><dd>{context.graph.attempt_count}</dd></div>
                    <div><dt>Tool replacement/reset</dt><dd>{String(context.governance.tool_wear_continuity.tool_replacement_event_count ?? "—")} / {String(context.governance.tool_wear_continuity.aligned_reset_transition_count ?? "—")}</dd></div>
                    <div><dt>False upstream claim rate</dt><dd>{String(context.governance.agent_example_evaluation.false_upstream_claim_rate ?? "—")}</dd></div>
                  </dl>
                  <p className="pm-semantic-warning">Release evidence is governance metadata, not an individual prediction accuracy label.</p>
                </>
              ) : null}
            </section>
          </div>
        </>
      ) : null}

      <section className="pm-replay-workbench" aria-label="Historical replay controls">
        <header><strong>Historical replay</strong><small>Stored observations and precomputed prediction timeline</small></header>
        <div className="pm-replay-cursor">
          <span><small>Simulation time</small>{timeLabel(replay?.cursor.simulation_time)}</span>
          <span><small>Source freshness</small>{timeLabel(replay?.cursor.source_freshness_at)}</span>
          <span><small>Nearest prediction</small>{timeLabel(replay?.nearest_prediction_time)}</span>
          <span><small>State</small>{replay?.cursor.state ?? "not started"}</span>
        </div>
        <div className="pm-replay-controls">
          <label><span>Speed, min/sec</span><input type="number" min="0.1" max="10080" step="1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></label>
          <label><span>Seek time</span><input type="datetime-local" value={seekTime} onChange={(event) => setSeekTime(event.target.value)} /></label>
          {!replay ? (
            <button type="button" className="primary" disabled={!context || busy} onClick={() => void startReplay()}>Start replay</button>
          ) : (
            <>
              {replay.cursor.state === "running" ? (
                <button type="button" disabled={busy} onClick={() => void control("pause")}>Pause</button>
              ) : (
                <button type="button" disabled={busy || replay.cursor.state === "completed"} onClick={() => void control("resume")}>Resume</button>
              )}
              <button type="button" disabled={busy} onClick={() => void control("speed", { speed_minutes_per_second: speed })}>Apply speed</button>
              <button type="button" disabled={busy || !seekTime} onClick={() => void control("seek", { time: new Date(seekTime).toISOString() })}>Seek</button>
              <button type="button" disabled={busy} onClick={() => void control("reset")}>Reset</button>
            </>
          )}
        </div>
      </section>

      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </section>
  );
}
