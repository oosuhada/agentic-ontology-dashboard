import { Database, Files, GitBranch, Layers3, Network, Rows3, Sigma, TableProperties } from "lucide-react";
import { useMemo, useState } from "react";
import { InspectorTabs } from "../../ui/foundry/InspectorTabs";
import { MetricStrip } from "../../ui/foundry/MetricStrip";
import { PropertyTable } from "../../ui/foundry/PropertyTable";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState, LoadingState } from "../../ui/foundry/WorkbenchState";
import type { DatasetCatalogDetail, ProjectionStatus, StoreKind } from "./types";

type DatasetInspectorTab = "overview" | "schema" | "profile" | "files" | "versions" | "lineage" | "projections";

const STORE_LABELS: Record<StoreKind, string> = { relational: "PostgreSQL", graph: "Neo4j", vector: "Project 3 RAG" };

function projectionIntent(status: ProjectionStatus | "not_configured") {
  if (status === "ready") return "success" as const;
  if (status === "failed") return "danger" as const;
  if (status === "indexing" || status === "pending") return "warning" as const;
  return "neutral" as const;
}

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function previewValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

interface DatasetDetailInspectorProps {
  detail: DatasetCatalogDetail | null;
  loading: boolean;
}

export function DatasetDetailInspector({ detail, loading }: DatasetDetailInspectorProps) {
  const [activeTab, setActiveTab] = useState<DatasetInspectorTab>("overview");
  const latestVersion = detail?.versions[0] ?? null;
  const schemaRows = useMemo(() => latestVersion ? Object.entries(latestVersion.schema).map(([key, value]) => ({ id: key, label: key, value: previewValue(value), type: typeof value, mono: typeof value === "string" && key.includes("id") })) : [], [latestVersion]);
  const profileRows = useMemo(() => latestVersion ? Object.entries(latestVersion.profile).map(([key, value]) => ({ id: key, label: key, value: previewValue(value), type: "profile" })) : [], [latestVersion]);

  if (loading && !detail) return <section className="dataset-catalog-detail-pane"><LoadingState title="Loading Dataset detail" detail="Resolving versions, files, mappings, and projections." /></section>;
  if (!detail) return <section className="dataset-catalog-detail-pane"><EmptyState title="Select a Dataset" detail="Inspect immutable identity, schema, quality, lineage, and projection readiness." /></section>;

  return (
    <section className="dataset-catalog-detail-pane">
      <header className="dataset-entity-header">
        <div><span className="section-label">DATASET RESOURCE</span><strong>{detail.dataset.display_name}</strong><small>{detail.dataset.id} · {detail.dataset.workspace_id}</small></div>
        <div><StatusPill intent={detail.dataset.status === "active" ? "success" : "warning"}>{detail.dataset.status}</StatusPill><StatusPill intent="primary">{detail.dataset.latest_version_label ?? "No version"}</StatusPill></div>
      </header>
      <InspectorTabs
        activeTab={activeTab}
        onChange={setActiveTab}
        label="Dataset inspector sections"
        tabs={[
          { id: "overview", label: "Overview", icon: <Database size={11} /> },
          { id: "schema", label: "Schema", count: schemaRows.length, icon: <TableProperties size={11} /> },
          { id: "profile", label: "Profile", count: profileRows.length, icon: <Sigma size={11} /> },
          { id: "files", label: "Files", count: detail.files.length, icon: <Files size={11} /> },
          { id: "versions", label: "Versions", count: detail.versions.length, icon: <Layers3 size={11} /> },
          { id: "lineage", label: "Lineage", count: detail.lineage_references.length, icon: <GitBranch size={11} /> },
          { id: "projections", label: "Projections", count: detail.projections.length, icon: <Network size={11} /> },
        ]}
      />
      <div className="dataset-detail-scroll">
        {activeTab === "overview" ? (
          <>
            <MetricStrip metrics={[
              { id: "records", label: "Records", value: detail.dataset.record_count.toLocaleString(), detail: `${detail.versions.length} immutable versions` },
              { id: "version", label: "Current version", value: detail.dataset.latest_version_label ?? "—", detail: detail.dataset.latest_source_version ?? "—" },
              { id: "index", label: "Document index", value: detail.document_index_readiness.status, detail: `${detail.document_index_readiness.indexed_record_count.toLocaleString()} indexed`, tone: detail.document_index_readiness.status === "ready" ? "success" : detail.document_index_readiness.status === "failed" ? "danger" : "warning" },
              { id: "quarantine", label: "Quarantine", value: detail.quarantine_records.length, detail: `${detail.ingestion_runs.length} ingestion runs`, tone: detail.quarantine_records.length ? "warning" : "success" },
            ]} />
            <PropertyTable rows={[
              { id: "slug", label: "Slug", value: detail.dataset.slug, type: "resource", mono: true },
              { id: "source", label: "Source type", value: detail.dataset.source_type, type: "connector" },
              { id: "creator", label: "Created by", value: detail.dataset.created_by ?? "system", type: "principal", mono: true },
              { id: "created", label: "Created", value: new Date(detail.dataset.created_at).toLocaleString(), type: "datetime" },
              { id: "updated", label: "Updated", value: new Date(detail.dataset.updated_at).toLocaleString(), type: "datetime" },
              { id: "description", label: "Description", value: detail.dataset.description || "—", type: "text" },
            ]} />
            <section className="dataset-ingestion-summary"><header><span className="section-label">INGESTION HEALTH</span><strong>{detail.ingestion_runs.length} runs</strong></header>{detail.ingestion_runs.map((run) => <article key={run.id}><div><strong>{run.adapter_code}</strong><StatusPill intent={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warning"}>{run.status}</StatusPill></div><span>{run.accepted_record_count.toLocaleString()} accepted · {run.quarantined_record_count.toLocaleString()} quarantined</span><small>{new Date(run.started_at).toLocaleString()}</small></article>)}</section>
          </>
        ) : null}

        {activeTab === "schema" ? <PropertyTable rows={schemaRows} emptyMessage="No schema registered for the current Dataset Version." /> : null}
        {activeTab === "profile" ? <><MetricStrip metrics={[
          { id: "rows", label: "Rows", value: latestVersion?.record_count.toLocaleString() ?? "0", detail: latestVersion?.version_label ?? "—" },
          { id: "fields", label: "Profile fields", value: profileRows.length, detail: "server-computed" },
          { id: "checksum", label: "Checksum", value: latestVersion?.checksum_sha256.slice(0, 10) ?? "—", detail: "sha256" },
        ]} /><PropertyTable rows={profileRows} emptyMessage="No profile registered for the current Dataset Version." /></> : null}

        {activeTab === "files" ? <div className="dataset-inspector-list">{detail.files.map((file) => <article key={file.id}><div><Rows3 size={14} /><span><strong>{file.media_type}</strong><small>{file.dataset_version_id}</small></span></div><code>{file.uri}</code><footer><span>{formatBytes(file.size_bytes)}</span><StatusPill>{file.checksum_sha256.slice(0, 10)}</StatusPill></footer></article>)}{!detail.files.length ? <EmptyState title="No source files" detail="This Dataset Version has no registered file artifact." /> : null}</div> : null}

        {activeTab === "versions" ? <div className="fd-resource-table dataset-version-resource-table" role="table"><div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: "90px minmax(160px,1fr) 90px 90px 150px" }}><span>Version</span><span>Source revision</span><span>Rows</span><span>Status</span><span>Created</span></div>{detail.versions.map((version) => <div className="fd-resource-table__row" role="row" key={version.id} style={{ gridTemplateColumns: "90px minmax(160px,1fr) 90px 90px 150px" }}><span><strong>{version.version_label}</strong></span><span><code>{version.source_version}</code></span><span className="fd-resource-table__numeric">{version.record_count.toLocaleString()}</span><span><StatusPill intent={version.status === "ready" ? "success" : version.status === "failed" ? "danger" : "warning"}>{version.status}</StatusPill></span><span>{new Date(version.created_at).toLocaleString()}</span></div>)}</div> : null}

        {activeTab === "lineage" ? <div className="dataset-lineage-browser"><section><span className="section-label">ONTOLOGY MAPPINGS</span>{detail.mappings.map((mapping) => <article key={mapping.id}><div><strong>{mapping.object_type}</strong><StatusPill>{mapping.status}</StatusPill></div><span>identity · {mapping.identity_field}</span><small>content · {mapping.content_fields.join(", ") || "not configured"}</small></article>)}{!detail.mappings.length ? <p>No approved mappings.</p> : null}</section><section><span className="section-label">DOWNSTREAM REFERENCES</span>{detail.lineage_references.map((reference) => <code key={reference}>{reference}</code>)}{!detail.lineage_references.length ? <p>No downstream lineage reference.</p> : null}</section><section><span className="section-label">MATERIALIZATIONS</span>{detail.materializations.map((item) => <article key={item.id}><div><strong>{item.format.toUpperCase()}</strong><StatusPill intent={item.status === "ready" ? "success" : "warning"}>{item.status}</StatusPill></div><span>{item.source_kind} · {item.record_count.toLocaleString()} rows</span><code>{item.source_reference}</code></article>)}</section></div> : null}

        {activeTab === "projections" ? <div className="dataset-projection-inspector">{detail.projections.map((projection) => <article key={projection.id}><header><div><strong>{STORE_LABELS[projection.store_kind]}</strong><small>{projection.dataset_version_id}</small></div><StatusPill intent={projectionIntent(projection.status)}>{projection.status}</StatusPill></header><PropertyTable rows={[
          { id: "source", label: "Source version", value: projection.source_version, type: "version", mono: true },
          { id: "records", label: "Records", value: projection.record_count, type: "integer", numeric: true },
          { id: "attempts", label: "Attempts", value: projection.attempt_count, type: "integer", numeric: true },
          { id: "namespace", label: "Namespace", value: projection.object_namespace, type: "namespace", mono: true },
          { id: "updated", label: "Updated", value: new Date(projection.updated_at).toLocaleString(), type: "datetime" },
        ]} />{projection.last_error ? <p className="dataset-projection-error">{projection.last_error}</p> : null}</article>)}</div> : null}
      </div>
    </section>
  );
}
