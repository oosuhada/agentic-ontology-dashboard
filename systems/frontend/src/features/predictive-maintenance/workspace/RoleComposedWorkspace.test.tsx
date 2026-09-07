import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { OperationsEventDetailModel } from "../../operations/api/operationsContracts";
import { DisplayPreferencesProvider } from "../../../ui/foundry/displayPreferences";
import { FeatureTrendBlock } from "./RoleComposedWorkspace";

let container: HTMLDivElement;
let root: Root;

const detail = {
  event: {
    eventId: "event-sensor-expand",
    assetId: "CNC-01",
    observedAt: "2026-09-07T09:30:00Z",
    failureProbability: 0.81,
    status: "warning",
  },
  threshold: 0.75,
  riskSeries: [
    { observedAt: "2026-09-07T08:30:00Z", failureProbability: 0.62, status: "warning" },
    { observedAt: "2026-09-07T09:00:00Z", failureProbability: 0.71, status: "warning" },
    { observedAt: "2026-09-07T09:30:00Z", failureProbability: 0.81, status: "critical" },
  ],
  sensors: [
    {
      id: "spindle_vibration",
      label: "Spindle vibration",
      value: 6.4,
      unit: "mm/s",
      observedAt: "2026-09-07T09:30:00Z",
      qualityStatus: "good",
      historySourceRef: "sensor://spindle_vibration",
      historyPointCount: 3,
      historyWindow: null,
      historyPoints: [
        { observedAt: "2026-09-07T08:30:00Z", value: 3.2, qualityStatus: "good" },
        { observedAt: "2026-09-07T09:00:00Z", value: 4.8, qualityStatus: "good" },
        { observedAt: "2026-09-07T09:30:00Z", value: 6.4, qualityStatus: "good" },
      ],
    },
  ],
} as OperationsEventDetailModel;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  document.querySelectorAll(".rw-feature-detail-layer").forEach((element) => element.remove());
  container.remove();
});

describe("FeatureTrendBlock", () => {
  it("expands a sensor chart through a body-level portal and closes it with Escape", async () => {
    await act(async () => {
      root.render(
        <DisplayPreferencesProvider scope="guest">
          <FeatureTrendBlock detail={detail} loading={false} />
        </DisplayPreferencesProvider>,
      );
    });

    const sensorExpand = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Spindle vibration 그래프 확대"]',
    );
    expect(sensorExpand).not.toBeNull();

    await act(async () => sensorExpand?.click());
    const layer = document.body.querySelector<HTMLElement>(".rw-feature-detail-layer");
    const dialog = document.body.querySelector<HTMLElement>(
      '[role="dialog"][aria-label="Spindle vibration 상세 그래프"]',
    );
    expect(layer).not.toBeNull();
    expect(layer?.parentElement).toBe(document.body);
    expect(dialog).not.toBeNull();
    expect(dialog?.querySelector("svg.asset-series-chart")).not.toBeNull();

    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(document.body.querySelector(".rw-feature-detail-layer")).toBeNull();
  });
});
