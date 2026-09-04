import type { AnalysisCanvasDefinition, AnalysisFlowNode, AnalysisPresentationState } from "./types";

function defaultFrames(nodes: AnalysisFlowNode[]) {
  return Object.fromEntries(nodes.map((node, index) => [node.id, {
    x: 28 + (index % 2) * 390,
    y: 34 + Math.floor(index / 2) * 232,
    width: 356,
    height: 204,
  }]));
}

export function defaultAnalysisPresentation(nodes: AnalysisFlowNode[]): AnalysisPresentationState {
  const nodeIds = nodes.map((node) => node.id);
  const canvas: AnalysisCanvasDefinition = { id: "overview", name: "Overview", nodeIds, frames: defaultFrames(nodes) };
  return {
    activeView: "path",
    activeCanvasId: canvas.id,
    canvases: [canvas],
    hiddenNodeIds: [],
    showComputationalNodes: true,
  };
}

export function loadAnalysisPresentation(analysisId: string, nodes: AnalysisFlowNode[]): AnalysisPresentationState {
  const fallback = defaultAnalysisPresentation(nodes);
  try {
    const stored = JSON.parse(window.localStorage.getItem(`ontology-dashboard:analysis-presentation:${analysisId}`) ?? "null") as Partial<AnalysisPresentationState> | null;
    if (!stored?.canvases?.length) return fallback;
    const nodeIds = new Set(nodes.map((node) => node.id));
    const canvases = stored.canvases.map((canvas, canvasIndex) => {
      const known = canvas.nodeIds.filter((id) => nodeIds.has(id));
      const missing = nodes.filter((node) => !known.includes(node.id)).map((node) => node.id);
      return {
        id: canvas.id || `canvas-${canvasIndex + 1}`,
        name: canvas.name || `Canvas ${canvasIndex + 1}`,
        nodeIds: [...known, ...missing],
        frames: { ...defaultFrames(nodes), ...canvas.frames },
      };
    });
    return {
      activeView: stored.activeView === "canvas" || stored.activeView === "graph" ? stored.activeView : "path",
      activeCanvasId: canvases.some((canvas) => canvas.id === stored.activeCanvasId) ? String(stored.activeCanvasId) : canvases[0].id,
      canvases,
      hiddenNodeIds: (stored.hiddenNodeIds ?? []).filter((id) => nodeIds.has(id)),
      showComputationalNodes: stored.showComputationalNodes !== false,
    };
  } catch {
    return fallback;
  }
}

export function saveAnalysisPresentation(analysisId: string, state: AnalysisPresentationState) {
  window.localStorage.setItem(`ontology-dashboard:analysis-presentation:${analysisId}`, JSON.stringify(state));
}

export function reconcileAnalysisPresentation(state: AnalysisPresentationState, nodes: AnalysisFlowNode[]): AnalysisPresentationState {
  const nodeIds = nodes.map((node) => node.id);
  const valid = new Set(nodeIds);
  const fallbackFrames = defaultFrames(nodes);
  const canvases = state.canvases.length ? state.canvases.map((canvas) => {
    const known = canvas.nodeIds.filter((id) => valid.has(id));
    const missing = nodeIds.filter((id) => !known.includes(id));
    return { ...canvas, nodeIds: [...known, ...missing], frames: { ...fallbackFrames, ...canvas.frames } };
  }) : defaultAnalysisPresentation(nodes).canvases;
  return {
    ...state,
    canvases,
    activeCanvasId: canvases.some((canvas) => canvas.id === state.activeCanvasId) ? state.activeCanvasId : canvases[0].id,
    hiddenNodeIds: state.hiddenNodeIds.filter((id) => valid.has(id)),
  };
}
