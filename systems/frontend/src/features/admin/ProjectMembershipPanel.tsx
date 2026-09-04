import { useEffect, useMemo, useState } from "react";

import {
  getProjectMembers,
  getProjects,
  updateProjectMembership,
} from "../../api";
import type { Project, ProjectMembership } from "../../types";

const ROLE_OPTIONS = [
  "tenant_admin",
  "process_manager",
  "process_engineer",
  "executive_viewer",
  "quality_auditor",
  "field_technician",
  "fde",
  "ml_validator",
] as const;

export function ProjectMembershipPanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [members, setMembers] = useState<ProjectMembership[]>([]);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getProjects()
      .then((items) => {
        setProjects(items);
        setProjectId((current) => current || items[0]?.id || "");
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Project 목록을 불러오지 못했습니다.");
      });
  }, []);

  useEffect(() => {
    if (!projectId) {
      setMembers([]);
      return;
    }
    getProjectMembers(projectId)
      .then(setMembers)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Project membership을 불러오지 못했습니다.");
      });
  }, [projectId]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId) ?? null,
    [projectId, projects],
  );

  function patchMember(userId: string, patch: Partial<ProjectMembership>) {
    setMembers((current) => current.map((item) => (
      item.user_id === userId ? { ...item, ...patch } : item
    )));
  }

  async function save(member: ProjectMembership) {
    setSavingUserId(member.user_id);
    setError("");
    try {
      const updated = await updateProjectMembership(projectId, member.user_id, {
        status: member.status,
        roles: member.roles,
      });
      patchMember(member.user_id, updated);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Project membership 저장에 실패했습니다.");
    } finally {
      setSavingUserId(null);
    }
  }

  return (
    <section className="admin-card project-membership-panel" aria-labelledby="project-membership-title">
      <div className="admin-card-header">
        <div>
          <p className="eyebrow">Project access</p>
          <h2 id="project-membership-title">Project membership & roles</h2>
          <p className="muted">
            사용자의 역할과 권한은 선택한 Project 안에서만 적용됩니다.
          </p>
        </div>
        <label>
          Project
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.display_name}</option>
            ))}
          </select>
        </label>
      </div>

      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      {selectedProject ? (
        <p className="muted">{selectedProject.description || selectedProject.domain_pack_code}</p>
      ) : null}

      <div className="admin-membership-list">
        {members.map((member) => (
          <article className="admin-membership-row" key={member.user_id}>
            <div>
              <strong>{member.display_name}</strong>
              <p className="muted">{member.email}</p>
            </div>
            <label>
              Status
              <select
                value={member.status}
                onChange={(event) => patchMember(member.user_id, {
                  status: event.target.value as ProjectMembership["status"],
                })}
              >
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
            </label>
            <fieldset>
              <legend>Project roles</legend>
              <div className="admin-role-options">
                {ROLE_OPTIONS.map((role) => (
                  <label key={role}>
                    <input
                      type="checkbox"
                      checked={member.roles.includes(role)}
                      onChange={(event) => {
                        const roles = event.target.checked
                          ? [...member.roles, role].sort()
                          : member.roles.filter((item) => item !== role);
                        patchMember(member.user_id, { roles });
                      }}
                    />
                    {role.replaceAll("_", " ")}
                  </label>
                ))}
              </div>
            </fieldset>
            <button
              type="button"
              disabled={savingUserId === member.user_id || member.roles.length === 0}
              onClick={() => void save(member)}
            >
              {savingUserId === member.user_id ? "Saving…" : "Save membership"}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
