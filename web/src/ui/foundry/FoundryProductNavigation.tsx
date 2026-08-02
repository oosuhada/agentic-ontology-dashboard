import type { LucideIcon } from "lucide-react";
import {
  ChevronLeft,
  ChevronRight,
  GitBranch,
  LogOut,
  UserCog,
} from "lucide-react";

export interface FoundryNavigationItem {
  id: string;
  label: string;
  icon: LucideIcon;
  enabled: boolean;
}

interface FoundryProductNavigationProps {
  items: readonly FoundryNavigationItem[];
  activeId: string;
  collapsed: boolean;
  mobileOpen: boolean;
  projectName: string;
  workspaceName: string;
  userName: string;
  roleLabel: string;
  isAdmin: boolean;
  onNavigate: (id: string) => void;
  onToggleCollapsed: () => void;
  onAdmin: () => void;
  onLogout: () => void;
}

export function FoundryProductNavigation({
  items,
  activeId,
  collapsed,
  mobileOpen,
  projectName,
  workspaceName,
  userName,
  roleLabel,
  isAdmin,
  onNavigate,
  onToggleCollapsed,
  onAdmin,
  onLogout,
}: FoundryProductNavigationProps) {
  const activeItem = items.find((item) => item.id === activeId) ?? items[0];
  const ActiveIcon = activeItem.icon;

  return (
    <aside className={`od-primary-sidebar fd-product-navigation ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="fd-platform-rail" aria-label="Platform rail">
        <div className="fd-platform-mark" title="Ontology Dashboard" aria-label="Ontology Dashboard">OD</div>
        <nav className="fd-platform-shortcuts" aria-label="Workbench shortcuts">
          {items.map((item) => {
            const Icon = item.icon;
            if (!collapsed) {
              return (
                <span
                  key={item.id}
                  className={item.id === activeId ? "active" : ""}
                  title={`${item.label} shortcut`}
                  aria-hidden="true"
                >
                  <Icon size={16} />
                </span>
              );
            }
            return (
              <button
                type="button"
                key={item.id}
                className={item.id === activeId ? "active" : ""}
                disabled={!item.enabled}
                title={item.label}
                aria-label={`Open ${item.id}`}
                onClick={() => item.enabled && onNavigate(item.id)}
              >
                <Icon size={16} />
              </button>
            );
          })}
        </nav>
        <div className="fd-platform-rail__spacer" />
        {isAdmin ? <button type="button" title="Administration" aria-label="Administration" onClick={onAdmin}><UserCog size={16} /></button> : null}
        <button type="button" title="Sign out" aria-label="로그아웃" onClick={onLogout}><LogOut size={16} /></button>
      </div>

      {!collapsed ? (
        <div className="fd-resource-navigation">
          <header className="fd-resource-navigation__header">
            <span className="fd-resource-navigation__icon"><ActiveIcon size={15} /></span>
            <div>
              <small>APPLICATION</small>
              <strong>{activeItem.label}</strong>
            </div>
            <button type="button" className="od-sidebar-collapse" onClick={onToggleCollapsed} title="사이드바 접기"><ChevronLeft size={15} /></button>
          </header>

          <nav className="od-primary-nav" aria-label="Product navigation">
            <span className="od-nav-section">WORKBENCHES</span>
            {items.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  type="button"
                  key={item.id}
                  className={item.id === activeId ? "active" : ""}
                  disabled={!item.enabled}
                  title={item.label}
                  aria-label={item.id === "governance" ? "Governance navigation" : item.label}
                  onClick={() => item.enabled && onNavigate(item.id)}
                >
                  <Icon size={14} />
                  <span>{item.label}</span>
                  {!item.enabled ? <small>SOON</small> : null}
                </button>
              );
            })}
          </nav>

          <div className="od-sidebar-spacer" />
          <section className="od-sidebar-scope">
            <span className="od-nav-section">ACTIVE SCOPE</span>
            <div>
              <GitBranch size={14} />
              <span><strong>{projectName}</strong><small>{workspaceName}</small></span>
            </div>
          </section>
          <footer className="fd-resource-navigation__footer">
            <span>{userName.slice(0, 1).toUpperCase()}</span>
            <div><strong>{userName}</strong><small>{roleLabel}</small></div>
          </footer>
        </div>
      ) : (
        <button type="button" className="fd-sidebar-expand" onClick={onToggleCollapsed} title="사이드바 펼치기" aria-label="사이드바 펼치기"><ChevronRight size={15} /></button>
      )}
    </aside>
  );
}
