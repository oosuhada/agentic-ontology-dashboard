import { AlertTriangle, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { OntologyLifecycleLoader } from "./OntologyLifecycleLoader";

interface StateProps {
  title: string;
  detail?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, detail, action, className = "" }: StateProps) {
  return (
    <div className={`fd-state ${className}`.trim()}>
      <Inbox size={22} />
      <strong>{title}</strong>
      {detail ? <span>{detail}</span> : null}
      {action}
    </div>
  );
}

export function LoadingState({ title, detail, className = "" }: Omit<StateProps, "action">) {
  return (
    <div className={`fd-state ${className}`.trim()} role="status">
      <OntologyLifecycleLoader variant="panel" operation={title} detail={detail} />
    </div>
  );
}

export function ErrorState({ title, detail, action, className = "" }: StateProps) {
  return (
    <div className={`fd-state intent-danger ${className}`.trim()} role="alert">
      <AlertTriangle size={22} />
      <strong>{title}</strong>
      {detail ? <span>{detail}</span> : null}
      {action}
    </div>
  );
}
