import { BarChart3, Calculator, Database, Filter, GitMerge, Plus, Sigma, Table2 } from "lucide-react";
import { DataPill } from "../../ui/foundry/DataPill";
import { ANALYSIS_BOARD_LIBRARY, analysisCardMetadata, compatibleAnalysisBoards } from "./catalog";
import type { AnalysisBoardDefinition, AnalysisDataKind, AnalysisStepKind } from "./types";

const ICONS = { filter: Filter, group: GitMerge, aggregate: Sigma, formula: Calculator, join: GitMerge, chart: BarChart3, table: Table2, evidence: Database } as const;

interface AnalysisBoardRailProps {
  onAddStep: (kind: Exclude<AnalysisStepKind, "input">) => void;
  selectedOutput?: AnalysisDataKind;
}

type AnalysisPaletteKind = Exclude<AnalysisStepKind, "input">;

const GROUPS: Array<{ label: string; kinds: AnalysisPaletteKind[] }> = [
  { label: "TRANSFORM", kinds: ["filter", "formula", "join", "evidence"] },
  { label: "AGGREGATE", kinds: ["group", "aggregate"] },
  { label: "VISUALIZE & OUTPUT", kinds: ["chart", "table"] },
];

export function AnalysisBoardRail({ onAddStep, selectedOutput = "object-set" }: AnalysisBoardRailProps) {
  const byKind = new Map(ANALYSIS_BOARD_LIBRARY.map((item) => [item.kind, item]));
  const compatibleKinds = new Set(compatibleAnalysisBoards(selectedOutput).map((item) => item.kind));
  return (
    <aside className="analysis-board-rail">
      <div className="analysis-rail-heading">
        <span className="section-label">BOARD PALETTE</span>
        <strong>Build the path</strong>
        <p>현재 output contract와 호환되는 governed board만 추가합니다.</p>
      </div>
      <div className="analysis-input-source">
        <span><Database size={13} /></span>
        <div><small>CURRENT OUTPUT</small><strong><DataPill kind={selectedOutput} /></strong></div>
      </div>
      {GROUPS.map((group) => (
        <section className="analysis-board-group" key={group.label}>
          <header>{group.label}</header>
          {group.kinds.map((kind) => {
            const item = byKind.get(kind) as AnalysisBoardDefinition | undefined;
            if (!item) return null;
            const Icon = ICONS[item.kind];
            const metadata = analysisCardMetadata(item.kind);
            const compatible = compatibleKinds.has(item.kind);
            return (
              <button type="button" key={item.kind} disabled={!compatible} title={compatible ? `Compatible with ${selectedOutput}` : `Requires ${metadata.input.join(" or ")}`} onClick={() => onAddStep(item.kind)}>
                <span><Icon size={13} /></span>
                <div><strong>{item.title}</strong><small><DataPill kind={metadata.input[0] ?? "none"} compact /> → <DataPill kind={metadata.output} compact /> {compatible ? "Compatible" : "Unavailable"}</small><p>{item.description}</p></div>
                <b><Plus size={13} /></b>
              </button>
            );
          })}
        </section>
      ))}
    </aside>
  );
}
