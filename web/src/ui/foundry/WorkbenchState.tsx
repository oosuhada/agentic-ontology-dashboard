import { AlertTriangle, Ban, Inbox, RefreshCw, ShieldAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "../i18n/I18nProvider";
import { OntologyLifecycleLoader } from "./OntologyLifecycleLoader";

export type WorkbenchStateKind = "loading" | "refreshing" | "empty" | "degraded" | "error" | "permission" | "unavailable";

interface StateProps {
  title?: string;
  detail?: string;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}

interface WorkbenchStateProps extends StateProps {
  kind: WorkbenchStateKind;
}

export function WorkbenchState({ kind, title, detail, action, className = "", compact = false }: WorkbenchStateProps) {
  const { t } = useI18n();
  const defaults = {
    loading: t("state.loadingTitle"),
    refreshing: t("state.refreshingTitle"),
    empty: t("state.emptyTitle"),
    degraded: t("state.degradedTitle"),
    error: t("state.errorTitle"),
    permission: t("state.permissionTitle"),
    unavailable: t("state.errorTitle"),
  } satisfies Record<WorkbenchStateKind, string>;

  if (kind === "loading" || kind === "refreshing") {
    return (
      <div className={`fd-state state-${kind} ${compact ? "is-compact" : ""} ${className}`.trim()} role="status" aria-live="polite">
        <OntologyLifecycleLoader variant={compact ? "inline" : "panel"} operation={title ?? defaults[kind]} detail={detail} />
      </div>
    );
  }

  const Icon = kind === "empty"
    ? Inbox
    : kind === "degraded"
      ? TriangleAlert
      : kind === "permission"
        ? ShieldAlert
        : kind === "unavailable"
          ? Ban
          : AlertTriangle;
  const intent = kind === "error" || kind === "unavailable"
    ? "intent-danger"
    : kind === "degraded"
      ? "intent-warning"
      : kind === "permission"
        ? "intent-permission"
        : "";

  return (
    <div className={`fd-state state-${kind} ${intent} ${compact ? "is-compact" : ""} ${className}`.trim()} role={kind === "error" || kind === "permission" ? "alert" : "status"}>
      <Icon size={22} />
      <strong>{title ?? defaults[kind]}</strong>
      {detail ? <span>{detail}</span> : null}
      {action ? <div className="fd-state__action">{action}</div> : kind === "degraded" ? <RefreshCw size={14} aria-hidden="true" /> : null}
    </div>
  );
}

export function EmptyState(props: StateProps) { return <WorkbenchState kind="empty" {...props} />; }
export function LoadingState(props: Omit<StateProps, "action">) { return <WorkbenchState kind="loading" {...props} />; }
export function ErrorState(props: StateProps) { return <WorkbenchState kind="error" {...props} />; }
export function DegradedState(props: StateProps) { return <WorkbenchState kind="degraded" {...props} />; }
export function PermissionState(props: StateProps) { return <WorkbenchState kind="permission" {...props} />; }
export function RefreshingState(props: Omit<StateProps, "action">) { return <WorkbenchState kind="refreshing" {...props} />; }
