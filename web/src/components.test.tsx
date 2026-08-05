import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./components";
import { I18nProvider } from "./ui/i18n/I18nProvider";

function renderBadge(status: string) {
  return renderToString(<I18nProvider><StatusBadge status={status} /></I18nProvider>);
}

describe("StatusBadge", () => {
  it("renders governed Korean labels", () => {
    expect(renderBadge("warning")).toContain("경고");
    expect(renderBadge("critical")).toContain("긴급 검토");
    expect(renderBadge("data_quality_hold")).toContain("데이터 확인");
  });
});
