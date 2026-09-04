import type { ReactNode } from "react";

export type MetricTone = "default" | "success" | "warning" | "danger" | "critical";

export interface MetricStripItem {
  id: string;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: MetricTone;
  accessory?: ReactNode;
}

interface MetricStripProps {
  metrics: MetricStripItem[];
  className?: string;
}

export function MetricStrip({ metrics, className = "" }: MetricStripProps) {
  return (
    <div className={`fd-metric-strip ${className}`.trim()}>
      {metrics.map((metric) => (
        <article key={metric.id} className={`fd-metric tone-${metric.tone ?? "default"}`}>
          <div className="fd-metric__label">{metric.label}</div>
          <strong className="fd-metric__value">{metric.value}</strong>
          {metric.detail ? <small className="fd-metric__detail">{metric.detail}</small> : null}
          {metric.accessory}
        </article>
      ))}
    </div>
  );
}
