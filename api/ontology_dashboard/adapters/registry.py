from __future__ import annotations

from .protocol import DatasetAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DatasetAdapter] = {}

    def register(self, adapter: DatasetAdapter) -> None:
        if not adapter.code:
            raise ValueError("adapter code is required")
        if adapter.code in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.code}")
        self._adapters[adapter.code] = adapter

    def get(self, code: str) -> DatasetAdapter:
        try:
            return self._adapters[code]
        except KeyError as exc:
            raise ValueError(f"unknown dataset adapter: {code}") from exc

    def list(self) -> list[dict[str, str]]:
        return [
            {"code": adapter.code, "display_name": adapter.display_name}
            for adapter in sorted(self._adapters.values(), key=lambda item: item.code)
        ]


def default_adapter_registry() -> AdapterRegistry:
    from .azure_fleet import AzureFleetMaintenanceAdapter
    from .metropt import MetroPTCompressorAdapter

    registry = AdapterRegistry()
    registry.register(AzureFleetMaintenanceAdapter())
    registry.register(MetroPTCompressorAdapter())
    return registry
