"""NEXUS core primitives: configuration, environment state, errors, identity, time.

Design rules enforced here (NEXUS Living Master Specification):
- Fail closed: unknown/missing state resolves to the most restrictive value.
- Live trading is disabled unless every independent gate is satisfied (Section 2, 34).
- No secrets in code or logs; configuration carries references, never values.
"""

from nexus.core.config import Settings, get_settings
from nexus.core.environment import EnvironmentState, is_pre_live
from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import new_id
from nexus.core.time import utc_now

__all__ = [
    "EnvironmentState",
    "NexusError",
    "RejectReason",
    "Settings",
    "get_settings",
    "is_pre_live",
    "new_id",
    "utc_now",
]
