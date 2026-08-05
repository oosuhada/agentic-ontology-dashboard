export type ApplicationVersion = "v1" | "v2" | "v3" | "v4";
export type CapabilityState = "ready" | "planned" | "blocked" | "not_configured";

export type CommercialSurfaceId =
  | "overview"
  | "identity"
  | "deployment"
  | "runtime"
  | "artifacts"
  | "operations"
  | "ingestion"
  | "objects"
  | "analysis"
  | "models"
  | "lineage"
  | "governance"
  | "actions"
  | "automation"
  | "settings";

export interface ApplicationSurfaceDefinition {
  id: CommercialSurfaceId;
  label: string;
  description: string;
  state: CapabilityState;
  phase: number;
  permission?: string;
  launchPath?: (context: ApplicationRouteContext) => string;
}

export interface ApplicationRouteContext {
  projectId: string;
  workspaceId: string;
}

export interface VersionedApplicationDefinition {
  id: string;
  version: ApplicationVersion;
  applicationIdentity: string;
  route: (projectId: string) => string;
  storageNamespace: string;
  queryNamespace: string;
  collaborationNamespace: string;
  surfaces: readonly ApplicationSurfaceDefinition[];
}

function projectRoute(projectId: string, suffix = "") {
  return `/app/projects/${encodeURIComponent(projectId)}${suffix}`;
}

function workspaceRoute(context: ApplicationRouteContext, suffix: string) {
  return `${projectRoute(context.projectId)}/workspaces/${encodeURIComponent(context.workspaceId)}${suffix}`;
}

const V4_SURFACES: readonly ApplicationSurfaceDefinition[] = [
  {
    id: "overview",
    label: "Operations overview",
    description: "Project, Dataset Version, role and production capability context.",
    state: "ready",
    phase: 18,
  },
  {
    id: "identity",
    label: "Identity & access",
    description: "OIDC, group mapping, SCIM, MFA, service identity and session lifecycle readiness.",
    state: "ready",
    phase: 21,
  },
  {
    id: "deployment",
    label: "Deployment",
    description: "Production topology, probes, ingress, migration and release readiness.",
    state: "ready",
    phase: 22,
  },
  {
    id: "runtime",
    label: "Distributed runtime",
    description: "Redis coordination, durable workers, retry, cancellation and dead-letter operations.",
    state: "ready",
    phase: 23,
  },
  {
    id: "artifacts",
    label: "Artifacts",
    description: "Object storage, checksum, signed download, retention and reconciliation governance.",
    state: "ready",
    phase: 24,
    permission: "governance.read",
  },
  {
    id: "operations",
    label: "Operations & SLO",
    description: "Telemetry, service level objectives, burn-rate alerts and production diagnostics.",
    state: "ready",
    phase: 25,
    permission: "governance.read",
  },
  {
    id: "ingestion",
    label: "Ingestion",
    description: "Governed connector lifecycle, checkpoint, schema drift and quarantine operations.",
    state: "ready",
    phase: 26,
    permission: "governance.read",
  },
  {
    id: "objects",
    label: "Objects",
    description: "Existing governed Object Explorer; standard Object Views arrive in Phase 29.",
    state: "ready",
    phase: 18,
    permission: "ontology.objects.read",
    launchPath: (context) => workspaceRoute(context, "/ontology"),
  },
  {
    id: "analysis",
    label: "Analysis & Pipeline",
    description: "Existing Analysis entry point; scalable visual pipeline runtime arrives in Phase 30.",
    state: "ready",
    phase: 18,
    launchPath: (context) => `${projectRoute(context.projectId)}?view=analysis`,
  },
  {
    id: "models",
    label: "Model operations",
    description: "Existing ML Validator entry point; continuous MLOps controls arrive in Phase 31.",
    state: "ready",
    phase: 18,
    permission: "ml.console.read",
    launchPath: (context) => workspaceRoute(context, "/modeling"),
  },
  {
    id: "lineage",
    label: "Lineage & evidence",
    description: "Global product branches, end-to-end lineage, impact context and marking-aware access policy.",
    state: "ready",
    phase: 28,
    permission: "governance.read",
  },
  {
    id: "governance",
    label: "Governance",
    description: "Existing governance workbench with a version-scoped V4 launch path.",
    state: "ready",
    phase: 18,
    permission: "governance.read",
    launchPath: (context) => workspaceRoute(context, "/governance"),
  },
  {
    id: "actions",
    label: "Actions & functions",
    description: "Versioned Ontology Interfaces, schema-driven Actions and deterministic governed Functions.",
    state: "ready",
    phase: 27,
    permission: "ontology.registry.read",
  },
  {
    id: "automation",
    label: "Automation",
    description: "Governed event-condition-Action orchestration is planned for Phase 32.",
    state: "planned",
    phase: 32,
  },
  {
    id: "settings",
    label: "Application settings",
    description: "V4 application metadata, state namespaces and release policy.",
    state: "ready",
    phase: 18,
  },
] as const;

export const APPLICATION_REGISTRY: readonly VersionedApplicationDefinition[] = [
  {
    id: "ontology-dashboard-original",
    version: "v1",
    applicationIdentity: "Ontology Dashboard · Original",
    route: (projectId) => projectRoute(projectId),
    storageNamespace: "ontology-dashboard:v1",
    queryNamespace: "ontology-dashboard:v1",
    collaborationNamespace: "ontology-dashboard:v1",
    surfaces: [],
  },
  {
    id: "blueprint-workbench-v1",
    version: "v2",
    applicationIdentity: "Blueprint Workbench · V1",
    route: (projectId) => projectRoute(projectId, "/blueprint"),
    storageNamespace: "ontology-dashboard:v2",
    queryNamespace: "ontology-dashboard:v2",
    collaborationNamespace: "ontology-dashboard:v2",
    surfaces: [],
  },
  {
    id: "blueprint-workbench-v2",
    version: "v3",
    applicationIdentity: "Blueprint Workbench · V2",
    route: (projectId) => projectRoute(projectId, "/blueprint-v2"),
    storageNamespace: "ontology-dashboard:v3",
    queryNamespace: "ontology-dashboard:v3",
    collaborationNamespace: "ontology-dashboard:v3",
    surfaces: [],
  },
  {
    id: "ontology-commercial-v4",
    version: "v4",
    applicationIdentity: "Ontology Platform · Commercial V4",
    route: (projectId) => projectRoute(projectId, "/blueprint-v4"),
    storageNamespace: "ontology-dashboard:v4",
    queryNamespace: "ontology-dashboard:v4",
    collaborationNamespace: "ontology-dashboard:v4",
    surfaces: V4_SURFACES,
  },
] as const;

export function applicationDefinition(version: ApplicationVersion): VersionedApplicationDefinition {
  const definition = APPLICATION_REGISTRY.find((item) => item.version === version);
  if (!definition) throw new Error(`Unknown application version: ${version}`);
  return definition;
}

export const COMMERCIAL_V4_APPLICATION = applicationDefinition("v4");

export function accessibleCommercialSurfaces(permissions: readonly string[]) {
  return COMMERCIAL_V4_APPLICATION.surfaces.map((surface) => ({
    ...surface,
    accessible: !surface.permission || permissions.includes(surface.permission),
  }));
}
