import { Button, Callout, Card, Spinner, Tag } from "@blueprintjs/core";
import { useEffect, useMemo, useState } from "react";
import {
  getDatasetCatalogPage,
  getProject3Status,
  getProjectEvents,
  getProjects,
  getProjectWorkspaces,
} from "../../api";
import {
  agentPath,
  datasetCatalogPath,
  governancePath,
  navigate,
  ontologyPath,
} from "../../routing";
import type { EventSummary, Project, Workspace } from "../../types";
import { useAuth } from "../auth/AuthContext";
import type { Project3IntegrationSnapshot } from "../ontology/types";

interface ProjectHomePageProps {
  projectId: string;
}

function statusIntent(status: string): "success" | "warning" | "danger" | "none" {
  if (["active", "ready", "succeeded"].includes(status)) return "success";
  if (["failed", "unavailable", "archived"].includes(status)) return "danger";
  if (["draft", "degraded", "pending", "indexing"].includes(status)) return "warning";
  return "none";
}

export function ProjectHomePage({ projectId }: ProjectHomePageProps) {
  const { user, setActiveProject } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [datasetCount, setDatasetCount] = useState(0);
  const [integration, setIntegration] = useState<Project3IntegrationSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        if (user?.active_project_id !== projectId) await setActiveProject(projectId);
        const [projects, nextWorkspaces, nextEvents, datasets, project3] = await Promise.all([
          getProjects(),
          getProjectWorkspaces(projectId),
          getProjectEvents(projectId),
          getDatasetCatalogPage({ project_id: projectId, limit: 1 }),
          getProject3Status(projectId),
        ]);
        if (cancelled) return;
        setProject(projects.find((item) => item.id === projectId) ?? null);
        setWorkspaces(nextWorkspaces);
        setEvents(nextEvents);
        setDatasetCount(datasets.total);
        setIntegration(project3);
        setError("");
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Project Home을 불러오지 못했습니다.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [projectId]);

  const defaultWorkspace = useMemo(
    () => workspaces.find((item) => item.id === project?.default_workspace_id) ?? workspaces[0] ?? null,
    [project?.default_workspace_id, workspaces],
  );
  const roleCodes = user?.project_roles[projectId] ?? user?.active_project_roles ?? [];
  const criticalEvents = events.filter((item) => item.status === "critical").length;

  if (loading && !project) {
    return <main className="project-home-loading"><Spinner size={32} /><p>Project resources를 구성하고 있습니다.</p></main>;
  }

  return (
    <main className="project-home-page">
      <header className="project-home-header">
        <div>
          <span className="eyebrow">PROJECT HOME</span>
          <h1>{project?.display_name ?? projectId}</h1>
          <p>{project?.description || "Governed resources, workspaces, roles, and integration readiness."}</p>
        </div>
        <div className="project-home-actions">
          <Tag intent={statusIntent(project?.status ?? "draft")}>{project?.status ?? "unknown"}</Tag>
          <Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Open Dashboard</Button>
        </div>
      </header>

      {error ? <Callout intent="danger" title="Project Home error">{error}</Callout> : null}

      <section className="project-home-kpis">
        <Card elevation={0}><small>WORKSPACES</small><strong>{workspaces.length}</strong><span>{defaultWorkspace?.display_name ?? "No default workspace"}</span></Card>
        <Card elevation={0}><small>DATASETS</small><strong>{datasetCount}</strong><span>immutable catalog entries</span></Card>
        <Card elevation={0}><small>RISK EVENTS</small><strong>{events.length}</strong><span>{criticalEvents} critical</span></Card>
        <Card elevation={0}><small>PROJECT 3</small><strong>{integration?.health.status ?? "unknown"}</strong><span>{integration?.readiness?.node_count?.toLocaleString() ?? 0} graph nodes</span></Card>
      </section>

      <section className="project-home-grid">
        <Card elevation={0} className="project-home-panel">
          <header><div><small>ACTIVE ROLE CONTEXT</small><h2>{roleCodes.length} allowed roles</h2></div></header>
          <div className="project-home-role-list">
            {roleCodes.map((role) => <Tag key={role} minimal>{role}</Tag>)}
            {!roleCodes.length ? <span>No project role assigned.</span> : null}
          </div>
          <p>Dashboard의 Role selector는 이 Project에 허용된 역할 안에서만 template과 workflow 관점을 전환합니다.</p>
        </Card>

        <Card elevation={0} className="project-home-panel">
          <header><div><small>INTEGRATION READINESS</small><h2>Typed Project 3 boundary</h2></div><Tag intent={statusIntent(integration?.health.status ?? "unavailable")}>{integration?.health.status ?? "unavailable"}</Tag></header>
          <dl>
            <div><dt>Mapped project</dt><dd>{integration?.health.mapped_project_id ?? "—"}</dd></div>
            <div><dt>Can query</dt><dd>{integration?.readiness?.can_query ? "Yes" : "No"}</dd></div>
            <div><dt>Relationships</dt><dd>{integration?.readiness?.relationship_count?.toLocaleString() ?? 0}</dd></div>
            <div><dt>Degraded reason</dt><dd>{integration?.degraded_reason ?? "None"}</dd></div>
          </dl>
        </Card>
      </section>

      <section className="project-home-workspaces">
        <header><div><small>WORKSPACES</small><h2>Open a governed workbench</h2></div></header>
        <div>
          {workspaces.map((workspace) => (
            <Card key={workspace.id} elevation={0}>
              <div><strong>{workspace.display_name}</strong><Tag minimal>{workspace.domain_pack}</Tag></div>
              <small>{workspace.id}</small>
              <div className="project-workspace-actions">
                <Button small onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button>
                <Button small onClick={() => navigate(agentPath(projectId, workspace.id))}>Agent</Button>
                <Button small onClick={() => navigate(ontologyPath(projectId, workspace.id))}>Ontology</Button>
                <Button small onClick={() => navigate(governancePath(projectId, workspace.id))}>Governance</Button>
                <Button small onClick={() => navigate(datasetCatalogPath(projectId))}>Datasets</Button>
              </div>
            </Card>
          ))}
          {!workspaces.length ? <p>No accessible workspace in this Project.</p> : null}
        </div>
      </section>
    </main>
  );
}
