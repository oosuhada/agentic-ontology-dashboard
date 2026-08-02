import { Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag } from "@blueprintjs/core";
import { useEffect, useMemo, useState } from "react";
import { getDatasetCatalogDetail, getDatasetCatalogPage } from "../../api";
import { navigate } from "../../routing";
import type {
  DatasetCatalogDetail,
  DatasetCatalogItem,
  DatasetCatalogPage as DatasetPage,
  ProjectionStatus,
  StoreKind,
} from "./types";

interface DatasetCatalogPageProps {
  projectId: string;
}

const PAGE_SIZE = 25;
const STORE_LABELS: Record<StoreKind, string> = {
  relational: "PostgreSQL",
  graph: "Neo4j",
  vector: "Project 3 RAG",
};

function projectionIntent(status: ProjectionStatus | "not_configured") {
  if (status === "ready") return "success" as const;
  if (status === "failed") return "danger" as const;
  if (status === "indexing" || status === "pending") return "warning" as const;
  return "none" as const;
}

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
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

function JsonPreview({ value }: { value: unknown }) {
  return <pre className="dataset-json-preview">{JSON.stringify(value, null, 2)}</pre>;
}

export function DatasetCatalogPage({ projectId }: DatasetCatalogPageProps) {
  const [page, setPage] = useState<DatasetPage>({ items: [], offset: 0, limit: PAGE_SIZE, total: 0 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DatasetCatalogDetail | null>(null);
  const [search, setSearch] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const sourceTypes = useMemo(
    () => Array.from(new Set(page.items.map((item) => item.source_type))).sort(),
    [page.items],
  );

  async function refreshPage(nextOffset = offset) {
    setLoading(true);
    try {
      const payload = await getDatasetCatalogPage({
        project_id: projectId,
        offset: nextOffset,
        limit: PAGE_SIZE,
        search: search.trim() || undefined,
        source_type: sourceType || undefined,
      });
      setPage(payload);
      setOffset(payload.offset);
      setSelectedId((current) => {
        if (current && payload.items.some((item) => item.id === current)) return current;
        return payload.items[0]?.id ?? null;
      });
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Dataset Catalog를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshPage(0), 250);
    return () => window.clearTimeout(timer);
  }, [projectId, search, sourceType]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    getDatasetCatalogDetail(projectId, selectedId)
      .then((nextDetail) => {
        if (!cancelled) {
          setDetail(nextDetail);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Dataset 상세를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId, selectedId]);

  return (
    <main className="dataset-catalog-page">
      <header className="dataset-catalog-header">
        <div>
          <span className="eyebrow">DATASET CATALOG</span>
          <h1>Versions, quality, lineage, and store projections</h1>
          <p>{projectId} · {page.total} governed datasets</p>
        </div>
        <div className="dataset-header-actions">
          <Button icon="refresh" loading={loading} onClick={() => void refreshPage(offset)}>Refresh</Button>
          <Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button>
        </div>
      </header>

      {error ? <Callout intent="danger" title="Catalog error"><span>{error}</span> <Button minimal small onClick={() => setError("")}>Dismiss</Button></Callout> : null}

      <section className="dataset-catalog-grid">
        <aside className="dataset-catalog-list-pane">
          <div className="pane-heading">
            <div><small>PROJECT DATASETS</small><strong>{page.total} datasets</strong></div>
            {loading ? <Spinner size={16} /> : null}
          </div>
          <InputGroup
            aria-label="Dataset catalog search"
            leftIcon="search"
            placeholder="Search name, slug, description"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
          <HTMLSelect fill value={sourceType} onChange={(event) => setSourceType(event.currentTarget.value)}>
            <option value="">All source types</option>
            {sourceTypes.map((value) => <option key={value} value={value}>{value}</option>)}
          </HTMLSelect>
          <div className="dataset-catalog-list">
            {page.items.map((item) => (
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
            {!loading && !page.items.length ? (
              <div className="dataset-catalog-empty">
                <strong>No cataloged datasets</strong>
                <p>Adapter ingestion or “Save Analysis Result as Dataset” creates an immutable Dataset Version here.</p>
              </div>
            ) : null}
          </div>
          <footer className="dataset-catalog-pagination">
            <Button small icon="chevron-left" disabled={offset === 0 || loading} onClick={() => void refreshPage(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
            <span>{page.total ? `${offset + 1}-${Math.min(offset + page.items.length, page.total)} / ${page.total}` : "0 datasets"}</span>
            <Button small rightIcon="chevron-right" disabled={offset + page.items.length >= page.total || loading} onClick={() => void refreshPage(offset + PAGE_SIZE)}>Next</Button>
          </footer>
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
                <Card elevation={0}><small>Document index</small><strong>{detail.document_index_readiness.status}</strong><span>{detail.document_index_readiness.content_fields.join(", ") || "content mapping required"}</span></Card>
              </section>

              <section className="dataset-detail-section">
                <header><div><small>STORE PROJECTIONS</small><h2>Cross-store health</h2></div><Tag minimal>{detail.projections.length} projections</Tag></header>
                <div className="dataset-projection-cards">
                  {detail.projections.map((projection) => (
                    <Card key={projection.id} elevation={0}>
                      <div><strong>{STORE_LABELS[projection.store_kind]}</strong><Tag minimal intent={projectionIntent(projection.status)}>{projection.status}</Tag></div>
                      <dl>
                        <div><dt>Dataset version</dt><dd>{projection.dataset_version_id}</dd></div>
                        <div><dt>Source version</dt><dd>{projection.source_version}</dd></div>
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
                <header><div><small>VERSION HISTORY</small><h2>Schema, profile, and immutable source revisions</h2></div></header>
                <div className="dataset-version-table">
                  <div className="header"><span>Version</span><span>Source revision</span><span>Rows</span><span>Status</span><span>Created</span></div>
                  {detail.versions.map((version) => (
                    <details key={version.id} className="dataset-version-detail-row">
                      <summary>
                        <strong>{version.version_label}</strong>
                        <code>{version.source_version}</code>
                        <span>{version.record_count.toLocaleString()}</span>
                        <Tag minimal intent={version.status === "ready" ? "success" : version.status === "failed" ? "danger" : "warning"}>{version.status}</Tag>
                        <time>{new Date(version.created_at).toLocaleString()}</time>
                      </summary>
                      <div className="dataset-version-json-grid">
                        <div><small>SCHEMA</small><JsonPreview value={version.schema} /></div>
                        <div><small>PROFILE</small><JsonPreview value={version.profile} /></div>
                      </div>
                    </details>
                  ))}
                </div>
              </section>

              <section className="dataset-detail-section dataset-detail-two-column">
                <Card elevation={0}>
                  <small>SOURCE FILES</small>
                  {detail.files.map((file) => (
                    <div className="dataset-mapping-row" key={file.id}>
                      <div><strong>{file.media_type}</strong><span>{file.dataset_version_id} · {formatBytes(file.size_bytes)}</span><code>{file.uri}</code></div>
                      <Tag minimal>{file.checksum_sha256.slice(0, 10)}</Tag>
                    </div>
                  ))}
                  {!detail.files.length ? <p>No registered source file.</p> : null}
                </Card>
                <Card elevation={0}>
                  <small>ONTOLOGY MAPPINGS</small>
                  {detail.mappings.map((mapping) => (
                    <div className="dataset-mapping-row" key={mapping.id}>
                      <div><strong>{mapping.object_type}</strong><span>identity: {mapping.identity_field}</span><span>content: {mapping.content_fields.join(", ") || "not configured"}</span></div>
                      <Tag minimal>{mapping.status}</Tag>
                    </div>
                  ))}
                  {!detail.mappings.length ? <p>No approved mapping yet.</p> : null}
                </Card>
              </section>

              <section className="dataset-detail-section">
                <header><div><small>INGESTION & QUARANTINE</small><h2>Adapter run quality</h2></div><Tag minimal intent={detail.quarantine_records.length ? "warning" : "success"}>{detail.quarantine_records.length} quarantined</Tag></header>
                <div className="dataset-ingestion-grid">
                  {detail.ingestion_runs.map((run) => (
                    <Card key={run.id} elevation={0}>
                      <div><strong>{run.adapter_code}</strong><Tag minimal intent={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warning"}>{run.status}</Tag></div>
                      <dl>
                        <div><dt>Source</dt><dd>{run.source_record_count}</dd></div>
                        <div><dt>Accepted</dt><dd>{run.accepted_record_count}</dd></div>
                        <div><dt>Quarantined</dt><dd>{run.quarantined_record_count}</dd></div>
                        <div><dt>Started</dt><dd>{new Date(run.started_at).toLocaleString()}</dd></div>
                      </dl>
                      {run.error_message ? <Callout intent="danger">{run.error_message}</Callout> : null}
                    </Card>
                  ))}
                  {!detail.ingestion_runs.length ? <p className="dataset-catalog-empty">No adapter ingestion run is linked to this Dataset Version.</p> : null}
                </div>
                {detail.quarantine_records.length ? (
                  <div className="dataset-quarantine-table">
                    {detail.quarantine_records.map((record) => (
                      <details key={record.id}>
                        <summary><code>row {record.source_row_number ?? "?"}</code><strong>{record.error_code}</strong><span>{record.error_message}</span></summary>
                        <JsonPreview value={record.record} />
                      </details>
                    ))}
                  </div>
                ) : null}
              </section>

              <section className="dataset-detail-section dataset-detail-two-column">
                <Card elevation={0}>
                  <small>MATERIALIZATIONS</small>
                  {detail.materializations.map((item) => (
                    <div className="dataset-mapping-row" key={item.id}>
                      <div><strong>{item.format.toUpperCase()}</strong><span>{item.source_kind} · {item.record_count.toLocaleString()} rows</span><code>{item.source_reference}</code></div>
                      <Tag minimal intent={item.status === "ready" ? "success" : "warning"}>{item.status}</Tag>
                    </div>
                  ))}
                  {!detail.materializations.length ? <p>No reusable materialization yet.</p> : null}
                </Card>
                <Card elevation={0}>
                  <small>LINEAGE REFERENCES</small>
                  <div className="dataset-lineage-references">
                    {detail.lineage_references.map((reference) => <code key={reference}>{reference}</code>)}
                    {!detail.lineage_references.length ? <p>No downstream lineage reference.</p> : null}
                  </div>
                </Card>
              </section>
            </div>
          ) : <div className="dataset-catalog-empty"><strong>Select a dataset</strong><p>Inspect immutable versions, mappings, ingestion quality, and all store projections.</p></div>}
        </section>
      </section>
    </main>
  );
}
