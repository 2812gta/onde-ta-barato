from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core import clock
from apps.prices import services
from apps.prices.models import PriceObservation


def test_clock_is_strictly_increasing_even_on_a_coarse_os_clock():
    values = [clock.now() for _ in range(5000)]
    assert all(a < b for a, b in zip(values, values[1:], strict=False))


def test_clock_never_goes_backwards_when_os_time_repeats(monkeypatch):
    class Frozen:
        @staticmethod
        def now(tz=None):
            from datetime import datetime

            return datetime(2026, 1, 1, tzinfo=tz)

    monkeypatch.setattr(clock, "datetime", Frozen)
    first, second, third = clock.now(), clock.now(), clock.now()
    assert first < second < third
    assert third - first == timedelta(microseconds=2)


@pytest.mark.django_db
def test_rapid_price_changes_keep_a_correct_chain(
    make_user, make_merchant, make_store, make_variant
):
    """Regression: on Windows consecutive writes shared a timestamp and 'previous' was ambiguous."""
    owner = make_user()
    store = make_store(merchant=make_merchant(owner=owner))
    variant = make_variant()
    prices = [Decimal(f"{20 + i}.00") for i in range(25)]
    for price in prices:
        services.publish_merchant_price(store=store, actor=owner, variant=variant, price=price)
    rows = list(PriceObservation.objects.order_by("created_at"))
    assert [r.price for r in rows] == prices
    assert rows[0].supersedes is None
    for previous, current in zip(rows, rows[1:], strict=False):
        assert current.supersedes_id == previous.pk
