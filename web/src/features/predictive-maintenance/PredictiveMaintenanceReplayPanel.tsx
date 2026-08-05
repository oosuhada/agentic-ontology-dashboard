import { useEffect, useMemo, useState } from "react";
import {
  controlPredictiveMaintenanceReplay,
  getPredictiveMaintenanceLatestResults,
  getPredictiveMaintenanceObservations,
  getPredictiveMaintenanceRuntimeContext,
  getPredictiveMaintenanceVersions,
  predictiveMaintenanceReplayEventsUrl,
  selectPredictiveMaintenanceVersion,
  startPredictiveMaintenanceReplay,
} from "../../api";
import type { AppRole } from "../../types";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { translate, type AppLocale, type MessageKey } from "../../ui/i18n/messages";
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
type Translate = (key: MessageKey, values?: Record<string, string | number>) => string;

const STATUS_ORDER: StatusGrade[] = ["critical", "warning", "attention", "normal"];
export const AI4I_V3_1_DATASET_NAME = "UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1";
const AI4I_V2_DATASET_NAME = "UCI AI4I 2020 Manufacturing Predictive Maintenance — Canonical V2 compatibility snapshot";

export function replayTimestamp(value: string): string | undefined {
  if (!value) return undefined;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}

function timeLabel(value: string | null | undefined, locale: AppLocale): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

