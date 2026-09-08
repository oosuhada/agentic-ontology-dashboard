import type { ObjectRecord } from "./types";

export function displayObjectValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function objectIdentity(record: ObjectRecord): string {
  const preferred = [
    "equipment_id",
    "asset_id",
    "event_id",
    "work_order_id",
    "maintenance_action_id",
    "component_label",
    "component_id",
    "sop_id",
    "product_id",
    "inspection_id",
    "action_id",
    "evidence_id",
    "display_name",
    "title",
    "name",
  ];
  for (const key of preferred) {
    const value = record.properties[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return record.id;
}

export function objectStatus(record: ObjectRecord): string {
  for (const key of ["status", "state", "confidence", "criticality"]) {
    const value = record.properties[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "active";
}
