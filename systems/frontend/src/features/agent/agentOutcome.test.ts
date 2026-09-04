import { describe, expect, it } from "vitest";
import { agentOutcomeLabel, deriveAgentOutcome } from "./agentOutcome";

describe("deriveAgentOutcome", () => {
  it("does not present a zero-evidence run as succeeded", () => {
    const outcome = deriveAgentOutcome({ status: "succeeded", evidenceCount: 0, claimCount: 0 });
    expect(outcome).toBe("no_evidence");
    expect(agentOutcomeLabel(outcome, "ko-KR")).toBe("근거 없음");
  });

  it("marks a run partial when an evidence store failed", () => {
    expect(deriveAgentOutcome({
      status: "succeeded",
      evidenceCount: 3,
      claimCount: 1,
      failedStepCount: 1,
    })).toBe("partial");
  });

  it("keeps a fully grounded run successful", () => {
    expect(deriveAgentOutcome({
      status: "succeeded",
      evidenceCount: 3,
      claimCount: 2,
      failedStepCount: 0,
    })).toBe("succeeded");
  });
});
