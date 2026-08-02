import {
  ArrowDown,
  ArrowUp,
  Binary,
  CalendarClock,
  CircleDot,
  Database,
  Hash,
  Link2,
  ListFilter,
  MoreHorizontal,
  Pin,
  PinOff,
  TextCursorInput,
  ToggleLeft,
} from "lucide-react";

export type ResourceColumnType =
  | "object"
  | "text"
  | "number"
  | "date"
  | "status"
  | "relation"
  | "version"
  | "boolean";

interface ResourceTableHeaderCellProps {
  label: string;
  type?: ResourceColumnType;
  description?: string;
  sortDirection?: "asc" | "desc" | null;
  filterActive?: boolean;
  pinned?: boolean;
  onSort?: (direction?: "asc" | "desc") => void;
  onTogglePin?: () => void;
}

const TYPE_ICONS = {
  object: Database,
  text: TextCursorInput,
  number: Hash,
  date: CalendarClock,
  status: CircleDot,
  relation: Link2,
  version: Binary,
  boolean: ToggleLeft,
} satisfies Record<ResourceColumnType, typeof Database>;

export function ResourceTableHeaderCell({
  label,
  type = "text",
  description,
  sortDirection,
  filterActive = false,
  pinned = false,
  onSort,
  onTogglePin,
}: ResourceTableHeaderCellProps) {
  const TypeIcon = TYPE_ICONS[type];
  const SortIcon = sortDirection === "asc" ? ArrowUp : sortDirection === "desc" ? ArrowDown : null;
  return (
    <div
      role="columnheader"
      className={`fd-resource-column-header ${pinned ? "is-pinned" : ""} ${filterActive ? "has-filter" : ""}`.trim()}
      title={description}
    >
      <button type="button" className="fd-resource-column-header__sort" onClick={() => onSort?.()} disabled={!onSort}>
        <TypeIcon size={10} aria-hidden="true" />
        <span>{label}</span>
        {filterActive ? <ListFilter size={9} aria-label="Filtered" /> : null}
        {SortIcon ? <SortIcon size={10} aria-label={`Sorted ${sortDirection}`} /> : null}
      </button>
      {onSort || onTogglePin ? (
        <details className="fd-resource-column-menu">
          <summary aria-label={`${label} column menu`}><MoreHorizontal size={11} /></summary>
          <div role="menu">
            {onSort ? <button type="button" role="menuitem" onClick={() => onSort("asc")}><ArrowUp size={11} /> Sort ascending</button> : null}
            {onSort ? <button type="button" role="menuitem" onClick={() => onSort("desc")}><ArrowDown size={11} /> Sort descending</button> : null}
            {onTogglePin ? <button type="button" role="menuitem" onClick={onTogglePin}>{pinned ? <PinOff size={11} /> : <Pin size={11} />}{pinned ? "Unpin column" : "Pin column"}</button> : null}
            {description ? <p>{description}</p> : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}
