import type { AnalysisFlowNode } from "./types";

interface AnalysisInspectorProps {
  node: AnalysisFlowNode;
  sourceOptions?: Array<{ value: string; label: string }>;
  onConfigChange: (key: string, value: string) => void;
}

const OPTIONS: Record<string, string[]> = {
  field: ["status", "line", "confidence", "equipment_id"],
  operator: ["equals", "not_equals", "greater_than", "less_than"],
  metric: ["average_risk", "count", "downtime_sum", "max_risk"],
  relationship: ["risk_event_equipment", "risk_event_evidence", "equipment_work_order"],
  chart: ["bar", "line", "pie", "histogram"],
  version: ["latest_published", "pinned"],
};

export function AnalysisInspector({ node, sourceOptions = [], onConfigChange }: AnalysisInspectorProps) {
  return (
    <section className="analysis-node-config">
      <h3>Configuration</h3>
      {Object.entries(node.data.config).map(([key, value]) => {
        const options = key === "source"
          ? [
              { value: "risk_event", label: "Ontology · Risk Event" },
              ...sourceOptions,
            ]
          : (OPTIONS[key] ?? []).map((option) => ({ value: option, label: option }));
        return (
          <label key={key}>
            {key}
            {options.length ? (
              <select value={value} onChange={(event) => onConfigChange(key, event.target.value)}>
                {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            ) : <input value={value} onChange={(event) => onConfigChange(key, event.target.value)} />}
          </label>
        );
      })}
      {node.data.kind === "formula" ? <small>자유 SQL은 허용하지 않습니다. field와 연산자를 선택하는 방식만 사용합니다.</small> : null}
      {node.data.kind === "join" || node.data.kind === "evidence" ? <small>Join 관계는 RiskEvent↔Equipment, RiskEvent↔Evidence, Equipment↔WorkOrder 세 종류로 제한됩니다.</small> : null}
    </section>
  );
}
