import { Component, type ErrorInfo, type ReactNode } from "react";
import { Braces, Database, Link2, RefreshCw } from "lucide-react";
import { ErrorState } from "../../ui/foundry/WorkbenchState";
import { StatusPill } from "../../ui/foundry/StatusPill";
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
      <ErrorState
        className="board-runtime-error"
        title="Board renderer failed"
        detail={this.state.error.message}
        action={<button type="button" className="fd-toolbar-button" onClick={() => this.setState({ error: null })}><RefreshCw size={13} /> Retry</button>}
      />
    );
  }
}

export function BoardRuntimeSurface({ board, definition, parameterState, affected, children }: BoardRuntimeSurfaceProps) {
  const activeBindings = definition.accepts.filter((parameterId) => parameterState[parameterId] !== undefined);
  const dataSource = definition.object_types[0] ?? (definition.category === "build" ? "configuration" : "dashboard context");
  const sourceVersion = board.source
    ? `${board.source.version_policy}${board.source.version ? ` · v${board.source.version}` : ""}`
    : "governed template";
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return (
    <div className={`board-runtime-surface renderer-${definition.renderer.toLowerCase()} ${affected ? "is-querying" : ""}`}>
      <div className="board-runtime-meta">
        <span title="데이터 출처"><Database size={10} /> {dataSource}</span>
        {activeBindings.length ? <span title="활성 parameter binding"><Link2 size={10} /> {activeBindings.length} bindings</span> : null}
        <span title="Renderer"><Braces size={10} /> {definition.renderer}</span>
        <StatusPill className="runtime-state" intent={affected ? "primary" : "success"}>{affected ? "querying" : "ready"}</StatusPill>
      </div>
      <div className="board-runtime-body">
        <BoardErrorBoundary boardTitle={board.title}>{children}</BoardErrorBoundary>
      </div>
      <footer className="board-runtime-footer">
        <span>{board.custom ? "Personal instance" : "Governed template"} · {sourceVersion}</span>
        <span>{definition.accepts.length ? `Accepts ${definition.accepts.join(" · ")}` : "No parameter dependency"} · {timezone}</span>
      </footer>
    </div>
  );
}
