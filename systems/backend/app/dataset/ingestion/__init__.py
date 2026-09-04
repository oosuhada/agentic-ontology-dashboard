"""Dataset ingestion contracts and canonical adapters."""

from .bundle_file_adapter import BundleFileAdapter
from ..bundle_contract import (
    BundleFileSchemaMetadata,
    BundleGenerationMetadata,
    BundleGovernanceArtifact,
    BundleRoleValidationSummary,
    BundleValidationIssue,
    BundleValidationResult,
    DatasetBundleFile,
    DatasetBundleManifestV2,
    DatasetSourceReference,
    DatasetVersionIdentity,
    Neo4jProjectionIdentity,
    PostgreSQLBundleIngestionResult,
    PostgreSQLObjectIdentity,
    PredictiveMaintenanceSourceContract,
    canonical_bundle_checksum_payload,
    compute_bundle_checksum,
)
from .file_adapter import FileAdapter
from .ingestion_schema import (
    DatasetManifest,
    DatasetSchema,
    DatasetSource,
    IngestionResult,
    QualityRule,
    QuarantinedRecord,
)
from .predictive_maintenance_v2 import (
    PredictiveMaintenanceCanonicalV2Adapter,
    PredictiveMaintenanceCanonicalV3SourceAdapter,
)
from .registry import AdapterRegistry, default_adapter_registry
from .service import DatasetIngestionService

__all__ = [
    "AdapterRegistry",
    "BundleFileAdapter",
    "BundleFileSchemaMetadata",
    "BundleGenerationMetadata",
    "BundleGovernanceArtifact",
    "BundleRoleValidationSummary",
    "BundleValidationIssue",
    "BundleValidationResult",
    "DatasetBundleFile",
    "DatasetBundleManifestV2",
    "DatasetIngestionService",
    "DatasetManifest",
    "DatasetSchema",
    "DatasetSource",
    "DatasetSourceReference",
    "DatasetVersionIdentity",
    "FileAdapter",
    "IngestionResult",
    "Neo4jProjectionIdentity",
    "PostgreSQLBundleIngestionResult",
    "PostgreSQLObjectIdentity",
    "PredictiveMaintenanceCanonicalV2Adapter",
    "PredictiveMaintenanceCanonicalV3SourceAdapter",
    "PredictiveMaintenanceSourceContract",
    "QualityRule",
    "QuarantinedRecord",
    "canonical_bundle_checksum_payload",
    "compute_bundle_checksum",
    "default_adapter_registry",
]
