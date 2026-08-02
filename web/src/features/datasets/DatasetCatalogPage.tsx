import { Button, Callout, HTMLSelect, InputGroup, Spinner } from "@blueprintjs/core";
import { Database } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getDatasetCatalogDetail, getDatasetCatalogPage } from "../../api";
import { navigate } from "../../routing";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader } from "../../ui/foundry/WorkbenchChrome";
import { DatasetDetailInspector } from "./DatasetDetailInspector";
import { DatasetResourceTable } from "./DatasetResourceTable";
import type {
  DatasetCatalogDetail,
  DatasetCatalogPage as DatasetPage,
} from "./types";

interface DatasetCatalogPageProps {
  projectId: string;
}

const PAGE_SIZE = 25;

export function DatasetCatalogPage({ projectId }: DatasetCatalogPageProps) {
  const [page, setPage] = useState<DatasetPage>({ items: [], offset: 0, limit: PAGE_SIZE, total: 0 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DatasetCatalogDetail | null>(null);
  const [search, setSearch] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [status, setStatus] = useState("");
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
        status: status || undefined,
      });
      setPage(payload);
      setOffset(payload.offset);
      setSelectedId((current) => current && payload.items.some((item) => item.id === current)
        ? current
        : payload.items[0]?.id ?? null);
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
  }, [projectId, search, sourceType, status]);

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
      <WorkbenchHeader
        className="dataset-catalog-header"
        title={<EntityTitle
          icon={Database}
          eyebrow="DATASET CATALOG"
          title="Governed Dataset Browser"
          subtitle={`${projectId} · immutable versions, quality, lineage, and store projections`}
        />}
        metadata={<StatusPill intent="primary">{page.total} Datasets</StatusPill>}
        actions={<div className="dataset-header-actions">
          <Button icon="refresh" loading={loading} onClick={() => void refreshPage(offset)}>Refresh</Button>
          <Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button>
        </div>}
      />

      {error ? <Callout intent="danger" title="Catalog error"><span>{error}</span> <Button minimal small onClick={() => setError("")}>Dismiss</Button></Callout> : null}

      <section className="dataset-catalog-grid">
        <section className="dataset-catalog-list-pane">
          <div className="pane-heading">
            <div><small>PROJECT DATASETS</small><strong>{page.total} governed resources</strong></div>
            {loading ? <Spinner size={16} /> : null}
          </div>
          <div className="dataset-catalog-toolbar fd-resource-toolbar">
            <div className="fd-resource-toolbar__group">
              <InputGroup
                aria-label="Dataset catalog search"
                leftIcon="search"
                placeholder="Search name, slug, description"
                value={search}
                onChange={(event) => setSearch(event.currentTarget.value)}
              />
            </div>
            <div className="fd-resource-toolbar__group">
              <HTMLSelect value={sourceType} onChange={(event) => setSourceType(event.currentTarget.value)}>
                <option value="">All source types</option>
                {sourceTypes.map((value) => <option key={value} value={value}>{value}</option>)}
              </HTMLSelect>
              <HTMLSelect value={status} onChange={(event) => setStatus(event.currentTarget.value)}>
                <option value="">All status</option>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="archived">Archived</option>
              </HTMLSelect>
            </div>
          </div>
          <DatasetResourceTable
            items={page.items}
            selectedId={selectedId}
            loading={loading}
            onSelect={setSelectedId}
          />
          <footer className="dataset-catalog-pagination">
            <Button small icon="chevron-left" disabled={offset === 0 || loading} onClick={() => void refreshPage(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
            <span>{page.total ? `${offset + 1}-${Math.min(offset + page.items.length, page.total)} / ${page.total}` : "0 datasets"}</span>
            <Button small rightIcon="chevron-right" disabled={offset + page.items.length >= page.total || loading} onClick={() => void refreshPage(offset + PAGE_SIZE)}>Next</Button>
          </footer>
        </section>

        <DatasetDetailInspector detail={detail} loading={detailLoading} />
      </section>
    </main>
  );
}
