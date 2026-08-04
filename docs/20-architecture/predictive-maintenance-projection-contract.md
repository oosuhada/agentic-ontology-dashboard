# Predictive Maintenance Bundle and Projection Contract

- Status: frozen draft for Phase 0
- Contract date: 2026-08-04
- Runtime owner: Ontology Dashboard / Project 2
- Graph capability owner: Project 3
- Related decisions: ADR-003, ADR-004, ADR-013, ADR-014, ADR-017

## 1. Scope

This contract freezes the boundary before PostgreSQL ingestion, Ontology
materialization, or Neo4j writes are implemented.

It defines:

- Dataset Bundle Manifest v2
- deterministic bundle checksum canonicalization
- Project, Workspace, Dataset, Dataset Version, object, and projection identity
- runtime source and evaluation-truth separation
- Project 3 graph projection request, response, status, and error payloads

This phase does **not** implement fact tables, `COPY`, materialization, graph
writes, delivery retries, or Dashboard UI.

## 2. Dataset Bundle Manifest v2

The JSON Schema is `schemas/dataset-bundle-manifest.schema.json`. The typed
model is `ontology_dashboard.adapters.bundle_models.DatasetBundleManifestV2`.

One manifest represents one immutable Dataset Version and groups multiple
runtime files by a unique `files[].role`.

Required envelope fields:

```text
manifest_version = 2.0
manifest_id
organization_id
project_id
workspace_id
adapter_code
dataset_name
dataset_version
schema_version
bundle_checksum_sha256
generation
source_contract
files[]
created_at
```

Each runtime file requires:

```text
role
uri
format
media_type
checksum_sha256
size_bytes
schema.schema_version
schema.required_fields
schema.primary_key
schema.timestamp_field
schema.timezone
```

Phase 1's predictive-maintenance adapter must require these runtime roles:

```text
asset_master
asset_relation
compressor_sensor_observation
cnc_sensor_observation
cnc_production_cycle
maintenance_event
prediction_snapshot
prediction_factor
prediction_timeline
```

The generic v2 contract requires role uniqueness but leaves required role-set
enforcement to the domain adapter so future domain packs can reuse the bundle
format.

## 3. Canonical Bundle Checksum

`bundle_checksum_sha256` identifies immutable dataset content and the contract
that produced it. It must not identify a local checkout or a particular
manifest document.

Included in the canonical checksum payload:

```text
dataset_version
schema_version
generation.generator_version
generation.seed
generation.period_start normalized to UTC
generation.period_end normalized to UTC
generation.observation_interval_minutes
generation.rate_profile
all source_contract flags with sorted keys
files sorted by role:
  role
  checksum_sha256 normalized to lowercase
  format
  media_type
  complete file schema metadata
```

Excluded from the canonical checksum payload:

```text
manifest_id
organization_id
project_id
workspace_id
adapter_code
dataset_name
created_at
files[].uri
files[].size_bytes
original files[] ordering
```

Canonical serialization uses UTF-8 JSON with sorted object keys and compact
separators, followed by SHA-256.

Consequences:

- the same files copied to another absolute path produce the same checksum;
- the same files listed in another order produce the same checksum;
- a changed file checksum, seed, period, generator version, schema version,
  schema metadata, or source-contract flag produces a different checksum;
- identical content can be registered in another Project without changing the
  bundle checksum, while its catalog identity remains project-scoped.

The executable canonicalizer is
`ontology_dashboard.adapters.bundle_models.compute_bundle_checksum`.

## 4. Identity Rules

### 4.1 Project and Workspace

```text
Project identity   = (organization_id, project_id)
Workspace identity = (organization_id, project_id, workspace_id)
```

A Workspace is subordinate to a Project. A bundle may not be registered into a
global or project-less Workspace.

### 4.2 Dataset and Dataset Version

```text
Dataset identity =
  (organization_id, project_id, workspace_id, dataset_id)

Dataset Version identity =
  (organization_id, project_id, workspace_id, dataset_id, dataset_version_id)
```

`dataset_version` in the source manifest is the producer's source version.
`dataset_version_id` is the Ontology Dashboard catalog record identity created
during registration. A changed bundle checksum creates or resolves to a
different Dataset Version record; existing records are not overwritten.

### 4.3 PostgreSQL Object Identity

Operational and ontology-derived records use:

```text
(organization_id,
 project_id,
 workspace_id,
 dataset_id,
 dataset_version_id,
 object_type,
 source_identity)
```

Canonical text form:

```text
org:<org>:project:<project>:workspace:<workspace>:
dataset:<dataset>:version:<dataset-version-id>:
object:<object-type>:<source-identity>
```

PostgreSQL primary or unique constraints may use separate typed columns rather
than storing the rendered string. The rendered form is for stable audit and
contract comparison.

### 4.4 Neo4j Projection Identity

Neo4j projection identity uses:

