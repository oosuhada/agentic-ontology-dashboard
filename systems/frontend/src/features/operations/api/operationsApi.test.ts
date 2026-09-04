import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  inspectionRequestIdempotencyKey,
  submitOperationsDecision,
} from "./operationsApi";
import type { OperationsEvidenceSnapshotBasis } from "./operationsContracts";

const apiMocks = vi.hoisted(() => ({
  addNote: vi.fn(),
  getEvidence: vi.fn(),
  getPredictiveMaintenanceDashboard: vi.fn(),
  getPredictiveMaintenanceLatestResults: vi.fn(),
  getProject: vi.fn(),
  getProjectEvents: vi.fn(),
  getProjectWorkspaces: vi.fn(),
  getReport: vi.fn(),
  recordDecision: vi.fn(),
  requestInspectionWorkOrder: vi.fn(),
}));

vi.mock("../../../api", () => ({
  API_BASE: "http://127.0.0.1:8100",
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public code: string,
      message: string,
    ) {
      super(message);
    }
  },
  addNote: apiMocks.addNote,
  getEvidence: apiMocks.getEvidence,
  getPredictiveMaintenanceDashboard: apiMocks.getPredictiveMaintenanceDashboard,
  getPredictiveMaintenanceLatestResults: apiMocks.getPredictiveMaintenanceLatestResults,
  getProject: apiMocks.getProject,
  getProjectEvents: apiMocks.getProjectEvents,
  getProjectWorkspaces: apiMocks.getProjectWorkspaces,
  getReport: apiMocks.getReport,
  recordDecision: apiMocks.recordDecision,
  requestInspectionWorkOrder: apiMocks.requestInspectionWorkOrder,
}));

const snapshotBasis: OperationsEvidenceSnapshotBasis = {
  artifactId: "artifact-1",
  evidencePayloadReference: "evidence://artifact-1",
  assetId: "CNC-S04-L02-03",
  eventId: "EVT-GS-004",
  observedAt: "2026-06-28T00:00:00Z",
  modelVersion: "pdm-v1",
  datasetVersion: "dsv-canonical-v3-1",
  sourceSha256: "a".repeat(64),
};

describe("Operations decision API helpers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.recordDecision.mockResolvedValue({});
    apiMocks.requestInspectionWorkOrder.mockResolvedValue({});
  });

  it("separates work-order idempotency by decision type", () => {
    const inspectionKey = inspectionRequestIdempotencyKey({
      eventId: "EVT-GS-004",
      decision: "request_inspection",
      userId: "user-1",
      snapshotBasis,
    });
    const shutdownKey = inspectionRequestIdempotencyKey({
      eventId: "EVT-GS-004",
      decision: "review_shutdown",
      userId: "user-1",
      snapshotBasis,
    });

    expect(inspectionKey).toContain("request_inspection");
    expect(shutdownKey).toContain("review_shutdown");
    expect(inspectionKey).not.toBe(shutdownKey);
  });

  it("records the operator decision after creating the inspection work order", async () => {
    await submitOperationsDecision({
      projectId: "manufacturing-demo-project",
      workspaceId: "manufacturing-demo",
      eventId: "EVT-GS-004",
      userId: "user-1",
      actor: "현장 담당자",
      decision: "request_inspection",
      note: "구동 토크 상승 확인",
      snapshotBasis,
    });

    expect(apiMocks.requestInspectionWorkOrder).toHaveBeenCalledWith(
      expect.objectContaining({
        eventId: "EVT-GS-004",
        idempotencyKey: expect.stringContaining("request_inspection"),
      }),
    );
    expect(apiMocks.recordDecision).toHaveBeenCalledWith(
      "EVT-GS-004",
      "현장 담당자",
      "request_inspection",
      "구동 토크 상승 확인",
    );
  });
});
