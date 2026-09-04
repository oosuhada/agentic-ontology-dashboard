"""Public context-provider port for the manufacturing Operations.

HTTP/fallback provider implementations live in ``app.infra``.  The Operations only
knows how to ask the composition root for a provider appropriate to a fixture.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.diagnosis.ports import ContextProvider


class ContextProviderFactory(Protocol):
    def __call__(self, fixture: dict[str, Any]) -> ContextProvider: ...


__all__ = ["ContextProviderFactory"]
