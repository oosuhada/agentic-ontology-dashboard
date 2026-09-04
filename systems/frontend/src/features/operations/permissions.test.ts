import { describe, expect, it } from "vitest";
import {
  canMaterializeAgentReviewSummary,
  canReadOperationsSystemLogs,
} from "./permissions";

describe("Operations permissions", () => {
  it("keeps Agent Review Summary materialization behind the dedicated permission", () => {
    expect(canMaterializeAgentReviewSummary(["events.read", "events.decision"])).toBe(false);
    expect(canMaterializeAgentReviewSummary(["agent.review.materialize"])).toBe(true);
  });

  it("keeps system runtime logs behind the administrator audit permission", () => {
    expect(canReadOperationsSystemLogs(["events.read", "agent.review.materialize"])).toBe(false);
    expect(canReadOperationsSystemLogs(["admin.audit.read"])).toBe(true);
  });
});
