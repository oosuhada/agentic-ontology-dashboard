import { BarChart3, Calculator, Database, Filter, GitMerge, Plus, Sigma, Table2 } from "lucide-react";
import { ANALYSIS_BOARD_LIBRARY } from "./catalog";
import type { AnalysisStepKind } from "./types";

const ICONS = { filter: Filter, group: GitMerge, aggregate: Sigma, formula: Calculator, join: GitMerge, chart: BarChart3, table: Table2, evidence: Database } as const;

interface AnalysisBoardRailProps {
  onAddStep: (kind: Exclude<AnalysisStepKind, "input">) => void;
}

export function AnalysisBoardRail({ onAddStep }: AnalysisBoardRailProps) {
  return (
    <aside className="analysis-board-rail">
      <span className="section-label">NODE CATALOG</span>
      <p>현재 output과 호환되는 transform·visualization node입니다.</p>
      {ANALYSIS_BOARD_LIBRARY.map((item) => {
        const Icon = ICONS[item.kind];
        return (
          <button type="button" key={item.kind} onClick={() => onAddStep(item.kind)}>
            <span><Icon size={13} /></span>
            <div><strong>{item.title}</strong><small>{item.input} → {item.output}</small><p>{item.description}</p></div>
            <b><Plus size={13} /></b>
          </button>
        );
      })}
    </aside>
  );
}
