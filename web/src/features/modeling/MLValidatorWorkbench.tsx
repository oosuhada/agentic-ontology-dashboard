import { useCallback, useEffect, useMemo, useState } from "react";
import {
  activateModel,
  decideModelRelease,
  fetchModelingWorkbench,
  requestModelRelease,
  rollbackModel,
  scoreModel,
} from "./modelingApi";
import type { CandidateResult, ExplanationArtifact, MetricSet, ModelVersion, WorkbenchPayload } from "./types";
import { useAuth } from "../auth/AuthContext";
import { datasetCatalogPath, navigate } from "../../routing";
import "./MLValidatorWorkbench.css";

type Props = { projectId: string; workspaceId: string };
type Tab = "experiments" | "threshold" | "models" | "lineage" | "explanation";

const number = (value: number | null | undefined, digits = 3) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";

function Status({ value }: { value: string }) {
  return <span className={`mlv-status is-${value.replaceAll("_", "-")}`}>{value}</span>;
}

function LinePlot({
  rows,
  xKey,
  series,
  label,
}: {
  rows: Array<Record<string, number>>;
  xKey: string;
  series: Array<{ key: string; label: string }>;
  label: string;
}) {
  if (!rows.length) return <div className="mlv-empty">표시할 curve artifact가 없습니다.</div>;
  const width = 640;
  const height = 220;
  const pad = 28;
  const xValues = rows.map((row) => Number(row[xKey] ?? 0));
  const allY = series.flatMap(({ key }) => rows.map((row) => Number(row[key] ?? 0)));
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMin = Math.min(0, ...allY);
  const yMax = Math.max(1, ...allY);
  const point = (x: number, y: number) => {
    const px = pad + ((x - xMin) / Math.max(1e-9, xMax - xMin)) * (width - pad * 2);
    const py = height - pad - ((y - yMin) / Math.max(1e-9, yMax - yMin)) * (height - pad * 2);
    return `${px},${py}`;
  };
  return (
    <figure className="mlv-plot" aria-label={label}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} />
        <line x1={pad} x2={pad} y1={pad} y2={height - pad} />
        {series.map(({ key, label: seriesLabel }, index) => (
          <polyline
            key={key}
            data-series={seriesLabel}
            className={`series-${index + 1}`}
            points={rows.map((row) => point(Number(row[xKey] ?? 0), Number(row[key] ?? 0))).join(" ")}
          />
        ))}
      </svg>
      <figcaption>
        {series.map((item, index) => <span key={item.key} className={`series-${index + 1}`}>{item.label}</span>)}
      </figcaption>
    </figure>
  );
}

function ConfusionMatrix({ metrics }: { metrics: MetricSet | null }) {
  const matrix = metrics?.confusion_matrix;
  if (!matrix) return <div className="mlv-empty">Confusion Matrix unavailable</div>;
  return (
    <div className="mlv-confusion" aria-label="Confusion matrix">
      <span /> <b>예측 정상</b> <b>예측 위험</b>
      <b>실제 정상</b> <strong>{matrix[0]?.[0] ?? 0}</strong> <strong>{matrix[0]?.[1] ?? 0}</strong>
      <b>실제 위험</b> <strong>{matrix[1]?.[0] ?? 0}</strong> <strong>{matrix[1]?.[1] ?? 0}</strong>
    </div>
  );
}

