import { useEffect, useMemo, useRef, useState } from "react";
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

type SortState = { columnId: string; direction: "asc" | "desc" } | null;
const ROW_HEIGHT = 38;
const OVERSCAN = 10;

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

function compareValues(left: unknown, right: unknown): number {
  if (left === right) return 0;
  if (left === null || left === undefined) return 1;
  if (right === null || right === undefined) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
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
  const [sort, setSort] = useState<SortState>(null);
  const [visibleColumnIds, setVisibleColumnIds] = useState<Set<string>>(
    () => new Set(columns.filter((column) => !column.hidden).map((column) => column.id)),
  );
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(320);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const globalFilter = serverPagination ? serverPagination.search ?? "" : localFilter;

  useEffect(() => {
    setVisibleColumnIds((current) => {
      const known = new Set(columns.map((column) => column.id));
      const next = new Set([...current].filter((id) => known.has(id)));
      for (const column of columns) {
        if (!column.hidden && !current.has(column.id)) next.add(column.id);
      }
      return next;
    });
  }, [columns]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setViewportHeight(entry.contentRect.height));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const visibleColumns = useMemo(
    () => columns.filter((column) => visibleColumnIds.has(column.id)),
    [columns, visibleColumnIds],
  );
  const processedRows = useMemo(() => {
    const normalized = globalFilter.trim().toLowerCase();
    const filtered = serverPagination || !normalized
      ? rows
      : rows.filter((row) => visibleColumns.some((column) => String(row[column.id] ?? "").toLowerCase().includes(normalized)));
    if (!sort) return filtered;
    return [...filtered].sort((left, right) => {
      const result = compareValues(left[sort.columnId], right[sort.columnId]);
      return sort.direction === "asc" ? result : -result;
    });
  }, [globalFilter, rows, serverPagination, sort, visibleColumns]);
  const template = visibleColumns.map((column) => `${Math.max(80, column.size ?? 120)}px`).join(" ");
  const tableWidth = visibleColumns.reduce((sum, column) => sum + Math.max(80, column.size ?? 120), 0);
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
  const endIndex = Math.min(processedRows.length, startIndex + visibleCount);
  const virtualRows = processedRows.slice(startIndex, endIndex);
  const totalPages = serverPagination ? Math.max(1, Math.ceil(serverPagination.totalRows / serverPagination.pageSize)) : 1;

  function toggleSort(columnId: string) {
    setSort((current) => {
      if (!current || current.columnId !== columnId) return { columnId, direction: "asc" };
      if (current.direction === "asc") return { columnId, direction: "desc" };
      return null;
    });
  }

  function toggleColumn(columnId: string) {
    setVisibleColumnIds((current) => {
      const next = new Set(current);
      if (next.has(columnId)) {
        if (next.size > 1) next.delete(columnId);
      } else {
        next.add(columnId);
      }
      return next;
    });
  }

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
            : `${processedRows.length} / ${rows.length} rows`}
        </span>
        {serverPagination?.loading ? <LoaderCircle className="spin" size={13} /> : null}
        <button type="button" className={columnsOpen ? "active" : ""} onClick={() => setColumnsOpen((current) => !current)}><Columns3 size={13} /> Columns</button>
        {columnsOpen ? (
          <div className="generic-column-popover">
            {columns.map((column) => (
              <label key={column.id}><input type="checkbox" checked={visibleColumnIds.has(column.id)} onChange={() => toggleColumn(column.id)} />{column.label}</label>
            ))}
          </div>
        ) : null}
      </header>
      {serverPagination?.error ? <div className="od-callout intent-danger">{serverPagination.error}</div> : null}
      {rows.length ? (
        <div
          ref={scrollRef}
          className="generic-data-table"
          role="table"
          aria-busy={serverPagination?.loading ?? false}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
          <div className="generic-data-table-head" role="row" style={{ gridTemplateColumns: template, minWidth: tableWidth }}>
            {visibleColumns.map((column) => (
              <button type="button" role="columnheader" key={column.id} onClick={() => toggleSort(column.id)}>
                {column.label}{sort?.columnId === column.id ? sort.direction === "asc" ? " ↑" : " ↓" : ""}
              </button>
            ))}
          </div>
          <div className="generic-data-table-body" style={{ height: processedRows.length * ROW_HEIGHT, minWidth: tableWidth }}>
            {virtualRows.map((row, index) => {
              const absoluteIndex = startIndex + index;
              const key = String(row[rowKey] ?? absoluteIndex);
              return (
                <button
                  type="button"
                  role="row"
                  key={`${key}:${absoluteIndex}`}
                  className={key === selectedRowKey ? "active" : ""}
                  style={{ transform: `translateY(${absoluteIndex * ROW_HEIGHT}px)`, gridTemplateColumns: template }}
                  onClick={() => onRowSelect?.(row, {
                    id: crypto.randomUUID(),
                    source_board_id: boardId,
                    field: rowKey,
                    operator: "eq",
                    values: [key],
                    created_at: new Date().toISOString(),
                  })}
                >
                  {visibleColumns.map((column) => <span role="cell" key={column.id}><CellValue value={row[column.id]} format={column.format} /></span>)}
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
