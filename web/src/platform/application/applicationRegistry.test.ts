import { describe, expect, it } from "vitest";
import {
  APPLICATION_REGISTRY,
  COMMERCIAL_V4_APPLICATION,
  accessibleCommercialSurfaces,
} from "./applicationRegistry";
import { applicationQueryKey, applicationStorageKey } from "./applicationState";

describe("versioned application registry", () => {
  it("keeps four independent routes and state namespaces", () => {
    expect(APPLICATION_REGISTRY.map((item) => item.route("manufacturing-demo-project"))).toEqual([
      "/app/projects/manufacturing-demo-project",
      "/app/projects/manufacturing-demo-project/blueprint",
      "/app/projects/manufacturing-demo-project/blueprint-v2",
      "/app/projects/manufacturing-demo-project/blueprint-v4",
    ]);
    expect(new Set(APPLICATION_REGISTRY.map((item) => item.storageNamespace)).size).toBe(4);
    expect(new Set(APPLICATION_REGISTRY.map((item) => item.queryNamespace)).size).toBe(4);
    expect(new Set(APPLICATION_REGISTRY.map((item) => item.collaborationNamespace)).size).toBe(4);
  });

  it("does not advertise future V4 capabilities as ready", () => {
    const states = Object.fromEntries(COMMERCIAL_V4_APPLICATION.surfaces.map((item) => [item.id, item.state]));
    expect(states.lineage).toBe("planned");
    expect(states.actions).toBe("planned");
    expect(states.automation).toBe("planned");
    expect(states.overview).toBe("ready");
  });

  it("scopes permissions, browser storage and query identity", () => {
    const surfaces = accessibleCommercialSurfaces(["ontology.objects.read"]);
    expect(surfaces.find((item) => item.id === "objects")?.accessible).toBe(true);
    expect(surfaces.find((item) => item.id === "models")?.accessible).toBe(false);
    expect(applicationStorageKey({
      version: "v4",
      projectId: "project-a",
      userId: "user-a",
      key: "preference",
    })).toBe("ontology-dashboard:v4:project-a:user-a:preference");
    expect(applicationQueryKey({
      version: "v4",
      organizationId: "org-a",
      projectId: "project-a",
      workspaceId: "workspace-a",
      resource: "overview",
    })).toEqual(["ontology-dashboard:v4", "org-a", "project-a", "workspace-a", "overview"]);
  });
});
