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

  it("supports context-specific lifecycle labels", () => {
    const markup = renderToString(
      <OntologyLifecycleLoader
        variant="page"
        operation="Checking session"
        steps={["Session", "Scope", "Workspace"]}
      />,
    );
    expect(markup).toContain("Session");
    expect(markup).toContain("Scope");
    expect(markup).toContain("Workspace");
  });
});
