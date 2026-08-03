import { RotateCcw, SlidersHorizontal } from "lucide-react";
import {
  DISPLAY_DENSITY_OPTIONS,
  DISPLAY_PRESET_OPTIONS,
  DISPLAY_TEXT_SIZE_OPTIONS,
  displayPreset,
  useDisplayPreferences,
} from "./displayPreferences";
import { useI18n } from "../i18n/I18nProvider";

export function DisplayMenu({ className = "" }: { className?: string }) {
  const { preferences, setDensity, setPreset, setShowTechnicalMetadata, setTextSize, reset } = useDisplayPreferences();
  const { locale, setLocale, t } = useI18n();
  const preset = displayPreset(preferences);
  return (
    <details className={`od-display-menu ${className}`.trim()}>
      <summary aria-label={t("display.title")} title={t("display.title")}>
        <SlidersHorizontal size={15} />
        <span>{t("display.title")}</span>
      </summary>
      <section className="od-display-popover" role="dialog" aria-label={t("display.title")}>
        <header>
          <div><span className="section-label">DISPLAY</span><strong>{t("display.subtitle")}</strong></div>
          <button type="button" className="od-display-reset" onClick={reset}><RotateCcw size={12} /> {t("display.reset")}</button>
        </header>
        <fieldset>
          <legend>{t("display.preset")}</legend>
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
          <summary>{t("display.advanced")}</summary>
          <fieldset>
            <legend>{t("display.textSize")}</legend>
            <div className="od-display-options">
              {DISPLAY_TEXT_SIZE_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.textSize === option.value} className={preferences.textSize === option.value ? "active" : ""} onClick={() => setTextSize(option.value)}>{option.label}</button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>{t("display.density")}</legend>
            <div className="od-display-options three-up">
              {DISPLAY_DENSITY_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.density === option.value} className={preferences.density === option.value ? "active" : ""} onClick={() => setDensity(option.value)}>{option.label}</button>
              ))}
            </div>
          </fieldset>
        </details>
        <fieldset>
          <legend>{t("display.locale")}</legend>
          <div className="od-display-options two-up">
            <button type="button" aria-pressed={locale === "ko-KR"} className={locale === "ko-KR" ? "active" : ""} onClick={() => setLocale("ko-KR")}>한국어</button>
            <button type="button" aria-pressed={locale === "en-US"} className={locale === "en-US" ? "active" : ""} onClick={() => setLocale("en-US")}>English</button>
          </div>
        </fieldset>
        <button
          type="button"
          className="od-display-metadata-toggle"
          aria-pressed={preferences.showTechnicalMetadata}
          onClick={() => setShowTechnicalMetadata(!preferences.showTechnicalMetadata)}
        >
          <span><strong>{t("display.technical")}</strong><small>{t("display.technicalDetail")}</small></span>
          <b>{preferences.showTechnicalMetadata ? t("display.shown") : t("display.hidden")}</b>
        </button>
        <p>{t("display.savedPerUser")}</p>
      </section>
    </details>
  );
}
