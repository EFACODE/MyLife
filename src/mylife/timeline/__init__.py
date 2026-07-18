"""Timeline bounded context.

The read/query side of the timeline over the event kernel (`mylife.core.events`).
Phase 1 starts with the query API (T3.1); capture, projections and the briefing
follow.
"""

from mylife.timeline.query import (
    TimelineEvent,
    TimelinePage,
    TimelineQueryFilter,
    TimelineQueryService,
)

__all__ = [
    "TimelineEvent",
    "TimelinePage",
    "TimelineQueryFilter",
    "TimelineQueryService",
]
