import { useEffect, useRef } from "react";
import type { LucideIcon } from "lucide-react";
import {
  ChevronLeft,
  ChevronRight,
  GitBranch,
  LogOut,
  UserCog,
} from "lucide-react";
import { useI18n } from "../i18n/I18nProvider";

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
  onCloseMobile: () => void;
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
  onCloseMobile,
  onAdmin,
  onLogout,
}: FoundryProductNavigationProps) {
  const { t } = useI18n();
  const navigationRef = useRef<HTMLElement | null>(null);
  const activeItem = items.find((item) => item.id === activeId) ?? items[0];
  const ActiveIcon = activeItem.icon;

  useEffect(() => {
    if (!mobileOpen || !window.matchMedia("(max-width: 900px)").matches) return;
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const navigation = navigationRef.current;
    const shellMain = navigation?.parentElement?.querySelector<HTMLElement>(".od-shell-main");
    const previousOverflow = document.body.style.overflow;
    if (shellMain) shellMain.inert = true;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => navigation?.querySelector<HTMLElement>("button:not([disabled])")?.focus());

    function handleKeyDown(event: KeyboardEvent) {
      if (!navigationRef.current) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseMobile();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(navigationRef.current.querySelectorAll<HTMLElement>("button:not([disabled]),a[href],[tabindex]:not([tabindex='-1'])"));
      if (!focusable.length) return;
      const current = focusable.indexOf(document.activeElement as HTMLElement);
      const next = event.shiftKey
        ? (current <= 0 ? focusable.length - 1 : current - 1)
        : (current === focusable.length - 1 ? 0 : current + 1);
      event.preventDefault();
      focusable[next]?.focus();
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown, true);
      if (shellMain) shellMain.inert = false;
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => returnFocus?.focus());
    };
  }, [mobileOpen, onCloseMobile]);

  return (
    <aside
      ref={navigationRef}
      className={`od-primary-sidebar fd-product-navigation ${mobileOpen ? "mobile-open" : ""}`}
      role={mobileOpen ? "dialog" : undefined}
      aria-modal={mobileOpen ? "true" : undefined}
      aria-label={mobileOpen ? t("nav.open") : undefined}
      tabIndex={mobileOpen ? -1 : undefined}
    >
      <div className="fd-platform-rail" aria-label="Platform rail">
        <div className="fd-platform-mark" title="Ontology Dashboard" aria-label="Ontology Dashboard">OD</div>
        <nav className="fd-platform-shortcuts" aria-label={t("nav.workbenches")}>
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
        {isAdmin ? <button type="button" title={t("nav.administration")} aria-label={t("nav.administration")} onClick={onAdmin}><UserCog size={16} /></button> : null}
        <button type="button" title={t("nav.signOut")} aria-label={t("nav.signOut")} onClick={onLogout}><LogOut size={16} /></button>
      </div>

      {!collapsed ? (
        <div className="fd-resource-navigation">
          <header className="fd-resource-navigation__header">
            <span className="fd-resource-navigation__icon"><ActiveIcon size={15} /></span>
            <div>
              <small>{t("nav.application").toUpperCase()}</small>
              <strong>{activeItem.label}</strong>
            </div>
            <button type="button" className="od-sidebar-collapse" onClick={onToggleCollapsed} title={t("nav.collapseSidebar")}><ChevronLeft size={15} /></button>
          </header>

          <nav className="od-primary-nav" aria-label={t("nav.open")}>
            <span className="od-nav-section">{t("nav.workbenches").toUpperCase()}</span>
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
                  {!item.enabled ? <small>{t("nav.soon").toUpperCase()}</small> : null}
                </button>
              );
            })}
          </nav>

          <div className="od-sidebar-spacer" />
          <section className="od-sidebar-scope">
            <span className="od-nav-section">{t("nav.activeScope").toUpperCase()}</span>
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
        <button type="button" className="fd-sidebar-expand" onClick={onToggleCollapsed} title={t("nav.expandSidebar")} aria-label={t("nav.expandSidebar")}><ChevronRight size={15} /></button>
      )}
    </aside>
  );
}
