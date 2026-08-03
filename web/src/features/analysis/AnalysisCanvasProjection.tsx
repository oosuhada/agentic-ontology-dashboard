import { GripHorizontal, Maximize2 } from "lucide-react";
import { useRef, type PointerEvent as ReactPointerEvent } from "react";
import { DataPill } from "../../ui/foundry/DataPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { analysisCardMetadata } from "./catalog";
import type { AnalysisCanvasDefinition, AnalysisCanvasFrame, AnalysisFlowNode } from "./types";

interface AnalysisCanvasProjectionProps {
  nodes: AnalysisFlowNode[];
  canvas: AnalysisCanvasDefinition;
  selectedNodeId: string;
  hiddenNodeIds: Set<string>;
  onSelectNode: (nodeId: string) => void;
  onFrameChange: (nodeId: string, frame: AnalysisCanvasFrame) => void;
}

type DragState = { nodeId: string; operation: "move" | "resize"; startX: number; startY: number; frame: AnalysisCanvasFrame };

export function AnalysisCanvasProjection({ nodes, canvas, selectedNodeId, hiddenNodeIds, onSelectNode, onFrameChange }: AnalysisCanvasProjectionProps) {
  const drag = useRef<DragState | null>(null);
  const visibleNodes = canvas.nodeIds.map((id) => nodes.find((node) => node.id === id)).filter((node): node is AnalysisFlowNode => Boolean(node && !hiddenNodeIds.has(node.id)));

  function begin(event: ReactPointerEvent<HTMLElement>, nodeId: string, operation: DragState["operation"]) {
    const frame = canvas.frames[nodeId];
    if (!frame) return;
    event.stopPropagation();
    drag.current = { nodeId, operation, startX: event.clientX, startY: event.clientY, frame };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function move(event: ReactPointerEvent<HTMLElement>) {
    if (!drag.current) return;
    const deltaX = event.clientX - drag.current.startX;
    const deltaY = event.clientY - drag.current.startY;
    const { frame, operation, nodeId } = drag.current;
    onFrameChange(nodeId, operation === "move"
      ? { ...frame, x: Math.max(0, frame.x + deltaX), y: Math.max(0, frame.y + deltaY) }
      : { ...frame, width: Math.max(260, frame.width + deltaX), height: Math.max(160, frame.height + deltaY) });
  }

  function end(event: ReactPointerEvent<HTMLElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  return (
    <section className="analysis-freeform-canvas">
      <header><div><strong>{canvas.name}</strong><span>Free-form presentation · {visibleNodes.length} visible cards</span></div><div><span>100%</span><Maximize2 size={12} /></div></header>
      <div className="analysis-freeform-stage">
        {!visibleNodes.length ? <EmptyState title="This canvas is empty" detail="Show a hidden card or add a compatible board from the catalog." /> : null}
        {visibleNodes.map((node) => {
          const frame = canvas.frames[node.id] ?? { x: 24, y: 24, width: 356, height: 204 };
          const metadata = analysisCardMetadata(node.data.kind);
          return (
            <article className={`analysis-canvas-card ${selectedNodeId === node.id ? "selected" : ""}`} key={node.id} style={{ left: frame.x, top: frame.y, width: frame.width, height: frame.height }} onClick={() => onSelectNode(node.id)}>
              <header onPointerDown={(event) => begin(event, node.id, "move")} onPointerMove={move} onPointerUp={end}><GripHorizontal size={13} /><div><small>{metadata.category.toUpperCase()}</small><strong>{node.data.title}</strong></div><DataPill kind={metadata.output} compact /></header>
              <div className="analysis-canvas-card__body"><div><DataPill kind={metadata.input[0] ?? "none"} /><span>→</span><DataPill kind={metadata.output} /></div><strong>{node.data.rows.toLocaleString()}</strong><span>rows · {node.data.status} · {node.data.elapsedMs}ms</span><dl>{Object.entries(node.data.config).slice(0, 3).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></div>
              <button type="button" className="analysis-canvas-resize" aria-label={`Resize ${node.data.title}`} onPointerDown={(event) => begin(event, node.id, "resize")} onPointerMove={move} onPointerUp={end} />
            </article>
          );
        })}
      </div>
    </section>
  );
}
