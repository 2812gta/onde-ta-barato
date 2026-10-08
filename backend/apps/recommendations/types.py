"""Data the recommendation engine is allowed to see.

This is a WHITELIST. Anything not declared here cannot influence a recommendation. In
particular there is no field for plans, payments, sponsorship or advertising, and
tests/architecture/ fails if one is ever added.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from apps.promotions.engine import PurchaseContext


@dataclass(frozen=True)
class BasketItem:
    key: str  # opaque id (the variant id)
    quantity: Decimal
    label: str = ""


@dataclass(frozen=True)
class PriceQuote:
    """The price we would assume for one item at one store, with its honesty flags."""

    unit_price: Decimal  # representative price; the HIGHER one when sources conflict
    low_price: Decimal  # lowest live price seen for the same condition
    condition: str  # payment condition the price belongs to
    source: str
    age_hours: float
    freshness: str  # CURRENT | STALE (expired prices never become quotes)
    confidence: float  # 0..1, already reduced when sources conflict
    conflict: bool = False


@dataclass(frozen=True)
class PromoOffer:
    promotion_id: str
    title: str
    rule: Mapping[str, object]
    confirmed: bool  # only promotions from verified merchants count toward totals


@dataclass(frozen=True)
class StoreCandidate:
    store_id: str
    name: str
    distance_m: float  # from the shopper, straight line (computed by PostGIS)
    quotes: Mapping[str, PriceQuote]  # item key -> quote
    promos: Mapping[str, tuple[PromoOffer, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanParams:
    mode: str
    cost_per_km: Decimal
    detour_factor: Decimal
    max_stores: int
    context: PurchaseContext
    # distance in meters between two candidate stores, keyed by frozenset({id_a, id_b})
    store_distances_m: Mapping[frozenset[str], float] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanLine:
    item_key: str
    label: str
    store_id: str
    quantity: Decimal
    unit_price: Decimal
    gross: Decimal
    net: Decimal
    savings: Decimal
    cashback: Decimal
    promo_title: str | None
    unconfirmed_potential: Decimal  # benefit of an unconfirmed promotion we did NOT count
    conflict: bool
    low_net: Decimal  # line cost if the lowest conflicting price were the true one
    confidence: float
    age_hours: float
    freshness: str
    condition: str


@dataclass(frozen=True)
class Plan:
    store_ids: tuple[str, ...]
    lines: tuple[PlanLine, ...]
    missing: tuple[str, ...]  # item keys with no usable price in these stores
    items_total: Decimal
    savings_total: Decimal
    cashback_total: Decimal
    transport_cost: Decimal
    effective_total: Decimal  # items - cashback + transport
    optimistic_total: Decimal  # same, if conflicting prices resolved to their lowest value
    unconfirmed_potential_total: Decimal
    coverage: float
    complete: bool
    route_km: float
    avg_confidence: float
    fresh_ratio: float
    conflicts: int
    promos_applied: int
    gross_total: Decimal
    components: Mapping[str, float] = field(default_factory=dict)
    score: float = 0.0


@dataclass(frozen=True)
class Reason:
    code: str
    text: str
    value: float | str | None = None


@dataclass(frozen=True)
class Recommendation:
    verdict: str  # RECOMMENDED | TIE | INSUFFICIENT_DATA
    message: str
    plans: tuple[Plan, ...]  # ranked, best first (may be empty)
    reasons: tuple[Reason, ...]
    warnings: tuple[str, ...]
    assumptions: Mapping[str, object] = field(default_factory=dict)
