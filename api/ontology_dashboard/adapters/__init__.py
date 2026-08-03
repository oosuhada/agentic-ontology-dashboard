"""Dataset and Prediction Result adapter layer."""

from .file_adapter import FileAdapter, IngestionResult
from .models import DatasetManifest, PredictionResult
from .registry import AdapterRegistry, default_adapter_registry

__all__ = [
    "AdapterRegistry",
    "DatasetManifest",
    "FileAdapter",
    "IngestionResult",
    "PredictionResult",
    "default_adapter_registry",
]
