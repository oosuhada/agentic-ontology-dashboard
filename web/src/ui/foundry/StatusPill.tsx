import type { ReactNode } from "react";

export type StatusPillIntent = "neutral" | "primary" | "success" | "warning" | "danger";

interface StatusPillProps {
  children: ReactNode;
  intent?: StatusPillIntent;
  title?: string;
  className?: string;
}

export function StatusPill({ children, intent = "neutral", title, className = "" }: StatusPillProps) {
  return (
    <span className={`fd-status-pill intent-${intent} ${className}`.trim()} title={title}>
      {children}
    </span>
  );
}