function Leaderboard({ rows }: { rows: CandidateResult[] }) {
  return (
    <div className="mlv-table-wrap">
      <table className="mlv-table">
        <thead><tr><th>Model</th><th>Status</th><th>PR-AUC</th><th>ROC-AUC</th><th>Precision</th><th>Recall</th><th>F1</th><th>Brier</th><th>Selection</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.candidate_id} className={row.selected ? "is-selected" : ""}>
              <td><strong>{row.algorithm}</strong><small>{row.dependency_version ?? "dependency unavailable"}</small></td>
              <td><Status value={row.status} />{row.error_reason ? <small>{row.error_reason}</small> : null}</td>
              <td>{number(row.validation_metrics?.average_precision)}</td>
              <td>{number(row.validation_metrics?.roc_auc)}</td>
              <td>{number(row.validation_metrics?.precision)}</td>
              <td>{number(row.validation_metrics?.recall)}</td>
              <td>{number(row.validation_metrics?.f1)}</td>
              <td>{number(row.validation_metrics?.brier_score)}</td>
              <td>{row.selected ? "Validation selected" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricCards({ candidate }: { candidate?: CandidateResult }) {
  const metrics = candidate?.validation_metrics;
  const cards = [
    ["Validation PR-AUC", metrics?.average_precision],
    ["Validation Recall", metrics?.recall],
    ["Validation Precision", metrics?.precision],
    ["Validation F1", metrics?.f1],
    ["Held-out PR-AUC", candidate?.held_out_test_metrics?.average_precision],
    ["Held-out Recall", candidate?.held_out_test_metrics?.recall],
  ];
  return <div className="mlv-metrics">{cards.map(([label, value]) => <article key={String(label)}><span>{label}</span><strong>{number(value as number | null)}</strong></article>)}</div>;
}

export function MLValidatorWorkbench({ projectId, workspaceId }: Props) {
  const { user } = useAuth();
  const scope = useMemo(() => ({ projectId, workspaceId }), [projectId, workspaceId]);
  const [payload, setPayload] = useState<WorkbenchPayload | null>(null);
  const [selectedExperiment, setSelectedExperiment] = useState<string>();
  const [selectedModel, setSelectedModel] = useState<string>();
  const [tab, setTab] = useState<Tab>("experiments");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [errorTimestamp, setErrorTimestamp] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [featureText, setFeatureText] = useState("{}");
  const [explanation, setExplanation] = useState<ExplanationArtifact | null>(null);

  const load = useCallback(async (experimentId?: string) => {
    setLoading(true);
    setError("");
    try {
      const result = await fetchModelingWorkbench(scope, experimentId);
      setPayload(result);
      setSelectedExperiment(result.selected_experiment_id ?? undefined);
      setSelectedModel((current) => current ?? result.active_models[0]?.model_version_id ?? result.models[0]?.model_version_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ML Validator Workbench를 불러오지 못했습니다.");
      setErrorTimestamp(new Date().toISOString());
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    setPayload(null);
    setSelectedExperiment(undefined);
    setSelectedModel(undefined);
    setExplanation(null);
    setFeatureText("{}");
    setNotice("");
    setError("");
    setErrorTimestamp(null);
  }, [projectId, workspaceId]);

  useEffect(() => { void load(); }, [load]);

  const selectedCandidate = payload?.leaderboard.find((item) => item.selected);
  const selectedModelRecord = payload?.models.find((item) => item.model_version_id === selectedModel);
  const canRequestRelease = Boolean(user?.permissions.includes("ml.release.request"));
  const canApproveRelease = Boolean(user?.permissions.includes("ml.release.approve"));
  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
      await load(selectedExperiment);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "작업에 실패했습니다.");
    }
  };

  const payloadMatchesScope = Boolean(
    payload
    && payload.scope.project_id === projectId
    && payload.scope.workspace_id === workspaceId,
  );
  if ((loading && !payload) || (payload && !payloadMatchesScope)) return <main className="mlv-shell"><div className="mlv-loading">Experiment artifact와 Model Registry를 불러오는 중입니다.</div></main>;
  if (error && !payload) {
    const reference = `MLW-${Math.abs(Array.from(`${projectId}:${workspaceId}:${errorTimestamp ?? "unknown"}`).reduce((hash, character) => ((hash << 5) - hash) + character.charCodeAt(0), 0)).toString(36).toUpperCase()}`;
    return <main className="mlv-shell"><section className="mlv-error mlv-error-recovery" role="alert"><div><span>ML VALIDATOR UNAVAILABLE</span><strong>모델 검증 Workbench를 불러오지 못했습니다.</strong><p>서버 응답 계약이나 모델링 Runtime을 확인한 뒤 다시 시도하세요. Dataset과 Dashboard는 계속 사용할 수 있습니다.</p></div><dl><div><dt>오류 참조</dt><dd><code>{reference}</code></dd></div><div><dt>발생 시각</dt><dd>{errorTimestamp ? new Date(errorTimestamp).toLocaleString() : "—"}</dd></div><div><dt>기술 메시지</dt><dd>{error}</dd></div></dl><div className="mlv-error-actions"><button onClick={() => void load()}>다시 시도</button><button onClick={() => navigate(datasetCatalogPath(projectId))}>Dataset Browser</button><button onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</button></div></section></main>;
  }

  return (
    <main className="mlv-shell">
      <header className="mlv-header">
        <div><span>ML VALIDATOR · ADAPTIVE MODELING</span><h1>예지보전 모델 검증 Workbench</h1><p>실험 선택과 운영 승격을 분리하고, 모든 판단을 Dataset·Feature·Threshold artifact에 연결합니다.</p></div>
        <div className="mlv-context"><code>{projectId}</code><code>{workspaceId}</code><Status value={payload?.readiness.status ?? "unknown"} /><Status value={payload?.capabilities.artifact_store.status ?? "unknown"} /></div>
      </header>
      {notice ? <div className="mlv-notice">{notice}</div> : null}
      {error ? <div className="mlv-error-inline">{error}</div> : null}
      {payload?.empty ? <section className="mlv-empty-state"><h2>아직 실행된 Experiment가 없습니다.</h2><p>승인된 Mapping Set과 Feature Recipe Set으로 Feature Dataset Version을 만든 뒤 Experiment를 queue하세요.</p></section> : null}
      <section className="mlv-panel"><header><div><span>UPSTREAM READINESS</span><h2>Dataset Intake → Mapping → Feature Dataset</h2></div><p>{payload?.readiness.missing_prerequisites.length ? `Missing: ${payload.readiness.missing_prerequisites.join(", ")}` : "All governed prerequisites are ready."}</p></header><div className="mlv-metrics">{payload?.readiness.steps.map((step) => <article key={step.step}><span>{step.step}</span><strong>{step.status}</strong><small>{step.identity ?? "not created"}</small></article>)}</div><p><strong>Worker:</strong> {payload?.capabilities.worker_health.status} · queued {payload?.capabilities.worker_health.queued_count} · running {payload?.capabilities.worker_health.running_count}</p>{payload?.capabilities.worker_health.reason ? <small>{payload.capabilities.worker_health.reason}</small> : null}</section>
      <section className="mlv-toolbar">
        <label>Experiment<select value={selectedExperiment ?? ""} onChange={(event) => { const id = event.target.value; setSelectedExperiment(id); void load(id); }}>{payload?.experiments.map((item) => <option key={item.experiment_id} value={item.experiment_id}>{item.experiment_id} · {item.status}</option>)}</select></label>
        <div role="tablist">{(["experiments", "threshold", "models", "lineage", "explanation"] as Tab[]).map((item) => <button key={item} role="tab" aria-selected={tab === item} onClick={() => setTab(item)}>{item}</button>)}</div>
      </section>

      {tab === "experiments" ? <>
        <MetricCards candidate={selectedCandidate} />
        <section className="mlv-panel"><header><div><span>MODEL CANDIDATES</span><h2>Validation leaderboard</h2></div><p>Held-out test는 선택된 후보 한 건에만 표시됩니다.</p></header><Leaderboard rows={payload?.leaderboard ?? []} /></section>
        <section className="mlv-grid-two"><article className="mlv-panel"><header><div><span>PRIMARY EVALUATION</span><h2>Validation Precision–Recall</h2></div><p>희소 고장 데이터의 primary ranking curve입니다.</p></header><LinePlot rows={payload?.report.precision_recall_curve ?? []} xKey="recall" series={[{ key: "precision", label: "Precision" }]} label="Validation precision recall curve" /></article><article className="mlv-panel"><header><div><span>SECONDARY EVALUATION</span><h2>Validation ROC</h2></div><p>False-positive rate 대비 true-positive rate를 보조 지표로 확인합니다.</p></header><LinePlot rows={payload?.report.roc_curve ?? []} xKey="false_positive_rate" series={[{ key: "true_positive_rate", label: "True positive rate" }]} label="Validation ROC curve" /></article></section>
        <section className="mlv-grid-two"><article className="mlv-panel"><header><h2>Validation confusion matrix</h2></header><ConfusionMatrix metrics={selectedCandidate?.validation_metrics ?? null} /></article><article className="mlv-panel"><header><h2>Held-out test confusion matrix</h2></header><ConfusionMatrix metrics={selectedCandidate?.held_out_test_metrics ?? null} /></article></section>
      </> : null}

      {tab === "threshold" ? <section className="mlv-grid-two">
        <article className="mlv-panel"><header><h2>Threshold policy</h2><Status value={payload?.report.status ?? "unavailable"} /></header><LinePlot rows={payload?.report.threshold_curve ?? []} xKey="threshold" series={[{ key: "precision", label: "Precision" }, { key: "recall", label: "Recall" }]} label="Threshold precision recall curve" /></article>
        <article className="mlv-panel"><header><h2>Calibration</h2><p>예측 확률과 관측 양성률을 비교합니다.</p></header><LinePlot rows={payload?.report.calibration ?? []} xKey="mean_predicted_probability" series={[{ key: "observed_positive_rate", label: "Observed positive rate" }]} label="Calibration curve" /></article>
        <article className="mlv-panel is-wide"><header><h2>Slice metrics</h2></header><div className="mlv-table-wrap"><table className="mlv-table"><thead><tr><th>Field</th><th>Value</th><th>Available</th><th>PR-AUC</th><th>Recall</th><th>Reason</th></tr></thead><tbody>{(payload?.report.slice_metrics ?? []).map((row, index) => { const metrics = row.metrics as MetricSet | undefined; return <tr key={`${String(row.slice_value)}-${index}`}><td>{String(row.slice_field ?? "—")}</td><td>{String(row.slice_value ?? "—")}</td><td>{String(row.available ?? false)}</td><td>{number(metrics?.average_precision)}</td><td>{number(metrics?.recall)}</td><td>{String(row.reason ?? "—")}</td></tr>; })}</tbody></table></div></article>
      </section> : null}

      {tab === "models" ? <section className="mlv-grid-two">
        <article className="mlv-panel is-wide"><header><h2>Model Registry</h2><p>candidate → approved → active → retired</p></header><div className="mlv-model-list">{payload?.models.map((model) => <div key={model.model_version_id} className={model.model_version_id === selectedModel ? "is-selected" : ""}><button className="mlv-model-main" onClick={() => setSelectedModel(model.model_version_id)}><strong>{model.algorithm}</strong><code>{model.model_version_id}</code><Status value={model.status} /><span>threshold {number(model.threshold_policy.selected_operational_threshold, 2)}</span></button><div className="mlv-actions">{model.status === "candidate" && canRequestRelease ? <button onClick={() => void runAction(() => requestModelRelease(scope, model.model_version_id), "승인 요청을 생성했습니다.")}>승인 요청</button> : null}{model.status === "approved" && canApproveRelease ? <button onClick={() => void runAction(() => activateModel(scope, model.model_version_id, model.revision), "모델을 active로 전환했습니다.")}>활성화</button> : null}{model.status === "retired" && canApproveRelease ? <button onClick={() => void runAction(() => rollbackModel(scope, model.model_version_id), "선택한 모델로 rollback했습니다.")}>Rollback</button> : null}</div></div>)}</div></article>
        <article className="mlv-panel is-wide"><header><h2>Release approvals</h2><p>{canApproveRelease ? "Tenant administrator approval control" : "승인 결정은 tenant administrator에게만 표시됩니다."}</p></header><div className="mlv-release-list">{payload?.release_requests.map((request) => <div key={request.release_request_id}><code>{request.release_request_id}</code><span>{request.model_version_id}</span><Status value={request.status} />{request.status === "pending" && canApproveRelease ? <div><button onClick={() => void runAction(() => decideModelRelease(scope, request.release_request_id, request.revision, "approve"), "모델을 승인했습니다.")}>승인</button><button onClick={() => void runAction(() => decideModelRelease(scope, request.release_request_id, request.revision, "reject"), "모델을 거절했습니다.")}>거절</button></div> : null}</div>)}</div></article>
        <article className="mlv-panel is-wide"><header><h2>Rollback history</h2><p>Model activation audit에서 재구성한 이력입니다.</p></header>{payload?.rollback_history.length ? <pre>{JSON.stringify(payload.rollback_history, null, 2)}</pre> : <div className="mlv-empty">아직 rollback 기록이 없습니다.</div>}</article>
      </section> : null}

      {tab === "lineage" ? <section className="mlv-grid-two">
        <article className="mlv-panel is-wide"><header><h2>Selected experiment lineage</h2></header><dl className="mlv-lineage">{Object.entries(payload?.report.lineage ?? {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd><code>{value}</code></dd></div>)}</dl></article>
        <article className="mlv-panel is-wide"><header><h2>Mapping, recipe and materialization contract</h2><p>승인 상태, group/order/leakage 정책과 artifact checksum을 함께 표시합니다.</p></header><pre>{JSON.stringify(payload?.lineage_detail, null, 2)}</pre></article>
        <article className="mlv-panel"><header><h2>Selection safety</h2></header><ul><li>Validation used for selection: <strong>{String(payload?.report.validation_used_for_selection)}</strong></li><li>Test used for selection: <strong>{String(payload?.report.test_used_for_selection)}</strong></li><li>Synchronous training endpoint: <strong>{String(payload?.capabilities.synchronous_training_endpoint)}</strong></li></ul></article>
        <article className="mlv-panel"><header><h2>Global feature importance</h2><Status value={payload?.global_feature_importance.status ?? "unavailable"} /></header><p>{payload?.global_feature_importance.reason}</p><p>Local contribution과 global importance는 서로 다른 artifact입니다.</p></article>
        <article className="mlv-panel"><header><h2>Operational monitoring</h2><Status value={payload?.operational_monitoring.status ?? "unavailable"} /></header><p>{payload?.operational_monitoring.reason}</p></article>
        <article className="mlv-panel"><header><h2>Limitations</h2></header><ul>{payload?.report.limitations.map((item) => <li key={item}>{item}</li>)}</ul></article>
      </section> : null}

      {tab === "explanation" ? <section className="mlv-grid-two"><article className="mlv-panel"><header><h2>Local explanation input</h2><p>Active Model Version의 정확한 input schema를 사용합니다.</p></header><label>Model<select value={selectedModel ?? ""} onChange={(event) => setSelectedModel(event.target.value)}>{payload?.models.map((model) => <option key={model.model_version_id} value={model.model_version_id}>{model.algorithm} · {model.status}</option>)}</select></label><div className="mlv-feature-tags">{selectedModelRecord?.input_features.map((feature) => <code key={feature}>{feature}</code>)}</div><textarea value={featureText} onChange={(event) => setFeatureText(event.target.value)} rows={10} spellCheck={false} /><button disabled={!selectedModelRecord || selectedModelRecord.status !== "active"} onClick={async () => { if (!selectedModelRecord) return; try { const features = JSON.parse(featureText) as Record<string, unknown>; const result = await scoreModel(scope, selectedModelRecord.model_version_id, selectedModelRecord.input_schema_checksum_sha256, features); setExplanation(result.explanation); setError(""); } catch (reason) { setError(reason instanceof Error ? reason.message : "Scoring failed"); } }}>Active 모델로 설명 생성</button></article><article className="mlv-panel"><header><h2>Explanation Artifact</h2>{explanation ? <Status value={explanation.status} /> : null}</header>{explanation ? <><p><strong>{explanation.provider}</strong> · causal proof: {String(explanation.causal_proof)}</p><ol className="mlv-factors">{explanation.top_factors.map((factor) => <li key={factor.rank}><code>{factor.feature}</code><span>{factor.direction}</span><strong>{number(factor.contribution, 4)}</strong></li>)}</ol>{explanation.unavailable_reason ? <p>{explanation.unavailable_reason}</p> : null}</> : <div className="mlv-empty">아직 생성된 local explanation이 없습니다.</div>}</article></section> : null}
    </main>
  );
}

export function MLValidatorWorkbenchPage() {
  const query = new URLSearchParams(window.location.search);
  const projectId = query.get("project_id") ?? window.localStorage.getItem("activeProjectId") ?? "";
  const workspaceId = query.get("workspace_id") ?? window.localStorage.getItem("activeWorkspaceId") ?? "";
  if (!projectId || !workspaceId) return <main className="mlv-shell"><div className="mlv-error"><strong>Project/Workspace context required</strong><p>`/ml-validator?project_id=...&workspace_id=...` 형태로 열어주세요.</p></div></main>;
  return <MLValidatorWorkbench projectId={projectId} workspaceId={workspaceId} />;
}
