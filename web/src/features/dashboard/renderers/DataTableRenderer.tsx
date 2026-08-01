import { useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronLeft, ChevronRight, Columns3, LoaderCircle, Search } from "lucide-react";
import type { SelectionFilter } from "../types";

export type TableDatum = Record<string, string | number | boolean | null | undefined>;

export interface DataTableColumn {
  id: string;
  label: string;
  size?: number;
  format?: "text" | "code" | "percent" | "minutes" | "status";
  hidden?: boolean;
}

export interface ServerPaginationState {
  pageIndex: number;
  pageSize: number;
  totalRows: number;
  loading?: boolean;
  error?: string;
  search?: string;
  onPageIndexChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSearchChange?: (search: string) => void;
}

interface DataTableRendererProps {
  boardId: string;
  rows: TableDatum[];
  columns: DataTableColumn[];
  rowKey: string;
  selectedRowKey?: string;
  searchPlaceholder?: string;
  serverPagination?: ServerPaginationState;
  onRowSelect?: (row: TableDatum, filter: SelectionFilter) => void;
}

function CellValue({ value, format }: { value: unknown; format?: DataTableColumn["format"] }) {
  if (format === "code") return <code>{String(value ?? "-")}</code>;
  if (format === "percent") return <>{(Number(value ?? 0) * 100).toFixed(1)}%</>;
  if (format === "minutes") return <>{String(value ?? 0)} min</>;
  if (format === "status") {
    const status = String(value ?? "unknown");
    const intent = status === "critical" || status === "data_quality_hold"
      ? "danger"
      : status === "warning" || status === "attention"
        ? "warning"
        : "success";
    return <span className={`od-tag intent-${intent}`}>{status}</span>;
  }
  return <>{String(value ?? "-")}</>;
}

export function DataTableRenderer({
  boardId,
  rows,
  columns,
  rowKey,
  selectedRowKey,
  searchPlaceholder = "Search rows",
  serverPagination,
  onRowSelect,
}: DataTableRendererProps) {
  const [localFilter, setLocalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() => Object.fromEntries(
    columns.filter((column) => column.hidden).map((column) => [column.id, false]),
  ));
  const [columnsOpen, setColumnsOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const globalFilter = serverPagination ? serverPagination.search ?? "" : localFilter;

  const tableColumns = useMemo<ColumnDef<TableDatum>[]>(() => columns.map((column) => ({
    accessorKey: column.id,
    header: column.label,
    size: column.size ?? 120,
    cell: ({ getValue }) => <CellValue value={getValue()} format={column.format} />,
  })), [columns]);
  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting, globalFilter: serverPagination ? "" : globalFilter, columnVisibility },
    onSortingChange: setSorting,
    onGlobalFilterChange: serverPagination ? undefined : setLocalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: serverPagination ? undefined : getFilteredRowModel(),
    globalFilterFn: "includesString",
    manualPagination: Boolean(serverPagination),
    pageCount: serverPagination ? Math.max(1, Math.ceil(serverPagination.totalRows / serverPagination.pageSize)) : undefined,
  });
  const visibleRows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 38,
    overscan: 10,
  });
  const visibleColumns = table.getVisibleLeafColumns();
  const template = visibleColumns.map((column) => `${Math.max(80, column.getSize())}px`).join(" ");
  const totalPages = serverPagination ? Math.max(1, Math.ceil(serverPagination.totalRows / serverPagination.pageSize)) : 1;

  return (
    <section className="generic-data-table-renderer">
      <header>
        <label>
          <Search size={13} />
          <input
            value={globalFilter}
            onChange={(event) => serverPagination?.onSearchChange
              ? serverPagination.onSearchChange(event.target.value)
              : setLocalFilter(event.target.value)}
            placeholder={searchPlaceholder}
          />
        </label>
        <span>
          {serverPagination
            ? `${serverPagination.totalRows} rows · page ${serverPagination.pageIndex + 1}/${totalPages}`
            : `${visibleRows.length} / ${rows.length} rows`}
        </span>
        {serverPagination?.loading ? <LoaderCircle className="spin" size={13} /> : null}
        <button type="button" className={columnsOpen ? "active" : ""} onClick={() => setColumnsOpen((current) => !current)}><Columns3 size={13} /> Columns</button>
        {columnsOpen ? (
          <div className="generic-column-popover">
            {table.getAllLeafColumns().map((column) => (
              <label key={column.id}><input type="checkbox" checked={column.getIsVisible()} onChange={column.getToggleVisibilityHandler()} />{String(column.columnDef.header ?? column.id)}</label>
            ))}
          </div>
        ) : null}
      </header>
      {serverPagination?.error ? <div className="od-callout intent-danger">{serverPagination.error}</div> : null}
      {rows.length ? (
        <div ref={scrollRef} className="generic-data-table" role="table" aria-busy={serverPagination?.loading ?? false}>
          <div className="generic-data-table-head" role="row" style={{ gridTemplateColumns: template }}>
            {table.getFlatHeaders().filter((header) => header.column.getIsVisible()).map((header) => (
              <button type="button" role="columnheader" key={header.id} onClick={header.column.getToggleSortingHandler()}>
                {String(header.column.columnDef.header ?? header.id)}{header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
              </button>
            ))}
          </div>
          <div className="generic-data-table-body" style={{ height: virtualizer.getTotalSize(), minWidth: visibleColumns.reduce((sum, column) => sum + Math.max(80, column.getSize()), 0) }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = visibleRows[virtualRow.index];
              const key = String(row.original[rowKey] ?? row.id);
              return (
                <button
                  type="button"
                  role="row"
                  key={row.id}
                  className={key === selectedRowKey ? "active" : ""}
                  style={{ transform: `translateY(${virtualRow.start}px)`, gridTemplateColumns: template }}
                  onClick={() => onRowSelect?.(row.original, {
                    id: crypto.randomUUID(),
                    source_board_id: boardId,
                    field: rowKey,
                    operator: "eq",
                    values: [key],
                    created_at: new Date().toISOString(),
                  })}
                >
                  {row.getVisibleCells().map((cell) => <span role="cell" key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</span>)}
                </button>
              );
            })}
          </div>
        </div>
      ) : <div className="od-non-ideal-state"><strong>No matching rows</strong><span>현재 filter scope에 포함되는 Object가 없습니다.</span></div>}
      {serverPagination ? (
        <footer className="generic-pagination-controls">
          <label>Rows <select value={serverPagination.pageSize} onChange={(event) => serverPagination.onPageSizeChange(Number(event.target.value))}>{[25, 50, 100, 200].map((size) => <option value={size} key={size}>{size}</option>)}</select></label>
          <button type="button" disabled={serverPagination.loading || serverPagination.pageIndex <= 0} onClick={() => serverPagination.onPageIndexChange(serverPagination.pageIndex - 1)}><ChevronLeft size={13} /> Previous</button>
          <span>{serverPagination.pageIndex + 1} / {totalPages}</span>
          <button type="button" disabled={serverPagination.loading || serverPagination.pageIndex + 1 >= totalPages} onClick={() => serverPagination.onPageIndexChange(serverPagination.pageIndex + 1)}>Next <ChevronRight size={13} /></button>
        </footer>
      ) : null}
    </section>
  );
}
