from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import clock
from apps.stores.models import Store
from apps.users.models import User

from . import services
from .engine import PurchaseContext, calculate_line
from .models import Promotion
from .serializers import (
    CalculateSerializer,
    LineResultSerializer,
    PromotionSerializer,
    PromotionWriteSerializer,
)


class StorePromotionsView(APIView):
    @extend_schema(responses=PromotionSerializer(many=True))
    def get(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        promotions = (
            Promotion.objects.filter(store=store, is_active=True)
            .select_related("store__merchant")
            .order_by("-created_at")
        )
        return Response(PromotionSerializer(promotions, many=True).data)

    @extend_schema(request=PromotionWriteSerializer, responses={201: PromotionSerializer})
    def post(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        serializer = PromotionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        promotion = services.create_promotion(
            store=store,
            actor=cast(User, request.user),
            variant=data["variant"],
            title=data["title"],
            rule=data["rule"],
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
        )
        return Response(PromotionSerializer(promotion).data, status=status.HTTP_201_CREATED)


class PromotionDetailView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request: Request, promotion_id: str) -> Response:
        promotion = get_object_or_404(
            Promotion.objects.select_related("store__merchant"), pk=promotion_id
        )
        services.deactivate_promotion(promotion=promotion, actor=cast(User, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CalculateView(APIView):
    """Stateless calculator: same engine the cart and recommendations use. Stores nothing."""

    @extend_schema(request=CalculateSerializer, responses=LineResultSerializer)
    def post(self, request: Request) -> Response:
        serializer = CalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        context = PurchaseContext(
            at=data.get("at") or clock.now(),
            payment_condition=data["payment_condition"],
            has_loyalty=data["has_loyalty"],
            coupon_codes=frozenset(data["coupon_codes"]),
        )
        result = calculate_line(data["unit_price"], data["quantity"], data["rule"], context)
        return Response(LineResultSerializer.from_result(result))
