import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DisplayTextSize = "small" | "default" | "large" | "extra-large";
export type DisplayDensity = "compact" | "standard" | "comfortable";

export interface DisplayPreferences {
  version: 2;
  textSize: DisplayTextSize;
  density: DisplayDensity;
}

interface DisplayPreferencesContextValue {
  preferences: DisplayPreferences;
  setTextSize: (value: DisplayTextSize) => void;
  setDensity: (value: DisplayDensity) => void;
  reset: () => void;
}

const DEFAULT_PREFERENCES: DisplayPreferences = {
  version: 2,
  textSize: "default",
  density: "compact",
};

const TEXT_SIZES = new Set<DisplayTextSize>(["small", "default", "large", "extra-large"]);
const DENSITIES = new Set<DisplayDensity>(["compact", "standard", "comfortable"]);
const DisplayPreferencesContext = createContext<DisplayPreferencesContextValue | null>(null);

export function displayPreferenceStorageKey(scope: string) {
  return `ontology-dashboard:display:v2:${scope || "guest"}`;
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
  return { version: 2, textSize, density };
}

export function loadDisplayPreferences(scope: string, storage: Pick<Storage, "getItem" | "setItem"> = window.localStorage) {
  const key = displayPreferenceStorageKey(scope);
  const candidates = [
    storage.getItem(key),
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
}

export function DisplayPreferencesProvider({ scope, children }: { scope: string; children: ReactNode }) {
  const [preferences, setPreferences] = useState<DisplayPreferences>(() => loadDisplayPreferences(scope));

  useEffect(() => {
    applyDisplayPreferences(preferences);
    window.localStorage.setItem(displayPreferenceStorageKey(scope), JSON.stringify(preferences));
  }, [preferences, scope]);

  const value = useMemo<DisplayPreferencesContextValue>(() => ({
    preferences,
    setTextSize: (textSize) => setPreferences((current) => ({ ...current, textSize })),
    setDensity: (density) => setPreferences((current) => ({ ...current, density })),
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
