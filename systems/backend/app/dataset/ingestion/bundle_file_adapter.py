"""Generic access, checksum, and atomic validation orchestration for bundles."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from ..bundle_contract import (
    BundleRoleValidationSummary,
    BundleValidationIssue,
    BundleValidationResult,
    DatasetBundleManifestV2,
)
from .file_adapter import FileAccessPolicy
from .protocol import ResolvedBundleFile
from .registry import AdapterRegistry, default_adapter_registry


def bundle_source_path(uri: str) -> Path:
    if len(uri) >= 3 and uri[0].isalpha() and uri[1] == ":" and uri[2] in {"/", "\\"}:
        return Path(uri)
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file"}:
        value = unquote(parsed.path) if parsed.scheme == "file" else uri
        if parsed.scheme == "file" and len(value) >= 3 and value[0] == "/" and value[1].isalpha() and value[2] == ":":
            value = value[1:]
        return Path(value)
    raise ValueError("Bundle File Adapter only supports local paths and file:// URIs")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BundleFileAdapter:
    """Validate a multi-file bundle without retaining source rows in memory."""

    def __init__(
        self,
        *,
        allowed_roots: Iterable[str | Path],
        registry: AdapterRegistry | None = None,
        issue_sample_limit: int = 100,
    ) -> None:
        if issue_sample_limit < 1:
            raise ValueError("issue_sample_limit must be positive")
        self.registry = registry or default_adapter_registry()
        self.policy = FileAccessPolicy(allowed_roots)
        self.issue_sample_limit = issue_sample_limit

    def validate(self, manifest: DatasetBundleManifestV2) -> BundleValidationResult:
        adapter = self.registry.get_bundle(manifest.adapter_code)
        required_roles = (
            adapter.required_roles_for(manifest)
            if hasattr(adapter, "required_roles_for")
            else adapter.required_roles
        )
        allowed_roles = (
            adapter.allowed_roles_for(manifest)
            if hasattr(adapter, "allowed_roles_for")
            else adapter.allowed_roles
        )
        descriptors = {item.role: item for item in manifest.files}
        missing = sorted(required_roles - set(descriptors))
        unexpected = sorted(set(descriptors) - allowed_roles)
        issues: list[BundleValidationIssue] = []
        issue_total = 0
        summaries: dict[str, BundleRoleValidationSummary] = {}
        resolved: dict[str, ResolvedBundleFile] = {}

        def add_issue(issue: BundleValidationIssue) -> None:
            nonlocal issue_total
            issue_total += 1
            if len(issues) < self.issue_sample_limit:
                issues.append(issue)

        for role in missing:
            add_issue(
                BundleValidationIssue(
                    role=role,
                    code="missing_required_role",
                    message="required runtime bundle role is missing",
                )
            )
        for role in unexpected:
            add_issue(
                BundleValidationIssue(
                    role=role,
                    code="unexpected_runtime_role",
                    message="runtime bundle role is not in the adapter allowlist",
                )
            )

        for role, descriptor in sorted(descriptors.items()):
            summary = BundleRoleValidationSummary(
                role=role,
                uri=descriptor.uri,
                format=descriptor.format,
                media_type=descriptor.media_type,
                expected_checksum_sha256=descriptor.checksum_sha256,
                required_fields=list(descriptor.schema_.required_fields),
            )
            summaries[role] = summary
            if role in unexpected:
                summary.status = "failed"
                summary.issue_counts["unexpected_runtime_role"] = 1
                continue
            try:
                path = self.policy.validate(bundle_source_path(descriptor.uri))
            except (OSError, ValueError) as exc:
                summary.status = "failed"
                summary.issue_counts["file_access_failed"] = 1
                add_issue(
                    BundleValidationIssue(
                        role=role,
                        code="file_access_failed",
                        message=str(exc),
                    )
                )
                continue
            actual_checksum = sha256_file(path)
            summary.actual_checksum_sha256 = actual_checksum
            summary.checksum_valid = actual_checksum == descriptor.checksum_sha256
            if path.stat().st_size != descriptor.size_bytes:
                summary.status = "failed"
                summary.issue_counts["size_mismatch"] = 1
                add_issue(
                    BundleValidationIssue(
                        role=role,
                        code="size_mismatch",
                        message=(
                            f"manifest size_bytes={descriptor.size_bytes}, "
                            f"actual={path.stat().st_size}"
                        ),
                    )
                )
            if not summary.checksum_valid:
                summary.status = "failed"
                summary.issue_counts["checksum_mismatch"] = 1
                add_issue(
                    BundleValidationIssue(
                        role=role,
                        code="checksum_mismatch",
                        message="runtime file checksum does not match the bundle manifest",
                    )
                )
            if summary.status != "failed":
                resolved[role] = ResolvedBundleFile(
                    descriptor=descriptor,
                    path=path,
                    actual_checksum_sha256=actual_checksum,
                )

        access_gate_passed = (
            not missing
            and not unexpected
            and set(resolved) == required_roles
            and not issues
        )
        if access_gate_passed:
            content = adapter.validate_files(
                manifest,
                resolved,
                issue_sample_limit=self.issue_sample_limit,
            )
            summaries = {item.role: item for item in content.roles}
            issues = list(content.issues)
            issue_total = sum(sum(item.issue_counts.values()) for item in content.roles)
            truncated = content.issue_sample_truncated
        else:
            truncated = issue_total > len(issues)
            summaries = {
                role: BundleRoleValidationSummary.model_validate(
                    summary.model_dump(mode="python")
                )
                for role, summary in summaries.items()
            }

        return self._build_result(
            manifest,
            roles=sorted(summaries.values(), key=lambda item: item.role),
            issues=issues,
            issue_total=issue_total,
            truncated=truncated,
        )

    @staticmethod
    def _validation_checksum(
        manifest: DatasetBundleManifestV2,
        roles: list[BundleRoleValidationSummary],
        issues: list[BundleValidationIssue],
    ) -> str:
        role_payloads = []
        for role in roles:
            payload = role.model_dump(mode="json", exclude={"uri"})
            role_payloads.append(payload)
        payload = {
            "bundle_checksum_sha256": manifest.bundle_checksum_sha256,
            "adapter_code": manifest.adapter_code,
            "roles": role_payloads,
            "issues": [item.model_dump(mode="json") for item in issues],
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _build_result(
        self,
        manifest: DatasetBundleManifestV2,
        *,
        roles: list[BundleRoleValidationSummary],
        issues: list[BundleValidationIssue],
        issue_total: int,
        truncated: bool,
    ) -> BundleValidationResult:
        source_count = sum(item.source_record_count for item in roles)
        validated_count = sum(item.accepted_record_count for item in roles)
        quarantined_count = sum(item.quarantined_record_count for item in roles)
        failed = bool(issues) or any(item.status != "passed" for item in roles)
        status = "failed" if failed else "completed"
        idempotency_key = (
            f"dataset-bundle:{manifest.adapter_code}:{manifest.bundle_checksum_sha256}"
        )
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key))
        return BundleValidationResult(
            ingestion_run_id=run_id,
            idempotency_key=idempotency_key,
            validation_checksum_sha256=self._validation_checksum(manifest, roles, issues),
            manifest_id=manifest.manifest_id,
            organization_id=manifest.organization_id,
            project_id=manifest.project_id,
            workspace_id=manifest.workspace_id,
            adapter_code=manifest.adapter_code,
            dataset_version=manifest.dataset_version,
            bundle_checksum_sha256=manifest.bundle_checksum_sha256,
            status=status,
            source_record_count=source_count,
            validated_record_count=validated_count,
            accepted_record_count=0 if failed else source_count,
            quarantined_record_count=quarantined_count,
            roles=roles,
            issues=issues,
            issue_sample_truncated=truncated,
            metrics={
                "streaming_validation": True,
                "source_rows_materialized_in_memory": 0,
                "atomic_bundle_acceptance": True,
                "role_count": len(roles),
                "issue_occurrence_count": issue_total,
                "issue_sample_count": len(issues),
                "issue_sample_limit": self.issue_sample_limit,
            },
            validated_at=datetime.now(timezone.utc),
        )


__all__ = ["BundleFileAdapter", "bundle_source_path", "sha256_file"]
