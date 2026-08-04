"""Dataset and Prediction Result adapter layer."""

from .bundle_models import (
    BundleFileSchemaMetadata,
    BundleGenerationMetadata,
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
from .file_adapter import FileAdapter, IngestionResult
from .models import DatasetManifest, PredictionResult
from .registry import AdapterRegistry, default_adapter_registry

__all__ = [
    "AdapterRegistry",
    "BundleFileSchemaMetadata",
    "BundleGenerationMetadata",
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
    "PredictiveMaintenanceSourceContract",
    "canonical_bundle_checksum_payload",
    "compute_bundle_checksum",
    "default_adapter_registry",
]
