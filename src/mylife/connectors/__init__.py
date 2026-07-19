"""Connectors.

The ingestion framework (T3.4): a connector contract, an idempotent runner and a
registry. Concrete connectors (T3.5, T4.x) implement the contract and register
themselves.
"""

from mylife.connectors.base import (
    Connector,
    ConnectorRunner,
    FetchContext,
    ProvenanceMismatchError,
    RawPayload,
    SyncResult,
)
from mylife.connectors.calendar_csv import CALENDAR_SOURCE, CalendarCsvConnector
from mylife.connectors.registry import ConnectorRegistry, UnknownConnectorError, registry

__all__ = [
    "CALENDAR_SOURCE",
    "CalendarCsvConnector",
    "Connector",
    "ConnectorRegistry",
    "ConnectorRunner",
    "FetchContext",
    "ProvenanceMismatchError",
    "RawPayload",
    "SyncResult",
    "UnknownConnectorError",
    "registry",
]
