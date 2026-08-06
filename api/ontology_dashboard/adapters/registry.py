from __future__ import annotations

from .protocol import BundleDatasetAdapter, DatasetAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DatasetAdapter] = {}
        self._bundle_adapters: dict[str, BundleDatasetAdapter] = {}

    def register(self, adapter: DatasetAdapter) -> None:
        if not adapter.code or adapter.code in self._adapters or adapter.code in self._bundle_adapters:
            raise ValueError(f"adapter already registered: {adapter.code}")
        self._adapters[adapter.code] = adapter

    def register_bundle(self, adapter: BundleDatasetAdapter) -> None:
        if not adapter.code or adapter.code in self._adapters or adapter.code in self._bundle_adapters:
            raise ValueError(f"adapter already registered: {adapter.code}")
        self._bundle_adapters[adapter.code] = adapter

    def get(self, code: str) -> DatasetAdapter:
        try:
            return self._adapters[code]
        except KeyError as error:
            raise ValueError(f"unknown dataset adapter: {code}") from error

    def get_bundle(self, code: str) -> BundleDatasetAdapter:
        try:
            return self._bundle_adapters[code]
        except KeyError as error:
            raise ValueError(f"unknown bundle dataset adapter: {code}") from error

    def list(self) -> list[dict[str, str]]:
        items = [*self._adapters.values(), *self._bundle_adapters.values()]
        return [{"code": item.code, "display_name": item.display_name} for item in items]


def default_adapter_registry() -> AdapterRegistry:
    from .predictive_maintenance_v2 import PredictiveMaintenanceCanonicalV2Adapter

    registry = AdapterRegistry()
    registry.register_bundle(PredictiveMaintenanceCanonicalV2Adapter())
    return registry


__all__ = ["AdapterRegistry", "default_adapter_registry"]
