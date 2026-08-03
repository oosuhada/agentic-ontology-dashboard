import { Activity, CalendarRange, Check, ChevronDown, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { DataPill } from "../../ui/foundry/DataPill";
import type { AnalysisNodeExecutionResult, AnalysisResult } from "./types";

type ForecastModel = "Linear" | "Constant" | "Seasonal";

interface AnalysisTimeSeriesForecastProps {
  result: AnalysisResult;
  serverResult?: AnalysisNodeExecutionResult;
}

function numericSeries(result: AnalysisResult, serverResult?: AnalysisNodeExecutionResult) {
  const serverValues = (serverResult?.rows ?? []).map((row) => Number(row.value ?? row.average_risk ?? row.risk ?? row.metric)).filter(Number.isFinite);
  if (serverValues.length >= 3) return serverValues.slice(0, 24).map((value) => value <= 1 ? value * 100 : value);
  const grouped = result.grouped.map((group) => group.averageRisk * 100);
  if (grouped.length >= 3) return grouped;
  return [42, 46, 44, 53, 58, 56, 64, 69, 67, 74, 72, 78];
}

function forecastValue(model: ForecastModel, index: number, last: number, slope: number, seasonality: number) {
  if (model === "Constant") return last;
  if (model === "Seasonal") return last + slope * index + Math.sin(index * Math.PI / 2) * seasonality;
  return last + slope * index;
}

export function AnalysisTimeSeriesForecast({ result, serverResult }: AnalysisTimeSeriesForecastProps) {
  const values = useMemo(() => numericSeries(result, serverResult), [result, serverResult]);
  const [rangeStart, setRangeStart] = useState(0);
  const [rangeEnd, setRangeEnd] = useState(values.length - 1);
  const [forecastEnabled, setForecastEnabled] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [model, setModel] = useState<ForecastModel>("Linear");
  const [horizon, setHorizon] = useState(6);
  const [confidence, setConfidence] = useState(90);
  const [slope, setSlope] = useState(1.8);
  const [seasonality, setSeasonality] = useState(4);
  const [eventMarkers, setEventMarkers] = useState(true);
  const width = 560;
  const height = 230;
  const left = 38;
  const top = 20;
  const bottom = 34;
  const plotWidth = width - left - 18;
  const plotHeight = height - top - bottom;
  const projected = forecastEnabled ? Array.from({ length: horizon }, (_, index) => forecastValue(model, index + 1, values[values.length - 1], slope, seasonality)) : [];
  const allValues = [...values, ...projected];
  const min = Math.min(...allValues) - 8;
  const max = Math.max(...allValues) + 8;
  const x = (index: number) => left + index * (plotWidth / Math.max(1, allValues.length - 1));
  const y = (value: number) => top + (max - value) / Math.max(1, max - min) * plotHeight;
  const actualPoints = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const forecastPoints = projected.length ? [values[values.length - 1], ...projected].map((value, index) => `${x(values.length - 1 + index)},${y(value)}`).join(" ") : "";
  const confidenceWidth = Math.max(3, (100 - confidence) * .38 + 4);
  const upper = projected.length ? [values[values.length - 1], ...projected].map((value, index) => `${x(values.length - 1 + index)},${y(value + confidenceWidth * index)}`).join(" ") : "";
  const lower = projected.length ? [values[values.length - 1], ...projected].map((value, index) => ({ value, index })).reverse().map(({ value, index }) => `${x(values.length - 1 + index)},${y(value - confidenceWidth * index)}`).join(" ") : "";
  const rangeLeft = x(rangeStart);
  const rangeRight = x(rangeEnd);

  return (
    <section className="analysis-timeseries-forecast">
      <header><div><DataPill kind="time-series" /><span><strong>Operational risk over time</strong><small>{serverResult ? "Server result rows" : "Client preview rows"} · presentation-only forecast settings</small></span></div><button type="button" onClick={() => setEditorOpen((value) => !value)}><SlidersHorizontal size={12} /> Forecast settings <ChevronDown size={11} /></button></header>
      <div className="analysis-timeseries-chart">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Time series with selected range, forecast, confidence band, and event markers">
          {[0, .25, .5, .75, 1].map((ratio) => <line key={ratio} x1={left} x2={width - 18} y1={top + plotHeight * ratio} y2={top + plotHeight * ratio} className="forecast-gridline" />)}
          <rect x={rangeLeft} y={top} width={Math.max(2, rangeRight - rangeLeft)} height={plotHeight} className="forecast-range" />
          {forecastEnabled && projected.length ? <polygon points={`${upper} ${lower}`} className="forecast-confidence" /> : null}
          <polyline points={actualPoints} className="forecast-actual-line" />
          {forecastEnabled && projected.length ? <><line x1={x(values.length - 1)} x2={x(values.length - 1)} y1={top} y2={top + plotHeight} className="forecast-divider" /><polyline points={forecastPoints} className="forecast-projected-line" /><text x={x(values.length - 1) + 7} y={top + 13} className="forecast-divider-label">Forecast</text></> : null}
          {eventMarkers ? [2, Math.max(3, values.length - 3)].filter((index) => index < values.length).map((index) => <g key={index}><line x1={x(index)} x2={x(index)} y1={top + 10} y2={top + plotHeight} className="forecast-event-line" /><circle cx={x(index)} cy={y(values[index])} r="4" className="forecast-event-dot" /><text x={x(index) + 5} y={top + 24} className="forecast-event-label">Event {index + 1}</text></g>) : null}
        </svg>
      </div>
      <div className="analysis-range-controls">
        <label><span>Training range start</span><input aria-label="Training range start" type="range" min="0" max={Math.max(0, values.length - 2)} value={rangeStart} onChange={(event) => setRangeStart(Math.min(Number(event.currentTarget.value), rangeEnd - 1))} /></label>
        <label><span>Training range end</span><input aria-label="Training range end" type="range" min="1" max={values.length - 1} value={rangeEnd} onChange={(event) => setRangeEnd(Math.max(Number(event.currentTarget.value), rangeStart + 1))} /></label>
        <div><CalendarRange size={12} /><span>{rangeStart + 1} → {rangeEnd + 1}</span><button type="button" onClick={() => { setRangeStart(0); setRangeEnd(values.length - 1); }}>Full range</button></div>
      </div>
      <div className="analysis-forecast-summary"><label><input type="checkbox" checked={forecastEnabled} onChange={(event) => setForecastEnabled(event.currentTarget.checked)} /> Enable forecast</label><label><input type="checkbox" checked={eventMarkers} onChange={(event) => setEventMarkers(event.currentTarget.checked)} /> Event markers</label><span><Activity size={11} /> {model} · {horizon} periods · {confidence}% interval</span></div>
      {editorOpen ? <div className="analysis-forecast-editor">
        <label><span>Model</span><select value={model} onChange={(event) => setModel(event.currentTarget.value as ForecastModel)}><option>Linear</option><option>Constant</option><option>Seasonal</option></select></label>
        <label><span>Forecast periods</span><input type="number" min="1" max="24" value={horizon} onChange={(event) => setHorizon(Math.max(1, Math.min(24, Number(event.currentTarget.value))))} /></label>
        <label><span>Confidence interval</span><select value={confidence} onChange={(event) => setConfidence(Number(event.currentTarget.value))}><option value="80">80%</option><option value="90">90%</option><option value="95">95%</option><option value="99">99%</option></select></label>
        <label><span>Slope coefficient</span><input type="number" step="0.1" value={slope} onChange={(event) => setSlope(Number(event.currentTarget.value))} /></label>
        {model === "Seasonal" ? <label><span>Seasonality amplitude</span><input type="number" step="0.5" value={seasonality} onChange={(event) => setSeasonality(Number(event.currentTarget.value))} /></label> : null}
        <footer><span>UI preview; authoritative forecast values must come from the Prediction Result Contract.</span><button type="button" onClick={() => setEditorOpen(false)}><Check size={11} /> Apply</button></footer>
      </div> : null}
    </section>
  );
}
