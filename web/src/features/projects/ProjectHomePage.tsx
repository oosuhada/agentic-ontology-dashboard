import { Button, Callout, Card, Tag } from "@blueprintjs/core";
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
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import { useI18n } from "../../ui/i18n/I18nProvider";

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
  const { locale } = useI18n();
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
  const attentionEvents = events
    .filter((item) => ["critical", "warning", "attention", "data_quality_hold"].includes(item.status))
    .sort((a, b) => (b.failure_probability ?? 0) - (a.failure_probability ?? 0))
    .slice(0, 4);
  const project3Available = Boolean(integration?.health.available);

  if (loading && !project) {
    return <main className="project-home-loading"><WorkbenchState kind="loading" title="Project resources를 구성하고 있습니다." /></main>;
  }

  return (
    <main className="project-home-page">
      <header className="project-home-header">
        <div>
          <span className="eyebrow">{locale === "ko-KR" ? "프로젝트 홈" : "PROJECT HOME"}</span>
          <h1>{project?.display_name ?? projectId}</h1>
          <p>{project?.description || (locale === "ko-KR" ? "관리형 리소스, Workspace, 역할과 연결 상태를 확인합니다." : "Governed resources, workspaces, roles, and integration readiness.")}</p>
        </div>
        <div className="project-home-actions">
          <Tag intent={statusIntent(project?.status ?? "draft")}>{project?.status ?? "unknown"}</Tag>
          <Button intent="primary" icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>{locale === "ko-KR" ? "내 Dashboard 열기" : "Open my dashboard"}</Button>
        </div>
      </header>

      {error ? <Callout intent="danger" title="Project Home error">{error}</Callout> : null}
      {!project3Available ? <Callout intent="warning" title={locale === "ko-KR" ? "일부 기능이 제한되어 있습니다" : "Some capabilities are limited"}>{locale === "ko-KR" ? "Project 3 Graph·RAG 연결이 준비되지 않아 관계 그래프와 Vector 근거 검색은 제한됩니다. Dashboard와 Dataset, 관계형 Object 조회는 계속 사용할 수 있습니다." : "Project 3 Graph and RAG are unavailable. Dashboard, Dataset, and relational object browsing remain available."}</Callout> : null}

      <section className="project-home-kpis">
        <Card elevation={0}><small>{locale === "ko-KR" ? "조치 필요 Risk Event" : "RISK EVENTS NEEDING ACTION"}</small><strong>{attentionEvents.length}</strong><span>{criticalEvents} {locale === "ko-KR" ? "긴급 검토" : "critical"}</span></Card>
        <Card elevation={0}><small>DATASETS</small><strong>{datasetCount}</strong><span>{locale === "ko-KR" ? "변경 불가 Catalog 리소스" : "immutable catalog entries"}</span></Card>
        <Card elevation={0}><small>WORKSPACES</small><strong>{workspaces.length}</strong><span>{defaultWorkspace?.display_name ?? (locale === "ko-KR" ? "기본 Workspace 없음" : "No default workspace")}</span></Card>
        <Card elevation={0}><small>PROJECT 3</small><strong>{project3Available ? (locale === "ko-KR" ? "연결됨" : "available") : (locale === "ko-KR" ? "연결 필요" : "unavailable")}</strong><span>{integration?.readiness?.node_count?.toLocaleString() ?? 0} graph nodes</span></Card>
      </section>

      <section className="project-home-grid">
        <Card elevation={0} className="project-home-panel project-home-attention-panel">
          <header><div><small>{locale === "ko-KR" ? "지금 확인할 항목" : "NEEDS ATTENTION"}</small><h2>{locale === "ko-KR" ? "위험도가 높은 설비" : "Highest-risk equipment"}</h2></div><Button minimal small onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>{locale === "ko-KR" ? "Dashboard에서 보기" : "Open dashboard"}</Button></header>
          <div className="project-home-attention-list">
            {attentionEvents.map((event) => <button type="button" key={event.event_id} onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}><div><strong>{event.equipment.display_name}</strong><small>{event.event_id} · {event.equipment.line}</small></div><span>{Math.round((event.failure_probability ?? 0) * 100)}%</span></button>)}
            {!attentionEvents.length ? <p>{locale === "ko-KR" ? "현재 조치가 필요한 Risk Event가 없습니다." : "No risk events currently require action."}</p> : null}
          </div>
        </Card>
        <Card elevation={0} className="project-home-panel">
          <header><div><small>{locale === "ko-KR" ? "현재 역할 범위" : "ACTIVE ROLE CONTEXT"}</small><h2>{roleCodes.length} {locale === "ko-KR" ? "개 역할 사용 가능" : "allowed roles"}</h2></div></header>
          <div className="project-home-role-list">
            {roleCodes.map((role) => <Tag key={role} minimal>{role.replaceAll("_", " ")}</Tag>)}
            {!roleCodes.length ? <span>{locale === "ko-KR" ? "할당된 Project 역할이 없습니다." : "No project role assigned."}</span> : null}
          </div>
          <p>{locale === "ko-KR" ? "Dashboard의 역할 선택기는 이 Project에서 허용된 역할 안에서만 Template과 업무 관점을 전환합니다." : "The role selector changes templates and workflow perspectives only within the roles allowed for this project."}</p>
        </Card>

        <Card elevation={0} className="project-home-panel">
          <header><div><small>{locale === "ko-KR" ? "연결 상태" : "INTEGRATION READINESS"}</small><h2>Typed Project 3 boundary</h2></div><Tag intent={statusIntent(integration?.health.status ?? "unavailable")}>{project3Available ? (locale === "ko-KR" ? "연결됨" : integration?.health.status) : (locale === "ko-KR" ? "연결 필요" : "unavailable")}</Tag></header>
          <dl>
            <div><dt>Mapped project</dt><dd>{integration?.health.mapped_project_id ?? "—"}</dd></div>
            <div><dt>Can query</dt><dd>{integration?.readiness?.can_query ? "Yes" : "No"}</dd></div>
            <div><dt>Relationships</dt><dd>{integration?.readiness?.relationship_count?.toLocaleString() ?? 0}</dd></div>
            <div><dt>Degraded reason</dt><dd>{integration?.degraded_reason ?? "None"}</dd></div>
          </dl>
        </Card>
      </section>

      <section className="project-home-workspaces">
        <header><div><small>WORKSPACES</small><h2>{locale === "ko-KR" ? "업무 화면 열기" : "Open a governed workbench"}</h2></div></header>
        <div>
          {workspaces.map((workspace) => (
            <Card key={workspace.id} elevation={0}>
              <div><strong>{workspace.display_name}</strong><Tag minimal>{workspace.domain_pack}</Tag></div>
              <small>{workspace.id}</small>
              <div className="project-workspace-actions">
                <Button intent="primary" small onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button>
                <details className="project-workspace-more"><summary>{locale === "ko-KR" ? "다른 Workbench" : "More workbenches"}</summary><div><Button small onClick={() => navigate(agentPath(projectId, workspace.id))}>Agent</Button><Button small onClick={() => navigate(ontologyPath(projectId, workspace.id))}>Ontology</Button><Button small onClick={() => navigate(governancePath(projectId, workspace.id))}>Governance</Button><Button small onClick={() => navigate(datasetCatalogPath(projectId))}>Datasets</Button></div></details>
              </div>
            </Card>
          ))}
          {!workspaces.length ? <p>No accessible workspace in this Project.</p> : null}
        </div>
      </section>
    </main>
  );
}
