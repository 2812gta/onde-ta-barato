"""Prices a cart at its store with the same rules the recommendations use.

* One honest unit price per item (`build_quote`): expired prices are not used, stale ones are
  flagged, and when live sources disagree the HIGHER price is used.
* Only promotions of VERIFIED merchants change the total (ADR 0010); the others are reported
  as "possible saving, not confirmed". One promotion per line, no stacking.
* Items without a usable price are listed as unpriced and left OUT of the total, never
  guessed, and the response says how many there are.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.core.money import quantize_money
from apps.prices.selectors import current_prices
from apps.promotions.engine import PurchaseContext, best_promotion
from apps.promotions.selectors import is_confirmed, running_promotions
from apps.recommendations.quotes import build_quote
from apps.recommendations.types import PriceQuote

from .models import CartItem, ShoppingCart

ZERO = Decimal("0.00")
DISCLAIMER = "Os preços podem divergir do caixa."


@dataclass(frozen=True)
class PricedLine:
    item: CartItem
    quote: PriceQuote | None
    gross: Decimal = ZERO
    net: Decimal = ZERO
    savings: Decimal = ZERO
    cashback: Decimal = ZERO
    promo_title: str | None = None
    unconfirmed_potential: Decimal = ZERO

    @property
    def priced(self) -> bool:
        return self.quote is not None


@dataclass(frozen=True)
class PricedCart:
    cart: ShoppingCart
    lines: list[PricedLine]
    gross_total: Decimal = ZERO
    total: Decimal = ZERO
    savings: Decimal = ZERO
    cashback: Decimal = ZERO
    unconfirmed_potential: Decimal = ZERO
    unpriced_count: int = 0
    warnings: list[str] = field(default_factory=list)


def context_for(cart: ShoppingCart, now: datetime) -> PurchaseContext:
    return PurchaseContext(
        at=now,
        payment_condition=cart.payment_condition,
        has_loyalty=cart.has_loyalty,
        coupon_codes=frozenset(str(c) for c in cart.coupon_codes),
    )


def price_cart(cart: ShoppingCart, now: datetime) -> PricedCart:
    items = list(cart.items.select_related("product_variant__product__brand"))
    store = cart.store
    if store is None:
        bare = [PricedLine(item=i, quote=None) for i in items]
        hint = ["Escolha o mercado para ver os preços."] if items else []
        return PricedCart(cart, bare, unpriced_count=len(items), warnings=hint)

    ctx = context_for(cart, now)
    variants = [i.product_variant for i in items]
    promos = running_promotions(store_ids=[store.pk], variant_ids=[v.pk for v in variants], now=now)

    lines: list[PricedLine] = []
    for item in items:
        views = current_prices(variant=item.product_variant, store_ids=[store.pk], now=now)
        quote = build_quote(views.get(store.pk, []), ctx)
        if quote is None:
            lines.append(PricedLine(item=item, quote=None))
            continue
        gross = quantize_money(quote.unit_price * item.quantity)
        found = promos.get((store.pk, item.product_variant_id), [])
        confirmed = [p for p in found if is_confirmed(p)]
        unconfirmed = [p for p in found if not is_confirmed(p)]
        best, evaluated = best_promotion(
            quote.unit_price, item.quantity, [p.rule for p in confirmed], ctx
        )
        potential, _ = best_promotion(
            quote.unit_price, item.quantity, [p.rule for p in unconfirmed], ctx
        )
        lines.append(
            PricedLine(
                item=item,
                quote=quote,
                gross=gross,
                net=best.net if best else gross,
                savings=best.savings if best else ZERO,
                cashback=best.cashback if best else ZERO,
                promo_title=confirmed[evaluated.index(best)].title if best else None,
                unconfirmed_potential=potential.benefit if potential else ZERO,
            )
        )

    priced = [line for line in lines if line.priced]
    unpriced = len(lines) - len(priced)
    warnings: list[str] = []
    if unpriced:
        warnings.append(f"{unpriced} item(ns) sem preço atual neste mercado ficaram fora do total.")
    if any(line.quote and line.quote.freshness != "CURRENT" for line in priced):
        warnings.append("Alguns preços estão desatualizados.")
    if any(line.quote and line.quote.conflict for line in priced):
        warnings.append("Há preços divergentes; usamos o maior para não prometer economia falsa.")
    if priced:
        warnings.append(DISCLAIMER)
    return PricedCart(
        cart=cart,
        lines=lines,
        gross_total=sum((line.gross for line in priced), ZERO),
        total=sum((line.net for line in priced), ZERO),
        savings=sum((line.savings for line in priced), ZERO),
        cashback=sum((line.cashback for line in priced), ZERO),
        unconfirmed_potential=sum((line.unconfirmed_potential for line in priced), ZERO),
        unpriced_count=unpriced,
        warnings=warnings,
    )