function compactChecksum(value: string | null | undefined): string {
  if (!value) return "—";
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

export function graphStatusLabel(context: PredictiveMaintenanceRuntimeContext, locale: AppLocale = "en-US"): string {
  if (context.graph.status === "ready") return translate(locale, "pm.graphReady", { count: context.graph.record_count.toLocaleString(locale) });
  if (context.graph.status === "failed") return translate(locale, "pm.graphDegraded");
  return translate(locale, "pm.graphStatus", { status: context.graph.status });
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

function selectedVersionLabel(versions: PredictiveMaintenanceDatasetVersions | null, id: string, t: Translate): string {
  const item = versions?.items.find((version) => version.dataset_version_id === id);
  if (!item) return id;
  const datasetName = item.is_v3_1
    ? AI4I_V3_1_DATASET_NAME
    : item.source_version.includes("ai4i")
      ? AI4I_V2_DATASET_NAME
      : item.dataset_name;
  return `${datasetName} · ${item.source_version} · v${item.version_number}${item.is_latest ? ` · ${t("pm.latest")}` : ""}`;
}

function displayPolicyToken(value: string, locale: AppLocale): string {
  const normalized = value.trim().toLowerCase();
  const ko: Record<string, string> = {
    immediate: "즉시",
    urgent: "긴급",
    high: "높음",
    medium: "중간",
    routine: "정기",
    inspect_and_schedule_maintenance: "점검 후 정비 일정 수립",
    schedule_maintenance: "정비 일정 수립",
    review_during_next_shift: "다음 교대조 검토",
    continue_monitoring: "모니터링 계속",
  };
  if (locale === "ko-KR" && ko[normalized]) return ko[normalized];
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function recommendationSummary(items: GovernedProductResultSummary[], locale: AppLocale): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const item of items) {
    const recommendation = item.recommended_action;
    if (!recommendation) continue;
    const key = `${displayPolicyToken(recommendation.priority, locale)} · ${displayPolicyToken(recommendation.action, locale)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 5);
}

const FEATURE_KEYS: Record<string, MessageKey> = {
  rotation_raw_6h_mean: "pm.feature.rotation_raw_6h_mean",
  rotation_raw_6h_abs_mean: "pm.feature.rotation_raw_6h_abs_mean",
  rotation_raw_6h_std: "pm.feature.rotation_raw_6h_std",
  power_w: "pm.feature.power_w",
  temperature_gap_k: "pm.feature.temperature_gap_k",
  overstrain_load: "pm.feature.overstrain_load",
};

const MEASURE_KEYS: Record<string, MessageKey> = {
  power_w: "pm.measure.power_w",
  temperature_gap_k: "pm.measure.temperature_gap_k",
  overstrain_load: "pm.measure.overstrain_load",
};

function featureLabel(feature: string, t: Translate): string {
  const key = FEATURE_KEYS[feature];
  return key ? t(key) : feature.replaceAll("_", " ");
}

function measureLabel(measure: string, t: Translate): string {
  const key = MEASURE_KEYS[measure];
  return key ? t(key) : measure.replaceAll("_", " ");
}

function statusLabel(status: StatusGrade, t: Translate): string {
  return t(`pm.status.${status}` as MessageKey);
}

function replayStateLabel(state: string | null | undefined, locale: AppLocale, t: Translate): string {
  if (!state) return t("pm.notStarted");
  if (locale === "en-US") return state.replaceAll("_", " ");
  const labels: Record<string, string> = {
    running: "실행 중",
    paused: "일시정지",
    completed: "완료",
    ready: "준비",
    reset: "초기화",
  };
  return labels[state] ?? state.replaceAll("_", " ");
}

export function PredictiveMaintenanceReplayPanel({
  projectId,
  workspaceId,
  appRole,
}: PredictiveMaintenanceReplayPanelProps) {
  const { locale, t } = useI18n();
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
        setError(reason instanceof Error ? reason.message : t("pm.error.versions"));
      });
    return () => controller.abort();
  }, [projectId, t, workspaceId]);

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
        setError(reason instanceof Error ? reason.message : t("pm.error.runtime"));
      });
    return () => controller.abort();
  }, [projectId, selectedVersionId, t, workspaceId]);

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
          setError(reason instanceof Error ? reason.message : t("pm.error.sensor"));
        }
      });
    return () => controller.abort();
  }, [projectId, runtimeMode, selectedResult, selectedVersionId, t, workspaceId]);

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
  const actionSummary = useMemo(() => recommendationSummary(results?.items ?? [], locale), [locale, results]);
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
        start_time: replayTimestamp(seekTime),
        speed_minutes_per_second: speed,
      });
      setReplay(next);
      setSeekTime(next.cursor.simulation_time.slice(0, 16));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("pm.error.startReplay"));
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
      setError(reason instanceof Error ? reason.message : t("pm.error.controlReplay"));
    } finally {
      setBusy(false);
    }
  }

  async function changeDatasetVersion(nextVersionId: string) {
    setBusy(true);
    setError("");
    try {
      const nextVersions = await selectPredictiveMaintenanceVersion(projectId, workspaceId, nextVersionId);
      setVersions(nextVersions);
      setSelectedVersionId(nextVersionId);
      setSelectedAssetId("");
      setReplay(null);
      setObservations(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("pm.error.selectVersion"));
    } finally {
      setBusy(false);
    }
  }

  if (unsupported) return null;

  return (
    <section className={`pm-replay-panel pm-runtime-mode-${runtimeMode}`} aria-label={t("pm.aria.runtime")}>
      <header>
        <div>
          <span className="eyebrow">{t("pm.eyebrow")}</span>
          <strong>{AI4I_V3_1_DATASET_NAME}</strong>
        </div>
        <div className="pm-runtime-header-actions">
          <label>
            <span>{t("pm.datasetVersion")}</span>
            <select
              aria-label={t("pm.datasetVersionAria")}
              value={selectedVersionId}
              disabled={!versions?.items.length}
              onChange={(event) => void changeDatasetVersion(event.target.value)}
            >
              {versions?.items.map((version) => (
                <option key={version.dataset_version_id} value={version.dataset_version_id}>
                  {selectedVersionLabel(versions, version.dataset_version_id, t)}
                </option>
              ))}
            </select>
          </label>
          <span className={`pm-replay-graph status-${context?.graph.status ?? "loading"}`}>
            {context ? graphStatusLabel(context, locale) : t("pm.resolvingDataset")}
          </span>
        </div>
      </header>

      {context ? (
        <>
          <div className="pm-replay-summary" aria-label={t("pm.provenance")}>
            <span><small>{t("pm.datasetVersionId")}</small><code>{context.dataset_version_id}</code></span>
            <span><small>{t("pm.sourceVersion")}</small>{context.source_version}</span>
            <span><small>{t("pm.bundleChecksum")}</small><code title={context.bundle_checksum_sha256}>{compactChecksum(context.bundle_checksum_sha256)}</code></span>
            <span><small>{t("pm.model")}</small>{context.model_version ?? t("pm.snapshotCompatibility")}</span>
            <span><small>{t("pm.task")}</small>{context.prediction_task ?? t("pm.legacyCompatibility")}</span>
            <span><small>{t("pm.resultSchema")}</small>{context.result_artifact_schema_version ?? t("pm.notAvailableValue")}</span>
            <span><small>{t("pm.latestResults")}</small>{(results?.total ?? 0).toLocaleString(locale)} {t("pm.assets")}</span>
          </div>

          <div className="pm-status-grid" aria-label={t("pm.currentRiskStatus")}>
            {STATUS_ORDER.map((status) => (
              <article key={status} className={`status-${status}`}>
                <small>{statusLabel(status, t)}</small>
                <strong>{statusCounts[status]}</strong>
                <span>{t("pm.assets")}</span>
              </article>
            ))}
          </div>

          <div className="pm-runtime-layout">
            <section className="pm-risk-list" aria-label={t("pm.highestCurrentRisk")}>
              <header><strong>{t("pm.highestCurrentRisk")}</strong><small>{t("pm.currentRiskDetail")}</small></header>
              {highRisk.map((item) => (
                <button
                  key={item.asset_id}
                  type="button"
                  className={selectedAssetId === item.asset_id ? "active" : ""}
                  onClick={() => setSelectedAssetId(item.asset_id)}
                >
                  <span><strong>{item.asset_id}</strong><small>{item.site_id} · {item.cell_id}</small></span>
                  <span><b>{(item.failure_probability * 100).toFixed(1)}%</b><small>{statusLabel(item.status_grade, t)}</small></span>
                </button>
              ))}
              {!highRisk.length ? <p className="pm-empty-state">{t("pm.noLatestResults")}</p> : null}
            </section>

            <section className="pm-role-detail" aria-label={`${runtimeMode} predictive maintenance detail`}>
              {runtimeMode === "manager" ? (
                <>
                  <header><strong>{t("pm.recommendedQueue")}</strong><small>{t("pm.recommendedQueueDetail")}</small></header>
                  <div className="pm-action-summary">
                    {actionSummary.map(([label, count]) => <span key={label}><strong>{count}</strong><small>{label}</small></span>)}
                    {!actionSummary.length ? <p className="pm-empty-state">{t("pm.noRecommendations")}</p> : null}
                  </div>
                </>
              ) : null}

              {runtimeMode === "engineer" ? (
                <>
                  <header><strong>{t("pm.sensorFactorEvidence", { asset: selectedResult?.asset_id ?? t("pm.selectEquipment") })}</strong><small>{t("pm.sensorFactorDetail")}</small></header>
                  <div className="pm-factor-list">
                    {selectedResult?.top_factors.map((factor) => (
                      <span key={`${selectedResult.asset_id}:${factor.rank}`}>
                        <strong title={factor.feature}>{featureLabel(factor.feature, t)}</strong>
                        <small>{t(`pm.direction.${factor.direction}` as MessageKey)} · {t("pm.contribution")} {factor.signed_contribution.toFixed(4)}</small>
                      </span>
                    ))}
                  </div>
                  <div className="pm-derived-grid">
                    {Object.entries(latestObservation?.derived_measures ?? {}).map(([key, value]) => (
                      <span key={key}><small title={key}>{measureLabel(key, t)}</small><strong>{Number(value).toLocaleString(locale, { maximumFractionDigits: 2 })}</strong></span>
                    ))}
                    {!latestObservation ? <p className="pm-empty-state">{t("pm.preparingSensor")}</p> : null}
                  </div>
                </>
              ) : null}

              {runtimeMode === "model" ? (
                <>
                  <header><strong>{t("pm.modelValidationScope")}</strong><small>{t("pm.binaryModel")}</small></header>
                  <dl className="pm-contract-list">
                    <div><dt>{t("pm.modelVersion")}</dt><dd>{context.model_version ?? "—"}</dd></div>
                    <div><dt>{t("pm.predictionTask")}</dt><dd>{context.prediction_task ?? "—"}</dd></div>
                    <div><dt>{t("pm.resultSchema")}</dt><dd>{context.result_artifact_schema_version ?? "—"}</dd></div>
                    <div><dt>{t("pm.semanticCatalog")}</dt><dd>{context.semantic_catalog_version}</dd></div>
                    <div><dt>{t("pm.timelineRows")}</dt><dd>{(context.row_counts.prediction_timeline ?? 0).toLocaleString(locale)}</dd></div>
                    <div><dt>{t("pm.factorMethod")}</dt><dd>{selectedResult?.top_factors[0]?.explanation_method ?? "—"}</dd></div>
                  </dl>
                  <p className="pm-semantic-warning">{t("pm.notApplicableClasses")}</p>
                </>
              ) : null}

              {runtimeMode === "governance" ? (
                <>
                  <header><strong>{t("pm.releaseProjectionEvidence")}</strong><small>{t("pm.safeAggregateGates")}</small></header>
                  <dl className="pm-contract-list">
                    <div><dt>{t("pm.datasetStatus")}</dt><dd>{displayPolicyToken(context.dataset_status, locale)}</dd></div>
                    <div><dt>{t("pm.immutableVersions")}</dt><dd>{versions?.items.length ?? 0}</dd></div>
                    <div><dt>{t("pm.rollback")}</dt><dd>{versions?.rollback_supported ? t("pm.available") : t("pm.notAvailable")}</dd></div>
                    <div><dt>{t("pm.graphAttempts")}</dt><dd>{context.graph.attempt_count}</dd></div>
                    <div><dt>{t("pm.toolReplacementReset")}</dt><dd>{String(context.governance.tool_wear_continuity.tool_replacement_event_count ?? "—")} / {String(context.governance.tool_wear_continuity.aligned_reset_transition_count ?? "—")}</dd></div>
                    <div><dt>{t("pm.falseUpstreamClaimRate")}</dt><dd>{String(context.governance.agent_example_evaluation.false_upstream_claim_rate ?? "—")}</dd></div>
                  </dl>
                  <p className="pm-semantic-warning">{t("pm.releaseMetadataWarning")}</p>
                </>
              ) : null}
            </section>
          </div>
        </>
      ) : null}

      <section className="pm-replay-workbench" aria-label={t("pm.historicalReplay")}>
        <header><strong>{t("pm.historicalReplay")}</strong><small>{t("pm.historicalReplayDetail")}</small></header>
        <div className="pm-replay-cursor">
          <span><small>{t("pm.simulationTime")}</small>{timeLabel(replay?.cursor.simulation_time, locale)}</span>
          <span><small>{t("pm.sourceFreshness")}</small>{timeLabel(replay?.cursor.source_freshness_at, locale)}</span>
          <span><small>{t("pm.nearestPrediction")}</small>{timeLabel(replay?.nearest_prediction_time, locale)}</span>
          <span><small>{t("pm.state")}</small>{replayStateLabel(replay?.cursor.state, locale, t)}</span>
        </div>
        <div className="pm-replay-controls">
          <label><span>{t("pm.speed")}</span><input type="number" min="0.1" max="10080" step="1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></label>
          <label><span>{t("pm.seekTime")}</span><input type="datetime-local" value={seekTime} onChange={(event) => setSeekTime(event.target.value)} /></label>
          {!replay ? (
            <button type="button" className="primary" disabled={!context || busy} onClick={() => void startReplay()}>{t("pm.startReplay")}</button>
          ) : (
            <>
              {replay.cursor.state === "running" ? (
                <button type="button" disabled={busy} onClick={() => void control("pause")}>{t("pm.pause")}</button>
              ) : (
                <button type="button" disabled={busy || replay.cursor.state === "completed"} onClick={() => void control("resume")}>{t("pm.resume")}</button>
              )}
              <button type="button" disabled={busy} onClick={() => void control("speed", { speed_minutes_per_second: speed })}>{t("pm.applySpeed")}</button>
              <button type="button" disabled={busy || !seekTime} onClick={() => void control("seek", { time: replayTimestamp(seekTime) })}>{t("pm.seek")}</button>
              <button type="button" disabled={busy} onClick={() => void control("reset")}>{t("pm.reset")}</button>
            </>
          )}
        </div>
      </section>

      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </section>
  );
}
