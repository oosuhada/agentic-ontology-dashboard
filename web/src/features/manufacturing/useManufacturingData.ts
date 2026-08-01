import { useCallback, useEffect, useState } from "react";
import {
  getAuditWorkspace,
  getDomainPacks,
  getEvidence,
  getExecutiveWorkspace,
  getFDEWorkspace,
  getFieldWorkspace,
  getLayout,
  getModelConsole,
  getProjects,
  getProjectEvents,
  getProjectWorkspaces,
  getReport,
} from "../../api";
import type {
  AppRole,
  DomainPack,
  Evidence,
  EventSummary,
  FollowUp,
  Intent,
  Layout,
  Project,
  Report,
  Role,
  Workspace,
} from "../../types";
import type { RoleWorkspaceData } from "../roles/types";

export function useWorkspaceCatalog(
  activeProjectId: string | null,
  activateProject: (projectId: string) => Promise<void>,
  onError: (message: string) => void,
) {
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [domainPacks, setDomainPacks] = useState<DomainPack[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [selectedEventId, setSelectedEventId] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getProjects(), getDomainPacks()])
      .then(([projectItems, packItems]) => {
        if (!active) return;
        const routeProjectId = window.location.pathname.match(/^\/app\/projects\/([^/]+)/)?.[1];
        const decodedRouteProjectId = routeProjectId ? decodeURIComponent(routeProjectId) : "";
        const initialProjectId = projectItems.some((project) => project.id === decodedRouteProjectId)
          ? decodedRouteProjectId
          : projectItems.some((project) => project.id === activeProjectId)
            ? activeProjectId ?? ""
            : projectItems[0]?.id ?? "";
        setProjects(projectItems);
        setDomainPacks(packItems);
        setSelectedProjectId(initialProjectId);
      })
      .catch((reason: Error) => active && onError(reason.message));
    return () => { active = false; };
  }, [activeProjectId, onError]);

  useEffect(() => {
    if (!selectedProjectId) {
      setEvents([]);
      setWorkspaces([]);
      setSelectedWorkspaceId("");
      setSelectedEventId("");
      return;
    }
    let active = true;
    setEvents([]);
    setWorkspaces([]);
    setSelectedWorkspaceId("");
    setSelectedEventId("");
    activateProject(selectedProjectId)
      .then(() => Promise.all([
        getProjectWorkspaces(selectedProjectId),
        getProjectEvents(selectedProjectId),
      ]))
      .then(([workspaceItems, eventItems]) => {
        if (!active) return;
        setEvents(eventItems);
        setSelectedEventId((current) => (
          eventItems.some((event) => event.event_id === current)
            ? current
            : eventItems[0]?.event_id ?? ""
        ));
        setWorkspaces(workspaceItems);
        setSelectedWorkspaceId((current) => (
          workspaceItems.some((workspace) => workspace.id === current)
            ? current
            : workspaceItems[0]?.id ?? ""
        ));
      })
      .catch((reason: Error) => active && onError(reason.message));
    return () => { active = false; };
  }, [selectedProjectId, activateProject, onError]);

  return {
    events,
    projects,
    workspaces,
    domainPacks,
    selectedProjectId,
    setSelectedProjectId,
    selectedWorkspaceId,
    setSelectedWorkspaceId,
    selectedEventId,
    setSelectedEventId,
  };
}

export function useEventDetail(
  eventId: string,
  intent: Intent,
  role: Role,
  onError: (message: string) => void,
) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [lastFollowUp, setLastFollowUp] = useState<FollowUp | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (nextEventId: string, activeIntent: Intent) => {
    if (!nextEventId) return;
    setLoading(true);
    try {
      const [nextEvidence, nextReport, nextLayout] = await Promise.all([
        getEvidence(nextEventId),
        getReport(nextEventId, role, true),
        getLayout(nextEventId, role, activeIntent, true),
      ]);
      setEvidence(nextEvidence);
      setReport(nextReport);
      setLayout(nextLayout);
      setLastFollowUp(null);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Evidence 화면을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [onError, role]);

  useEffect(() => {
    void load(eventId, intent);
  }, [eventId, intent, load]);

  return {
    evidence,
    report,
    layout,
    lastFollowUp,
    loading,
    load,
    setReport,
    setLayout,
    setLastFollowUp,
  };
}

export function useRoleWorkspace(
  appRole: AppRole,
  projectId: string,
  workspaceId: string,
  eventId: string,
  onError: (message: string) => void,
) {
  const [data, setData] = useState<RoleWorkspaceData | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (nextWorkspaceId: string, nextEventId: string) => {
    if (!nextWorkspaceId) return;
    if (projectId !== "manufacturing-demo-project") {
      setData(null);
      return;
    }
    const supported = new Set<AppRole>([
      "executive_viewer",
      "quality_auditor",
      "maintenance_technician",
      "fde",
      "ml_validator",
    ]);
    if (!supported.has(appRole)) {
      setData(null);
      return;
    }
    if (appRole === "quality_auditor" && !nextEventId) return;
    setLoading(true);
    try {
      const nextData = appRole === "executive_viewer"
        ? await getExecutiveWorkspace(nextWorkspaceId)
        : appRole === "quality_auditor"
          ? await getAuditWorkspace(nextWorkspaceId, nextEventId)
          : appRole === "maintenance_technician"
            ? await getFieldWorkspace(nextWorkspaceId)
            : appRole === "fde"
              ? await getFDEWorkspace(nextWorkspaceId)
              : await getModelConsole(nextWorkspaceId);
      setData(nextData);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "역할 전용 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [appRole, projectId, onError]);

  useEffect(() => {
    void load(workspaceId, eventId);
  }, [workspaceId, eventId, load]);

  return { data, loading, load };
}
