from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.merchants.models import Merchant
from apps.users.models import User

from . import selectors, services
from .models import Store
from .serializers import (
    StoreSearchSerializer,
    StoreSerializer,
    StoreUpdateSerializer,
    StoreWriteSerializer,
)

SEARCH_LIMIT = 100


class StoreSearchView(APIView):
    """Nearby stores. POST on purpose: coordinates in a URL end up in access logs."""

    throttle_scope = "geo"

    @extend_schema(request=StoreSearchSerializer, responses=StoreSerializer(many=True))
    def post(self, request: Request) -> Response:
        serializer = StoreSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stores = selectors.stores_within(
            lat=data["lat"],
            lon=data["lon"],
            radius_km=data["radius_km"],
            store_type=data.get("store_type"),
            name=data.get("q", ""),
        )[:SEARCH_LIMIT]
        return Response(StoreSerializer(stores, many=True).data)


class StoreDetailView(APIView):
    @extend_schema(responses=StoreSerializer)
    def get(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        return Response(StoreSerializer(store).data)

    @extend_schema(request=StoreUpdateSerializer, responses=StoreSerializer)
    def patch(self, request: Request, store_id: str) -> Response:
        store = get_object_or_404(Store.objects.select_related("merchant"), pk=store_id)
        serializer = StoreUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_store(
            store=store, actor=cast(User, request.user), **serializer.validated_data
        )
        return Response(StoreSerializer(store).data)


class MerchantStoresView(APIView):
    @extend_schema(request=StoreWriteSerializer, responses={201: StoreSerializer})
    def post(self, request: Request, merchant_id: str) -> Response:
        merchant = get_object_or_404(Merchant, pk=merchant_id)
        serializer = StoreWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store = services.create_store(
            merchant=merchant, actor=cast(User, request.user), **serializer.validated_data
        )
        return Response(StoreSerializer(store).data, status=status.HTTP_201_CREATED)
