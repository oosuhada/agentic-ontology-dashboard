import { useId } from "react";

export type OntologyLifecycleLoaderVariant = "page" | "panel" | "board" | "inline";

export function OntologyLifecycleLoader({
  operation,
  detail,
  variant = "panel",
  className = "",
}: {
  operation: string;
  detail?: string;
  variant?: OntologyLifecycleLoaderVariant;
  className?: string;
}) {
  const glowId = `od-loader-glow-${useId().replace(/:/g, "")}`;
  return (
    <div
      className={`od-lifecycle-loader variant-${variant} ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-label={operation}
    >
      <svg className="od-lifecycle-loader__orbit" viewBox="0 0 180 112" aria-hidden="true">
        <defs>
          <radialGradient id={glowId}>
            <stop offset="0" stopColor="currentColor" stopOpacity=".2" />
            <stop offset="1" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle className="od-lifecycle-loader__glow" cx="90" cy="54" r="47" fill={`url(#${glowId})`} />
        <g className="od-lifecycle-loader__rings" fill="none">
          <ellipse cx="90" cy="54" rx="63" ry="24" />
          <ellipse cx="90" cy="54" rx="63" ry="24" transform="rotate(60 90 54)" />
          <ellipse cx="90" cy="54" rx="63" ry="24" transform="rotate(120 90 54)" />
        </g>
        <g className="od-lifecycle-loader__nodes phase-data">
          <circle cx="27" cy="54" r="5" />
          <circle cx="153" cy="54" r="5" />
          <circle cx="90" cy="78" r="5" />
        </g>
        <g className="od-lifecycle-loader__nodes phase-logic">
          <circle cx="68" cy="31" r="5" />
          <circle cx="117" cy="39" r="5" />
          <circle cx="116" cy="78" r="5" />
        </g>
        <g className="od-lifecycle-loader__nodes phase-action">
          <circle cx="48" cy="76" r="5" />
          <circle cx="126" cy="22" r="5" />
        </g>
      </svg>
      <div className="od-lifecycle-loader__copy">
        <div className="od-lifecycle-loader__phases" aria-hidden="true">
          <span>Data</span><i>→</i><span>Logic</span><i>→</i><span>Action</span>
        </div>
        <strong>{operation}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
    </div>
  );
}
