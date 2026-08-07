import { describe, expect, it } from "vitest";
import { MESSAGE_CATALOG, translate } from "./messages";

describe("message catalog", () => {
  it("keeps Korean and English catalogs structurally aligned", () => {
    expect(Object.keys(MESSAGE_CATALOG["ko-KR"]).sort()).toEqual(Object.keys(MESSAGE_CATALOG["en-US"]).sort());
  });

  it("resolves common actions in both locales", () => {
    expect(translate("ko-KR", "common.save")).toBe("저장");
    expect(translate("en-US", "common.save")).toBe("Save");
  });
});
