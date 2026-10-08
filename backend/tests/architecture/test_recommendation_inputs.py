"""The recommendation engine may only see an explicit, reviewed set of facts.

Adding a field to these types changes what can influence a recommendation. That must be a
deliberate decision: this test fails until the new field is added HERE, in review, with the
question answered: "is it a fact about the price, the product, the distance or the data
quality, and never about what a merchant pays?"
"""

from dataclasses import fields

from apps.recommendations import config, types

ALLOWED = {
    "BasketItem": {"key", "quantity", "label"},
    "PriceQuote": {
        "unit_price",
        "low_price",
        "condition",
        "source",
        "age_hours",
        "freshness",
        "confidence",
        "conflict",
    },
    "PromoOffer": {"promotion_id", "title", "rule", "confirmed"},
    "StoreCandidate": {"store_id", "name", "distance_m", "quotes", "promos"},
    "PlanParams": {
        "mode",
        "cost_per_km",
        "detour_factor",
        "max_stores",
        "context",
        "store_distances_m",
    },
}


def test_engine_input_types_expose_exactly_the_reviewed_fields():
    for name, expected in ALLOWED.items():
        actual = {f.name for f in fields(getattr(types, name))}
        assert actual == expected, f"{name} changed: {sorted(actual ^ expected)}"


def test_scoring_components_are_exactly_the_documented_five():
    assert set(config.COMPONENTS) == {"cost", "distance", "coverage", "promotions", "confidence"}


def test_every_mode_weights_exactly_the_documented_components():
    for mode in config.MODES:
        assert set(config.weights_for(mode)) == set(config.COMPONENTS)


def test_settings_cannot_smuggle_in_a_new_component(settings):
    """An override that adds a weight for something else is ignored by scoring, never summed."""
    settings.RECOMMENDATION = {
        "weights": {
            **config.DEFAULTS["weights"],
            config.ECONOMIZAR_MAIS: {
                **config.DEFAULTS["weights"][config.ECONOMIZAR_MAIS],
                "sponsored_boost": 5.0,
            },
        }
    }
    from datetime import datetime
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from apps.promotions.engine import PurchaseContext
    from apps.recommendations.engine import recommend
    from apps.recommendations.types import BasketItem, PlanParams, PriceQuote, StoreCandidate

    def store(sid, price):
        quote = PriceQuote(
            Decimal(price), Decimal(price), "NORMAL", "MERCHANT", 1.0, "CURRENT", 0.7
        )
        return StoreCandidate(sid, sid, 1000, {"x": quote})

    params = PlanParams(
        mode=config.ECONOMIZAR_MAIS,
        cost_per_km=Decimal("0"),
        detour_factor=Decimal("1.3"),
        max_stores=1,
        context=PurchaseContext(at=datetime(2026, 10, 7, 12, tzinfo=ZoneInfo("America/Fortaleza"))),
    )
    result = recommend(
        [BasketItem("x", Decimal(1))], [store("A", "10.00"), store("B", "11.00")], params
    )
    assert all(0 <= plan.score <= 1.0000001 for plan in result.plans)
    assert result.plans[0].store_ids == ("A",)
