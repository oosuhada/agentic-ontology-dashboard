import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./components";

describe("StatusBadge", () => {
  it("renders governed Korean labels", () => {
    expect(renderToString(<StatusBadge status="warning" />)).toContain("경고");
    expect(renderToString(<StatusBadge status="critical" />)).toContain("긴급 검토");
    expect(renderToString(<StatusBadge status="data_quality_hold" />)).toContain("데이터 확인");
  });
});
