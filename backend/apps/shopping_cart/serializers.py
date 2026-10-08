from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.products.models import ProductVariant
from apps.shopping_lists.models import ShoppingList
from apps.shopping_lists.serializers import QUANTITY, variant_label
from apps.stores.models import Store

from .models import ShoppingCart
from .pricing import PricedCart, PricedLine


class CartSettingsSerializer(serializers.Serializer):
    """Every field is optional: only what is sent changes. `store_id: null` clears the store."""

    store_id = serializers.PrimaryKeyRelatedField(
        queryset=Store.objects.all(), source="store", allow_null=True, required=False
    )
    payment_condition = serializers.ChoiceField(
        choices=["NORMAL", "PIX", "DEBIT", "CREDIT"], required=False
    )
    has_loyalty = serializers.BooleanField(required=False)
    coupon_codes = serializers.ListField(
        child=serializers.CharField(max_length=40), max_length=10, required=False
    )


class CartItemCreateSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__brand"), source="variant"
    )
    quantity = serializers.DecimalField(default=Decimal("1"), **QUANTITY)  # type: ignore[arg-type]


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(required=False, **QUANTITY)  # type: ignore[arg-type]
    in_basket = serializers.BooleanField(required=False)


class ImportListSerializer(serializers.Serializer):
    list_id = serializers.PrimaryKeyRelatedField(
        queryset=ShoppingList.objects.all(), source="shopping_list"
    )


class CartLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    variant_id = serializers.UUIDField()
    label = serializers.CharField()  # type: ignore[assignment]
    brand = serializers.CharField(allow_null=True)
    quantity = serializers.CharField()
    in_basket = serializers.BooleanField()
    priced = serializers.BooleanField()
    unit_price = serializers.CharField(allow_null=True)
    gross = serializers.CharField(allow_null=True)
    net = serializers.CharField(allow_null=True)
    savings = serializers.CharField(allow_null=True)
    cashback = serializers.CharField(allow_null=True)
    promotion = serializers.CharField(allow_null=True)
    unconfirmed_potential = serializers.CharField(allow_null=True)
    freshness = serializers.CharField(allow_null=True)
    confidence = serializers.FloatField(allow_null=True)
    conflict = serializers.BooleanField()
    age_hours = serializers.FloatField(allow_null=True)


class CartSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    store = serializers.DictField(allow_null=True)
    payment_condition = serializers.CharField()
    has_loyalty = serializers.BooleanField()
    coupon_codes = serializers.ListField(child=serializers.CharField())
    items = CartLineSerializer(many=True)
    totals = serializers.DictField()
    warnings = serializers.ListField(child=serializers.CharField())


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _line(line: PricedLine) -> dict[str, Any]:
    item, quote = line.item, line.quote
    variant = item.product_variant
    brand = variant.product.brand
    return {
        "id": item.pk,
        "variant_id": item.product_variant_id,
        "label": variant_label(variant),
        "brand": brand.name if brand else None,
        "quantity": f"{item.quantity:f}",
        "in_basket": item.in_basket,
        "priced": quote is not None,
        "unit_price": _money(quote.unit_price) if quote else None,
        "gross": _money(line.gross) if quote else None,
        "net": _money(line.net) if quote else None,
        "savings": _money(line.savings) if quote else None,
        "cashback": _money(line.cashback) if quote else None,
        "promotion": line.promo_title,
        "unconfirmed_potential": _money(line.unconfirmed_potential) if quote else None,
        "freshness": quote.freshness if quote else None,
        "confidence": round(quote.confidence, 2) if quote else None,
        "conflict": bool(quote and quote.conflict),
        "age_hours": round(quote.age_hours, 1) if quote else None,
    }


def present(priced: PricedCart) -> dict[str, Any]:
    cart = priced.cart
    store = cart.store
    return CartSerializer(
        {
            "id": cart.pk,
            "status": cart.status,
            "store": {"id": str(store.pk), "name": store.name} if store else None,
            "payment_condition": cart.payment_condition,
            "has_loyalty": cart.has_loyalty,
            "coupon_codes": cart.coupon_codes,
            "items": [_line(line) for line in priced.lines],
            "totals": {
                "gross": _money(priced.gross_total),
                "total": _money(priced.total),
                "savings": _money(priced.savings),
                "cashback": _money(priced.cashback),
                "unconfirmed_potential": _money(priced.unconfirmed_potential),
                "unpriced_count": priced.unpriced_count,
            },
            "warnings": priced.warnings,
        }
    ).data


def empty_cart() -> dict[str, Any]:
    """What a shopper without an open cart sees: nothing is created by a read."""
    data = dict(present(PricedCart(cart=ShoppingCart(), lines=[])))
    data["id"] = None  # an unsaved cart carries a random default id; there is no cart yet
    return data
