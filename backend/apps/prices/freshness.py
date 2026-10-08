"""Price status. A price is never silently presented as current when it is old."""

from datetime import datetime
from enum import StrEnum


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


def age_hours(collected_at: datetime, now: datetime) -> float:
    return max((now - collected_at).total_seconds() / 3600, 0.0)


def freshness(
    *, collected_at: datetime, valid_until: datetime | None, ttl_hours: float, now: datetime
) -> Freshness:
    """With an explicit validity (promotion, flyer) the end date rules; otherwise the category TTL.

    CURRENT: age <= TTL. STALE: up to twice the TTL. EXPIRED: older, or past valid_until.
    """
    if valid_until is not None:
        return Freshness.EXPIRED if now > valid_until else Freshness.CURRENT
    age = age_hours(collected_at, now)
    if age <= ttl_hours:
        return Freshness.CURRENT
    if age <= ttl_hours * 2:
        return Freshness.STALE
    return Freshness.EXPIRED
