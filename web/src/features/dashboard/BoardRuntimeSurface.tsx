import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, Braces, CircleDot, Database, Link2, RefreshCw } from "lucide-react";
import type { BoardCatalogDefinition, DashboardBoard } from "./types";

interface BoardRuntimeSurfaceProps {
  board: DashboardBoard;
  definition: BoardCatalogDefinition;
  parameterState: Record<string, unknown>;
  affected: boolean;
  children: ReactNode;
}

interface BoundaryProps {
  boardTitle: string;
  children: ReactNode;
}

interface BoundaryState {
  error: Error | null;
}

class BoardErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Board runtime failed: ${this.props.boardTitle}`, error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="board-runtime-error" role="alert">
        <AlertTriangle size={20} />
        <div><strong>Board renderer failed</strong><p>{this.state.error.message}</p></div>
        <button type="button" onClick={() => this.setState({ error: null })}><RefreshCw size={13} /> Retry</button>
      </div>
    );
  }
}

export function BoardRuntimeSurface({ board, definition, parameterState, affected, children }: BoardRuntimeSurfaceProps) {
  const activeBindings = definition.accepts.filter((parameterId) => parameterState[parameterId] !== undefined);
  const dataSource = definition.object_types[0] ?? (definition.category === "build" ? "configuration" : "dashboard context");
  return (
    <div className={`board-runtime-surface renderer-${definition.renderer.toLowerCase()} ${affected ? "is-querying" : ""}`}>
      <div className="board-runtime-meta">
        <span title="데이터 출처"><Database size={10} /> {dataSource}</span>
        {activeBindings.length ? <span title="활성 parameter binding"><Link2 size={10} /> {activeBindings.length} bindings</span> : null}
        <span title="Renderer"><Braces size={10} /> {definition.renderer}</span>
        <span className={affected ? "runtime-state querying" : "runtime-state ready"}><CircleDot size={9} /> {affected ? "querying" : "ready"}</span>
      </div>
      <div className="board-runtime-body">
        <BoardErrorBoundary boardTitle={board.title}>{children}</BoardErrorBoundary>
      </div>
      <footer className="board-runtime-footer">
        <span>{board.custom ? "Personal instance" : "Governed template"}</span>
        <span>{definition.accepts.length ? `Accepts ${definition.accepts.join(" · ")}` : "No parameter dependency"}</span>
      </footer>
    </div>
  );
}
