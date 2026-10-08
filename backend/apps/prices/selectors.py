"""Read side: turns stored observations into what the consumer should see.

No ranking or "best price" decision lives here (that is M3). This module only answers
"what was seen, where, when, from whom, how reliable, and does anything disagree".
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Count, QuerySet

from apps.core import clock
from apps.products.models import ProductVariant
from apps.products.units import UnitPrice, unit_price

from .confidence import Confidence, ConfidenceInput, compute_confidence
from .freshness import Freshness, age_hours, freshness
from .models import PriceConfirmation, PriceEvidence, PriceObservation, PriceSource

CONFLICT = "CONFLICTING"
VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"

DEFAULT_TTL_HOURS = 168
CONFLICT_TOLERANCE = Decimal("0.01")  # prices closer than 1% are not a conflict
MIN_VERIFYING_CONFIRMATIONS = 2


def ttl_hours_for(variant: ProductVariant) -> int:
    category = variant.product.category
    default = getattr(settings, "PRICE_DEFAULT_TTL_HOURS", DEFAULT_TTL_HOURS)
    return category.price_ttl_hours if category is not None else default


@dataclass(frozen=True)
class PriceView:
    observation: PriceObservation
    status: str  # CURRENT | STALE | EXPIRED | CONFLICTING
    freshness: str
    verification: str  # VERIFIED | UNVERIFIED
    confidence: Confidence
    unit_price: UnitPrice
    age_hours: float
    confirmations: int
    contradictions: int
    has_evidence: bool


def _confirmation_counts(ids: Iterable[Any]) -> dict[Any, dict[bool, int]]:
    rows = (
        PriceConfirmation.objects.filter(observation_id__in=list(ids))
        .values("observation_id", "agrees")
        .annotate(total=Count("id"))
    )
    counts: dict[Any, dict[bool, int]] = defaultdict(lambda: {True: 0, False: 0})
    for row in rows:
        counts[row["observation_id"]][row["agrees"]] = row["total"]
    return counts


def _build_views(
    observations: list[PriceObservation], variant: ProductVariant, now: datetime
) -> list[PriceView]:
    ids = [o.pk for o in observations]
    counts = _confirmation_counts(ids)
    with_evidence = set(
        PriceEvidence.objects.filter(observation_id__in=ids).values_list(
            "observation_id", flat=True
        )
    )
    ttl = ttl_hours_for(variant)
    views = []
    for obs in observations:
        agree, disagree = counts[obs.pk][True], counts[obs.pk][False]
        merchant = obs.store.merchant
        merchant_verified = bool(
            obs.source == PriceSource.MERCHANT and merchant is not None and merchant.is_verified
        )
        age = age_hours(obs.collected_at, now)
        state = freshness(
            collected_at=obs.collected_at, valid_until=obs.valid_until, ttl_hours=ttl, now=now
        )
        confidence = compute_confidence(
            ConfidenceInput(
                source=obs.source,
                age_hours=age,
                ttl_hours=ttl,
                has_evidence=obs.pk in with_evidence,
                confirmations=agree,
                contradictions=disagree,
                merchant_verified=merchant_verified,
                location_verified=obs.location_verified,
            )
        )
        verified = merchant_verified or (agree >= MIN_VERIFYING_CONFIRMATIONS and disagree == 0)
        views.append(
            PriceView(
                observation=obs,
                status=state.value,
                freshness=state.value,
                verification=VERIFIED if verified else UNVERIFIED,
                confidence=confidence,
                unit_price=unit_price(obs.price, variant.base_quantity, variant.base_unit),
                age_hours=age,
                confirmations=agree,
                contradictions=disagree,
                has_evidence=obs.pk in with_evidence,
            )
        )
    return _mark_conflicts(views)


def _mark_conflicts(views: list[PriceView]) -> list[PriceView]:
    """If live observations for the same store and condition disagree, show all of them as such."""
    groups: dict[tuple[Any, str], list[int]] = defaultdict(list)
    for index, view in enumerate(views):
        if view.freshness != Freshness.EXPIRED:
            groups[(view.observation.store_id, view.observation.payment_condition)].append(index)
    result = list(views)
    for indexes in groups.values():
        prices = [views[i].observation.price for i in indexes]
        if len(indexes) > 1 and (max(prices) - min(prices)) / min(prices) > CONFLICT_TOLERANCE:
            for i in indexes:
                result[i] = PriceView(**{**views[i].__dict__, "status": CONFLICT})
    return result


def has_conflict(views: list[PriceView]) -> bool:
    return any(v.status == CONFLICT for v in views)


def current_prices(
    *,
    variant: ProductVariant,
    store_ids: Iterable[Any],
    now: datetime | None = None,
) -> dict[Any, list[PriceView]]:
    """Latest observation per (store, payment condition, source), grouped by store.

    Old prices are included and labelled STALE/EXPIRED rather than hidden, up to a listing
    horizon (PRICE_MAX_LISTED_AGE_DAYS) after which they are only reachable via history.
    """
    now = now or clock.now()
    horizon = now - timedelta(days=getattr(settings, "PRICE_MAX_LISTED_AGE_DAYS", 90))
    observations = list(
        PriceObservation.objects.filter(
            product_variant=variant, store_id__in=list(store_ids), collected_at__gte=horizon
        )
        .select_related("store__merchant")
        .order_by("store_id", "payment_condition", "source", "-collected_at", "-created_at")
        .distinct("store_id", "payment_condition", "source")
    )
    grouped: dict[Any, list[PriceView]] = defaultdict(list)
    for view in _build_views(observations, variant, now):
        grouped[view.observation.store_id].append(view)
    return grouped


def price_history(
    *,
    variant: ProductVariant,
    store_id: Any,
    payment_condition: str | None = None,
    limit: int = 200,
) -> QuerySet[PriceObservation]:
    queryset = PriceObservation.objects.filter(product_variant=variant, store_id=store_id)
    if payment_condition:
        queryset = queryset.filter(payment_condition=payment_condition)
    return queryset.select_related("supersedes").order_by("-collected_at", "-created_at")[:limit]
