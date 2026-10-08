from decimal import Decimal

from rest_framework import serializers

from apps.products.models import ProductVariant

from .models import ShoppingList, ShoppingListItem

QUANTITY = {"max_digits": 10, "decimal_places": 3, "min_value": Decimal("0.001")}


def variant_label(variant: ProductVariant) -> str:
    parts = [variant.product.name, f"{variant.quantity.normalize():f} {variant.unit}"]
    return " ".join(parts)


class ListItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.UUIDField(source="product_variant_id", read_only=True)
    label = serializers.SerializerMethodField()  # type: ignore[assignment]
    brand = serializers.CharField(source="product_variant.product.brand.name", default=None)

    class Meta:
        model = ShoppingListItem
        fields = ["id", "variant_id", "label", "brand", "quantity", "checked"]
        read_only_fields = fields

    def get_label(self, obj: ShoppingListItem) -> str:
        return variant_label(obj.product_variant)


class ListSummarySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    checked_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShoppingList
        fields = ["id", "name", "item_count", "checked_count", "created_at", "updated_at"]
        read_only_fields = fields


class ListDetailSerializer(serializers.ModelSerializer):
    items = ListItemSerializer(many=True, read_only=True)

    class Meta:
        model = ShoppingList
        fields = ["id", "name", "items", "created_at", "updated_at"]
        read_only_fields = fields


class ListWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)


class ItemCreateSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__brand"), source="variant"
    )
    quantity = serializers.DecimalField(default=Decimal("1"), **QUANTITY)  # type: ignore[arg-type]


class ItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(required=False, **QUANTITY)  # type: ignore[arg-type]
    checked = serializers.BooleanField(required=False)
