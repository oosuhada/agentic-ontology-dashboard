import { describe, expect, it } from "vitest";
import { ApiError } from "../../../api";
import { postMaintenancePollingFailure } from "./MaintenanceWorkflowActionPanel";

describe("post-maintenance result polling", () => {
  it("surfaces authorization and contract failures immediately", () => {
    expect(postMaintenancePollingFailure(
      new ApiError(403, "forbidden", "권한이 없습니다."),
      1,
    )).toEqual({
      message: "정비 후 결과 조회가 거부되었습니다: 권한이 없습니다.",
      stop: true,
    });
  });

  it("retries transient failures but surfaces repeated failures", () => {
    expect(postMaintenancePollingFailure(new Error("connection reset"), 2)).toEqual({
      message: null,
      stop: false,
    });
    expect(postMaintenancePollingFailure(new Error("connection reset"), 3)).toEqual({
      message: "정비 후 결과 조회가 3회 연속 실패했습니다: connection reset",
      stop: false,
    });
  });

  it("localizes polling failures for the English reliability workspace", () => {
    expect(postMaintenancePollingFailure(new Error("connection reset"), 3, "en-US")).toEqual({
      message: "Post-maintenance result lookup failed 3 consecutive times: connection reset",
      stop: false,
    });
  });
});
