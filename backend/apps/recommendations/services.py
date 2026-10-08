from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.core import clock
from apps.prices.selectors import current_prices
from apps.products.models import ProductVariant
from apps.products.units import UnitPrice, unit_price
from apps.promotions.engine import PurchaseContext
from apps.stores.models import Store
from apps.stores.selectors import stores_within

from . import config, selectors
from .engine import recommend
from .quotes import applicable_conditions, build_quote
from .types import PlanParams, PriceQuote, Recommendation

LOWEST_LABEL = "Menor preço encontrado na nossa base"


@dataclass(frozen=True)
class BasketResult:
    recommendation: Recommendation
    labels: dict[str, str]
    names: dict[str, str]
    distances_m: dict[str, float]
    stores_in_radius: int
    stores_with_prices: int
    generated_at: datetime


def recommend_basket(
    *,
    pairs: Sequence[tuple[ProductVariant, Decimal]],
    lat: float,
    lon: float,
    radius_km: float,
    mode: str,
    payment_condition: str = "NORMAL",
    has_loyalty: bool = False,
    coupon_codes: frozenset[str] = frozenset(),
    cost_per_km: Decimal | None = None,
    max_stores: int = 2,
    now: datetime | None = None,
) -> BasketResult:
    now = now or clock.now()
    cfg = config.get()
    ctx = PurchaseContext(
        at=now,
        payment_condition=payment_condition,
        has_loyalty=has_loyalty,
        coupon_codes=coupon_codes,
    )
    gathered = selectors.gather(
        variants=[v for v, _ in pairs], lat=lat, lon=lon, radius_km=radius_km, ctx=ctx, now=now
    )
    items = selectors.basket_items(pairs)
    params = PlanParams(
        mode=mode,
        cost_per_km=cfg["cost_per_km"] if cost_per_km is None else cost_per_km,
        detour_factor=cfg["detour_factor"],
        max_stores=max_stores,
        context=ctx,
        store_distances_m=gathered.store_distances_m,
    )
    result = recommend(items, gathered.candidates, params)
    return BasketResult(
        recommendation=result,
        labels={i.key: i.label for i in items},
        names={c.store_id: c.name for c in gathered.candidates},
        distances_m={c.store_id: c.distance_m for c in gathered.candidates},
        stores_in_radius=gathered.stores_in_radius,
        stores_with_prices=len(gathered.candidates),
        generated_at=now,
    )


# --- single product comparison -------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonRow:
    store: Store
    quote: PriceQuote
    unit_price: UnitPrice
    rank: int  # 1 = lowest unit price; equal prices share a rank
    price_range: tuple[Decimal, Decimal] | None  # only when sources conflict


@dataclass(frozen=True)
class Comparison:
    variant: ProductVariant
    rows: list[ComparisonRow]
    label: str | None  # "Menor preço encontrado na nossa base" only when it is true to say so
    notes: list[str]
    analysis: dict[str, Any]


def compare_variant(
    *,
    variant: ProductVariant,
    lat: float,
    lon: float,
    radius_km: float,
    payment_condition: str = "NORMAL",
    has_loyalty: bool = False,
    coupon_codes: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> Comparison:
    """Rank one product across nearby stores by unit price.

    Order is by price only (then distance). Confidence, verification and merchant status are
    shown but never reorder: only facts about the price itself decide the ranking.
    """
    now = now or clock.now()
    ctx = PurchaseContext(
        at=now,
        payment_condition=payment_condition,
        has_loyalty=has_loyalty,
        coupon_codes=coupon_codes,
    )
    stores = list(
        stores_within(lat=lat, lon=lon, radius_km=radius_km)[
            : config.get()["max_stores_considered"]
        ]
    )
    by_store = current_prices(variant=variant, store_ids=[s.pk for s in stores], now=now)

    priced: list[tuple[Store, PriceQuote, UnitPrice]] = []
    for store in stores:
        quote = build_quote(by_store.get(store.pk, []), ctx)
        if quote is not None:
            priced.append(
                (
                    store,
                    quote,
                    unit_price(quote.unit_price, variant.base_quantity, variant.base_unit),
                )
            )
    priced.sort(key=lambda row: (row[2].amount, row[0].distance.m, str(row[0].pk)))  # type: ignore[attr-defined]

    rows: list[ComparisonRow] = []
    rank = 0
    previous: Decimal | None = None
    for position, (store, quote, per_unit) in enumerate(priced, start=1):
        if previous is None or per_unit.amount != previous:
            rank = position
            previous = per_unit.amount
        rows.append(
            ComparisonRow(
                store=store,
                quote=quote,
                unit_price=per_unit,
                rank=rank,
                price_range=(quote.low_price, quote.unit_price) if quote.conflict else None,
            )
        )

    label, notes = _lowest_claim(rows)
    return Comparison(
        variant=variant,
        rows=rows,
        label=label,
        notes=notes,
        analysis={
            "generated_at": now,
            "stores_in_radius": len(stores),
            "stores_with_price": len(rows),
            "coverage": (len(rows) / len(stores)) if stores else 0.0,
            "payment_condition": payment_condition,
            "conditions_considered": sorted(applicable_conditions(ctx)),
            "ranking_basis": "preço por unidade (menor primeiro); confiança não altera a ordem",
        },
    )


def _lowest_claim(rows: list[ComparisonRow]) -> tuple[str | None, list[str]]:
    """Only claim 'lowest price found' when the data supports it."""
    if not rows:
        return None, ["Nenhum preço atual encontrado para este produto na região."]
    if len(rows) == 1:
        return None, ["Apenas um preço encontrado; não há com o que comparar."]
    top = [r for r in rows if r.rank == 1]
    notes: list[str] = []
    if any(r.quote.conflict for r in top):
        return None, [
            "O valor mais baixo encontrado tem informações conflitantes entre fontes; "
            "não é possível afirmar qual é o menor preço."
        ]
    if len(top) > 1:
        notes.append(f"{len(top)} lojas empatadas no menor preço por unidade.")
    if any(r.quote.freshness != "CURRENT" for r in top):
        notes.append("O menor preço encontrado está desatualizado; confirme no local.")
    if any(r.quote.confidence < config.get()["min_confidence"] for r in top):
        notes.append("O menor preço encontrado tem baixa confiança.")
    notes.append("Pode haver diferença no caixa.")
    return LOWEST_LABEL, notes
