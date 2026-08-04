"""Dataset and Prediction Result adapter layer."""

from .bundle_models import (
    BundleFileSchemaMetadata,
    BundleGenerationMetadata,
    BundleRoleValidationSummary,
    BundleValidationIssue,
    BundleValidationResult,
    DatasetBundleFile,
    DatasetBundleManifestV2,
    DatasetSourceReference,
    DatasetVersionIdentity,
    Neo4jProjectionIdentity,
    PostgreSQLObjectIdentity,
    PredictiveMaintenanceSourceContract,
    canonical_bundle_checksum_payload,
    compute_bundle_checksum,
)
from .bundle_file_adapter import BundleFileAdapter
from .file_adapter import FileAdapter, IngestionResult
from .models import DatasetManifest, PredictionResult
from .predictive_maintenance_v2 import PredictiveMaintenanceCanonicalV2Adapter
from .registry import AdapterRegistry, default_adapter_registry

__all__ = [
    "AdapterRegistry",
    "BundleFileSchemaMetadata",
    "BundleFileAdapter",
    "BundleGenerationMetadata",
    "BundleRoleValidationSummary",
    "BundleValidationIssue",
    "BundleValidationResult",
    "DatasetBundleFile",
    "DatasetBundleManifestV2",
    "DatasetManifest",
    "DatasetSourceReference",
    "DatasetVersionIdentity",
    "FileAdapter",
    "IngestionResult",
    "Neo4jProjectionIdentity",
    "PostgreSQLObjectIdentity",
    "PredictionResult",
    "PredictiveMaintenanceCanonicalV2Adapter",
    "PredictiveMaintenanceSourceContract",
    "canonical_bundle_checksum_payload",
    "compute_bundle_checksum",
    "default_adapter_registry",
]
