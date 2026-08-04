import type { CSSProperties, ReactNode } from "react";

export interface DenseColumn {
  id: string;
  label: string;
}

export interface DenseRow {
  key: string;
  selected?: boolean;
  cells: ReactNode[];
  style?: CSSProperties;
  onSelect?: () => void;
}

interface DenseDataTableProps {
  columns: DenseColumn[];
  rows: DenseRow[];
  gridTemplateColumns: string;
  tableWidth: number;
  bodyHeight: number;
  ariaBusy?: boolean;
  sort?: { columnId: string; direction: "asc" | "desc" } | null;
  onSort?: (columnId: string) => void;
  onScroll?: (scrollTop: number) => void;
  scrollRef?: (node: HTMLDivElement | null) => void;
}

export function DenseDataTable({
  columns,
  rows,
  gridTemplateColumns,
  tableWidth,
  bodyHeight,
  ariaBusy = false,
  sort,
  onSort,
  onScroll,
  scrollRef,
}: DenseDataTableProps) {
  return (
    <div
      ref={scrollRef}
      className="generic-data-table fd-dense-table"
      role="table"
      aria-busy={ariaBusy}
      onScroll={(event) => onScroll?.(event.currentTarget.scrollTop)}
    >
      <div className="generic-data-table-head fd-dense-table__head" role="row" style={{ gridTemplateColumns, minWidth: tableWidth }}>
        {columns.map((column) => (
          <button type="button" role="columnheader" key={column.id} onClick={() => onSort?.(column.id)}>
            {column.label}{sort?.columnId === column.id ? sort.direction === "asc" ? " ↑" : " ↓" : ""}
          </button>
        ))}
      </div>
      <div className="generic-data-table-body fd-dense-table__body" style={{ height: bodyHeight, minWidth: tableWidth }}>
        {rows.map((row) => (
          <button
            type="button"
            role="row"
            key={row.key}
            className={`fd-dense-table__row ${row.selected ? "active" : ""}`.trim()}
            style={{ gridTemplateColumns, ...row.style }}
            onClick={row.onSelect}
          >
            {row.cells.map((cell, index) => <span role="cell" key={`${row.key}:${columns[index]?.id ?? index}`}>{cell}</span>)}
          </button>
        ))}
      </div>
    </div>
  );
}
