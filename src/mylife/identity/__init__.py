"""Identity bounded context.

Users, households and the ``UserRegistered`` event — the upstream context every
other domain references by ``user_id``. Authentication (T2.2), consent (T2.3),
audit (T2.4) and data-subject rights (T2.5) build on this.
"""

from mylife.identity.credential_vault import CredentialVault, ThirdPartyCredentialRow
from mylife.identity.groups import (
    FINANCE_DOMAIN,
    GroupConflictError,
    GroupService,
    LastAdminError,
    UnknownGroupError,
    UnknownUserError,
)
from mylife.identity.models import (
    ADMIN_ROLE,
    MEMBER_ROLE,
    GroupDetail,
    GroupJoined,
    GroupLeft,
    GroupMember,
    Household,
    Role,
    RoleChanged,
    User,
    UserRegistered,
    UserRegisteredPayload,
    UserUpdated,
    UserUpdatedPayload,
)
from mylife.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidEmailError,
    UnknownHouseholdError,
)

__all__ = [
    "ADMIN_ROLE",
    "FINANCE_DOMAIN",
    "MEMBER_ROLE",
    "CredentialVault",
    "DuplicateUserError",
    "GroupConflictError",
    "GroupDetail",
    "GroupJoined",
    "GroupLeft",
    "GroupMember",
    "GroupService",
    "Household",
    "IdentityService",
    "InvalidEmailError",
    "LastAdminError",
    "Role",
    "RoleChanged",
    "ThirdPartyCredentialRow",
    "UnknownGroupError",
    "UnknownHouseholdError",
    "UnknownUserError",
    "User",
    "UserRegistered",
    "UserRegisteredPayload",
    "UserUpdated",
    "UserUpdatedPayload",
]
