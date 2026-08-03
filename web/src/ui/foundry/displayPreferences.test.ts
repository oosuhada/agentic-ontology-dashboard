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
      version: 2,
      textSize: "large",
      density: "compact",
    });
    expect(normalizeDisplayPreferences({ textSize: "small", density: "comfortable" })).toEqual({
      version: 2,
      textSize: "small",
      density: "comfortable",
    });
  });

  it("migrates legacy values and rejects invalid values", () => {
    expect(normalizeDisplayPreferences({ font_scale: "extra-large", density: "comfortable" })).toEqual({
      version: 2,
      textSize: "extra-large",
      density: "comfortable",
    });
    expect(normalizeDisplayPreferences({ textSize: "huge", density: "cramped" })).toEqual({
      version: 2,
      textSize: "default",
      density: "compact",
    });
  });

  it("persists a migrated user-scoped record", () => {
    const storage = new MemoryStorage();
    storage.setItem("ontology-dashboard:display:user-7", JSON.stringify({ font_scale: "large", density: "standard" }));
    expect(loadDisplayPreferences("user-7", storage)).toEqual({ version: 2, textSize: "large", density: "standard" });
    expect(JSON.parse(storage.getItem(displayPreferenceStorageKey("user-7")) ?? "null")).toEqual({
      version: 2,
      textSize: "large",
      density: "standard",
    });
  });
});
