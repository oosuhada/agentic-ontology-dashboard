import { Copy, Eye, EyeOff, LayoutGrid, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { DataPill } from "../../ui/foundry/DataPill";
import { analysisCardMetadata } from "./catalog";
import type { AnalysisCanvasDefinition, AnalysisFlowNode } from "./types";

interface AnalysisContentsPanelProps {
  nodes: AnalysisFlowNode[];
  canvases: AnalysisCanvasDefinition[];
  activeCanvasId: string;
  selectedNodeId: string;
  hiddenNodeIds: Set<string>;
  onSelectNode: (nodeId: string) => void;
  onSelectCanvas: (canvasId: string) => void;
  onAddCanvas: () => void;
  onRenameCanvas: (canvasId: string) => void;
  onDuplicateCanvas: (canvasId: string) => void;
  onDeleteCanvas: (canvasId: string) => void;
  onToggleHidden: (nodeId: string) => void;
}

export function AnalysisContentsPanel({
  nodes,
  canvases,
  activeCanvasId,
  selectedNodeId,
  hiddenNodeIds,
  onSelectNode,
  onSelectCanvas,
  onAddCanvas,
  onRenameCanvas,
  onDuplicateCanvas,
  onDeleteCanvas,
  onToggleHidden,
}: AnalysisContentsPanelProps) {
  const activeCanvas = canvases.find((canvas) => canvas.id === activeCanvasId) ?? canvases[0];
  return (
    <aside className="analysis-contents-panel">
      <header><span className="section-label">ANALYSIS CONTENTS</span><strong>Canvases and cards</strong></header>
      <section className="analysis-canvas-list">
        <div className="analysis-panel-section-heading"><span>CANVASES</span><button type="button" aria-label="Add canvas" onClick={onAddCanvas}><Plus size={12} /></button></div>
        {canvases.map((canvas) => (
          <div className={`analysis-canvas-row ${canvas.id === activeCanvasId ? "active" : ""}`} key={canvas.id}>
            <button type="button" onClick={() => onSelectCanvas(canvas.id)}><LayoutGrid size={12} /><span><strong>{canvas.name}</strong><small>{canvas.nodeIds.length} cards</small></span></button>
            <details>
              <summary aria-label={`${canvas.name} actions`}><MoreHorizontal size={13} /></summary>
              <div><button type="button" onClick={() => onRenameCanvas(canvas.id)}>Rename</button><button type="button" onClick={() => onDuplicateCanvas(canvas.id)}><Copy size={11} /> Duplicate</button><button type="button" disabled={canvases.length <= 1} onClick={() => onDeleteCanvas(canvas.id)}><Trash2 size={11} /> Delete</button></div>
            </details>
          </div>
        ))}
      </section>
      <section className="analysis-card-contents">
        <div className="analysis-panel-section-heading"><span>CARDS · {activeCanvas?.name ?? "Overview"}</span><small>{hiddenNodeIds.size} hidden</small></div>
        {(activeCanvas?.nodeIds ?? []).map((nodeId) => nodes.find((node) => node.id === nodeId)).filter(Boolean).map((node) => {
          const resolved = node as AnalysisFlowNode;
          const metadata = analysisCardMetadata(resolved.data.kind);
          const hidden = hiddenNodeIds.has(resolved.id);
          return (
            <div className={`analysis-content-card ${selectedNodeId === resolved.id ? "active" : ""} ${hidden ? "is-hidden" : ""}`} key={resolved.id}>
              <button type="button" onClick={() => onSelectNode(resolved.id)}><DataPill kind={metadata.output} compact /><span><strong>{resolved.data.title}</strong><small>{metadata.category} · {resolved.data.rows.toLocaleString()} rows</small></span></button>
              <button type="button" aria-label={hidden ? `Show ${resolved.data.title}` : `Hide ${resolved.data.title}`} onClick={() => onToggleHidden(resolved.id)}>{hidden ? <Eye size={12} /> : <EyeOff size={12} />}</button>
            </div>
          );
        })}
      </section>
    </aside>
  );
}
