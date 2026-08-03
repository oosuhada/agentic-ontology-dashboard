import { Download, LayoutDashboard, PanelRight, Play, Save, Share2, Square, Workflow } from "lucide-react";
import type { ReactNode } from "react";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { FoundryDrawer } from "../../ui/foundry/FoundryDrawer";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader } from "../../ui/foundry/WorkbenchChrome";
import { useMediaQuery } from "../../ui/foundry/useMediaQuery";
import { useI18n } from "../../ui/i18n/I18nProvider";

interface AnalysisShellProps {
  analysisId: string;
  revision: number;
  notice: string;
  dirty: boolean;
  showInspector: boolean;
  rail: ReactNode;
  canvas: ReactNode;
  inspector: ReactNode;
  canAddToDashboard: boolean;
  canSaveDataset: boolean;
  running: boolean;
  busy: boolean;
  runProgress: number;
  onRun: () => void;
  onCancelRun: () => void;
  onSave: () => void;
  onShare: () => void;
  onSaveDataset: () => void;
  onAddToDashboard: () => void;
  onToggleInspector: () => void;
}

export function AnalysisShell({
  analysisId,
  revision,
  notice,
  dirty,
  showInspector,
  rail,
  canvas,
  inspector,
  canAddToDashboard,
  canSaveDataset,
  running,
  busy,
  runProgress,
  onRun,
  onCancelRun,
  onSave,
  onShare,
  onSaveDataset,
  onAddToDashboard,
  onToggleInspector,
}: AnalysisShellProps) {
  const isMobile = useMediaQuery("(max-width: 760px)");
  const { t } = useI18n();
  return (
    <section className={`analysis-workbench flow-workbench ${showInspector ? "with-result-inspector" : ""}`}>
      <WorkbenchHeader
        className="analysis-workbench-header"
        title={<EntityTitle
          icon={Workflow}
          eyebrow="CONTOUR ANALYSIS"
          title="Risk Event Portfolio Analysis"
          subtitle={`${analysisId} · governed object transforms and result lineage`}
          trailing={<StatusPill intent={running ? "primary" : dirty ? "warning" : "success"}>{running ? `Running ${runProgress}%` : dirty ? "Unsaved" : "Saved"}</StatusPill>}
        />}
        metadata={<div className="analysis-resource-meta"><span>Revision {revision}</span><span>UTC+09:00</span><span>pinned inputs</span></div>}
        actions={<div className="analysis-run-actions">
          <button type="button" className="fd-toolbar-button icon-only" aria-label={showInspector ? "Hide inspector" : "Show inspector"} title={showInspector ? "Hide inspector" : "Show inspector"} onClick={onToggleInspector}><PanelRight size={13} /></button>
          <button type="button" className="fd-toolbar-button" disabled={!dirty || busy} onClick={onSave}><Save size={13} /> {t("common.save")}</button>
          <button type="button" className="fd-toolbar-button" onClick={onShare}><Share2 size={13} /> {t("common.share")}</button>
          <button type="button" className="fd-toolbar-button" disabled={!canSaveDataset} title={canSaveDataset ? t("analysis.saveDataset") : "datasets.ingest permission required"} onClick={onSaveDataset}><Download size={13} /> {t("analysis.saveDataset")}</button>
          <button type="button" className="fd-toolbar-button" disabled={!canAddToDashboard} onClick={onAddToDashboard}><LayoutDashboard size={13} /> Add to Dashboard</button>
          {running ? (
            <button type="button" className="fd-toolbar-button" onClick={onCancelRun}><Square size={13} /> Cancel</button>
          ) : (
            <button type="button" className="fd-toolbar-button primary" disabled={busy} onClick={onRun}><Play size={13} /> Run path</button>
          )}
        </div>}
      />
      <div className={`analysis-notice ${running ? "is-running" : ""}`} role="status">
        <span>{notice}</span>
        {running ? <i style={{ width: `${Math.max(2, runProgress)}%` }} /> : null}
      </div>
      <div className="analysis-workbench-grid flow-grid">
        {rail}
        {canvas}
        {showInspector && !isMobile ? inspector : null}
      </div>
      {showInspector && isMobile ? <FoundryDrawer ariaLabel="Analysis inspector" title="Analysis inspector" position="bottom" onClose={onToggleInspector}>{inspector}</FoundryDrawer> : null}
    </section>
  );
}
