import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OntologyLifecycleLoader } from "./OntologyLifecycleLoader";

describe("OntologyLifecycleLoader", () => {
  it("renders a truthful accessible operation without fake progress", () => {
    const markup = renderToString(
      <OntologyLifecycleLoader
        variant="board"
        operation="Loading governed objects"
        detail="Resolving object links."
      />,
    );
    expect(markup).toContain('role="status"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain('aria-label="Loading governed objects"');
    expect(markup).toContain("Data");
    expect(markup).toContain("Logic");
    expect(markup).toContain("Action");
    expect(markup).not.toMatch(/\d+%/);
  });
});
