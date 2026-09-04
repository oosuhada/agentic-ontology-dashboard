import { describe, expect, it } from "vitest";
import { week2OperationsRedirectPath } from "./routing";

describe("Operations workspace route boundary", () => {
  it("keeps the canonical operations route unchanged", () => {
    expect(week2OperationsRedirectPath("/app/projects/demo/operations", "fallback")).toBeNull();
  });

  it("keeps legacy operations links compatible", () => {
    expect(week2OperationsRedirectPath("/app/projects/demo/operations", "fallback")).toBeNull();
  });

  it("redirects imported project workbenches to the canonical operations route", () => {
    for (const path of [
      "/app/projects/demo",
      "/app/projects/demo/datasets",
      "/app/projects/demo/workspaces/main/agent",
      "/app/projects/demo/blueprint",
      "/app/projects/demo/blueprint-v2",
    ]) {
      expect(week2OperationsRedirectPath(path, "fallback")).toBe("/app/projects/demo/operations");
    }
  });

  it("keeps published Blueprint showcase routes available", () => {
    expect(week2OperationsRedirectPath("/app/projects/demo/blueprint-compare", "fallback")).toBeNull();
    expect(week2OperationsRedirectPath("/app/projects/demo/blueprint-v4", "fallback")).toBeNull();
  });

  it("keeps only comparison iframe workbenches available with the embed marker", () => {
    for (const path of [
      "/app/projects/demo",
      "/app/projects/demo/blueprint",
      "/app/projects/demo/blueprint-v2",
      "/app/projects/demo/workspaces/main/ontology",
    ]) {
      expect(week2OperationsRedirectPath(path, "fallback", "?comparison_embed=1")).toBeNull();
    }
    expect(
      week2OperationsRedirectPath(
        "/app/projects/demo/workspaces/main/governance",
        "fallback",
        "?comparison_embed=1",
      ),
    ).toBe("/app/projects/demo/operations");
  });

  it("uses the active project for non-project app paths", () => {
    expect(week2OperationsRedirectPath("/app/analysis/analysis-1", "active-project")).toBe("/app/projects/active-project/operations");
    expect(week2OperationsRedirectPath("/app", "active-project")).toBe("/app/projects/active-project/operations");
  });

  it("does not redirect public non-app routes", () => {
    expect(week2OperationsRedirectPath("/team-share", "active-project")).toBeNull();
  });
});
