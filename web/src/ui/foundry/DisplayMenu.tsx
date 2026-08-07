import { RotateCcw, SlidersHorizontal } from "lucide-react";
import {
  DISPLAY_DENSITY_OPTIONS,
  DISPLAY_PRESET_OPTIONS,
  DISPLAY_TEXT_SIZE_OPTIONS,
  displayPreset,
  useDisplayPreferences,
} from "./displayPreferences";

export function DisplayMenu({ className = "" }: { className?: string }) {
  const { preferences, setDensity, setPreset, setShowTechnicalMetadata, setTextSize, reset } = useDisplayPreferences();
  const preset = displayPreset(preferences);
  return (
    <details className={`od-display-menu ${className}`.trim()}>
      <summary aria-label="Display settings" title="Display settings">
        <SlidersHorizontal size={15} />
        <span>Display</span>
      </summary>
      <section className="od-display-popover" role="dialog" aria-label="Display settings">
        <header>
          <div><span className="section-label">DISPLAY</span><strong>Reading and spacing</strong></div>
          <button type="button" className="od-display-reset" onClick={reset}><RotateCcw size={12} /> Reset</button>
        </header>
        <fieldset>
          <legend>Preset</legend>
          <div className="od-display-presets">
            {DISPLAY_PRESET_OPTIONS.map((option) => (
              <button
                type="button"
                key={option.value}
                aria-pressed={preset === option.value}
                className={preset === option.value ? "active" : ""}
                onClick={() => setPreset(option.value)}
              ><strong>{option.label}</strong><small>{option.detail}</small></button>
            ))}
          </div>
        </fieldset>
        <details className="od-display-advanced">
          <summary>Advanced text and spacing</summary>
          <fieldset>
            <legend>Text size</legend>
            <div className="od-display-options">
              {DISPLAY_TEXT_SIZE_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.textSize === option.value} className={preferences.textSize === option.value ? "active" : ""} onClick={() => setTextSize(option.value)}>{option.label}</button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Density</legend>
            <div className="od-display-options three-up">
              {DISPLAY_DENSITY_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.density === option.value} className={preferences.density === option.value ? "active" : ""} onClick={() => setDensity(option.value)}>{option.label}</button>
              ))}
            </div>
          </fieldset>
        </details>
        <button
          type="button"
          className="od-display-metadata-toggle"
          aria-pressed={preferences.showTechnicalMetadata}
          onClick={() => setShowTechnicalMetadata(!preferences.showTechnicalMetadata)}
        >
          <span><strong>Technical metadata</strong><small>Renderer, bindings, contracts, and timezone</small></span>
          <b>{preferences.showTechnicalMetadata ? "Shown" : "Hidden"}</b>
        </button>
        <p>Preset and advanced choices are saved for this user.</p>
      </section>
    </details>
  );
}
