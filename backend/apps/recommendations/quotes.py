"""Turns the raw price views of one product at one store into a single honest quote.

The engine needs ONE price per item and store, but the data may hold several (different
sources, different payment conditions, conflicts). The rules below decide which one is used
without hiding the disagreement:

* expired prices are never used; stale ones are, and are flagged;
* only conditions that apply to this shopper count (normal, their payment method, loyalty,
  coupon), so a Pix price is not offered to someone paying by card;
* when live sources disagree for the same condition, the quote uses the HIGHER price (we do
  not promise a saving we cannot back) and keeps the lower one for the "optimistic" figure;
* across applicable conditions the cheapest valid one wins.
"""

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from apps.prices.freshness import Freshness
from apps.prices.selectors import CONFLICT, PriceView
from apps.promotions.engine import PurchaseContext

from . import config
from .types import PriceQuote


def applicable_conditions(ctx: PurchaseContext) -> set[str]:
    conditions = {"NORMAL", ctx.payment_condition}
    if ctx.has_loyalty:
        conditions.add("LOYALTY")
    if ctx.coupon_codes:
        conditions.add("COUPON")
    return conditions


def build_quote(views: Sequence[PriceView], ctx: PurchaseContext) -> PriceQuote | None:
    allowed = applicable_conditions(ctx)
    live = [
        v
        for v in views
        if v.freshness != Freshness.EXPIRED and v.observation.payment_condition in allowed
    ]
    if not live:
        return None

    factor = config.get()["conflict_confidence_factor"]
    by_condition: dict[str, list[PriceView]] = defaultdict(list)
    for view in live:
        by_condition[view.observation.payment_condition].append(view)

    quotes = []
    for condition, group in by_condition.items():
        conflict = any(v.status == CONFLICT for v in group)
        prices = [v.observation.price for v in group]
        # The most confident view speaks for the group; ties go to the higher (safer) price.
        speaker = max(group, key=lambda v: (v.confidence.score, v.observation.price))
        representative: Decimal = max(prices) if conflict else speaker.observation.price
        confidence = float(speaker.confidence.score) * (factor if conflict else 1.0)
        quotes.append(
            PriceQuote(
                unit_price=representative,
                low_price=min(prices),
                condition=condition,
                source="MIXED" if conflict else speaker.observation.source,
                age_hours=speaker.age_hours,
                freshness=speaker.freshness,
                confidence=confidence,
                conflict=conflict,
            )
        )
    return min(quotes, key=lambda q: (q.unit_price, -q.confidence))
