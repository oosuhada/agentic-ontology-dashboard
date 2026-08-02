import { Database } from "lucide-react";
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
  if (!items.length && !loading) return <EmptyState title="No cataloged datasets" detail="Adapter ingestion or Save Analysis Result creates an immutable Dataset Version here." />;
  return (
    <div className="fd-resource-table dataset-resource-table" role="table" aria-busy={loading}>
      <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: columns }}>
        <span role="columnheader">Dataset</span><span role="columnheader">Version</span><span role="columnheader">Source</span><span role="columnheader">Rows</span><span role="columnheader">Updated</span><span role="columnheader">Status</span><span role="columnheader">Projections</span>
      </div>
      {items.map((item) => {
        const statuses = Object.values(item.projection_health);
        const ready = statuses.filter((status) => status === "ready").length;
        const failed = statuses.filter((status) => status === "failed").length;
        return (
          <button type="button" role="row" key={item.id} className={`fd-resource-table__row ${selectedId === item.id ? "active" : ""}`.trim()} style={{ gridTemplateColumns: columns }} onClick={() => onSelect(item.id)}>
            <div className="fd-resource-table__primary" role="cell"><strong><Database size={11} /> {item.display_name}</strong><small>{item.slug} · {item.workspace_id}</small></div>
            <span role="cell"><strong>{item.latest_version_label ?? "—"}</strong></span>
            <span role="cell">{item.source_type}</span>
            <span role="cell" className="fd-resource-table__numeric">{item.record_count.toLocaleString()}</span>
            <span role="cell">{new Date(item.updated_at).toLocaleDateString()}</span>
            <span role="cell"><StatusPill intent={item.status === "active" ? "success" : item.status === "archived" ? "neutral" : "warning"}>{item.status}</StatusPill></span>
            <span role="cell"><StatusPill intent={failed ? "danger" : ready === statuses.length ? "success" : "warning"}>{ready}/{statuses.length} ready</StatusPill></span>
          </button>
        );
      })}
    </div>
  );
}
