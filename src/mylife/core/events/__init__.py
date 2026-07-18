"""Event kernel.

The canonical Life Event envelope (T1.1) shared by every bounded context, the
reference event that demonstrates the contract, and the append-only event store
(T1.2). Publishing (T1.3), provenance (T1.4) and corrections (T1.5) build on
these.
"""

from mylife.core.events.envelope import LifeEvent
from mylife.core.events.life_event import LifeEventRecorded, LifeEventRecordedPayload
from mylife.core.events.store import (
    DuplicateEventError,
    EventRow,
    EventStore,
    StoredEvent,
)

__all__ = [
    "DuplicateEventError",
    "EventRow",
    "EventStore",
    "LifeEvent",
    "LifeEventRecorded",
    "LifeEventRecordedPayload",
    "StoredEvent",
]
