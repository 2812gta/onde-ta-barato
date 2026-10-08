from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import ProductVariant

from . import present, services
from .serializers import BasketRequestSerializer, ShopperSerializer


class BasketRecommendationView(APIView):
    """Where is it worth buying this list? Explainable, never a black box.

    POST because it carries the shopper's location, which must stay out of URLs and logs.
    """

    throttle_scope = "geo"

    @extend_schema(request=BasketRequestSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = BasketRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.recommend_basket(
            pairs=[(item["variant"], item["quantity"]) for item in data["items"]],
            lat=data["lat"],
            lon=data["lon"],
            radius_km=data["radius_km"],
            mode=data["mode"],
            payment_condition=data["payment_condition"],
            has_loyalty=data["has_loyalty"],
            coupon_codes=frozenset(data["coupon_codes"]),
            cost_per_km=data.get("cost_per_km"),
            max_stores=data["max_stores"],
        )
        return Response(present.basket(result, mode=data["mode"]))


class VariantComparisonView(APIView):
    @extend_schema(request=ShopperSerializer, responses={200: dict})
    def post(self, request: Request, variant_id: str) -> Response:
        variant = get_object_or_404(
            ProductVariant.objects.select_related("product__brand", "product__category"),
            pk=variant_id,
        )
        serializer = ShopperSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.compare_variant(
            variant=variant,
            lat=data["lat"],
            lon=data["lon"],
            radius_km=data["radius_km"],
            payment_condition=data["payment_condition"],
            has_loyalty=data["has_loyalty"],
            coupon_codes=frozenset(data["coupon_codes"]),
        )
        return Response(present.comparison(result))
