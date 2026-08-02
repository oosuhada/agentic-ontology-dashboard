import { Box, Link2 } from "lucide-react";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { displayObjectValue, objectIdentity, objectStatus } from "./objectPresentation";
import type { ObjectRecord, ObjectTypeDefinition } from "./types";

interface ObjectSetTableProps {
  objects: ObjectRecord[];
  definition: ObjectTypeDefinition | null;
  selectedObjectId: string | null;
  onSelect: (object: ObjectRecord) => void;
}

function statusIntent(status: string) {
  const normalized = status.toLowerCase();
  if (["critical", "failed", "rejected", "disabled"].includes(normalized)) return "danger" as const;
  if (["warning", "attention", "pending", "medium", "low_confidence"].includes(normalized)) return "warning" as const;
  if (["ready", "active", "healthy", "success", "high"].includes(normalized)) return "success" as const;
  return "neutral" as const;
}

export function ObjectSetTable({ objects, definition, selectedObjectId, onSelect }: ObjectSetTableProps) {
  const properties = definition?.properties.slice(0, 3) ?? [];
  const columns = `minmax(180px,1.4fr) minmax(100px,.7fr) ${properties.map(() => "minmax(110px,.8fr)").join(" ")} 80px 90px`;
  if (!objects.length) return <EmptyState title="No objects" detail="Search or choose another object type to build an object set." />;

  return (
    <div className="fd-resource-table ontology-object-table" role="table">
      <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: columns }}>
        <span role="columnheader">Object</span>
        <span role="columnheader">Status</span>
        {properties.map((property) => <span role="columnheader" key={property.id}>{property.display_name}</span>)}
        <span role="columnheader">Version</span>
        <span role="columnheader">Sources</span>
      </div>
      {objects.map((object) => {
        const status = objectStatus(object);
        return (
          <button
            type="button"
            role="row"
            key={object.id}
            className={`fd-resource-table__row ${selectedObjectId === object.id ? "active" : ""}`.trim()}
            style={{ gridTemplateColumns: columns }}
            onClick={() => onSelect(object)}
          >
            <div className="fd-resource-table__primary" role="cell"><strong><Box size={11} /> {objectIdentity(object)}</strong><small>{object.object_type} · {object.id}</small></div>
            <span role="cell"><StatusPill intent={statusIntent(status)}>{status}</StatusPill></span>
            {properties.map((property) => <span role="cell" key={property.id} title={displayObjectValue(object.properties[property.id])}>{displayObjectValue(object.properties[property.id])}</span>)}
            <span role="cell" className="fd-resource-table__numeric">v{object.version}</span>
            <span role="cell"><Link2 size={10} /> {object.source_refs.length}</span>
          </button>
        );
      })}
    </div>
  );
}
