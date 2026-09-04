"""Canonical Dataset Catalog and cross-store projection contracts."""

from .materialization import (
    AnalysisDatasetMaterializer,
    AnalysisMaterializationRequest,
    AnalysisMaterializationResult,
)
from .dataset_domain import DatasetPrincipal, ObservationDatasetQuery
from .dataset_exception import DatasetAccessError
from .dataset_repository import DatasetRepositoryPort
from .dataset_schema import (
    CanonicalObjectEnvelope,
    DatasetCreateRequest,
    DatasetDetail,
    DatasetFileCreate,
    DatasetFileRecord,
    DatasetPage,
    DatasetRecord,
    DatasetVersionCreateRequest,
    DatasetVersionRecord,
    MaterializationCreateRequest,
    OntologyMappingCreateRequest,
    ProjectionRecord,
    ProjectionStatus,
    StoreKind,
)
from .dataset_service import DatasetCatalogService
from .source import DatasetMaterializationSource

__all__ = [
    "AnalysisDatasetMaterializer",
    "AnalysisMaterializationRequest",
    "AnalysisMaterializationResult",
    "CanonicalObjectEnvelope",
    "DatasetAccessError",
    "DatasetCatalogService",
    "DatasetCreateRequest",
    "DatasetDetail",
    "DatasetFileCreate",
    "DatasetFileRecord",
    "DatasetMaterializationSource",
    "DatasetPage",
    "DatasetPrincipal",
    "DatasetRecord",
    "DatasetRepositoryPort",
    "DatasetVersionCreateRequest",
    "DatasetVersionRecord",
    "MaterializationCreateRequest",
    "OntologyMappingCreateRequest",
    "ObservationDatasetQuery",
    "ProjectionRecord",
    "ProjectionStatus",
    "StoreKind",
]
