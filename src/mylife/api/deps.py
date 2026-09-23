"""Shared FastAPI dependencies.

Holds app-level singletons injected into routes. The in-process event bus is a
process-wide singleton in the modular monolith; subscribers register on it as
projections are added (T3.3 onward).
"""

from mylife.core.config import get_settings
from mylife.core.events import InProcessEventBus
from mylife.finance.openfinance import PierreFinanceClient
from mylife.knowledge.blob_store import BlobStore, FilesystemBlobStore

_event_bus = InProcessEventBus()
_blob_store: BlobStore = FilesystemBlobStore(get_settings().blob_store_path)
_pierre_client = PierreFinanceClient(base_url=get_settings().pierre_finance_base_url)


def get_event_bus() -> InProcessEventBus:
    """Return the shared in-process event bus."""
    return _event_bus


def get_blob_store() -> BlobStore:
    """Return the shared document blob store."""
    return _blob_store


def get_pierre_client() -> PierreFinanceClient:
    """Return the shared Pierre Finance API client (T4.9).

    Overridden in tests via ``app.dependency_overrides`` so no test hits the
    real network.
    """
    return _pierre_client
