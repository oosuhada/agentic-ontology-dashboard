import { describe, expect, it } from "vitest";
import type { AuthUser } from "../../../types";
import {
  RELIABILITY_ROLE_EXPERIENCES,
  reliabilityNavigation,
  resolveReliabilityRoleExperience,
} from "./roleExperience";

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    user_id: "user-1",
    email: "user@example.com",
    display_name: "Reliability User",
    status: "active",
    roles: ["process_engineer"],
    permissions: [],
    workspace_scopes: [],
    project_scopes: [],
    project_roles: {},
    active_project_id: "project-1",
    active_project_roles: [],
    is_admin: false,
    default_path: "/app",
    landing_key: "process_engineer",
    ...overrides,
  };
}

describe("resolveReliabilityRoleExperience", () => {
  it("resolves executive_viewer from active project roles", () => {
    const experience = resolveReliabilityRoleExperience(user({
      roles: ["process_manager"],
      active_project_roles: ["executive_viewer"],
    }));

    expect(experience.kind).toBe("executive");
    expect(resolveReliabilityRoleExperience(user({
      roles: ["executive_viewer"],
      active_project_roles: ["maintenance_technician"],
    })).kind).toBe("maintenance");
  });

  it("falls back to account roles and resolves process_manager", () => {
    const experience = resolveReliabilityRoleExperience(user({
      roles: ["process_manager"],
      active_project_roles: [],
      landing_key: "process_manager",
    }));

    expect(experience.kind).toBe("operations");
  });

  it("resolves maintenance_technician into the maintenance persona", () => {
    const experience = resolveReliabilityRoleExperience(user({
      roles: ["maintenance_technician"],
      landing_key: "maintenance_technician",
    }));

    expect(experience.kind).toBe("maintenance");
  });

  it("resolves process_engineer and preserves engineering as the fallback", () => {
    expect(resolveReliabilityRoleExperience(user()).kind).toBe("engineering");
    expect(resolveReliabilityRoleExperience(user({
      roles: ["quality_auditor"],
      landing_key: "quality_auditor",
    })).kind).toBe("engineering");
  });

  it("preserves existing admin priority without overriding executive_viewer", () => {
    expect(resolveReliabilityRoleExperience(user({
      roles: ["tenant_admin"],
      is_admin: true,
      landing_key: "tenant_admin",
    })).kind).toBe("operations");
    expect(resolveReliabilityRoleExperience(user({
      roles: ["maintenance_technician"],
      is_admin: true,
      landing_key: "maintenance_technician",
    })).kind).toBe("operations");

    expect(resolveReliabilityRoleExperience(user({
      active_project_roles: ["executive_viewer", "process_manager"],
      is_admin: true,
    })).kind).toBe("executive");
  });
});

describe("RELIABILITY_ROLE_EXPERIENCES", () => {
  it("defines the intended default view for every role experience", () => {
    expect(RELIABILITY_ROLE_EXPERIENCES.executive.defaultView).toBe("reports");
    expect(RELIABILITY_ROLE_EXPERIENCES.operations.defaultView).toBe("operations");
    expect(RELIABILITY_ROLE_EXPERIENCES.engineering.defaultView).toBe("overview");
    expect(RELIABILITY_ROLE_EXPERIENCES.maintenance.defaultView).toBe("operations");
  });

  it("renders each role's default surface as navigation item 01", () => {
    for (const experience of Object.values(RELIABILITY_ROLE_EXPERIENCES)) {
      expect(reliabilityNavigation(experience)[0].view).toBe(experience.defaultView);
    }
  });

  it("uses role-specific navigation order instead of one shared dashboard menu", () => {
    expect(reliabilityNavigation(RELIABILITY_ROLE_EXPERIENCES.executive).map((item) => item.view)).toEqual([
      "reports", "operations", "overview", "objects",
    ]);
    expect(reliabilityNavigation(RELIABILITY_ROLE_EXPERIENCES.operations).map((item) => item.view)).toEqual([
      "operations", "overview", "objects", "reports",
    ]);
    expect(reliabilityNavigation(RELIABILITY_ROLE_EXPERIENCES.engineering).map((item) => item.view)).toEqual([
      "overview", "objects", "operations", "reports",
    ]);
  });

  it("uses distinct presentation surfaces for executive, manager, and engineer", () => {
    expect(RELIABILITY_ROLE_EXPERIENCES.executive.primarySurface).toBe("executive_brief");
    expect(RELIABILITY_ROLE_EXPERIENCES.operations.primarySurface).toBe("decision_workspace");
    expect(RELIABILITY_ROLE_EXPERIENCES.engineering.primarySurface).toBe("monitoring_workspace");
  });

  it("defines the intended first-screen focus for every role experience", () => {
    expect(RELIABILITY_ROLE_EXPERIENCES.executive.focusIntent).toBe("continuity");
    expect(RELIABILITY_ROLE_EXPERIENCES.operations.focusIntent).toBe("decision");
    expect(RELIABILITY_ROLE_EXPERIENCES.engineering.focusIntent).toBe("investigation");
    expect(RELIABILITY_ROLE_EXPERIENCES.maintenance.focusIntent).toBe("execution");
  });

  it("defines the primary work question for every role experience", () => {
    expect(RELIABILITY_ROLE_EXPERIENCES.executive.primaryQuestion.ko).toBe("현재 어떤 운영 가치를 보호하고 있고 KPI에 어떤 영향을 주는가?");
    expect(RELIABILITY_ROLE_EXPERIENCES.operations.primaryQuestion.ko).toBe("지금 어떤 판단이 가장 큰 생산·비용 가치를 보호하는가?");
    expect(RELIABILITY_ROLE_EXPERIENCES.engineering.primaryQuestion.ko).toBe("어떤 설비를 조사해야 하고 근거는 무엇인가?");
    expect(RELIABILITY_ROLE_EXPERIENCES.maintenance.primaryQuestion.ko).toBe("지금 수행해야 할 승인된 작업은 무엇인가?");
  });

  it("keeps navigation views unique and all user-facing labels bilingual", () => {
    for (const experience of Object.values(RELIABILITY_ROLE_EXPERIENCES)) {
      const views = experience.navigation.map((item) => item.view);
      expect(new Set(views).size).toBe(views.length);
      expect(views).toContain(experience.defaultView);
      expect(experience.label.ko).toBeTruthy();
      expect(experience.label.en).toBeTruthy();
      expect(experience.primaryQuestion.ko).toBeTruthy();
      expect(experience.primaryQuestion.en).toBeTruthy();
      expect(experience.firstScreenIntent.ko).toBeTruthy();
      expect(experience.firstScreenIntent.en).toBeTruthy();
      expect(experience.operationalFocusHint.ko).toBeTruthy();
      expect(experience.operationalFocusHint.en).toBeTruthy();

      for (const item of experience.navigation) {
        expect(item.label.ko).toBeTruthy();
        expect(item.label.en).toBeTruthy();
        expect(item.detail.ko).toBeTruthy();
        expect(item.detail.en).toBeTruthy();
        expect(item.page.title.ko).toBeTruthy();
        expect(item.page.title.en).toBeTruthy();
      }
    }
  });
});
