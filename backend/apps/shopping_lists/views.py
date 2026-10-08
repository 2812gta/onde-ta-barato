from typing import cast

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User

from . import services
from .models import ShoppingList, ShoppingListItem
from .serializers import (
    ItemCreateSerializer,
    ItemUpdateSerializer,
    ListDetailSerializer,
    ListItemSerializer,
    ListSummarySerializer,
    ListWriteSerializer,
)


def _own_list(request: Request, list_id: str) -> ShoppingList:
    """Someone else's list is a 404, not a 403: its existence is not revealed."""
    queryset = ShoppingList.objects.filter(user=cast(User, request.user)).prefetch_related(
        "items__product_variant__product__brand"
    )
    return get_object_or_404(queryset, pk=list_id)


def _own_item(request: Request, list_id: str, item_id: str) -> ShoppingListItem:
    queryset = ShoppingListItem.objects.filter(
        shopping_list__user=cast(User, request.user), shopping_list__pk=list_id
    ).select_related("shopping_list", "product_variant__product__brand")
    return get_object_or_404(queryset, pk=item_id)


class ListsView(APIView):
    @extend_schema(responses=ListSummarySerializer(many=True))
    def get(self, request: Request) -> Response:
        lists = (
            ShoppingList.objects.filter(user=cast(User, request.user))
            .annotate(
                item_count=Count("items"),
                checked_count=Count("items", filter=Q(items__checked=True)),
            )
            .order_by("-updated_at")
        )
        return Response(ListSummarySerializer(lists, many=True).data)

    @extend_schema(request=ListWriteSerializer, responses={201: ListDetailSerializer})
    def post(self, request: Request) -> Response:
        serializer = ListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.create_list(
            user=cast(User, request.user), name=serializer.validated_data["name"]
        )
        return Response(ListDetailSerializer(created).data, status=status.HTTP_201_CREATED)


class ListDetailView(APIView):
    @extend_schema(responses=ListDetailSerializer)
    def get(self, request: Request, list_id: str) -> Response:
        return Response(ListDetailSerializer(_own_list(request, list_id)).data)

    @extend_schema(request=ListWriteSerializer, responses=ListDetailSerializer)
    def patch(self, request: Request, list_id: str) -> Response:
        shopping_list = _own_list(request, list_id)
        serializer = ListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.rename_list(shopping_list=shopping_list, name=serializer.validated_data["name"])
        return Response(ListDetailSerializer(shopping_list).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, list_id: str) -> Response:
        _own_list(request, list_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListItemsView(APIView):
    @extend_schema(request=ItemCreateSerializer, responses={201: ListItemSerializer})
    def post(self, request: Request, list_id: str) -> Response:
        shopping_list = _own_list(request, list_id)
        serializer = ItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = services.add_item(
            shopping_list=shopping_list, variant=data["variant"], quantity=data["quantity"]
        )
        return Response(ListItemSerializer(item).data, status=status.HTTP_201_CREATED)


class ListItemDetailView(APIView):
    @extend_schema(request=ItemUpdateSerializer, responses=ListItemSerializer)
    def patch(self, request: Request, list_id: str, item_id: str) -> Response:
        item = _own_item(request, list_id, item_id)
        serializer = ItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.update_item(item=item, quantity=data.get("quantity"), checked=data.get("checked"))
        return Response(ListItemSerializer(item).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, list_id: str, item_id: str) -> Response:
        services.remove_item(item=_own_item(request, list_id, item_id))
        return Response(status=status.HTTP_204_NO_CONTENT)
