import type { VisualizationKind } from "../types";

export type VisualizationIntent = "comparison" | "trend" | "composition" | "distribution" | "relationship" | "detail" | "summary";

export interface VisualizationDefinition {
  kind: VisualizationKind;
  displayName: string;
  shortName: string;
  intent: VisualizationIntent;
  requiredChannels: string[];
  supportsSelection: boolean;
  supportsBrush: boolean;
  supportsSeries: boolean;
  supportsStack: boolean;
}

export const VISUALIZATION_REGISTRY: readonly VisualizationDefinition[] = [
  { kind: "metric", displayName: "Metric", shortName: "Metric", intent: "summary", requiredChannels: ["value"], supportsSelection: false, supportsBrush: false, supportsSeries: false, supportsStack: false },
  { kind: "table", displayName: "Table", shortName: "Table", intent: "detail", requiredChannels: [], supportsSelection: true, supportsBrush: false, supportsSeries: false, supportsStack: false },
  { kind: "bar", displayName: "Bar chart", shortName: "Bar", intent: "comparison", requiredChannels: ["x", "y"], supportsSelection: true, supportsBrush: true, supportsSeries: true, supportsStack: false },
  { kind: "stacked_bar", displayName: "Stacked bar", shortName: "Stacked", intent: "composition", requiredChannels: ["x", "y", "series"], supportsSelection: true, supportsBrush: true, supportsSeries: true, supportsStack: true },
  { kind: "line", displayName: "Line chart", shortName: "Line", intent: "trend", requiredChannels: ["x", "y"], supportsSelection: true, supportsBrush: true, supportsSeries: true, supportsStack: false },
  { kind: "area", displayName: "Area chart", shortName: "Area", intent: "trend", requiredChannels: ["x", "y"], supportsSelection: true, supportsBrush: true, supportsSeries: true, supportsStack: true },
  { kind: "pie", displayName: "Pie / donut", shortName: "Donut", intent: "composition", requiredChannels: ["x", "value"], supportsSelection: true, supportsBrush: false, supportsSeries: false, supportsStack: false },
  { kind: "histogram", displayName: "Histogram", shortName: "Histogram", intent: "distribution", requiredChannels: ["value"], supportsSelection: true, supportsBrush: true, supportsSeries: false, supportsStack: false },
  { kind: "scatter", displayName: "Scatter plot", shortName: "Scatter", intent: "relationship", requiredChannels: ["x", "y"], supportsSelection: true, supportsBrush: true, supportsSeries: true, supportsStack: false },
  { kind: "heatmap", displayName: "Heatmap", shortName: "Heatmap", intent: "relationship", requiredChannels: ["row", "column", "value"], supportsSelection: true, supportsBrush: false, supportsSeries: false, supportsStack: false },
] as const;

export const VISUALIZATION_KIND_SET = new Set<VisualizationKind>(VISUALIZATION_REGISTRY.map((item) => item.kind));

export function visualizationDefinition(kind: VisualizationKind) {
  return VISUALIZATION_REGISTRY.find((item) => item.kind === kind) ?? VISUALIZATION_REGISTRY[1];
}