```text
(organization_id,
 project_id,
 dataset_id,
 dataset_version_id,
 object_type,
 source_identity)
```

Canonical text form:

```text
org:<org>:project:<project>:dataset:<dataset>:
version:<dataset-version-id>:object:<object-type>:<source-identity>
```

Project 3 must `MERGE` on this full identity. The same Dataset Version can be
reprojected idempotently; a different Dataset Version retains separate lineage.
`workspace_id` stays in the request envelope and authorization context but is
not part of the graph object key because a Project graph projection can be read
from multiple authorized Workspaces.

### 4.5 Source Reference

File reference:

```text
dataset:<dataset-id>:version:<dataset-version-id>:
role:<role>:sha256:<file-sha256>
```

Object reference:

```text
<file-reference>:object:<object-type>:<source-identity>
```

Time-window evidence reference:

```text
<object-reference>:window:<UTC-start>/<UTC-end>
```

Raw sensor rows are not graph nodes. Risk and prediction evidence points to a
registered file and optional object/time window through this source reference.

## 5. Runtime Source and Evaluation Truth

`canonical/evaluation_truth` is an evaluation-only artifact scope. It is not a
runtime Dataset Bundle file and must not be reachable from Dashboard, Agent,
Ontology, or normal Dataset queries.

The following roles are explicitly forbidden in runtime bundle files:

```text
evaluation_truth
failure_schedule
compressor_failure_truth
cnc_failure_truth
```

Any URI containing an `evaluation_truth` path segment is also rejected. The
manifest must set `source_contract.evaluation_truth_separate=true`.

Model outputs such as `prediction_snapshot`, `prediction_factor`, and
`prediction_timeline` are runtime artifacts, but they remain separate from the
canonical source inputs. The source-contract flag
`prediction_outputs_in_source=false` describes that producer boundary; it does
not forbid registered model-output roles in the runtime bundle.

## 6. Project 3 Graph Projection Draft

The JSON Schema is `schemas/project3-graph-projection.schema.json`. Typed models
are exported from `ontology_dashboard.integrations.project3`.

This is a draft provider contract only. No HTTP route or graph writer is added
in Phase 0.

### 6.1 Request

Message discriminator:

```text
contract_version = 1.0
message_type = graph_projection_request
```

Required envelope:

```text
projection_id
idempotency_key
organization_id
project_id
workspace_id
dataset_id
dataset_version_id
bundle_checksum_sha256
mapping_version
nodes[]
relationships[]
requested_at
```

Recommended idempotency key:

```text
graph-projection:<project_id>:<dataset_version_id>:
<mapping_version>:<bundle_checksum_sha256>
```

Each node contains the full Neo4j projection identity, governed properties,
source reference, and source file checksum. Each relationship contains typed
source and target identities, an uppercase relationship type, governed
properties, source reference, and source checksum.

All node and relationship endpoint scopes must match the request envelope.
Duplicate `(object_type, source_identity)` nodes in one request are invalid.

### 6.2 Response Status

```text
accepted   request validated and durably accepted
processing Project 3 run is active
completed  all accepted nodes and relationships are committed
failed     terminal attempt failure; error required
blocked    projection cannot start until a dependency or contract issue changes;
           error required
```

Project 2 maps `accepted` and `processing` to projection `indexing`, `completed`
to `ready`, and `failed` or `blocked` to `failed` while retaining the provider
error and retryability metadata.

### 6.3 Error Contract

Stable error codes:

```text
validation_failed
project_not_ready
schema_version_unsupported
identity_conflict
graph_unavailable
timeout
internal_error
```

Error payload:

```text
code
message
retryable
retry_after_seconds | null
details
```

Suggested retry semantics:

| Code | Default retryable |
|---|---:|
| `validation_failed` | false |
| `schema_version_unsupported` | false |
| `identity_conflict` | false |
| `project_not_ready` | true after readiness changes |
| `graph_unavailable` | true |
| `timeout` | true |
| `internal_error` | true with bounded retries |

Project 2 must not reset, rewrite, or silently replace a failed Dataset Version.
It records the attempt and last error in projection state and keeps relational
screens available in degraded mode.

## 7. Phase 1 Implementation Obligations

The next phase must implement a
`PredictiveMaintenanceCanonicalV2Adapter` that:

1. loads or generates Manifest v2 from the package metadata;
2. requires the nine predictive-maintenance runtime roles;
3. validates file existence, size, checksum, header/schema version, join keys,
   referenced assets, and time ranges;
4. verifies the bundle checksum before creating an ingestion run;
5. stores the validation report as an ingestion artifact;
6. quarantines or fails missing roles, checksum mismatch, invalid relations,
   and invalid asset references;
7. treats an identical bundle checksum as idempotent Dataset Version
   registration;
8. keeps evaluation-truth paths inaccessible to runtime readers.
