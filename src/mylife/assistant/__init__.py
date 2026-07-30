"""Assistant bounded context.

Evidence-led observations over the timeline. Phase 1 delivers the rule-based
daily briefing (T3.6); AI reasoning and the full evidence contract arrive in T7.
"""

from mylife.assistant.briefing import (
    Briefing,
    BriefingDelivered,
    BriefingDeliveredPayload,
    BriefingLine,
    BriefingService,
)

__all__ = [
    "Briefing",
    "BriefingDelivered",
    "BriefingDeliveredPayload",
    "BriefingLine",
    "BriefingService",
]
