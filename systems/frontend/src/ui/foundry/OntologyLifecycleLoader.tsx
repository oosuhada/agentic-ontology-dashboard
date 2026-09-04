import { useId } from "react";

export type OntologyLifecycleLoaderVariant = "page" | "panel" | "board" | "inline";

export function OntologyLifecycleLoader({
  operation,
  detail,
  variant = "panel",
  steps = ["Data", "Logic", "Action"],
  className = "",
}: {
  operation: string;
  detail?: string;
  variant?: OntologyLifecycleLoaderVariant;
  steps?: readonly [string, string, string];
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
        <g className="od-lifecycle-loader__system">
          <g className="od-lifecycle-loader__rings" fill="none">
            <ellipse cx="90" cy="54" rx="63" ry="24" />
            <ellipse cx="90" cy="54" rx="63" ry="24" transform="rotate(60 90 54)" />
            <ellipse cx="90" cy="54" rx="63" ry="24" transform="rotate(120 90 54)" />
          </g>
          <g className="od-lifecycle-loader__nodes phase-data">
            <g transform="translate(153 54)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
            <g transform="translate(58.5 74.785)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
          </g>
          <g className="od-lifecycle-loader__nodes phase-logic" transform="rotate(60 90 54)">
            <g transform="translate(121.5 33.215)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
            <g transform="translate(58.5 33.215)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
          </g>
          <g className="od-lifecycle-loader__nodes phase-action" transform="rotate(120 90 54)">
            <g transform="translate(121.5 74.785)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
            <g transform="translate(27 54)"><circle className="node-halo" r="7" /><circle className="node-core" r="3.2" /></g>
          </g>
        </g>
        <circle className="od-lifecycle-loader__center-halo" cx="90" cy="54" r="10" />
        <circle className="od-lifecycle-loader__center" cx="90" cy="54" r="3" />
      </svg>
      <div className="od-lifecycle-loader__copy">
        <div className="od-lifecycle-loader__phases" aria-hidden="true">
          <span>{steps[0]}</span><i>→</i><span>{steps[1]}</span><i>→</i><span>{steps[2]}</span>
        </div>
        <strong>{operation}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
    </div>
  );
}
