import type { MessageKey } from "../../ui/i18n/messages";
import type { AppRole } from "../../types";
import type { AdaptiveExperienceProfile, AdaptiveProfileId } from "./adaptiveExperience";
import type { RoleLanding } from "./roleLanding";

type Translate = (key: MessageKey, values?: Record<string, string | number>) => string;

const ROLE_KEYS: Record<AppRole, {
  label: MessageKey;
  description: MessageKey;
  focus: [MessageKey, MessageKey, MessageKey];
}> = {
  tenant_admin: { label: "role.tenant_admin", description: "role.tenant_admin.description", focus: ["role.tenant_admin.focus1", "role.tenant_admin.focus2", "role.tenant_admin.focus3"] },
  executive_viewer: { label: "role.executive_viewer", description: "role.executive_viewer.description", focus: ["role.executive_viewer.focus1", "role.executive_viewer.focus2", "role.executive_viewer.focus3"] },
  process_manager: { label: "role.process_manager", description: "role.process_manager.description", focus: ["role.process_manager.focus1", "role.process_manager.focus2", "role.process_manager.focus3"] },
  process_engineer: { label: "role.process_engineer", description: "role.process_engineer.description", focus: ["role.process_engineer.focus1", "role.process_engineer.focus2", "role.process_engineer.focus3"] },
  maintenance_technician: { label: "role.maintenance_technician", description: "role.maintenance_technician.description", focus: ["role.maintenance_technician.focus1", "role.maintenance_technician.focus2", "role.maintenance_technician.focus3"] },
  quality_auditor: { label: "role.quality_auditor", description: "role.quality_auditor.description", focus: ["role.quality_auditor.focus1", "role.quality_auditor.focus2", "role.quality_auditor.focus3"] },
  ml_validator: { label: "role.ml_validator", description: "role.ml_validator.description", focus: ["role.ml_validator.focus1", "role.ml_validator.focus2", "role.ml_validator.focus3"] },
  fde: { label: "role.fde", description: "role.fde.description", focus: ["role.fde.focus1", "role.fde.focus2", "role.fde.focus3"] },
};

const PROFILE_KEYS: Record<AdaptiveProfileId, {
  label: MessageKey;
  eyebrow: MessageKey;
  primaryEntity: MessageKey;
  primaryMetric: MessageKey;
  description: MessageKey;
  visual: MessageKey;
  reports: [MessageKey, MessageKey, MessageKey];
}> = {
  "factory-reliability": { label: "profile.factory.label", eyebrow: "profile.factory.eyebrow", primaryEntity: "profile.factory.primaryEntity", primaryMetric: "profile.factory.primaryMetric", description: "profile.factory.description", visual: "profile.factory.visual", reports: ["profile.factory.report1", "profile.factory.report2", "profile.factory.report3"] },
  "fleet-maintenance": { label: "profile.fleet.label", eyebrow: "profile.fleet.eyebrow", primaryEntity: "profile.fleet.primaryEntity", primaryMetric: "profile.fleet.primaryMetric", description: "profile.fleet.description", visual: "profile.fleet.visual", reports: ["profile.fleet.report1", "profile.fleet.report2", "profile.fleet.report3"] },
  "compressor-monitoring": { label: "profile.compressor.label", eyebrow: "profile.compressor.eyebrow", primaryEntity: "profile.compressor.primaryEntity", primaryMetric: "profile.compressor.primaryMetric", description: "profile.compressor.description", visual: "profile.compressor.visual", reports: ["profile.compressor.report1", "profile.compressor.report2", "profile.compressor.report3"] },
  "generic-operations": { label: "profile.generic.label", eyebrow: "profile.generic.eyebrow", primaryEntity: "profile.generic.primaryEntity", primaryMetric: "profile.generic.primaryMetric", description: "profile.generic.description", visual: "profile.generic.visual", reports: ["profile.generic.report1", "profile.generic.report2", "profile.generic.report3"] },
};

const ADAPTIVE_TAB_KEYS: Record<string, MessageKey> = {
  "Reliability Command": "dashboard.tab.reliabilityCommand",
  "Evidence & Maintenance": "dashboard.tab.evidenceMaintenance",
  "Fleet Briefing": "dashboard.tab.fleetBriefing",
  "Service & Route Impact": "dashboard.tab.serviceRouteImpact",
  "Condition Monitoring": "dashboard.tab.conditionMonitoring",
  "Anomaly & Prevention": "dashboard.tab.anomalyPrevention",
  "Adaptive Overview": "dashboard.tab.adaptiveOverview",
  "Data Evidence": "dashboard.tab.dataEvidence",
};

export function localizeRoleLanding(role: AppRole, landing: RoleLanding, t: Translate): RoleLanding {
  const keys = ROLE_KEYS[role];
  return {
    ...landing,
    label: t(keys.label),
    description: t(keys.description),
    focus: keys.focus.map((key) => t(key)),
  };
}

export function localizeAdaptiveProfile(
  profile: AdaptiveExperienceProfile,
  t: Translate,
  datasetCount: number,
  recordCount: number,
): AdaptiveExperienceProfile {
  const keys = PROFILE_KEYS[profile.id];
  return {
    ...profile,
    label: t(keys.label),
    eyebrow: t(keys.eyebrow),
    primaryEntity: t(keys.primaryEntity),
    primaryMetric: t(keys.primaryMetric),
    description: t(keys.description),
    visualLanguage: t(keys.visual),
    reportSections: keys.reports.map((key) => t(key)),
    datasetSummary: datasetCount
      ? t("profile.datasetSummary", {
          datasets: datasetCount.toLocaleString(),
          records: recordCount.toLocaleString(),
          fields: profile.signals.fields.length.toLocaleString(),
          sources: profile.signals.sourceTypes.join(", ") || "unknown source",
        })
      : t("profile.datasetResolving"),
  };
}

export function localizeAdaptiveTabTitle(title: string, t: Translate): string {
  const key = ADAPTIVE_TAB_KEYS[title];
  return key ? t(key) : title;
}
