import { Database } from "lucide-react";
import { useMemo, useState } from "react";
import { ResourceTableHeaderCell } from "../../ui/foundry/ResourceTableHeaderCell";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import type { DatasetCatalogItem } from "./types";

interface DatasetResourceTableProps {
  items: DatasetCatalogItem[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (datasetId: string) => void;
}

export function DatasetResourceTable({ items, selectedId, loading, onSelect }: DatasetResourceTableProps) {
  const columns = "minmax(220px,1.5fr) 92px 100px 90px 120px 80px 105px";
  const [sort, setSort] = useState<{ id: string; direction: "asc" | "desc" }>({ id: "updated", direction: "desc" });
  const [pinPrimary, setPinPrimary] = useState(true);
  const sortedItems = useMemo(() => [...items].sort((left, right) => {
    const projectionReady = (item: DatasetCatalogItem) => Object.values(item.projection_health).filter((status) => status === "ready").length;
    const values: Record<string, [string | number, string | number]> = {
      dataset: [left.display_name, right.display_name],
      version: [left.latest_version_label ?? "", right.latest_version_label ?? ""],
      source: [left.source_type, right.source_type],
      rows: [left.record_count, right.record_count],
      updated: [Date.parse(left.updated_at), Date.parse(right.updated_at)],
      status: [left.status, right.status],
      projections: [projectionReady(left), projectionReady(right)],
    };
    const [a, b] = values[sort.id] ?? values.dataset;
    const compared = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
    return sort.direction === "asc" ? compared : -compared;
  }), [items, sort]);
  const setSortColumn = (id: string, direction?: "asc" | "desc") => setSort((current) => ({
    id,
    direction: direction ?? (current.id === id && current.direction === "asc" ? "desc" : "asc"),
  }));
  const totalRows = items.reduce((sum, item) => sum + item.record_count, 0);
  const activeCount = items.filter((item) => item.status === "active").length;
  const projectionCount = items.reduce((sum, item) => sum + Object.values(item.projection_health).filter((status) => status === "ready").length, 0);
  if (!items.length && !loading) return <EmptyState title="No cataloged datasets" detail="Adapter ingestion or Save Analysis Result creates an immutable Dataset Version here." />;
  return (
    <div className={`fd-resource-table dataset-resource-table ${pinPrimary ? "has-pinned-primary" : ""}`} role="table" aria-busy={loading}>
      <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: columns }}>
        <ResourceTableHeaderCell label="Dataset" type="object" pinned={pinPrimary} sortDirection={sort.id === "dataset" ? sort.direction : null} onSort={(direction) => setSortColumn("dataset", direction)} onTogglePin={() => setPinPrimary((value) => !value)} description="Immutable Dataset identity and workspace scope" />
        <ResourceTableHeaderCell label="Version" type="version" sortDirection={sort.id === "version" ? sort.direction : null} onSort={(direction) => setSortColumn("version", direction)} description="Latest immutable version label" />
        <ResourceTableHeaderCell label="Source" type="relation" sortDirection={sort.id === "source" ? sort.direction : null} onSort={(direction) => setSortColumn("source", direction)} description="Origin adapter or Analysis materialization" />
        <ResourceTableHeaderCell label="Rows" type="number" sortDirection={sort.id === "rows" ? sort.direction : null} onSort={(direction) => setSortColumn("rows", direction)} />
        <ResourceTableHeaderCell label="Updated" type="date" sortDirection={sort.id === "updated" ? sort.direction : null} onSort={(direction) => setSortColumn("updated", direction)} />
        <ResourceTableHeaderCell label="Status" type="status" filterActive={items.some((item) => item.status !== "active")} sortDirection={sort.id === "status" ? sort.direction : null} onSort={(direction) => setSortColumn("status", direction)} />
        <ResourceTableHeaderCell label="Projections" type="relation" filterActive={items.some((item) => Object.values(item.projection_health).some((status) => status !== "ready"))} sortDirection={sort.id === "projections" ? sort.direction : null} onSort={(direction) => setSortColumn("projections", direction)} />
      </div>
      {sortedItems.map((item) => {
        const statuses = Object.values(item.projection_health);
        const ready = statuses.filter((status) => status === "ready").length;
        const failed = statuses.filter((status) => status === "failed").length;
        return (
          <button type="button" role="row" key={item.id} className={`fd-resource-table__row ${selectedId === item.id ? "active" : ""}`.trim()} style={{ gridTemplateColumns: columns }} onClick={() => onSelect(item.id)}>
            <div className={`fd-resource-table__primary ${pinPrimary ? "is-pinned" : ""}`} role="cell"><strong><Database size={11} /> {item.display_name}</strong><small>{item.slug} · {item.workspace_id}</small></div>
            <span role="cell"><strong>{item.latest_version_label ?? "—"}</strong></span>
            <span role="cell">{item.source_type}</span>
            <span role="cell" className="fd-resource-table__numeric">{item.record_count.toLocaleString()}</span>
            <span role="cell">{new Date(item.updated_at).toLocaleDateString()}</span>
            <span role="cell"><StatusPill intent={item.status === "active" ? "success" : item.status === "archived" ? "neutral" : "warning"}>{item.status}</StatusPill></span>
            <span role="cell"><StatusPill intent={failed ? "danger" : ready === statuses.length ? "success" : "warning"}>{ready}/{statuses.length} ready</StatusPill></span>
          </button>
        );
      })}
      <div className="fd-resource-table__summary" role="row" style={{ gridTemplateColumns: columns }}>
        <strong role="cell">{items.length} datasets</strong><span role="cell">latest versions</span><span role="cell">{new Set(items.map((item) => item.source_type)).size} sources</span><span role="cell" className="fd-resource-table__numeric">Σ {totalRows.toLocaleString()}</span><span role="cell">catalog total</span><span role="cell">{activeCount} active</span><span role="cell">{projectionCount} ready</span>
      </div>
    </div>
  );
}
