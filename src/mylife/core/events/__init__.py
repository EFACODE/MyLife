"""Event kernel.

The canonical Life Event envelope (T1.1) shared by every bounded context, and
the reference event that demonstrates the contract. Persistence (T1.2),
publishing (T1.3), provenance (T1.4) and corrections (T1.5) build on these.
"""

from mylife.core.events.envelope import LifeEvent
from mylife.core.events.life_event import LifeEventRecorded, LifeEventRecordedPayload

__all__ = [
    "LifeEvent",
    "LifeEventRecorded",
    "LifeEventRecordedPayload",
]
