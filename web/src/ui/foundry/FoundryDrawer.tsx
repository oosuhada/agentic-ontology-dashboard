import { X } from "lucide-react";
import type { ReactNode } from "react";
import { FoundryDialog } from "./FoundryDialog";

interface FoundryDrawerProps {
  ariaLabel: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
  position?: "left" | "right" | "bottom";
  className?: string;
}

export function FoundryDrawer({ ariaLabel, title, onClose, children, position = "right", className = "" }: FoundryDrawerProps) {
  return (
    <FoundryDialog
      ariaLabel={ariaLabel}
      overlayClassName="fd-drawer-backdrop"
      dialogClassName={`fd-drawer fd-drawer-${position} ${className}`.trim()}
      onClose={onClose}
    >
      <header className="fd-drawer__header">
        <strong>{title}</strong>
        <button type="button" aria-label={`${title} 닫기`} onClick={onClose}><X size={16} /></button>
      </header>
      <div className="fd-drawer__body">{children}</div>
    </FoundryDialog>
  );
}
