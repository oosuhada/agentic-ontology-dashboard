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
      <div className="generic-metric-grid">
        {metrics.map((metric) => (
          <article key={metric.id} className={`tone-${metric.tone ?? "default"}`}>
            <header><span>{metric.label}</span>{metric.tone && metric.tone !== "default" ? <span className={`od-tag intent-${metric.tone}`}>{metric.tone}</span> : null}</header>
            <strong>{metric.value}</strong>
            {metric.detail ? <small>{metric.detail}</small> : null}
          </article>
        ))}
      </div>
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
