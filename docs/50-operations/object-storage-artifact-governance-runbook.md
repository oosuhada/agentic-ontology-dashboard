# Object Storage and Artifact Governance Runbook

## Storage contract

PostgreSQL owns artifact identity, organization/Project/workspace scope, media type, size,
SHA-256, provenance, retention, legal hold and access audit. Object storage owns immutable bytes.
The application never treats an object key, local path or bucket URL as authorization.

Object keys are deterministic and tenant scoped:

```text
organizations/{org}/projects/{project}/workspaces/{workspace}/artifacts/
{resource-type}/{resource-id}/versions/{version}/{checksum-prefix}/{checksum}.{extension}
```

Production must configure a durable `s3`, `gcs` or `azure` provider, a bucket/container, a secret
reference, server-side encryption and object versioning. The `local` backend is a test/demo emulator
and reports `degraded` or `blocked`, never production-ready.

## Integrity and download

1. Upload computes SHA-256 before registration and compares the backend result.
2. Read, verification, reconciliation and restore recompute the digest.
3. A mismatch changes catalog state to `checksum_mismatch`; no download is returned.
4. Download requires current session permission and a user-bound token that expires in 30–900
   seconds. Sign and download are separate audit events.
5. Artifact APIs return opaque identity and object metadata, not filesystem paths or credentials.

## Retention and legal hold

Retention classes are `ephemeral`, `standard`, `regulated`, `backup` and `legal_hold`.
Always run a dry-run preview first. `legal_hold` blocks lifecycle deletion even after
`retain_until`. Deletion removes bytes, marks the catalog row `deleted`, and preserves audit and
provenance.

## Reconciliation and restore

Run reconciliation per Project to compare catalog and object storage:

- **missing**: catalog row exists, object does not
- **checksum_mismatch**: size or SHA-256 differs
- **orphan**: object exists without a catalog row
- **verified**: catalog and object agree

Apply mode changes catalog state but does not silently delete orphan objects. Investigate an orphan
before quarantine/deletion. Restore accepts only backup bytes whose checksum matches the existing
artifact identity, preserving lineage and preventing replacement with unrelated content.

## Provider recovery

During an object-storage outage, metadata/search may remain available but upload, verification and
download are blocked. Do not fall back to node-local storage in production. Restore provider access,
verify bucket versioning/encryption, run reconciliation, restore missing objects from backup, and
record the incident and reconciliation run ID.
