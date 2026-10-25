"""Optional provider contracts; no network providers are enabled by default."""

from __future__ import annotations

from typing import Protocol

from silknet.core.exceptions import IntegrationError


class IntegrationProvider(Protocol):
    name: str

    def search(self, query: str) -> list[dict[str, str]]: ...


class IntegrationRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, IntegrationProvider] = {}

    def register(self, provider: IntegrationProvider) -> None:
        name = provider.name.strip()
        if not name:
            raise ValueError("An integration must have a name.")
        self._providers[name.casefold()] = provider

    def names(self) -> tuple[str, ...]:
        return tuple(
            sorted((provider.name for provider in self._providers.values()), key=str.casefold)
        )

    def search(self, provider_name: str, query: str) -> list[dict[str, str]]:
        provider = self._providers.get(provider_name.casefold())
        if provider is None:
            raise LookupError(f"Integration '{provider_name}' is not configured.")
        try:
            return provider.search(query)
        except Exception as exc:
            raise IntegrationError(f"Integration '{provider.name}' failed: {exc}") from exc
