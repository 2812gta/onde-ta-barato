from decimal import Decimal

from rest_framework import serializers

from apps.core.api import GeoQuerySerializer
from apps.prices.models import PaymentCondition
from apps.products.models import ProductVariant

from . import config

# How a shopper can pay (price conditions like LOYALTY/COUPON are driven by has_loyalty/coupons).
SHOPPER_PAYMENT_CHOICES = [
    (PaymentCondition.NORMAL.value, PaymentCondition.NORMAL.label),
    (PaymentCondition.PIX.value, PaymentCondition.PIX.label),
    (PaymentCondition.DEBIT.value, PaymentCondition.DEBIT.label),
    (PaymentCondition.CREDIT.value, PaymentCondition.CREDIT.label),
]


class ShopperSerializer(GeoQuerySerializer):
    """Who is buying and how: shared by basket recommendations and product comparison."""

    payment_condition = serializers.ChoiceField(
        choices=SHOPPER_PAYMENT_CHOICES, default=PaymentCondition.NORMAL
    )
    has_loyalty = serializers.BooleanField(default=False)
    coupon_codes = serializers.ListField(
        child=serializers.CharField(max_length=40), default=list, max_length=10
    )


class BasketItemSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__brand", "product__category"),
        source="variant",
    )
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"), max_value=Decimal("1000")
    )


class BasketRequestSerializer(ShopperSerializer):
    # min_length/max_length are accepted by DRF's ListSerializer (the stubs do not know them)
    items = BasketItemSerializer(many=True, min_length=1, max_length=50)  # type: ignore[call-arg]
    mode = serializers.ChoiceField(
        choices=[(m, m) for m in config.MODES], default=config.MELHOR_CUSTO_BENEFICIO
    )
    cost_per_km = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("20"),
        required=False,
    )
    max_stores = serializers.IntegerField(min_value=1, max_value=2, default=2)

    def validate_items(self, items: list[dict]) -> list[dict]:
        ids = [i["variant"].pk for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Produto repetido na lista; some as quantidades.")
        return items
