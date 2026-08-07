import { describe, expect, it } from "vitest";
import {
  displayPreferenceStorageKey,
  loadDisplayPreferences,
  normalizeDisplayPreferences,
} from "./displayPreferences";

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe("display preferences", () => {
  it("keeps text size and density independent", () => {
    expect(normalizeDisplayPreferences({ textSize: "large", density: "compact" })).toEqual({
      version: 3,
      textSize: "large",
      density: "compact",
      showTechnicalMetadata: false,
    });
    expect(normalizeDisplayPreferences({ textSize: "small", density: "comfortable" })).toEqual({
      version: 3,
      textSize: "small",
      density: "comfortable",
      showTechnicalMetadata: false,
    });
  });

  it("migrates legacy values and rejects invalid values", () => {
    expect(normalizeDisplayPreferences({ font_scale: "extra-large", density: "comfortable" })).toEqual({
      version: 3,
      textSize: "extra-large",
      density: "comfortable",
      showTechnicalMetadata: false,
    });
    expect(normalizeDisplayPreferences({ textSize: "huge", density: "cramped" })).toEqual({
      version: 3,
      textSize: "default",
      density: "standard",
      showTechnicalMetadata: false,
    });
  });

  it("persists a migrated user-scoped record", () => {
    const storage = new MemoryStorage();
    storage.setItem("ontology-dashboard:display:user-7", JSON.stringify({ font_scale: "large", density: "standard" }));
    expect(loadDisplayPreferences("user-7", storage)).toEqual({ version: 3, textSize: "large", density: "standard", showTechnicalMetadata: false });
    expect(JSON.parse(storage.getItem(displayPreferenceStorageKey("user-7")) ?? "null")).toEqual({
      version: 3,
      textSize: "large",
      density: "standard",
      showTechnicalMetadata: false,
    });
  });

  it("migrates the old default compact pair to the new standard preset", () => {
    expect(normalizeDisplayPreferences({ version: 2, textSize: "default", density: "compact" })).toEqual({
      version: 3,
      textSize: "default",
      density: "standard",
      showTechnicalMetadata: false,
    });
  });
});
