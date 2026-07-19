"""Identity bounded context.

Users, households and the ``UserRegistered`` event — the upstream context every
other domain references by ``user_id``. Authentication (T2.2), consent (T2.3),
audit (T2.4) and data-subject rights (T2.5) build on this.
"""

from mylife.identity.models import (
    Household,
    User,
    UserRegistered,
    UserRegisteredPayload,
)
from mylife.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidEmailError,
    UnknownHouseholdError,
)

__all__ = [
    "DuplicateUserError",
    "Household",
    "IdentityService",
    "InvalidEmailError",
    "UnknownHouseholdError",
    "User",
    "UserRegistered",
    "UserRegisteredPayload",
]
