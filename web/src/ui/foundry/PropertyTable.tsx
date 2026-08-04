import type { ReactNode } from "react";
import { StatusPill, type StatusPillIntent } from "./StatusPill";

export interface PropertyRow {
  id: string;
  label: string;
  value: ReactNode;
  type?: string;
  status?: { label: string; intent?: StatusPillIntent };
  numeric?: boolean;
  mono?: boolean;
}

interface PropertyTableProps {
  rows: PropertyRow[];
  emptyMessage?: string;
  className?: string;
}

export function PropertyTable({ rows, emptyMessage = "No properties", className = "" }: PropertyTableProps) {
  return (
    <div className={`fd-property-table ${className}`.trim()} role="table">
      <div className="fd-property-table__header" role="row">
        <span role="columnheader">Property</span>
        <span role="columnheader">Value</span>
        <span role="columnheader">Type</span>
      </div>
      {rows.length ? rows.map((row) => (
        <div className="fd-property-table__row" role="row" key={row.id}>
          <strong role="cell">{row.label}</strong>
          <span role="cell" className={`${row.numeric ? "numeric" : ""} ${row.mono ? "mono" : ""}`.trim()}>{row.value}</span>
          <span role="cell">
            {row.status ? <StatusPill intent={row.status.intent}>{row.status.label}</StatusPill> : row.type ?? "—"}
          </span>
        </div>
      )) : <div className="fd-property-table__empty">{emptyMessage}</div>}
    </div>
  );
}
