import { Link2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ResourceTableHeaderCell, type ResourceColumnType } from "../../ui/foundry/ResourceTableHeaderCell";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { displayObjectValue, objectIdentity, objectStatus } from "./objectPresentation";
import { objectTypeIcon } from "./objectTypeIcon";
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
  const [sort, setSort] = useState<{ id: string; direction: "asc" | "desc" }>({ id: "object", direction: "asc" });
  const [pinPrimary, setPinPrimary] = useState(true);
  const sortedObjects = useMemo(() => [...objects].sort((left, right) => {
    const values = (object: ObjectRecord): Record<string, string | number> => ({
      object: objectIdentity(object),
      status: objectStatus(object),
      version: object.version,
      sources: object.source_refs.length,
      ...Object.fromEntries(properties.map((property) => [property.id, displayObjectValue(object.properties[property.id])])),
    });
    const a = values(left)[sort.id] ?? "";
    const b = values(right)[sort.id] ?? "";
    const compared = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
    return sort.direction === "asc" ? compared : -compared;
  }), [objects, properties, sort]);
  const setSortColumn = (id: string, direction?: "asc" | "desc") => setSort((current) => ({ id, direction: direction ?? (current.id === id && current.direction === "asc" ? "desc" : "asc") }));
  const propertyType = (valueType: string): ResourceColumnType => valueType === "number" || valueType === "integer" ? "number" : valueType === "datetime" ? "date" : valueType === "boolean" ? "boolean" : valueType === "object" || valueType === "array" ? "relation" : "text";
  const sourceTotal = objects.reduce((sum, object) => sum + object.source_refs.length, 0);
  if (!objects.length) return <EmptyState title="No objects" detail="Search or choose another object type to build an object set." />;

  return (
    <div className={`fd-resource-table ontology-object-table ${pinPrimary ? "has-pinned-primary" : ""}`} role="table">
      <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: columns }}>
        <ResourceTableHeaderCell label="Object" type="object" pinned={pinPrimary} sortDirection={sort.id === "object" ? sort.direction : null} onSort={(direction) => setSortColumn("object", direction)} onTogglePin={() => setPinPrimary((value) => !value)} description={`${definition?.display_name ?? "Ontology object"} identity`} />
        <ResourceTableHeaderCell label="Status" type="status" filterActive={objects.some((object) => objectStatus(object) !== "active")} sortDirection={sort.id === "status" ? sort.direction : null} onSort={(direction) => setSortColumn("status", direction)} />
        {properties.map((property) => <ResourceTableHeaderCell key={property.id} label={property.display_name} type={propertyType(property.value_type)} description={`${property.value_type}${property.unit ? ` · ${property.unit}` : ""}${property.required ? " · required" : ""}${property.description ? ` · ${property.description}` : ""}`} sortDirection={sort.id === property.id ? sort.direction : null} onSort={(direction) => setSortColumn(property.id, direction)} />)}
        <ResourceTableHeaderCell label="Version" type="version" sortDirection={sort.id === "version" ? sort.direction : null} onSort={(direction) => setSortColumn("version", direction)} />
        <ResourceTableHeaderCell label="Sources" type="relation" filterActive={objects.some((object) => object.source_refs.length === 0)} sortDirection={sort.id === "sources" ? sort.direction : null} onSort={(direction) => setSortColumn("sources", direction)} />
      </div>
      {sortedObjects.map((object) => {
        const status = objectStatus(object);
        const ObjectIcon = objectTypeIcon(object.object_type);
        return (
          <button
            type="button"
            role="row"
            key={object.id}
            className={`fd-resource-table__row ${selectedObjectId === object.id ? "active" : ""}`.trim()}
            style={{ gridTemplateColumns: columns }}
            onClick={() => onSelect(object)}
          >
            <div className={`fd-resource-table__primary ${pinPrimary ? "is-pinned" : ""}`} role="cell"><strong><ObjectIcon size={11} /> {objectIdentity(object)}</strong><small>{object.object_type} · {object.id}</small></div>
            <span role="cell"><StatusPill intent={statusIntent(status)}>{status}</StatusPill></span>
            {properties.map((property) => <span role="cell" key={property.id} title={displayObjectValue(object.properties[property.id])}>{displayObjectValue(object.properties[property.id])}</span>)}
            <span role="cell" className="fd-resource-table__numeric">v{object.version}</span>
            <span role="cell"><Link2 size={10} /> {object.source_refs.length}</span>
          </button>
        );
      })}
      <div className="fd-resource-table__summary" role="row" style={{ gridTemplateColumns: columns }}>
        <strong role="cell">{objects.length} objects</strong><span role="cell">{new Set(objects.map(objectStatus)).size} states</span>{properties.map((property) => <span role="cell" key={property.id}>{property.value_type}{property.unit ? ` · ${property.unit}` : ""}</span>)}<span role="cell">v{Math.max(...objects.map((object) => object.version))}</span><span role="cell">Σ {sourceTotal}</span>
      </div>
    </div>
  );
}
