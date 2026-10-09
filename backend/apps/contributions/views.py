from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.moderation import services as moderation_services
from apps.moderation.serializers import AppealCreateSerializer
from apps.prices.views import _price_response
from apps.stores.models import Store
from apps.users.models import User

from . import services
from .models import UserContribution
from .serializers import (
    ConfirmSerializer,
    ContributionSerializer,
    DraftCreateSerializer,
    DraftSerializer,
)


class ContributionListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def get_throttles(self):  # type: ignore[no-untyped-def]
        if self.request.method == "POST":
            self.throttle_scope = "contribution"
        return super().get_throttles()

    @extend_schema(responses=ContributionSerializer(many=True))
    def get(self, request: Request) -> Response:
        queryset = UserContribution.objects.filter(user=cast(User, request.user)).select_related(
            "store"
        )[:50]
        return Response(ContributionSerializer(queryset, many=True).data)

    @extend_schema(request=DraftCreateSerializer, responses={201: DraftSerializer})
    def post(self, request: Request) -> Response:
        serializer = DraftCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        store = get_object_or_404(Store, pk=data["store_id"])
        contribution, _ = services.create_draft(
            user=cast(User, request.user),
            store=store,
            photo=data["photo"].read(),
            ocr_text=data.get("ocr_text", ""),
            captured_at=data.get("captured_at"),
        )
        return Response(DraftSerializer(contribution).data, status=status.HTTP_201_CREATED)


class ContributionDetailView(APIView):
    @extend_schema(responses=DraftSerializer)
    def get(self, request: Request, contribution_id: str) -> Response:
        contribution = get_object_or_404(
            UserContribution.objects.select_related("store"),
            pk=contribution_id,
            user=cast(User, request.user),
        )
        return Response(DraftSerializer(contribution).data)


class ContributionConfirmView(APIView):
    throttle_scope = "contribution"

    @extend_schema(request=ConfirmSerializer, responses={201: dict})
    def post(self, request: Request, contribution_id: str) -> Response:
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        contribution, result, _signals = services.confirm(
            contribution_id=contribution_id,
            user=cast(User, request.user),
            variant=data["variant"],
            price=data["price"],
            payment_condition=data["payment_condition"],
            is_promotional=data["is_promotional"],
            lat=data.get("lat"),
            lon=data.get("lon"),
        )
        body = _price_response(result, data["variant"]).data
        # Fraud signals are for moderators: the contributor is not told which rules fired.
        body["contribution"] = ContributionSerializer(contribution).data
        return Response(body, status=status.HTTP_201_CREATED)


class ContributionCancelView(APIView):
    @extend_schema(request=None, responses={200: ContributionSerializer})
    def post(self, request: Request, contribution_id: str) -> Response:
        contribution = services.cancel(
            contribution_id=contribution_id, user=cast(User, request.user)
        )
        return Response(ContributionSerializer(contribution).data)


class ContributionAppealView(APIView):
    """The contributor contests a price that moderators hid."""

    throttle_scope = "contribution"

    @extend_schema(request=AppealCreateSerializer, responses={201: ContributionSerializer})
    def post(self, request: Request, contribution_id: str) -> Response:
        contribution = get_object_or_404(
            UserContribution.objects.select_related("store", "observation"),
            pk=contribution_id,
            user=cast(User, request.user),
        )
        if contribution.observation is None:
            return Response(
                {"detail": "Esta contribuição não gerou um preço."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = AppealCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        moderation_services.appeal(
            observation=contribution.observation,
            user=cast(User, request.user),
            message=serializer.validated_data["message"],
        )
        return Response(ContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)
