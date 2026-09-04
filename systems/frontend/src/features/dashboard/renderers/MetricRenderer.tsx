import { MetricStrip } from "../../../ui/foundry/MetricStrip";
import { StatusPill } from "../../../ui/foundry/StatusPill";

export interface MetricItem {
  id: string;
  label: string;
  value: string | number;
  detail?: string;
  tone?: "default" | "success" | "warning" | "danger";
}

interface MetricRendererProps {
  metrics: MetricItem[];
  footer?: { label: string; value: string; progress?: number };
  compact?: boolean;
}

export function MetricRenderer({ metrics, footer, compact = false }: MetricRendererProps) {
  return (
    <section className={`generic-metric-renderer ${compact ? "is-compact" : ""}`}>
      <MetricStrip
        className="generic-metric-grid"
        metrics={metrics.map((metric) => ({
          id: metric.id,
          label: metric.label,
          value: metric.value,
          detail: metric.detail,
          tone: metric.tone,
          accessory: metric.tone && metric.tone !== "default"
            ? <StatusPill intent={metric.tone === "danger" ? "danger" : metric.tone}>{metric.tone}</StatusPill>
            : null,
        }))}
      />
      {footer ? (
        <footer>
          <span>{footer.label}</span>
          {typeof footer.progress === "number" ? <div><i style={{ width: `${Math.max(0, Math.min(100, footer.progress))}%` }} /></div> : null}
          <strong>{footer.value}</strong>
        </footer>
      ) : null}
    </section>
  );
}
