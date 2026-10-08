from decimal import Decimal

from rest_framework import serializers

from apps.core.api import GeoQuerySerializer
from apps.products.models import ProductVariant

from .models import PaymentCondition, PriceObservation, PriceSource
from .selectors import PriceView


class PriceWriteSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__category"), source="variant"
    )
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payment_condition = serializers.ChoiceField(
        choices=PaymentCondition.choices, default=PaymentCondition.NORMAL
    )
    is_promotional = serializers.BooleanField(default=False)
    collected_at = serializers.DateTimeField(required=False)
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False)


class UserPriceReportSerializer(PriceWriteSerializer):
    # Used only to check proximity to the store. Never stored, never returned.
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False, source="user_lat")
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False, source="user_lon")


class ConfirmationSerializer(serializers.Serializer):
    agrees = serializers.BooleanField()


class PriceSearchSerializer(GeoQuerySerializer):
    pass


class UnitPriceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    per = serializers.CharField()
    display = serializers.CharField()


class PriceViewSerializer(serializers.Serializer):
    """What the consumer sees for one price: value + where it came from + how much to trust it."""

    id = serializers.UUIDField(source="observation.id")
    price = serializers.DecimalField(max_digits=12, decimal_places=2, source="observation.price")
    currency = serializers.CharField(source="observation.currency")
    payment_condition = serializers.CharField(source="observation.payment_condition")
    is_promotional = serializers.BooleanField(source="observation.is_promotional")
    # API field named "source" (shadows Field.source only in the static type; DRF handles it).
    source = serializers.CharField(source="observation.source")  # type: ignore[assignment]
    collected_at = serializers.DateTimeField(source="observation.collected_at")
    valid_until = serializers.DateTimeField(source="observation.valid_until")
    age_hours = serializers.FloatField()
    status = serializers.CharField()
    verification = serializers.CharField()
    confidence_score = serializers.DecimalField(
        max_digits=4, decimal_places=3, source="confidence.score"
    )
    confidence_level = serializers.CharField(source="confidence.level")
    confidence_factors = serializers.DictField(source="confidence.factors")
    confirmations = serializers.IntegerField()
    contradictions = serializers.IntegerField()
    has_evidence = serializers.BooleanField()
    location_verified = serializers.BooleanField(source="observation.location_verified")
    unit_price = UnitPriceSerializer()
    disclaimer = serializers.SerializerMethodField()

    def get_disclaimer(self, obj: PriceView) -> str:
        return "Pode haver diferença no caixa."


class HistoryEntrySerializer(serializers.ModelSerializer):
    """Public history. Authors are exposed as a role only, never as a person."""

    contributor = serializers.SerializerMethodField()
    previous_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, source="supersedes.price", default=None
    )

    class Meta:
        model = PriceObservation
        fields = [
            "id",
            "price",
            "previous_price",
            "payment_condition",
            "is_promotional",
            "source",
            "contributor",
            "collected_at",
            "valid_until",
            "confidence_level",
        ]
        read_only_fields = fields

    def get_contributor(self, obj: PriceObservation) -> str:
        return "ESTABELECIMENTO" if obj.source == PriceSource.MERCHANT else "CONSUMIDOR"
