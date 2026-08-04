import { Download, LayoutDashboard, Play, Square } from "lucide-react";
import type { ReactNode } from "react";

interface AnalysisShellProps {
  analysisId: string;
  revision: number;
  notice: string;
  showInspector: boolean;
  rail: ReactNode;
  canvas: ReactNode;
  inspector: ReactNode;
  canAddToDashboard: boolean;
  canSaveDataset: boolean;
  running: boolean;
  runProgress: number;
  onRun: () => void;
  onCancelRun: () => void;
  onSaveDataset: () => void;
  onAddToDashboard: () => void;
  onToggleInspector: () => void;
}

export function AnalysisShell({
  analysisId,
  revision,
  notice,
  showInspector,
  rail,
  canvas,
  inspector,
  canAddToDashboard,
  canSaveDataset,
  running,
  runProgress,
  onRun,
  onCancelRun,
  onSaveDataset,
  onAddToDashboard,
  onToggleInspector,
}: AnalysisShellProps) {
  return (
    <section className={`analysis-workbench flow-workbench ${showInspector ? "with-result-inspector" : ""}`}>
      <header className="analysis-workbench-header">
        <div><span className="eyebrow">ANALYSIS WORKBENCH</span><h2>Risk Event Portfolio Analysis</h2><p>{analysisId} · Object 변형, 결과 검증, 시각화와 lineage를 구성합니다.</p></div>
        <div className="analysis-run-actions">
          <span className="od-tag intent-primary">Draft · Revision {revision}</span>
          <button type="button" className="secondary" onClick={onToggleInspector}>{showInspector ? "Hide inspector" : "Show inspector"}</button>
          <button type="button" className="secondary" disabled={!canSaveDataset} title={canSaveDataset ? "Save immutable Dataset Version" : "datasets.ingest permission required"} onClick={onSaveDataset}><Download size={13} /> Save dataset</button>
          <button type="button" className="secondary" disabled={!canAddToDashboard} onClick={onAddToDashboard}><LayoutDashboard size={13} /> Add to Dashboard</button>
          {running ? (
            <button type="button" className="secondary" onClick={onCancelRun}><Square size={13} /> Cancel · {runProgress}%</button>
          ) : (
            <button type="button" className="primary" onClick={onRun}><Play size={13} /> Run path</button>
          )}
        </div>
      </header>
      <div className="analysis-notice">{notice}</div>
      <div className="analysis-workbench-grid flow-grid">
        {rail}
        {canvas}
        {showInspector ? inspector : null}
      </div>
    </section>
  );
}
