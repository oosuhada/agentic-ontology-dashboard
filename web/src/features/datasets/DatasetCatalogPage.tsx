import { Button, Callout, Card, InputGroup, Spinner, Tag } from "@blueprintjs/core";
import { useEffect, useMemo, useState } from "react";
import { getDatasetCatalog, getDatasetCatalogDetail } from "../../api";
import { navigate } from "../../routing";
import type {
  DatasetCatalogDetail,
  DatasetCatalogItem,
  ProjectionStatus,
  StoreKind,
} from "./types";

interface DatasetCatalogPageProps {
  projectId: string;
}

const STORE_LABELS: Record<StoreKind, string> = {
  relational: "PostgreSQL",
  graph: "Neo4j",
  vector: "pgvector",
};

function projectionIntent(status: ProjectionStatus) {
  if (status === "ready") return "success" as const;
  if (status === "failed") return "danger" as const;
  if (status === "indexing" || status === "pending") return "warning" as const;
  return "none" as const;
}

function ProjectionHealth({ item }: { item: DatasetCatalogItem }) {
  return (
    <div className="dataset-projection-health">
      {(Object.keys(STORE_LABELS) as StoreKind[]).map((store) => (
        <Tag key={store} minimal intent={projectionIntent(item.projection_health[store])}>
          {STORE_LABELS[store]} · {item.projection_health[store]}
        </Tag>
      ))}
    </div>
  );
}

