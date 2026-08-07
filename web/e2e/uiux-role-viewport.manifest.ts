export const ROLE_VISUAL_CASES = [
  { role: "tenant-admin", email: "admin@ontology.local", password: "OntologyAdmin!2026" },
  { role: "executive", email: "executive@ontology.local", password: "Executive!2026" },
  { role: "manager", email: "manager@ontology.local", password: "Manager!2026" },
  { role: "engineer", email: "engineer@ontology.local", password: "Engineer!2026" },
  { role: "technician", email: "technician@ontology.local", password: "Technician!2026" },
  { role: "quality", email: "quality@ontology.local", password: "Quality!2026" },
  { role: "data-scientist", email: "datascientist@ontology.local", password: "DataScience!2026" },
  { role: "fde", email: "fde@ontology.local", password: "FDE!2026" },
] as const;

export const VIEWPORT_VISUAL_CASES = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "tablet", width: 1024, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;

export const VISUAL_PROJECT_ID = "manufacturing-demo-project";
