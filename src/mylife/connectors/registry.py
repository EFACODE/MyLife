"""Connector registry.

Maps a ``source`` name to its connector so a sync can be started by name (e.g.
from a worker task). A default module-level registry is provided; connectors
register themselves as they are added (T3.5 onward).
"""

from mylife.connectors.base import Connector


class UnknownConnectorError(Exception):
    """Raised when no connector is registered for a source."""

    def __init__(self, source: str) -> None:
        super().__init__(f"no connector registered for source {source!r}")
        self.source = source


class ConnectorRegistry:
    """A name → connector registry."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        """Register ``connector`` under its ``source``."""
        self._connectors[connector.source] = connector

    def get(self, source: str) -> Connector:
        """Return the connector for ``source`` or raise ``UnknownConnectorError``."""
        try:
            return self._connectors[source]
        except KeyError:
            raise UnknownConnectorError(source) from None

    def all(self) -> list[Connector]:
        """Return all registered connectors."""
        return list(self._connectors.values())


registry = ConnectorRegistry()
