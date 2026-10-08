from datetime import timedelta

import pytest
from django.utils import timezone

from apps.prices.freshness import Freshness, age_hours, freshness

NOW = timezone.now()
TTL = 48


def state(hours_ago, valid_until=None, ttl=TTL):
    return freshness(
        collected_at=NOW - timedelta(hours=hours_ago),
        valid_until=valid_until,
        ttl_hours=ttl,
        now=NOW,
    )


@pytest.mark.parametrize(
    ("hours_ago", "expected"),
    [
        (0, Freshness.CURRENT),
        (48, Freshness.CURRENT),
        (48.01, Freshness.STALE),
        (96, Freshness.STALE),
        (96.01, Freshness.EXPIRED),
        (1000, Freshness.EXPIRED),
    ],
)
def test_ttl_boundaries(hours_ago, expected):
    assert state(hours_ago) == expected


def test_explicit_validity_overrides_ttl():
    future = NOW + timedelta(days=3)
    assert state(500, valid_until=future) == Freshness.CURRENT  # flyer valid until next week
    assert state(1, valid_until=NOW - timedelta(seconds=1)) == Freshness.EXPIRED


def test_ttl_differs_by_category():
    assert state(40, ttl=24) == Freshness.STALE  # produce: 40 h old is already stale
    assert state(40, ttl=240) == Freshness.CURRENT  # pantry staple: still current
    assert state(60, ttl=24) == Freshness.EXPIRED  # beyond twice the produce TTL


def test_age_is_never_negative():
    assert age_hours(NOW + timedelta(hours=1), NOW) == 0.0
