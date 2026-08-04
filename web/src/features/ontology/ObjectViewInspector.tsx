import { Activity, GitBranch, Link2, Play, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import { InspectorTabs } from "../../ui/foundry/InspectorTabs";
import { PropertyTable } from "../../ui/foundry/PropertyTable";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { displayObjectValue, objectIdentity, objectStatus } from "./objectPresentation";
import type {
  ActionTypeDefinition,
  ObjectRecord,
  ObjectTypeDefinition,
  OntologyTraversal,
  Project3IntegrationSnapshot,
} from "./types";

type ObjectInspectorTab = "properties" | "links" | "actions" | "lineage";

interface ObjectViewInspectorProps {
  object: ObjectRecord | null;
  definition: ObjectTypeDefinition | null;
  traversal: OntologyTraversal | null;
  traversalLoading: boolean;
  actions: ActionTypeDefinition[];
  status: Project3IntegrationSnapshot | null;
  permissions: string[];
  actionBusyId: string | null;
  actionNotice: string;
  onInvokeAction: (action: ActionTypeDefinition) => void;
}

function valueType(value: unknown): string {
  if (Array.isArray(value)) return "array";
  if (value === null) return "null";
  return typeof value;
}

export function ObjectViewInspector({
  object,
  definition,
  traversal,
  traversalLoading,
  actions,
  status,
  permissions,
  actionBusyId,
  actionNotice,
  onInvokeAction,
}: ObjectViewInspectorProps) {
  const [activeTab, setActiveTab] = useState<ObjectInspectorTab>("properties");
  useEffect(() => setActiveTab("properties"), [object?.id]);

  if (!object) return <aside className="ontology-inspector-pane"><EmptyState title="Select an object" detail="Properties, relationships, governed actions, and lineage will appear here." /></aside>;
  const statusLabel = objectStatus(object);
  const relatedObjects = traversal?.nodes.filter((item) => item.id !== object.id) ?? [];

  return (
    <aside className="ontology-inspector-pane">
      <header className="ontology-object-entity-header">
        <div><span className="section-label">{definition?.display_name ?? object.object_type}</span><strong>{objectIdentity(object)}</strong><small>{object.id}</small></div>
        <StatusPill intent={statusLabel === "critical" ? "danger" : statusLabel === "warning" ? "warning" : "success"}>{statusLabel}</StatusPill>
      </header>
      <InspectorTabs
        activeTab={activeTab}
        onChange={setActiveTab}
        label="Object inspector sections"
        tabs={[
          { id: "properties", label: "Properties", count: Object.keys(object.properties).length, icon: <Settings2 size={11} /> },
          { id: "links", label: "Links", count: traversal?.edges.length ?? 0, icon: <Link2 size={11} /> },
          { id: "actions", label: "Actions", count: actions.length, icon: <Play size={11} /> },
          { id: "lineage", label: "Lineage", count: object.source_refs.length, icon: <GitBranch size={11} /> },
        ]}
      />
      <div className="ontology-inspector-scroll">
        {activeTab === "properties" ? (
          <PropertyTable rows={[
            { id: "object_type", label: "Object type", value: object.object_type, type: "object type" },
            { id: "workspace", label: "Workspace", value: object.workspace_id, type: "scope", mono: true },
            { id: "version", label: "Version", value: object.version, type: "integer", numeric: true },
            ...Object.entries(object.properties).map(([key, value]) => ({ id: key, label: definition?.properties.find((item) => item.id === key)?.display_name ?? key, value: displayObjectValue(value), type: definition?.properties.find((item) => item.id === key)?.value_type ?? valueType(value), numeric: typeof value === "number", mono: key.endsWith("_id") })),
          ]} />
        ) : null}

        {activeTab === "links" ? (
          <div className="ontology-link-list">
            {traversalLoading ? <p>Loading governed links…</p> : null}
            {traversal?.edges.map((edge) => {
              const relatedId = edge.source_object_id === object.id ? edge.target_object_id : edge.source_object_id;
              const related = relatedObjects.find((item) => item.id === relatedId);
              return <article key={edge.id}><div><StatusPill intent="primary">{edge.link_type}</StatusPill><small>v{edge.version}</small></div><strong>{related ? objectIdentity(related) : relatedId}</strong><span>{edge.source_object_id} → {edge.target_object_id}</span></article>;
            })}
            {!traversalLoading && !traversal?.edges.length ? <EmptyState title="No links" detail="No governed links were returned for the selected direction and depth." /> : null}
          </div>
        ) : null}

        {activeTab === "actions" ? (
          <div className="ontology-action-list">
            {actions.map((action) => {
              const missingPermissions = action.required_permissions.filter((permission) => !permissions.includes(permission));
              const requiresParameters = action.parameters.some((parameter) => parameter.required);
              const disabled = Boolean(missingPermissions.length || requiresParameters || actionBusyId);
              return (
                <article key={action.id}>
                  <div><Activity size={15} /><span><strong>{action.display_name}</strong><small>{action.description}</small></span></div>
                  <div className="ontology-action-meta"><StatusPill intent={action.requires_human_approval ? "warning" : "neutral"}>{action.requires_human_approval ? "approval required" : "direct"}</StatusPill>{action.parameters.length ? <StatusPill>{action.parameters.length} parameters</StatusPill> : null}</div>
                  {missingPermissions.length ? <small>Read only · missing {missingPermissions.join(", ")}</small> : requiresParameters ? <small>Parameter form required; direct invocation is disabled in this compact inspector.</small> : null}
                  <button type="button" className="fd-toolbar-button" disabled={disabled} onClick={() => onInvokeAction(action)}><Play size={12} />{actionBusyId === action.id ? "Running" : "Invoke action"}</button>
                </article>
              );
            })}
            {!actions.length ? <EmptyState title="No actions" detail="No action type is registered for this object type." /> : null}
            {actionNotice ? <p className="ontology-action-notice">{actionNotice}</p> : null}
          </div>
        ) : null}

        {activeTab === "lineage" ? (
          <>
            <PropertyTable rows={[
              { id: "project", label: "Mapped Project", value: status?.health.mapped_project_id ?? "—", type: "project", mono: true },
              { id: "schema", label: "Graph schema", value: status?.schema?.schema_version ?? "—", type: "version" },
              { id: "lifecycle", label: "Lifecycle", value: status?.readiness?.lifecycle_status ?? "degraded", status: { label: status?.readiness?.lifecycle_status ?? "degraded", intent: status?.health.available ? "success" : "warning" } },
              { id: "graph_size", label: "Graph size", value: status?.readiness ? `${status.readiness.node_count} nodes / ${status.readiness.relationship_count} relationships` : "—", type: "graph" },
            ]} />
            <div className="ontology-source-list"><span className="section-label">SOURCE REFERENCES</span>{object.source_refs.map((reference) => <code key={reference}>{reference}</code>)}{!object.source_refs.length ? <p>No source references.</p> : null}</div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
