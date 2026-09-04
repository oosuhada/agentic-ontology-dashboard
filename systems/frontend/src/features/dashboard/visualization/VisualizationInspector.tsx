import { Check, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { recommendVisualization } from "../../../api";
import type { VisualizationPlannerResponse } from "../../planner/types";
import type { BoardVisualizationRuntime, DashboardBoard, VisualizationKind, VisualizationSettings } from "../types";
import { VisualizationKindMark } from "./VisualizationKindMark";
import { visualizationDefinition, VISUALIZATION_REGISTRY } from "./visualizationRegistry";
import { visualizationSettings } from "./visualizationProfile";

interface VisualizationInspectorProps {
  board: DashboardBoard;
  runtime: BoardVisualizationRuntime | null;
  workspaceId: string;
  dashboardId: string;
  onUpdate: (settings: VisualizationSettings) => void;
}

export function VisualizationInspector({ board, runtime, workspaceId, dashboardId, onUpdate }: VisualizationInspectorProps) {
  const [goal, setGoal] = useState("");
  const [plannerResult, setPlannerResult] = useState<VisualizationPlannerResponse | null>(null);
  const [plannerBusy, setPlannerBusy] = useState(false);
  const [plannerError, setPlannerError] = useState("");
  const settings = visualizationSettings(board.settings.visualization);
  const fields = runtime?.recommendation.profile ?? [];
  const activeKind = runtime?.active_kind ?? settings.kind ?? "table";
  const mapping = settings.field_mapping ?? runtime?.recommendation.recommended.field_mapping ?? {};
  const update = (patch: Partial<VisualizationSettings>) => onUpdate({ ...settings, ...patch, version: 1 });
  const updateMapping = (key: keyof NonNullable<VisualizationSettings["field_mapping"]>, value: string) => update({
    mode: "manual",
    kind: activeKind,
    field_mapping: { ...mapping, [key]: value || undefined },
    recommendation_revision: runtime?.recommendation.profile_hash,
  });
  const candidateByKind = new Map([
    ...(runtime ? [[runtime.recommendation.recommended.kind, runtime.recommendation.recommended.rationale] as const] : []),
    ...(runtime?.recommendation.alternatives.map((item) => [item.kind, item.rationale] as const) ?? []),
  ]);

  return (
    <section className="inspector-section visualization-inspector" id="board-visualization">
      <div className="visualization-inspector-heading">
        <span className="section-label">Visualization</span>
        <span className={`visualization-mode-pill is-${settings.mode}`}><Sparkles size={10} />{settings.mode}</span>
      </div>
      <label className="context-field">Mode
        <select value={settings.mode} onChange={(event) => update({ mode: event.target.value as VisualizationSettings["mode"] })}>
          <option value="auto">Auto recommendation</option>
          <option value="manual">Manual override</option>
        </select>
      </label>
      <div className="visualization-inspector-chart-picker" role="group" aria-label="Chart type">
        <span className="context-field-label">Chart type</span>
        <div className="visualization-inspector-chart-grid">
          {VISUALIZATION_REGISTRY.map((item) => {
            const unavailable = runtime?.recommendation.unavailable.find((candidate) => candidate.kind === item.kind);
            const reasonId = `visualization-inspector-${board.id}-${item.kind}-reason`;
            return (
              <button
                key={item.kind}
                type="button"
                className={activeKind === item.kind ? "is-selected" : ""}
                aria-pressed={activeKind === item.kind}
                aria-disabled={Boolean(unavailable)}
                aria-describedby={reasonId}
                onClick={() => {
                  if (unavailable) return;
                  update({ mode: "manual", kind: item.kind as VisualizationKind, recommendation_revision: runtime?.recommendation.profile_hash });
                }}
              >
                <VisualizationKindMark kind={item.kind} />
                <span><strong>{item.displayName}</strong><small id={reasonId}>{unavailable?.reason ?? candidateByKind.get(item.kind) ?? item.intent}</small></span>
                {activeKind === item.kind ? <Check size={12} /> : null}
              </button>
            );
          })}
        </div>
      </div>
      {runtime ? (
        <div className="visualization-rationale">
          <strong>Why {visualizationDefinition(runtime.recommendation.recommended.kind).shortName}?</strong>
          <p>{runtime.recommendation.recommended.rationale}</p>
          <ul>{runtime.recommendation.recommended.reason_codes.map((reason) => <li key={reason}>{reason.replaceAll("_", " ")}</li>)}</ul>
          <small>Deterministic profile · registry v1 · {runtime.recommendation.profile_hash}</small>
        </div>
      ) : null}
      {runtime ? (
        <div className="visualization-ai-section">
          <label className="context-field">AI intent hint
            <textarea value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="예: 시간에 따른 위험도 변화와 라인별 차이를 강조" />
          </label>
          <button
            type="button"
            disabled={plannerBusy || goal.trim().length < 2}
            onClick={() => {
              setPlannerBusy(true);
              setPlannerError("");
              void recommendVisualization({
                workspace_id: workspaceId,
                dashboard_id: dashboardId,
                board_id: board.id,
                goal: goal.trim(),
                field_profile: runtime.recommendation.profile,
                deterministic_candidates: [runtime.recommendation.recommended, ...runtime.recommendation.alternatives],
              })
                .then(setPlannerResult)
                .catch((reason: unknown) => setPlannerError(reason instanceof Error ? reason.message : String(reason)))
                .finally(() => setPlannerBusy(false));
            }}
          >
            <Sparkles size={12} /> {plannerBusy ? "Planner reviewing…" : "Ask Planner"}
          </button>
          {plannerError ? <small className="visualization-ai-error">{plannerError}</small> : null}
          {plannerResult ? (
            <div className="visualization-ai-result">
              <div className="visualization-ai-preview">
                <VisualizationKindMark kind={plannerResult.recommended.kind} />
                <span><strong>{visualizationDefinition(plannerResult.recommended.kind).displayName}</strong><small>{Object.entries(plannerResult.recommended.field_mapping).filter(([, value]) => Boolean(value)).map(([channel, value]) => `${channel}: ${value}`).join(" · ") || "Automatic field mapping"}</small></span>
              </div>
              <span>{plannerResult.mode} · {plannerResult.provider}</span>
              <p>{plannerResult.recommended.rationale}</p>
              <button type="button" onClick={() => onUpdate({
                ...settings,
                version: 1,
                mode: "manual",
                kind: plannerResult.recommended.kind,
                field_mapping: plannerResult.recommended.field_mapping,
                recommendation_revision: runtime.recommendation.profile_hash,
              })}>Apply recommendation</button>
            </div>
          ) : null}
        </div>
      ) : null}
      {settings.mode === "manual" ? (
        <>
          <div className="visualization-field-grid">
            {(["x", "y", "value", "series"] as const).map((channel) => (
              <label key={channel} className="context-field">{channel.toUpperCase()}
                <select value={mapping[channel] ?? ""} onChange={(event) => updateMapping(channel, event.target.value)}>
                  <option value="">Auto</option>
                  {fields.map((field) => <option key={field.id} value={field.id}>{field.id} · {field.semantic_type}</option>)}
                </select>
              </label>
            ))}
          </div>
          <label className="context-field">Aggregation
            <select value={settings.aggregation ?? "avg"} onChange={(event) => update({ aggregation: event.target.value as VisualizationSettings["aggregation"] })}>
              <option value="count">Count</option><option value="sum">Sum</option><option value="avg">Average</option><option value="min">Minimum</option><option value="max">Maximum</option>
            </select>
          </label>
          <div className="visualization-field-grid">
            <label className="context-field">Orientation<select value={settings.orientation ?? "vertical"} onChange={(event) => update({ orientation: event.target.value as VisualizationSettings["orientation"] })}><option value="vertical">Vertical</option><option value="horizontal">Horizontal</option></select></label>
            <label className="context-field">Stack<select value={settings.stack ?? "off"} onChange={(event) => update({ stack: event.target.value as VisualizationSettings["stack"] })}><option value="off">Off</option><option value="normal">Normal</option><option value="percent">Percent</option></select></label>
            <label className="context-field">Legend<select value={settings.legend ?? "auto"} onChange={(event) => update({ legend: event.target.value as VisualizationSettings["legend"] })}><option value="auto">Auto</option><option value="show">Show</option><option value="hide">Hide</option></select></label>
            <label className="context-field">Labels<select value={settings.labels ?? "auto"} onChange={(event) => update({ labels: event.target.value as VisualizationSettings["labels"] })}><option value="auto">Auto</option><option value="show">Show</option><option value="hide">Hide</option></select></label>
            <label className="context-field">Curve<select value={settings.curve ?? "smooth"} onChange={(event) => update({ curve: event.target.value as VisualizationSettings["curve"] })}><option value="straight">Straight</option><option value="smooth">Smooth</option><option value="step">Step</option></select></label>
            <label className="context-field">Color<select value={settings.color_strategy ?? "categorical"} onChange={(event) => update({ color_strategy: event.target.value as VisualizationSettings["color_strategy"] })}><option value="categorical">Categorical</option><option value="semantic">Semantic</option><option value="single_accent">Single accent</option></select></label>
          </div>
          <button type="button" className="visualization-inspector-reset" onClick={() => onUpdate({ version: 1, mode: "auto", recommendation_revision: runtime?.recommendation.profile_hash })}><RotateCcw size={12} /> Reset to Auto</button>
        </>
      ) : <button type="button" className="visualization-edit-manually" onClick={() => update({ mode: "manual", kind: activeKind })}>Edit manually</button>}
    </section>
  );
}