export function DatasetCatalogPage({ projectId }: DatasetCatalogPageProps) {
  const [items, setItems] = useState<DatasetCatalogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DatasetCatalogDetail | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) =>
      [item.display_name, item.slug, item.source_type, item.description]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [items, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDatasetCatalog(projectId)
      .then((nextItems) => {
        if (cancelled) return;
        setItems(nextItems);
        setSelectedId((current) => current ?? nextItems[0]?.id ?? null);
        setError("");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Dataset Catalog를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    getDatasetCatalogDetail(projectId, selectedId)
      .then((nextDetail) => {
        if (!cancelled) setDetail(nextDetail);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Dataset 상세를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId, selectedId]);

  if (loading) {
    return <main className="dataset-catalog-loading"><Spinner size={32} /><p>Dataset Catalog를 불러오고 있습니다.</p></main>;
  }

  return (
    <main className="dataset-catalog-page">
      <header className="dataset-catalog-header">
        <div>
          <span className="eyebrow">DATASET CATALOG</span>
          <h1>Versions, quality, lineage, and store projections</h1>
          <p>{projectId}</p>
        </div>
        <Button icon="dashboard" onClick={() => navigate("/app")}>Dashboard</Button>
      </header>

      {error ? <Callout intent="danger" title="Catalog error">{error}</Callout> : null}

      <section className="dataset-catalog-grid">
        <aside className="dataset-catalog-list-pane">
          <div className="pane-heading">
            <div><small>PROJECT DATASETS</small><strong>{filtered.length} datasets</strong></div>
          </div>
          <InputGroup
            leftIcon="search"
            placeholder="Search name, source, description"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
          <div className="dataset-catalog-list">
            {filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                className={selectedId === item.id ? "active" : ""}
                onClick={() => setSelectedId(item.id)}
              >
                <div><strong>{item.display_name}</strong><Tag minimal>{item.source_type}</Tag></div>
                <span>{item.latest_version_label ?? "No version"} · {item.record_count.toLocaleString()} rows</span>
                <ProjectionHealth item={item} />
              </button>
            ))}
            {!filtered.length ? (
              <div className="dataset-catalog-empty">
                <strong>No cataloged datasets</strong>
                <p>Adapter ingestion or a materialized analysis result creates a canonical Dataset Version here.</p>
              </div>
            ) : null}
          </div>
        </aside>

        <section className="dataset-catalog-detail-pane">
          <div className="pane-heading">
            <div><small>DATASET DETAIL</small><strong>{detail?.dataset.display_name ?? "Select a dataset"}</strong></div>
            {detailLoading ? <Spinner size={18} /> : null}
          </div>
          {detail ? (
            <div className="dataset-detail-scroll">
              <section className="dataset-detail-summary">
                <Card elevation={0}><small>Current version</small><strong>{detail.dataset.latest_version_label ?? "—"}</strong><span>{detail.dataset.latest_source_version ?? "—"}</span></Card>
                <Card elevation={0}><small>Records</small><strong>{detail.dataset.record_count.toLocaleString()}</strong><span>{detail.versions.length} immutable versions</span></Card>
                <Card elevation={0}><small>Workspace</small><strong>{detail.dataset.workspace_id}</strong><span>{detail.dataset.source_type}</span></Card>
              </section>

              <section className="dataset-detail-section">
                <header><div><small>STORE PROJECTIONS</small><h2>Cross-store health</h2></div></header>
                <div className="dataset-projection-cards">
                  {detail.projections.map((projection) => (
                    <Card key={projection.id} elevation={0}>
                      <div><strong>{STORE_LABELS[projection.store_kind]}</strong><Tag minimal intent={projectionIntent(projection.status)}>{projection.status}</Tag></div>
                      <dl>
                        <div><dt>Version</dt><dd>{projection.source_version}</dd></div>
                        <div><dt>Records</dt><dd>{projection.record_count.toLocaleString()}</dd></div>
                        <div><dt>Attempts</dt><dd>{projection.attempt_count}</dd></div>
                        <div><dt>Namespace</dt><dd>{projection.object_namespace}</dd></div>
                      </dl>
                      {projection.last_error ? <Callout intent="danger">{projection.last_error}</Callout> : null}
                    </Card>
                  ))}
                </div>
              </section>

              <section className="dataset-detail-section">
                <header><div><small>VERSION HISTORY</small><h2>Immutable source revisions</h2></div></header>
                <div className="dataset-version-table">
                  <div className="header"><span>Version</span><span>Source revision</span><span>Rows</span><span>Status</span><span>Created</span></div>
                  {detail.versions.map((version) => (
                    <div key={version.id}>
                      <strong>{version.version_label}</strong>
                      <code>{version.source_version}</code>
                      <span>{version.record_count.toLocaleString()}</span>
                      <Tag minimal intent={version.status === "ready" ? "success" : version.status === "failed" ? "danger" : "warning"}>{version.status}</Tag>
                      <time>{new Date(version.created_at).toLocaleString()}</time>
                    </div>
                  ))}
                </div>
              </section>

              <section className="dataset-detail-section dataset-detail-two-column">
                <Card elevation={0}>
                  <small>ONTOLOGY MAPPINGS</small>
                  {detail.mappings.map((mapping) => (
                    <div className="dataset-mapping-row" key={mapping.id}>
                      <div><strong>{mapping.object_type}</strong><span>identity: {mapping.identity_field}</span></div>
                      <Tag minimal>{mapping.status}</Tag>
                    </div>
                  ))}
                  {!detail.mappings.length ? <p>No approved mapping yet.</p> : null}
                </Card>
                <Card elevation={0}>
                  <small>MATERIALIZATIONS</small>
                  {detail.materializations.map((item) => (
                    <div className="dataset-mapping-row" key={item.id}>
                      <div><strong>{item.format.toUpperCase()}</strong><span>{item.source_kind} · {item.record_count.toLocaleString()} rows</span></div>
                      <Tag minimal intent={item.status === "ready" ? "success" : "warning"}>{item.status}</Tag>
                    </div>
                  ))}
                  {!detail.materializations.length ? <p>No reusable materialization yet.</p> : null}
                </Card>
              </section>
            </div>
          ) : <div className="dataset-catalog-empty"><strong>Select a dataset</strong><p>Inspect immutable versions, mappings and all three store projections.</p></div>}
        </section>
      </section>
    </main>
  );
}
