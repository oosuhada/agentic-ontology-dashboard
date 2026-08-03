import { Check, ChevronDown, RotateCcw } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { BoardVisualizationRuntime, VisualizationKind, VisualizationSettings } from "../types";
import { VisualizationKindMark } from "./VisualizationKindMark";
import { visualizationDefinition } from "./visualizationRegistry";

interface VisualizationSwitcherProps {
  runtime: BoardVisualizationRuntime | null;
  settings: VisualizationSettings;
  onChange: (settings: VisualizationSettings) => void;
  compact?: boolean;
}

export function VisualizationSwitcher({ runtime, settings, onChange, compact = false }: VisualizationSwitcherProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const activeKind = runtime?.active_kind ?? settings.kind ?? "table";
  const activeDefinition = visualizationDefinition(activeKind);
  const modeLabel = settings.mode === "manual" ? "Manual" : "Auto";

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("[data-visualization-menu-item]") ?? []);
      (items.find((item) => item.dataset.kind === activeKind) ?? items[0])?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeKind, open, runtime]);

  function closeMenu(restoreFocus = false) {
    setOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function choose(kind: VisualizationKind) {
    onChange({
      ...settings,
      version: 1,
      mode: "manual",
      kind,
      recommendation_revision: runtime?.recommendation.profile_hash,
    });
    closeMenu(true);
  }

  function handleMenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("[data-visualization-menu-item]") ?? []);
    if (!items.length) return;
    const current = document.activeElement instanceof HTMLButtonElement ? items.indexOf(document.activeElement) : -1;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeMenu(true);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End" || event.key === "Tab") {
      event.preventDefault();
      event.stopPropagation();
      let next = current;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = items.length - 1;
      else if (event.key === "ArrowDown" || (event.key === "Tab" && !event.shiftKey)) next = (current + 1 + items.length) % items.length;
      else next = (current - 1 + items.length) % items.length;
      items[next]?.focus();
    }
  }

  return (
    <div ref={rootRef} className={`visualization-switcher ${compact ? "is-compact" : ""}`} onClick={(event) => event.stopPropagation()}>
      <button
        ref={triggerRef}
        type="button"
        className={`visualization-switcher-trigger ${settings.mode === "manual" ? "is-manual" : "is-auto"}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Visualize as. ${modeLabel}, ${activeDefinition.displayName}`}
        title={`${modeLabel} · ${activeDefinition.displayName}`}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            closeMenu(false);
          }
          if (event.key === "ArrowDown") {
            event.preventDefault();
            event.stopPropagation();
            setOpen(true);
          }
        }}
      >
        <VisualizationKindMark kind={activeKind} variant="icon" />
        {compact ? <span className="visualization-switcher-mode" aria-hidden="true">{settings.mode === "manual" ? "M" : "A"}</span> : null}
        <span className="visualization-switcher-label">{compact ? activeDefinition.shortName : `${modeLabel} · ${activeDefinition.shortName}`}</span>
        <ChevronDown size={11} />
      </button>
      {open ? (
        <div ref={menuRef} id={menuId} className="visualization-menu" role="menu" aria-label="Visualize as" onKeyDown={handleMenuKeyDown}>
          {runtime ? (
            <>
              <section className="visualization-menu-section is-recommended">
                <span className="visualization-menu-label">Recommended</span>
                <button data-visualization-menu-item data-kind={runtime.recommendation.recommended.kind} type="button" role="menuitemradio" aria-checked={activeKind === runtime.recommendation.recommended.kind} aria-describedby={`${menuId}-recommended-reason`} onClick={() => choose(runtime.recommendation.recommended.kind)}>
                  <VisualizationKindMark kind={runtime.recommendation.recommended.kind} />
                  <span><strong>{visualizationDefinition(runtime.recommendation.recommended.kind).displayName}</strong><small id={`${menuId}-recommended-reason`}>{runtime.recommendation.recommended.rationale}</small></span>
                  {activeKind === runtime.recommendation.recommended.kind ? <Check size={13} /> : null}
                </button>
              </section>
              <section className="visualization-menu-section">
                <span className="visualization-menu-label">Alternatives</span>
                {runtime.recommendation.alternatives.map((item, index) => (
                  <button data-visualization-menu-item data-kind={item.kind} key={item.kind} type="button" role="menuitemradio" aria-checked={activeKind === item.kind} aria-describedby={`${menuId}-alternative-${index}`} onClick={() => choose(item.kind)}>
                    <VisualizationKindMark kind={item.kind} />
                    <span><strong>{visualizationDefinition(item.kind).displayName}</strong><small id={`${menuId}-alternative-${index}`}>{item.rationale}</small></span>
                    {activeKind === item.kind ? <Check size={13} /> : null}
                  </button>
                ))}
              </section>
              {runtime.recommendation.unavailable.length ? (
                <section className="visualization-menu-section is-unavailable">
                  <span className="visualization-menu-label">Unavailable</span>
                  {runtime.recommendation.unavailable.map((item, index) => (
                    <button data-visualization-menu-item data-kind={item.kind} key={item.kind} type="button" role="menuitem" aria-disabled="true" aria-describedby={`${menuId}-unavailable-${index}`} onClick={(event) => event.preventDefault()}>
                      <VisualizationKindMark kind={item.kind} />
                      <span><strong>{visualizationDefinition(item.kind).displayName}</strong><small id={`${menuId}-unavailable-${index}`}>{item.reason}</small></span>
                    </button>
                  ))}
                </section>
              ) : null}
            </>
          ) : <div className="visualization-menu-loading">Field profile is loading…</div>}
          {settings.mode === "manual" ? (
            <button
              data-visualization-menu-item
              type="button"
              role="menuitem"
              className="visualization-reset"
              onClick={() => {
                onChange({ version: 1, mode: "auto", recommendation_revision: runtime?.recommendation.profile_hash });
                closeMenu(true);
              }}
            >
              <RotateCcw size={12} /> Reset to Auto
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
