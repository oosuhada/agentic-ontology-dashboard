import {
  AlertTriangle,
  Boxes,
  Building2,
  ClipboardList,
  Database,
  FileText,
  Package,
  Settings,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export function objectTypeIcon(objectType: string): LucideIcon {
  const normalized = objectType.toLowerCase();
  if (normalized.includes("equipment") || normalized.includes("machine") || normalized.includes("asset")) return Settings;
  if (normalized.includes("event") || normalized.includes("risk") || normalized.includes("alert") || normalized.includes("incident")) return AlertTriangle;
  if (normalized.includes("component") || normalized.includes("part") || normalized.includes("material")) return Package;
  if (normalized.includes("work_order") || normalized.includes("task") || normalized.includes("inspection")) return ClipboardList;
  if (normalized.includes("document") || normalized.includes("sop") || normalized.includes("manual")) return FileText;
  if (normalized.includes("person") || normalized.includes("user") || normalized.includes("operator")) return UserRound;
  if (normalized.includes("site") || normalized.includes("plant") || normalized.includes("organization")) return Building2;
  if (normalized.includes("dataset") || normalized.includes("table")) return Database;
  if (normalized.includes("action") || normalized.includes("maintenance")) return Wrench;
  return Boxes;
}
