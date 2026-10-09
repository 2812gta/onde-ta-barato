from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contributions.models import FraudSignal
from apps.prices.models import PriceObservation
from apps.users import rbac
from apps.users.models import User

from . import selectors, services
from .serializers import ReasonSerializer, SignalReviewSerializer, appeal_row, signal_row

MODERATORS: list[type[BasePermission]] = [
    permissions.IsAuthenticated,
    rbac.require(rbac.MODERATION_REVIEW),
]


class QueueView(APIView):
    """What a moderator still has to look at: unreviewed signals and unanswered appeals."""

    permission_classes = MODERATORS

    @extend_schema(responses={200: dict})
    def get(self, request: Request) -> Response:
        return Response(
            {
                "signals": [signal_row(s) for s in selectors.pending_signals()],
                "appeals": [appeal_row(a) for a in selectors.pending_appeals()],
            }
        )


class SignalReviewView(APIView):
    permission_classes = MODERATORS

    @extend_schema(request=SignalReviewSerializer, responses={201: dict})
    def post(self, request: Request, signal_id: str) -> Response:
        signal = get_object_or_404(
            FraudSignal.objects.select_related("contribution__observation"), pk=signal_id
        )
        serializer = SignalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = services.review_signal(
            signal=signal, actor=cast(User, request.user), **serializer.validated_data
        )
        return Response({"decision": review.decision}, status=status.HTTP_201_CREATED)


class _PriceDecisionView(APIView):
    permission_classes = MODERATORS
    decide = staticmethod(services.hide_price)

    @extend_schema(request=ReasonSerializer, responses={201: dict})
    def post(self, request: Request, observation_id: str) -> Response:
        observation = get_object_or_404(PriceObservation, pk=observation_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        type(self).decide(
            observation=observation,
            actor=cast(User, request.user),
            reason=serializer.validated_data["reason"],
        )
        return Response(
            {"moderation": selectors.state_of(observation.pk).state},
            status=status.HTTP_201_CREATED,
        )


class HidePriceView(_PriceDecisionView):
    decide = staticmethod(services.hide_price)


class RestorePriceView(_PriceDecisionView):
    decide = staticmethod(services.restore_price)


class UpholdPriceView(_PriceDecisionView):
    decide = staticmethod(services.uphold_hide)
