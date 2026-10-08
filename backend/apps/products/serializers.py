from decimal import Decimal

from rest_framework import serializers

from .models import Category, ProductVariant, Unit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "price_ttl_hours"]
        read_only_fields = fields


class VariantSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    brand = serializers.CharField(source="product.brand.name", read_only=True, default=None)
    category = serializers.CharField(source="product.category.slug", read_only=True, default=None)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_id",
            "name",
            "brand",
            "category",
            "label",
            "gtin",
            "quantity",
            "unit",
            "pack_count",
            "base_quantity",
            "base_unit",
            "catalog_source",
        ]
        read_only_fields = fields


class VariantCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    brand = serializers.CharField(max_length=120, required=False, allow_blank=True)
    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.all(), required=False, allow_null=True
    )
    # API field named "label" (shadows Field.label only in the static type).
    label = serializers.CharField(  # type: ignore[assignment]
        max_length=120, required=False, allow_blank=True
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit = serializers.ChoiceField(choices=Unit.choices)
    gtin = serializers.CharField(max_length=20, required=False, allow_blank=True)
