function envFlag(name: string, defaultValue: boolean): boolean {
  const raw = (import.meta.env[name] as string | undefined)?.trim().toLowerCase();
  if (!raw) return defaultValue;
  return ["1", "true", "yes", "on", "enabled"].includes(raw);
}

export const featureFlags = {
  ontologyWorkbench: envFlag("VITE_FEATURE_ONTOLOGY_WORKBENCH", true),
  datasetCatalog: envFlag("VITE_FEATURE_DATASET_CATALOG", true),
  governanceWorkbench: envFlag("VITE_FEATURE_GOVERNANCE_WORKBENCH", true),
} as const;

export type ProductFeature = keyof typeof featureFlags;
