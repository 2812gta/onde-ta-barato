from typing import cast

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import rbac
from apps.users.models import User

from . import services
from .models import Merchant, MerchantMembership, VerificationStatus
from .serializers import (
    MemberInputSerializer,
    MemberSerializer,
    MerchantCreateSerializer,
    MerchantSerializer,
    TransitionSerializer,
    VerificationHistorySerializer,
)


def _user(request: Request) -> User:
    return cast(User, request.user)


def _visible_merchant(request: Request, merchant_id: str) -> Merchant:
    """Only members and reviewers may see a merchant (UUID ids: a 403 leaks nothing useful)."""
    merchant = get_object_or_404(Merchant, pk=merchant_id)
    user = _user(request)
    if services.membership_role(user, merchant) or rbac.has_permission(user, rbac.MERCHANTS_REVIEW):
        return merchant
    raise PermissionDenied


class MerchantListCreateView(APIView):
    @extend_schema(responses=MerchantSerializer(many=True))
    def get(self, request: Request) -> Response:
        merchants = Merchant.objects.filter(memberships__user=_user(request)).order_by("trade_name")
        return Response(MerchantSerializer(merchants, many=True).data)

    @extend_schema(request=MerchantCreateSerializer, responses={201: MerchantSerializer})
    def post(self, request: Request) -> Response:
        serializer = MerchantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        merchant = services.create_merchant(owner=_user(request), **serializer.validated_data)
        return Response(MerchantSerializer(merchant).data, status=status.HTTP_201_CREATED)


class MerchantDetailView(APIView):
    @extend_schema(responses=MerchantSerializer)
    def get(self, request: Request, merchant_id: str) -> Response:
        return Response(MerchantSerializer(_visible_merchant(request, merchant_id)).data)


class ReviewQueueView(APIView):
    permission_classes = [permissions.IsAuthenticated, rbac.require(rbac.MERCHANTS_REVIEW)]

    @extend_schema(responses=MerchantSerializer(many=True))
    def get(self, request: Request) -> Response:
        queue = Merchant.objects.filter(status=VerificationStatus.UNDER_REVIEW).order_by(
            "updated_at"
        )
        return Response(MerchantSerializer(queue, many=True).data)


class VerificationView(APIView):
    @extend_schema(responses=VerificationHistorySerializer(many=True))
    def get(self, request: Request, merchant_id: str) -> Response:
        merchant = _visible_merchant(request, merchant_id)
        return Response(VerificationHistorySerializer(merchant.verifications.all(), many=True).data)

    @extend_schema(request=TransitionSerializer, responses=MerchantSerializer)
    def post(self, request: Request, merchant_id: str) -> Response:
        merchant = _visible_merchant(request, merchant_id)
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition(
            merchant=merchant,
            to_status=serializer.validated_data["to"],
            actor=_user(request),
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(MerchantSerializer(merchant).data)


class MemberListCreateView(APIView):
    @extend_schema(responses=MemberSerializer(many=True))
    def get(self, request: Request, merchant_id: str) -> Response:
        merchant = _visible_merchant(request, merchant_id)
        members = MerchantMembership.objects.filter(merchant=merchant).select_related("user")
        return Response(MemberSerializer(members, many=True).data)

    @extend_schema(request=MemberInputSerializer, responses={201: MemberSerializer})
    def post(self, request: Request, merchant_id: str) -> Response:
        merchant = _visible_merchant(request, merchant_id)
        serializer = MemberInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.add_member(
            merchant=merchant, actor=_user(request), **serializer.validated_data
        )
        return Response(MemberSerializer(membership).data, status=status.HTTP_201_CREATED)


class MemberDeleteView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request: Request, merchant_id: str, user_id: str) -> Response:
        merchant = _visible_merchant(request, merchant_id)
        services.remove_member(merchant=merchant, actor=_user(request), user_id=user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
