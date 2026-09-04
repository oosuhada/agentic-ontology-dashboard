import { describe, expect, it } from "vitest";
import { parseOperationsSelection, selectionSearch } from "./OperationsSelectionContext";

describe("Operations URL selection contract", () => {
  it("uses a role-specific default view and report tab when URL and session state are empty", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "",
      defaultRole: "process_manager",
      defaultView: "reports",
      defaultReportTab: "executive-brief",
    });
    expect(selection.view).toBe("reports");
    expect(selection.reportTab).toBe("executive-brief");
    expect(selection.role).toBe("process_manager");
  });

  it("gives URL query precedence over session state", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=operations&asset_id=CNC-2&event_id=EVENT-2&role=field_operator&workspace_id=workspace-2",
      defaultRole: "process_manager",
      sessionValue: JSON.stringify({ view: "overview", assetId: "CNC-1", eventId: "EVENT-1", role: "process_manager", workspaceId: "workspace-1" }),
    });
    expect(selection).toEqual({
      projectId: "project-a",
      view: "operations",
      surface: null,
      dashboard: "workflow",
      reportTab: "status-map",
      assetId: "CNC-2",
      eventId: "EVENT-2",
      role: "field_operator",
      workspaceId: "workspace-2",
    });
  });

  it("maps unsupported Analysis links to Overview and preserves explicit invalid IDs for a safe empty state", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=analysis&asset_id=missing&event_id=missing-event",
      defaultRole: "process_manager",
    });
    expect(selection.view).toBe("overview");
    expect(selection.reportTab).toBe("status-map");
    expect(selection.assetId).toBe("missing");
    expect(selection.eventId).toBe("missing-event");
  });

  it("maps legacy report links to the Reports side tab", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=executive-report&asset_id=CNC-2&event_id=EVENT-2",
      defaultRole: "process_manager",
    });
    expect(selection.view).toBe("reports");
    expect(selection.reportTab).toBe("executive-brief");
  });

  it("keeps the system admin side tab as a first-class view", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=system&workspace_id=workspace-a",
      defaultRole: "process_manager",
    });
    expect(selection.view).toBe("system");

    const query = selectionSearch(selection);
    expect(new URLSearchParams(query).get("view")).toBe("system");
  });

  it("preserves the overview dashboard variant as a presentation choice", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=overview&dashboard=classic",
      defaultRole: "process_manager",
      sessionValue: JSON.stringify({ dashboard: "workflow" }),
    });
    expect(selection.dashboard).toBe("classic");

    const query = selectionSearch(selection);
    expect(new URLSearchParams(query).get("dashboard")).toBe("classic");
  });

  it("serializes a reproducible deep link", () => {
    const query = selectionSearch({
      projectId: "project-a",
      view: "reports",
      surface: "report-draft",
      dashboard: "workflow",
      reportTab: "inspection-request",
      role: "process_manager",
      workspaceId: "workspace-a",
      assetId: "CNC S01",
      eventId: "EVENT#1",
    });
    const params = new URLSearchParams(query);
    expect(params.get("view")).toBe("reports");
    expect(params.get("surface")).toBeNull();
    expect(params.get("dashboard")).toBe("workflow");
    expect(params.get("report")).toBe("inspection-request");
    expect(params.get("asset_id")).toBe("CNC S01");
    expect(params.get("event_id")).toBe("EVENT#1");
  });

  it("persists semantic role surface independently from the legacy view", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?surface=maintenance-approval&view=operations",
      defaultRole: "process_manager",
      defaultSurface: "operations-status",
    });
    expect(selection.surface).toBe("maintenance-approval");
    expect(selection.view).toBe("operations");
  });

  it("accepts the semantic surface from the route path when the query omits it", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=objects",
      defaultRole: "process_manager",
      defaultSurface: "factory-status",
      pathSurface: "production-impact",
    });
    expect(selection.surface).toBe("production-impact");
    expect(selection.view).toBe("objects");
  });

  it("does not restore a stale selected Case when a broad workspace URL is opened", () => {
    const selection = parseOperationsSelection({
      projectId: "project-a",
      search: "?view=overview&dashboard=workflow&role=process_manager&workspace_id=workspace-a",
      defaultRole: "process_manager",
      defaultSurface: "factory-status",
      pathSurface: "factory-status",
      sessionValue: JSON.stringify({
        view: "overview",
        surface: "factory-status",
        assetId: "CNC-S04-L04-01",
        eventId: "RESULT#OLD-SESSION",
        workspaceId: "workspace-a",
      }),
    });
    expect(selection.surface).toBe("factory-status");
    expect(selection.assetId).toBeNull();
    expect(selection.eventId).toBeNull();
  });
});
