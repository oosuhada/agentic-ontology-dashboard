import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getDisplayPreferences, saveDisplayPreferences } from "../../api";

export type DisplayTextSize = "small" | "default" | "large" | "extra-large";
export type DisplayDensity = "compact" | "standard" | "comfortable";

export interface DisplayPreferences {
  version: 3;
  textSize: DisplayTextSize;
  density: DisplayDensity;
  showTechnicalMetadata: boolean;
}

export type DisplayPreset = "compact" | "standard" | "accessible";

interface DisplayPreferencesContextValue {
  preferences: DisplayPreferences;
  setTextSize: (value: DisplayTextSize) => void;
  setDensity: (value: DisplayDensity) => void;
  setPreset: (value: DisplayPreset) => void;
  setShowTechnicalMetadata: (value: boolean) => void;
  reset: () => void;
}

const DEFAULT_PREFERENCES: DisplayPreferences = {
  version: 3,
  textSize: "default",
  density: "standard",
  showTechnicalMetadata: false,
};

const PRESETS: Record<DisplayPreset, Pick<DisplayPreferences, "textSize" | "density">> = {
  compact: { textSize: "default", density: "compact" },
  standard: { textSize: "default", density: "standard" },
  accessible: { textSize: "large", density: "comfortable" },
};

const TEXT_SIZES = new Set<DisplayTextSize>(["small", "default", "large", "extra-large"]);
const DENSITIES = new Set<DisplayDensity>(["compact", "standard", "comfortable"]);
const DisplayPreferencesContext = createContext<DisplayPreferencesContextValue | null>(null);

export function displayPreferenceStorageKey(scope: string) {
  return `ontology-dashboard:display:v3:${scope || "guest"}`;
}

export function normalizeDisplayPreferences(value: unknown): DisplayPreferences {
  if (!value || typeof value !== "object") return { ...DEFAULT_PREFERENCES };
  const candidate = value as Record<string, unknown>;
  const legacyTextSize = candidate.font_scale;
  const textSize = TEXT_SIZES.has(candidate.textSize as DisplayTextSize)
    ? candidate.textSize as DisplayTextSize
    : TEXT_SIZES.has(legacyTextSize as DisplayTextSize)
      ? legacyTextSize as DisplayTextSize
      : DEFAULT_PREFERENCES.textSize;
  const legacyDensity = candidate.density === "comfortable" || candidate.density === "compact"
    ? candidate.density
    : DEFAULT_PREFERENCES.density;
  const density = DENSITIES.has(candidate.density as DisplayDensity)
    ? candidate.density as DisplayDensity
    : legacyDensity as DisplayDensity;
  const version = Number(candidate.version ?? 2);
  const migratedDensity = version < 3 && textSize === "default" && density === "compact" ? "standard" : density;
  return {
    version: 3,
    textSize,
    density: migratedDensity,
    showTechnicalMetadata: candidate.showTechnicalMetadata === true,
  };
}

export function loadDisplayPreferences(scope: string, storage: Pick<Storage, "getItem" | "setItem"> = window.localStorage) {
  const key = displayPreferenceStorageKey(scope);
  const candidates = [
    storage.getItem(key),
    storage.getItem(`ontology-dashboard:display:v2:${scope || "guest"}`),
    storage.getItem(`ontology-dashboard:display:${scope || "guest"}`),
    scope === "guest" ? storage.getItem("ontology-dashboard-display") : null,
  ];
  for (const raw of candidates) {
    if (!raw) continue;
    try {
      const normalized = normalizeDisplayPreferences(JSON.parse(raw));
      storage.setItem(key, JSON.stringify(normalized));
      return normalized;
    } catch {
      // Ignore malformed legacy preferences and continue to a safe default.
    }
  }
  return { ...DEFAULT_PREFERENCES };
}

function applyDisplayPreferences(preferences: DisplayPreferences) {
  const root = document.documentElement;
  root.dataset.textSize = preferences.textSize;
  root.dataset.density = preferences.density;
  root.dataset.technicalMetadata = preferences.showTechnicalMetadata ? "shown" : "hidden";
}

export function DisplayPreferencesProvider({ scope, children }: { scope: string; children: ReactNode }) {
  const [preferences, setPreferences] = useState<DisplayPreferences>(() => loadDisplayPreferences(scope));
  const [serverReady, setServerReady] = useState(scope === "guest");

  useEffect(() => {
    if (scope === "guest") {
      setServerReady(true);
      return;
    }
    let active = true;
    setServerReady(false);
    getDisplayPreferences()
      .then((serverPreferences) => {
        if (!active || !serverPreferences) return;
        setPreferences(normalizeDisplayPreferences(serverPreferences));
      })
      .catch(() => {
        // Keep the user-scoped local cache when the server is temporarily unavailable.
      })
      .finally(() => active && setServerReady(true));
    return () => { active = false; };
  }, [scope]);

  useEffect(() => {
    applyDisplayPreferences(preferences);
    window.localStorage.setItem(displayPreferenceStorageKey(scope), JSON.stringify(preferences));
    if (!serverReady || scope === "guest") return;
    const timer = window.setTimeout(() => {
      void saveDisplayPreferences(preferences).catch(() => {
        // The local cache remains a safe offline fallback; the next change retries server persistence.
      });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [preferences, scope, serverReady]);

  const value = useMemo<DisplayPreferencesContextValue>(() => ({
    preferences,
    setTextSize: (textSize) => setPreferences((current) => ({ ...current, textSize })),
    setDensity: (density) => setPreferences((current) => ({ ...current, density })),
    setPreset: (preset) => setPreferences((current) => ({ ...current, ...PRESETS[preset] })),
    setShowTechnicalMetadata: (showTechnicalMetadata) => setPreferences((current) => ({ ...current, showTechnicalMetadata })),
    reset: () => setPreferences({ ...DEFAULT_PREFERENCES }),
  }), [preferences]);

  return <DisplayPreferencesContext.Provider value={value}>{children}</DisplayPreferencesContext.Provider>;
}

export function useDisplayPreferences() {
  const value = useContext(DisplayPreferencesContext);
  if (!value) throw new Error("useDisplayPreferences must be used inside DisplayPreferencesProvider");
  return value;
}

export const DISPLAY_TEXT_SIZE_OPTIONS: ReadonlyArray<{ value: DisplayTextSize; label: string }> = [
  { value: "small", label: "Small" },
  { value: "default", label: "Default" },
  { value: "large", label: "Large" },
  { value: "extra-large", label: "Extra large" },
];

export const DISPLAY_DENSITY_OPTIONS: ReadonlyArray<{ value: DisplayDensity; label: string }> = [
  { value: "compact", label: "Compact" },
  { value: "standard", label: "Standard" },
  { value: "comfortable", label: "Comfortable" },
];

export const DISPLAY_PRESET_OPTIONS: ReadonlyArray<{ value: DisplayPreset; label: string; detail: string }> = [
  { value: "compact", label: "Compact", detail: "More data, smaller spacing" },
  { value: "standard", label: "Standard", detail: "Balanced reading and density" },
  { value: "accessible", label: "Accessible", detail: "Larger text and touch targets" },
];

export function displayPreset(preferences: DisplayPreferences): DisplayPreset | "custom" {
  const match = (Object.entries(PRESETS) as Array<[DisplayPreset, Pick<DisplayPreferences, "textSize" | "density">]>).find(([, value]) => (
    value.textSize === preferences.textSize && value.density === preferences.density
  ));
  return match?.[0] ?? "custom";
}
