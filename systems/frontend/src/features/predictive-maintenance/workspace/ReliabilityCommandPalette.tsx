import { Activity, ArrowRight, Building2, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { OperationsView } from "../../operations/api/operationsContracts";
import type { ReliabilitySurface } from "./roleSurfaces";

export interface ReliabilitySearchEntity {
  id: string;
  kind: "asset" | "event";
  label: string;
  detail: string;
  assetId: string;
  eventId: string | null;
  keywords?: string;
}

export function ReliabilityCommandPalette({
  open,
  onClose,
  navigation,
  entities,
  onNavigate,
  onSelectEntity,
  english,
}: {
  open: boolean;
  onClose: () => void;
  navigation: ReliabilitySurface[];
  entities: ReliabilitySearchEntity[];
  onNavigate: (surfaceId: string, view: OperationsView) => void;
  onSelectEntity: (entity: ReliabilitySearchEntity) => void;
  english: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    setQuery("");
    window.requestAnimationFrame(() => inputRef.current?.focus());
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  const normalized = query.trim().toLocaleLowerCase();
  const surfaceResults = useMemo(() => navigation.filter((item) => {
    if (!normalized) return true;
    const text = `${item.label.ko} ${item.label.en} ${item.detail.ko} ${item.detail.en} ${item.page.title.ko} ${item.page.title.en}`.toLocaleLowerCase();
    return text.includes(normalized);
  }).slice(0, normalized ? 8 : 5), [navigation, normalized]);
  const entityResults = useMemo(() => entities.filter((item) => {
    if (!normalized) return item.kind === "event";
    return `${item.label} ${item.detail} ${item.assetId} ${item.eventId ?? ""} ${item.keywords ?? ""}`.toLocaleLowerCase().includes(normalized);
  }).slice(0, normalized ? 10 : 6), [entities, normalized]);

  if (!open) return null;

  return <div className="rw-command-palette-layer" role="presentation" onMouseDown={(event) => {
    if (event.currentTarget === event.target) onClose();
  }}>
    <section className="rw-command-palette" role="dialog" aria-modal="true" aria-label={english ? "Search Reliability Operations" : "Reliability Operations 검색"}>
      <header>
        <Search size={16} />
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={english ? "Search surfaces, equipment, or events" : "메뉴, 설비 또는 Event 검색"}
          aria-label={english ? "Search surfaces, equipment, or events" : "메뉴, 설비 또는 Event 검색"}
        />
        <kbd>ESC</kbd>
        <button type="button" onClick={onClose} aria-label={english ? "Close search" : "검색 닫기"}><X size={15} /></button>
      </header>
      <div className="rw-command-palette__results">
        {surfaceResults.length ? <section>
          <span>{english ? "WORKSPACE" : "업무 화면"}</span>
          {surfaceResults.map((item) => <button type="button" key={`surface:${item.id}`} onClick={() => {
            onNavigate(item.id, item.view);
            onClose();
          }}>
            <i><Building2 size={14} /></i>
            <div><strong>{english ? item.label.en : item.label.ko}</strong><small>{english ? item.detail.en : item.detail.ko}</small></div>
            <ArrowRight size={13} />
          </button>)}
        </section> : null}
        {entityResults.length ? <section>
          <span>{english ? "LIVE CONTEXT" : "실시간 운영 문맥"}</span>
          {entityResults.map((item) => <button type="button" key={item.id} onClick={() => {
            onSelectEntity(item);
            onClose();
          }}>
            <i><Activity size={14} /></i>
            <div><strong>{item.label}</strong><small>{item.detail}</small></div>
            <ArrowRight size={13} />
          </button>)}
        </section> : null}
        {!surfaceResults.length && !entityResults.length ? <p className="rw-command-palette__empty">{english ? "No matching workspace, equipment, or event." : "일치하는 업무 화면, 설비 또는 Event가 없습니다."}</p> : null}
      </div>
      <footer>{english ? "Enter a menu name, equipment ID, line, or Event ID." : "메뉴명, 설비 ID, 라인 또는 Event ID로 찾을 수 있습니다."}</footer>
    </section>
  </div>;
}
