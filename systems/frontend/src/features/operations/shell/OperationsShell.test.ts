import { describe, expect, it } from "vitest";
import { operationsNavigationItems } from "./OperationsShell";

describe("Operations shell navigation", () => {
  it("keeps the system admin tab visible in workflow navigation", () => {
    expect(operationsNavigationItems("workflow").map((item) => item.id)).toEqual([
      "field_operator",
      "process_manager",
      "system",
    ]);
  });

  it("keeps the system admin side tab visible in classic navigation", () => {
    expect(operationsNavigationItems("classic").map((item) => item.id)).toContain("system");
  });
});
