from __future__ import annotations

from .protocol import BundleDatasetAdapter, DatasetAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DatasetAdapter] = {}
        self._bundle_adapters: dict[str, BundleDatasetAdapter] = {}

    def register(self, adapter: DatasetAdapter) -> None:
        if not adapter.code:
            raise ValueError("adapter code is required")
        if adapter.code in self._adapters or adapter.code in self._bundle_adapters:
            raise ValueError(f"adapter already registered: {adapter.code}")
        self._adapters[adapter.code] = adapter

    def register_bundle(self, adapter: BundleDatasetAdapter) -> None:
        if not adapter.code:
            raise ValueError("adapter code is required")
        if adapter.code in self._adapters or adapter.code in self._bundle_adapters:
            raise ValueError(f"adapter already registered: {adapter.code}")
        self._bundle_adapters[adapter.code] = adapter

    def get(self, code: str) -> DatasetAdapter:
        try:
            return self._adapters[code]
        except KeyError as exc:
            raise ValueError(f"unknown dataset adapter: {code}") from exc

    def get_bundle(self, code: str) -> BundleDatasetAdapter:
        try:
            return self._bundle_adapters[code]
        except KeyError as exc:
            raise ValueError(f"unknown bundle dataset adapter: {code}") from exc

    def list(self) -> list[dict[str, str]]:
        adapters = [*self._adapters.values(), *self._bundle_adapters.values()]
        return [
            {"code": adapter.code, "display_name": adapter.display_name}
            for adapter in sorted(adapters, key=lambda item: item.code)
        ]


def default_adapter_registry() -> AdapterRegistry:
    from .azure_fleet import AzureFleetMaintenanceAdapter
    from .governed_tabular import GovernedTabularAdapter
    from .metropt import MetroPTCompressorAdapter
    from .predictive_maintenance_v2 import (
        PredictiveMaintenanceCanonicalV2Adapter,
        PredictiveMaintenanceCanonicalV3SourceAdapter,
    )

    registry = AdapterRegistry()
    registry.register(GovernedTabularAdapter())
    registry.register(AzureFleetMaintenanceAdapter())
    registry.register(MetroPTCompressorAdapter())
    registry.register_bundle(PredictiveMaintenanceCanonicalV2Adapter())
    registry.register_bundle(PredictiveMaintenanceCanonicalV3SourceAdapter())
    return registry
