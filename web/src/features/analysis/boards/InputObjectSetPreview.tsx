import { useEffect, useMemo, useState } from "react";
import { queryOntologyObjects } from "../../../api";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "../../dashboard/renderers/DataTableRenderer";

interface InputObjectSetPreviewProps {
  workspaceId: string;
  objectType: string;
  selectedEventId: string;
  onSelectEvent: (eventId: string) => void;
}

function flattenObject(item: {
  id: string;
  object_type: string;
  version: number;
  properties: Record<string, unknown>;
}): TableDatum {
  return {
    object_id: item.id,
    event_id: item.object_type === "risk_event" ? item.id.split(":", 2)[1] : undefined,
    object_type: item.object_type,
    version: item.version,
    ...Object.fromEntries(Object.entries(item.properties).map(([key, value]) => [
      key,
      typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value == null
        ? value
        : JSON.stringify(value),
    ])),
  };
}

function columnsFor(rows: TableDatum[]): DataTableColumn[] {
  const keys = Array.from(new Set(rows.slice(0, 20).flatMap((row) => Object.keys(row))));
  const preferred = ["event_id", "object_id", "status", "failure_probability", "predicted_failure_type", "observed_at", "version"];
  const ordered = [...preferred.filter((key) => keys.includes(key)), ...keys.filter((key) => !preferred.includes(key))];
  return ordered.slice(0, 12).map((id) => ({
    id,
    label: id.replaceAll("_", " "),
    format: id.includes("id") ? "code" : id === "status" ? "status" : "text",
    size: id.includes("id") ? 170 : 125,
  }));
}

export function InputObjectSetPreview({ workspaceId, objectType, selectedEventId, onSelectEvent }: InputObjectSetPreviewProps) {
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<TableDatum[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    queryOntologyObjects({
      workspace_id: workspaceId,
      object_type: objectType,
      search,
      offset: pageIndex * pageSize,
      limit: pageSize,
    })
      .then((payload) => {
        if (!active) return;
        setRows(payload.items.map(flattenObject));
        setTotalRows(payload.total);
      })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [objectType, pageIndex, pageSize, search, workspaceId]);

  useEffect(() => { setPageIndex(0); }, [objectType, search, workspaceId]);
  const columns = useMemo(() => columnsFor(rows), [rows]);

  return (
    <section className="analysis-input-object-preview">
      <h3>Input Object Set · server page</h3>
      <DataTableRenderer
        boardId="analysis-input-object-set"
        rows={rows}
        columns={columns}
        rowKey={objectType === "risk_event" ? "event_id" : "object_id"}
        selectedRowKey={selectedEventId}
        searchPlaceholder={`${objectType} Object 검색`}
        serverPagination={{
          pageIndex,
          pageSize,
          totalRows,
          loading,
          error,
          search,
          onPageIndexChange: setPageIndex,
          onPageSizeChange: (value) => { setPageSize(value); setPageIndex(0); },
          onSearchChange: (value) => { setSearch(value); setPageIndex(0); },
        }}
        onRowSelect={(row) => {
          const eventId = String(row.event_id ?? "");
          if (eventId) onSelectEvent(eventId);
        }}
      />
    </section>
  );
}
