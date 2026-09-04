import { Laptop, Moon, RotateCcw, SlidersHorizontal, Sun } from "lucide-react";
import { useEffect, useRef } from "react";
import {
  DISPLAY_DENSITY_OPTIONS,
  DISPLAY_PRESET_OPTIONS,
  DISPLAY_TEXT_SIZE_OPTIONS,
  displayPreset,
  useDisplayPreferences,
} from "./displayPreferences";
import { useI18n } from "../i18n/I18nProvider";

export function DisplayMenu({ className = "" }: { className?: string }) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const { preferences, setDensity, setPreset, setShowTechnicalMetadata, setTextSize, setTheme, reset } = useDisplayPreferences();
  const { locale, setLocale, t } = useI18n();
  const preset = displayPreset(preferences);
  const presetLabel = (value: (typeof DISPLAY_PRESET_OPTIONS)[number]["value"]) => value === "compact"
    ? [t("display.preset.compact"), t("display.preset.compactDetail")]
    : value === "standard"
      ? [t("display.preset.standard"), t("display.preset.standardDetail")]
      : value === "large"
        ? [t("display.preset.large"), t("display.preset.largeDetail")]
        : [t("display.preset.accessible"), t("display.preset.accessibleDetail")];
  const textSizeLabel = (value: (typeof DISPLAY_TEXT_SIZE_OPTIONS)[number]["value"]) => value === "small"
    ? t("display.size.small")
    : value === "default"
      ? t("display.size.default")
      : value === "large"
        ? t("display.size.large")
        : t("display.size.extraLarge");
  const densityLabel = (value: (typeof DISPLAY_DENSITY_OPTIONS)[number]["value"]) => value === "compact"
    ? t("display.density.compact")
    : value === "standard"
      ? t("display.density.standard")
      : t("display.density.comfortable");

  useEffect(() => {
    function closeOnOutsidePointer(event: PointerEvent) {
      if (!(event.target instanceof Node)) return;
      if (!detailsRef.current?.contains(event.target)) detailsRef.current?.removeAttribute("open");
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") detailsRef.current?.removeAttribute("open");
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  return (
    <details ref={detailsRef} className={`od-display-menu ${className}`.trim()}>
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
          <legend>{t("display.theme")}</legend>
          <div className="od-display-options three-up od-display-theme-options">
            <button type="button" aria-pressed={preferences.theme === "light"} className={preferences.theme === "light" ? "active" : ""} onClick={() => setTheme("light")}><Sun size={12} />{t("display.theme.light")}</button>
            <button type="button" aria-pressed={preferences.theme === "dark"} className={preferences.theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}><Moon size={12} />{t("display.theme.dark")}</button>
            <button type="button" aria-pressed={preferences.theme === "system"} className={preferences.theme === "system" ? "active" : ""} onClick={() => setTheme("system")}><Laptop size={12} />{t("display.theme.system")}</button>
          </div>
        </fieldset>
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
              ><strong>{presetLabel(option.value)[0]}</strong><small>{presetLabel(option.value)[1]}</small></button>
            ))}
          </div>
        </fieldset>
        <details className="od-display-advanced">
          <summary>{t("display.advanced")}</summary>
          <fieldset>
            <legend>{t("display.textSize")}</legend>
            <div className="od-display-options">
              {DISPLAY_TEXT_SIZE_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.textSize === option.value} className={preferences.textSize === option.value ? "active" : ""} onClick={() => setTextSize(option.value)}>{textSizeLabel(option.value)}</button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>{t("display.density")}</legend>
            <div className="od-display-options three-up">
              {DISPLAY_DENSITY_OPTIONS.map((option) => (
                <button type="button" key={option.value} aria-pressed={preferences.density === option.value} className={preferences.density === option.value ? "active" : ""} onClick={() => setDensity(option.value)}>{densityLabel(option.value)}</button>
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
