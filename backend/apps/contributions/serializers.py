from decimal import Decimal

from rest_framework import serializers

from apps.prices.models import PaymentCondition
from apps.products.models import ProductVariant
from apps.products.serializers import VariantSerializer

from .extraction import MAX_TEXT_CHARS
from .models import UserContribution


class DraftCreateSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()
    photo = serializers.ImageField()
    # Text read on the device (ML Kit). Interpreted on the server; never trusted as a price.
    ocr_text = serializers.CharField(
        max_length=MAX_TEXT_CHARS,
        allow_blank=True,
        trim_whitespace=False,
        required=False,
        default="",
    )
    captured_at = serializers.DateTimeField(required=False)


class ConfirmSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__category"), source="variant"
    )
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payment_condition = serializers.ChoiceField(
        choices=PaymentCondition.choices, default=PaymentCondition.NORMAL
    )
    is_promotional = serializers.BooleanField(default=False)
    # Only to check the device is near the store. Never stored, never returned.
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)


class ContributionSerializer(serializers.ModelSerializer):
    store_id = serializers.UUIDField(read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    observation_id = serializers.UUIDField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = UserContribution
        fields = [
            "id",
            "status",
            "store_id",
            "store_name",
            "captured_at",
            "corrected",
            "observation_id",
            "created_at",
            "expires_at",
            "resolved_at",
        ]
        read_only_fields = fields


class DraftSerializer(ContributionSerializer):
    """A draft plus what we read from it, each item labelled FACT or INFERENCE."""

    reading = serializers.SerializerMethodField()
    suggested_variants = serializers.SerializerMethodField()

    class Meta(ContributionSerializer.Meta):
        fields = [*ContributionSerializer.Meta.fields, "reading", "suggested_variants"]
        read_only_fields = fields

    def get_reading(self, obj: UserContribution) -> dict:
        data = obj.extraction
        return {
            "prices": data.get("prices", []),
            "gtins": data.get("gtins", []),
            "name_lines": data.get("name_lines", []),
            "note": "O que foi lido é uma sugestão. Confira antes de confirmar.",
        }

    def get_suggested_variants(self, obj: UserContribution) -> list[dict]:
        meta = {v["variant_id"]: v for v in obj.extraction.get("variants", [])}
        order = list(meta)
        variants = ProductVariant.objects.select_related(
            "product__brand", "product__category"
        ).filter(pk__in=order)
        ordered = sorted(variants, key=lambda v: order.index(str(v.pk)))
        return [
            {
                **VariantSerializer(variant).data,
                "basis": meta[str(variant.pk)]["basis"],
                "origin": meta[str(variant.pk)]["origin"],
            }
            for variant in ordered
        ]
