import type { ReactNode } from "react";

interface WorkbenchHeaderProps {
  title: ReactNode;
  metadata?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function WorkbenchHeader({ title, metadata, actions, className = "" }: WorkbenchHeaderProps) {
  return (
    <header className={`fd-workbench-header ${className}`.trim()}>
      <div className="fd-workbench-header__meta">{title}{metadata}</div>
      {actions ? <div className="fd-workbench-header__actions">{actions}</div> : null}
    </header>
  );
}

interface WorkbenchToolbarProps {
  start?: ReactNode;
  end?: ReactNode;
  className?: string;
  label?: string;
}

export function WorkbenchToolbar({ start, end, className = "", label = "Workbench toolbar" }: WorkbenchToolbarProps) {
  return (
    <div className={`fd-workbench-toolbar ${className}`.trim()} role="toolbar" aria-label={label}>
      <div className="fd-workbench-toolbar__group">{start}</div>
      <div className="fd-workbench-toolbar__group">{end}</div>
    </div>
  );
}
