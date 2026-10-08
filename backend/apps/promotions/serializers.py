from decimal import Decimal

from rest_framework import serializers

from apps.core import clock
from apps.products.models import ProductVariant

from .engine import InvalidRule, LineResult, validate_rule
from .models import Promotion


class RuleField(serializers.JSONField):
    """A promotion rule, validated by the same engine that will calculate it."""

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        value = super().to_internal_value(data)
        if not isinstance(value, dict):
            raise serializers.ValidationError("A regra deve ser um objeto JSON.")
        try:
            validate_rule(value)
        except InvalidRule as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value


class PromotionWriteSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(), source="variant"
    )
    title = serializers.CharField(max_length=120)
    rule = RuleField()
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False)


class PromotionSerializer(serializers.ModelSerializer):
    variant_id = serializers.UUIDField(source="product_variant_id", read_only=True)
    status = serializers.SerializerMethodField()
    confirmed = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            "id",
            "store_id",
            "variant_id",
            "title",
            "rule",
            "valid_from",
            "valid_until",
            "is_active",
            "status",
            "confirmed",
        ]
        read_only_fields = fields

    def get_status(self, obj: Promotion) -> str:

        from .selectors import status_of

        return status_of(obj, clock.now())

    def get_confirmed(self, obj: Promotion) -> bool:
        from .selectors import is_confirmed

        return is_confirmed(obj)


class CalculateSerializer(serializers.Serializer):
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"))
    rule = RuleField()
    payment_condition = serializers.CharField(default="NORMAL", max_length=10)
    has_loyalty = serializers.BooleanField(default=False)
    coupon_codes = serializers.ListField(
        child=serializers.CharField(max_length=40), default=list, max_length=10
    )
    at = serializers.DateTimeField(required=False)


class LineResultSerializer(serializers.Serializer):
    rule_type = serializers.CharField()
    applicable = serializers.BooleanField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    gross = serializers.DecimalField(max_digits=12, decimal_places=2)
    net = serializers.DecimalField(max_digits=12, decimal_places=2)
    savings = serializers.DecimalField(max_digits=12, decimal_places=2)
    cashback = serializers.DecimalField(max_digits=12, decimal_places=2)
    effective_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(allow_blank=True)
    steps = serializers.ListField(child=serializers.CharField())

    @classmethod
    def from_result(cls, result: LineResult) -> dict:
        data = {
            **result.__dict__,
            "effective_cost": result.effective_cost,
            "steps": list(result.steps),
        }
        return cls(data).data
