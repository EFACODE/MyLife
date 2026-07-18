"""Shared FastAPI dependencies.

Holds app-level singletons injected into routes. The in-process event bus is a
process-wide singleton in the modular monolith; subscribers register on it as
projections are added (T3.3 onward).
"""

from mylife.core.events import InProcessEventBus

_event_bus = InProcessEventBus()


def get_event_bus() -> InProcessEventBus:
    """Return the shared in-process event bus."""
    return _event_bus
