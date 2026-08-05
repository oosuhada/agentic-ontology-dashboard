import { API_BASE } from "../../api";

export interface BoundedContextDefinition {
  id: string;
  display_name: string;
  kind: "core" | "supporting" | "integration";
  owns: string[];
  consumes: string[];
  publishes: string[];
}

export interface ProjectV4ApplicationDefinition {
  application_id: "ontology-commercial-v4";
  application_version: "v4";
  project_id: string;
  workspace_ids: string[];
  domain_pack: {
    code: string;
    version: string;
    display_name: string;
    description: string;
    status: "active" | "draft" | "disabled";
    namespace: string;
    vocabulary: {
      object_label: string;
      object_plural_label: string;
      event_label: string;
      action_label: string;
      risk_label: string;
    };
    bounded_contexts: BoundedContextDefinition[];
    object_type_ids: string[];
    interface_ids: string[];
    action_type_ids: string[];
    feature_flags: Record<string, boolean>;
  };
  platform_namespace: "ontology_dashboard";
  compatibility_namespaces: string[];
  configuration_source: "project_metadata" | "default_platform";
}

export async function getProjectV4ApplicationDefinition(projectId: string): Promise<ProjectV4ApplicationDefinition> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/applications/v4`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `V4 application definition failed: ${response.status}`);
  }
  return payload as ProjectV4ApplicationDefinition;
}
