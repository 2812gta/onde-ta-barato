from typing import cast

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.validators import digits_only
from apps.users import rbac
from apps.users.models import User

from . import services
from .models import CatalogSource, Category, ProductVariant
from .normalization import normalize_text
from .serializers import CategorySerializer, VariantCreateSerializer, VariantSerializer


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None


class VariantListView(generics.ListAPIView):
    serializer_class = VariantSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Busca por nome ou marca"),
            OpenApiParameter("gtin", str, description="Código de barras (EAN/GTIN)"),
            OpenApiParameter("category", str, description="Slug da categoria"),
        ]
    )
    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = ProductVariant.objects.select_related("product__brand", "product__category")
        params = self.request.query_params
        if gtin := params.get("gtin"):
            digits = digits_only(gtin)
            queryset = queryset.filter(gtin=digits.zfill(14)) if digits else queryset.none()
        if q := normalize_text(params.get("q", "")):
            # Every word must appear in the product name or the brand (order independent).
            for word in q.split():
                queryset = queryset.filter(
                    Q(product__normalized_name__contains=word)
                    | Q(product__brand__normalized_name__contains=word)
                )
        if category := params.get("category"):
            queryset = queryset.filter(product__category__slug=category)
        return queryset.order_by("product__normalized_name", "base_quantity")


class VariantDetailView(generics.RetrieveAPIView):
    queryset = ProductVariant.objects.select_related("product__brand", "product__category")
    serializer_class = VariantSerializer
    lookup_url_kwarg = "variant_id"


class VariantCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, rbac.require(rbac.CATALOG_WRITE)]

    @extend_schema(request=VariantCreateSerializer, responses={201: VariantSerializer})
    def post(self, request: Request) -> Response:
        serializer = VariantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = cast(User, request.user)
        variant, created = services.get_or_create_variant(
            name=data["name"],
            brand_name=data.get("brand", ""),
            category=data.get("category"),
            label=data.get("label", ""),
            quantity=data["quantity"],
            unit=data["unit"],
            gtin=data.get("gtin", ""),
            source=(
                CatalogSource.MERCHANT if user.role.startswith("MERCHANT") else CatalogSource.MANUAL
            ),
            actor=user,
        )
        body = {**VariantSerializer(variant).data, "created": created}
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
