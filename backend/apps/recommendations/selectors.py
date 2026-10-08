"""Loads what the engine needs. Spatial work stays in PostGIS: radius filtering and ordering
come from `stores_within`, and the distance between candidate stores is a single SQL query."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import connection

from apps.prices.selectors import current_prices
from apps.products.models import ProductVariant
from apps.promotions.engine import PurchaseContext
from apps.promotions.selectors import is_confirmed, running_promotions
from apps.stores.models import Store
from apps.stores.selectors import stores_within

from . import config
from .quotes import build_quote
from .types import BasketItem, PromoOffer, StoreCandidate


@dataclass(frozen=True)
class Gathered:
    candidates: list[StoreCandidate]
    store_distances_m: dict[frozenset[str], float]
    stores_in_radius: int


def pairwise_distances_m(store_ids: Sequence[Any]) -> dict[frozenset[str], float]:
    """Geodesic meters between every pair of the given stores, computed by PostGIS."""
    if len(store_ids) < 2:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.id, b.id, ST_Distance(a.location, b.location)
            FROM stores_store a JOIN stores_store b ON a.id < b.id
            WHERE a.id = ANY(%s) AND b.id = ANY(%s)
            """,
            [list(store_ids), list(store_ids)],
        )
        return {frozenset({str(a), str(b)}): float(d) for a, b, d in cursor.fetchall()}


def gather(
    *,
    variants: Sequence[ProductVariant],
    lat: float,
    lon: float,
    radius_km: float,
    ctx: PurchaseContext,
    now: datetime,
) -> Gathered:
    cfg = config.get()
    stores: list[Store] = list(
        stores_within(lat=lat, lon=lon, radius_km=radius_km)[: cfg["max_stores_considered"]]
    )
    store_ids = [s.pk for s in stores]
    prices = {v.pk: current_prices(variant=v, store_ids=store_ids, now=now) for v in variants}
    promos = running_promotions(store_ids=store_ids, variant_ids=[v.pk for v in variants], now=now)

    candidates: list[StoreCandidate] = []
    for store in stores:
        quotes = {}
        offers: dict[str, tuple[PromoOffer, ...]] = {}
        for variant in variants:
            key = str(variant.pk)
            quote = build_quote(prices[variant.pk].get(store.pk, []), ctx)
            if quote is None:
                continue
            quotes[key] = quote
            found = promos.get((store.pk, variant.pk), [])
            if found:
                offers[key] = tuple(
                    PromoOffer(str(p.pk), p.title, p.rule, is_confirmed(p)) for p in found
                )
        if quotes:
            candidates.append(
                StoreCandidate(
                    store_id=str(store.pk),
                    name=store.name,
                    distance_m=float(store.distance.m),  # type: ignore[attr-defined]
                    quotes=quotes,
                    promos=offers,
                )
            )

    shortlist = sorted(candidates, key=lambda c: (-len(c.quotes), c.distance_m, c.store_id))[
        : cfg["pair_candidates"]
    ]
    distances = pairwise_distances_m([c.store_id for c in shortlist])
    return Gathered(candidates, distances, len(stores))


def basket_items(pairs: Sequence[tuple[ProductVariant, Decimal]]) -> list[BasketItem]:
    return [
        BasketItem(
            key=str(variant.pk),
            quantity=quantity,
            label=f"{variant.product.name} {variant.quantity.normalize():f} {variant.unit}",
        )
        for variant, quantity in pairs
    ]
