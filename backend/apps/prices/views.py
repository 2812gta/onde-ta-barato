from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import clock
from apps.products.models import ProductVariant
from apps.stores import selectors as store_selectors
from apps.stores.models import Store
from apps.stores.serializers import StoreSerializer
from apps.users.models import User

from . import selectors, services
from .models import PriceObservation
from .serializers import (
    ConfirmationSerializer,
    HistoryEntrySerializer,
    PriceSearchSerializer,
    PriceViewSerializer,
    PriceWriteSerializer,
    UserPriceReportSerializer,
)

SEARCH_LIMIT = 100


def _variant(variant_id: str) -> ProductVariant:
    return get_object_or_404(
        ProductVariant.objects.select_related("product__category", "product__brand"), pk=variant_id
    )


class VariantPricesSearchView(APIView):
    """Prices of one product in nearby stores.

    Results are grouped per store and ordered by distance only. Several observations for
    the same store are all shown (never silently merged), each with source, age, status and
    confidence. This endpoint makes no "cheapest" or "best" claim.
    """

    throttle_scope = "geo"

    @extend_schema(request=PriceSearchSerializer, responses={200: dict})
    def post(self, request: Request, variant_id: str) -> Response:
        variant = _variant(variant_id)
        serializer = PriceSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stores = list(
            store_selectors.stores_within(
                lat=data["lat"], lon=data["lon"], radius_km=data["radius_km"]
            )[:SEARCH_LIMIT]
        )
        by_store = selectors.current_prices(variant=variant, store_ids=[s.pk for s in stores])
        results = []
        for store in stores:
            views = by_store.get(store.pk, [])
            if not views:
                continue
            results.append(
                {
                    "store": StoreSerializer(store).data,
                    "prices": PriceViewSerializer(views, many=True).data,
                    "conflict": selectors.has_conflict(views),
                }
            )
        return Response(
            {
                "variant_id": str(variant.pk),
                "generated_at": clock.now(),
                "radius_km": data["radius_km"],
                "stores_in_radius": len(stores),
                "stores_with_price": len(results),
                "results": results,
            }
        )


class PriceHistoryView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("store", str, required=True),
            OpenApiParameter("payment_condition", str, required=False),
        ],
        responses=HistoryEntrySerializer(many=True),
    )
    def get(self, request: Request, variant_id: str) -> Response:
        variant = _variant(variant_id)
        store_id = request.query_params.get("store")
        if not store_id:
            return Response(
                {"store": ["Parâmetro obrigatório."]}, status=status.HTTP_400_BAD_REQUEST
            )
        store = get_object_or_404(Store, pk=store_id)
        history = selectors.price_history(
            variant=variant,
            store_id=store.pk,
            payment_condition=request.query_params.get("payment_condition"),
        )
        return Response(HistoryEntrySerializer(history, many=True).data)


def _price_response(result: services.RecordResult, variant: ProductVariant) -> Response:
    view = selectors.current_prices(variant=variant, store_ids=[result.observation.store_id])
    mine = next(
        (
            v
            for v in view.get(result.observation.store_id, [])
            if v.observation.pk == result.observation.pk
        ),
        None,
    )
    body = {
        "deduplicated": not result.created,
        "price": PriceViewSerializer(mine).data if mine else None,
    }
    return Response(body, status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


class MerchantPriceView(APIView):
    throttle_scope = "price_write"

    @extend_schema(request=PriceWriteSerializer, responses={201: dict, 200: dict})
    def post(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        serializer = PriceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.publish_merchant_price(
            store=store, actor=cast(User, request.user), **data
        )
        return _price_response(result, data["variant"])


class UserPriceReportView(APIView):
    throttle_scope = "price_write"

    @extend_schema(request=UserPriceReportSerializer, responses={201: dict, 200: dict})
    def post(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        serializer = UserPriceReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.report_user_price(store=store, actor=cast(User, request.user), **data)
        return _price_response(result, data["variant"])


class ConfirmationView(APIView):
    throttle_scope = "price_write"

    @extend_schema(request=ConfirmationSerializer, responses={201: None})
    def post(self, request: Request, price_id: str) -> Response:
        observation = get_object_or_404(
            PriceObservation.objects.select_related(
                "store__merchant", "product_variant__product__category"
            ),
            pk=price_id,
        )
        serializer = ConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_price(
            observation=observation,
            actor=cast(User, request.user),
            agrees=serializer.validated_data["agrees"],
        )
        return Response(status=status.HTTP_201_CREATED)
