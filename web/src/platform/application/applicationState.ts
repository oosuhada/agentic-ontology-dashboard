import type { ApplicationVersion, CommercialSurfaceId } from "./applicationRegistry";
import { applicationDefinition } from "./applicationRegistry";

export interface VersionedApplicationPreference {
  schemaVersion: 1;
  surface: CommercialSurfaceId;
  compactNavigation: boolean;
}

export function applicationStorageKey(input: {
  version: ApplicationVersion;
  projectId: string;
  userId: string;
  key: string;
}) {
  const namespace = applicationDefinition(input.version).storageNamespace;
  return `${namespace}:${encodeURIComponent(input.projectId)}:${encodeURIComponent(input.userId)}:${input.key}`;
}

export function applicationQueryKey(input: {
  version: ApplicationVersion;
  organizationId: string;
  projectId: string;
  workspaceId?: string;
  resource: string;
}) {
  const namespace = applicationDefinition(input.version).queryNamespace;
  return [namespace, input.organizationId, input.projectId, input.workspaceId ?? "project", input.resource] as const;
}

export function readApplicationPreference(key: string): VersionedApplicationPreference | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) ?? "null") as Partial<VersionedApplicationPreference> | null;
    if (!parsed || parsed.schemaVersion !== 1 || typeof parsed.surface !== "string") return null;
    return {
      schemaVersion: 1,
      surface: parsed.surface as CommercialSurfaceId,
      compactNavigation: parsed.compactNavigation === true,
    };
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

export function writeApplicationPreference(key: string, preference: VersionedApplicationPreference) {
  window.localStorage.setItem(key, JSON.stringify(preference));
}
