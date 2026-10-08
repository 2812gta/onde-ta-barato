from rest_framework import serializers

from apps.core.api import GeoQuerySerializer

from .models import Store, StoreStatus, StoreType


class StoreSearchSerializer(GeoQuerySerializer):
    store_type = serializers.ChoiceField(choices=StoreType.choices, required=False)
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)


class MerchantBadgeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    trade_name = serializers.CharField()
    is_verified = serializers.BooleanField()


class StoreSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(read_only=True)
    lon = serializers.FloatField(read_only=True)
    merchant = MerchantBadgeSerializer(read_only=True)
    distance_m = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "store_type",
            "merchant",
            "street",
            "number",
            "neighborhood",
            "city",
            "state",
            "postal_code",
            "lat",
            "lon",
            "phone",
            "opening_hours",
            "status",
            "source",
            "distance_m",
        ]
        read_only_fields = fields

    def get_distance_m(self, obj: Store) -> int | None:
        distance = getattr(obj, "distance", None)
        return None if distance is None else round(distance.m)


class StoreWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    store_type = serializers.ChoiceField(choices=StoreType.choices, required=False)
    cnpj = serializers.CharField(max_length=20, required=False, allow_blank=True)
    street = serializers.CharField(max_length=200, required=False, allow_blank=True)
    number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    neighborhood = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=8, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    opening_hours = serializers.JSONField(required=False)
    status = serializers.ChoiceField(choices=StoreStatus.choices, required=False)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class StoreUpdateSerializer(StoreWriteSerializer):
    name = serializers.CharField(max_length=200, required=False)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)
    cnpj = None  # type: ignore[assignment]  # CNPJ is not editable after creation
