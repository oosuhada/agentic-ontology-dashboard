import { Card, Tag } from "@blueprintjs/core";
import { Database, FileSearch, Network, SearchCode } from "lucide-react";
import { useEffect, useRef } from "react";
import type { AgentEvidenceItem, EvidenceStore } from "./types";

interface EvidenceTraceListProps {
  items: AgentEvidenceItem[];
  selectedEvidenceId: string | null;
  onSelectEvidence: (evidenceId: string) => void;
}

const STORE_LABELS: Record<EvidenceStore, string> = {
  postgresql: "PostgreSQL",
  neo4j: "Neo4j",
  pgvector: "pgvector",
  project3_rag: "Project 3 RAG",
};

function StoreIcon({ store }: { store: EvidenceStore }) {
  if (store === "postgresql") return <Database size={14} aria-hidden />;
  if (store === "neo4j") return <Network size={14} aria-hidden />;
  if (store === "pgvector") return <SearchCode size={14} aria-hidden />;
  return <FileSearch size={14} aria-hidden />;
}

function scoreLabel(score: number | null): string {
  if (score === null) return "unscored";
  return `${Math.round(score * 100)}%`;
}

export function EvidenceTraceList({
  items,
  selectedEvidenceId,
  onSelectEvidence,
}: EvidenceTraceListProps) {
  const elements = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    if (!selectedEvidenceId) return;
    elements.current.get(selectedEvidenceId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedEvidenceId]);

  if (!items.length) {
    return <div className="agent-empty-state"><strong>No evidence</strong><p>현재 scope와 질문에 일치하는 검증 가능한 근거가 없습니다.</p></div>;
  }

  return (
    <div className="agent-evidence-list" role="list" aria-label="Evidence sources">
      {items.map((item) => (
        <div
          key={item.evidence_id}
          role="listitem"
          className="agent-evidence-anchor"
          ref={(element: HTMLDivElement | null) => {
            if (element) elements.current.set(item.evidence_id, element);
            else elements.current.delete(item.evidence_id);
          }}
        >
          <Card
            elevation={0}
            interactive
            className={selectedEvidenceId === item.evidence_id ? "selected" : ""}
            onClick={() => onSelectEvidence(item.evidence_id)}
          >
            <header>
            <div className="agent-store-identity">
              <StoreIcon store={item.store} />
              <strong>{STORE_LABELS[item.store]}</strong>
            </div>
            <div className="agent-evidence-tags">
              <Tag minimal>{scoreLabel(item.score)}</Tag>
              {item.dataset_version_id ? <Tag minimal>{item.dataset_version_id}</Tag> : null}
            </div>
          </header>
          <h3>{item.title}</h3>
          <p>{item.content}</p>
          <dl>
            <div><dt>Evidence ID</dt><dd>{item.evidence_id}</dd></div>
            <div><dt>Reference</dt><dd>{item.reference}</dd></div>
            <div><dt>Object</dt><dd>{item.object_id ?? "—"}</dd></div>
            <div><dt>Scope</dt><dd>{item.project_id} · {item.workspace_id}</dd></div>
          </dl>
            {Object.keys(item.metadata).length ? (
              <details>
                <summary>Source metadata</summary>
                <pre>{JSON.stringify(item.metadata, null, 2)}</pre>
              </details>
            ) : null}
          </Card>
        </div>
      ))}
    </div>
  );
}
