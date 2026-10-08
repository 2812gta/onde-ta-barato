from typing import Any, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import clock
from apps.users.models import User

from . import services
from .models import CartItem, CartStatus, ShoppingCart
from .pricing import price_cart
from .serializers import (
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    CartSettingsSerializer,
    ImportListSerializer,
    empty_cart,
    present,
)


def _user(request: Request) -> User:
    return cast(User, request.user)


def _priced(cart: ShoppingCart) -> dict[str, Any]:
    return present(price_cart(cart, clock.now()))


class CartView(APIView):
    @extend_schema(responses=CartSerializer)
    def get(self, request: Request) -> Response:
        cart = services.open_cart(_user(request))
        return Response(_priced(cart) if cart else empty_cart())

    @extend_schema(request=CartSettingsSerializer, responses=CartSerializer)
    def put(self, request: Request) -> Response:
        serializer = CartSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.get_or_open_cart(_user(request))
        services.configure(cart=cart, changes=serializer.validated_data)
        return Response(_priced(cart))


class CartItemsView(APIView):
    @extend_schema(request=CartItemCreateSerializer, responses={201: CartSerializer})
    def post(self, request: Request) -> Response:
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cart = services.get_or_open_cart(_user(request))
        services.add_item(cart=cart, variant=data["variant"], quantity=data["quantity"])
        return Response(_priced(cart), status=status.HTTP_201_CREATED)


def _own_open_item(request: Request, item_id: str) -> CartItem:
    queryset = CartItem.objects.filter(
        cart__user=_user(request), cart__status=CartStatus.OPEN
    ).select_related("cart")
    return get_object_or_404(queryset, pk=item_id)


class CartItemDetailView(APIView):
    @extend_schema(request=CartItemUpdateSerializer, responses=CartSerializer)
    def patch(self, request: Request, item_id: str) -> Response:
        item = _own_open_item(request, item_id)
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.update_item(
            item=item, quantity=data.get("quantity"), in_basket=data.get("in_basket")
        )
        return Response(_priced(item.cart))

    @extend_schema(responses=CartSerializer)
    def delete(self, request: Request, item_id: str) -> Response:
        item = _own_open_item(request, item_id)
        cart = item.cart
        item.delete()
        return Response(_priced(cart))


class CartImportListView(APIView):
    @extend_schema(request=ImportListSerializer, responses=CartSerializer)
    def post(self, request: Request) -> Response:
        serializer = ImportListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shopping_list = serializer.validated_data["shopping_list"]
        if shopping_list.user_id != _user(request).pk:  # someone else's list does not exist
            return Response({"detail": "Não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        cart = services.get_or_open_cart(_user(request))
        services.import_list(cart=cart, shopping_list=shopping_list)
        return Response(_priced(cart))


class CartCloseView(APIView):
    @extend_schema(request=None, responses=CartSerializer)
    def post(self, request: Request) -> Response:
        cart = get_object_or_404(
            ShoppingCart.objects.select_related("store"),
            user=_user(request),
            status=CartStatus.OPEN,
        )
        return Response(present(services.close_cart(cart=cart)))
