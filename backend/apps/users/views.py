from contextlib import suppress
from typing import cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit import services as audit

from . import rbac, services
from .models import User
from .serializers import (
    CodeSerializer,
    ConsentInputSerializer,
    ConsentSerializer,
    DeleteAccountSerializer,
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    RefreshSerializer,
    RegisterSerializer,
    RoleChangeSerializer,
    TokenSerializer,
)

GENERIC_REGISTER_MESSAGE = (
    "Se os dados forem válidos, enviamos um e-mail para confirmar o cadastro."
)


def current_user(request: Request) -> User:
    """Authenticated user. Views using it require IsAuthenticated (the project default)."""
    return cast(User, request.user)


class PublicView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list[type] = []


class RegisterView(PublicView):
    throttle_scope = "register"

    @extend_schema(request=RegisterSerializer, responses={201: None})
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.register_user(
            email=data["email"],
            password=data["password"],
            display_name=data.get("display_name", ""),
            request=request._request,
        )
        return Response({"detail": GENERIC_REGISTER_MESSAGE}, status=status.HTTP_201_CREATED)


class LoginView(PublicView):
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: TokenSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tokens = services.login(request=request._request, **serializer.validated_data)
        except services.AccountLocked:
            return Response(
                {"detail": "Muitas tentativas. Tente novamente mais tarde."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except services.InvalidCredentials:
            return Response(
                {"detail": "Credenciais inválidas."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(tokens)


class RefreshView(PublicView):
    """Rotates the refresh token (old one is blacklisted)."""

    throttle_scope = "login"

    @extend_schema(request=RefreshSerializer, responses={200: TokenSerializer})
    def post(self, request: Request) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return Response(
                {"detail": "Token inválido ou expirado."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(serializer.validated_data)


class LogoutView(APIView):
    @extend_schema(request=RefreshSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # An already-invalid token is the outcome the caller wants.
        with suppress(TokenError):
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        audit.record(
            "user.logout",
            actor=current_user(request),
            entity_type="user",
            entity_id=current_user(request).pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class VerifyEmailView(PublicView):
    throttle_scope = "verification"

    @extend_schema(request=CodeSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.verify_email(serializer.validated_data["token"])
        except services.InvalidToken:
            return Response(
                {"detail": "Código inválido ou expirado."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({"detail": "E-mail confirmado."})


class ResendVerificationView(APIView):
    throttle_scope = "verification"

    @extend_schema(request=None, responses={202: None})
    def post(self, request: Request) -> Response:
        services.resend_verification(current_user(request))
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetRequestView(PublicView):
    throttle_scope = "password_reset"

    @extend_schema(request=EmailSerializer, responses={202: None})
    def post(self, request: Request) -> Response:
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(
            {"detail": "Se o e-mail estiver cadastrado, enviaremos as instruções."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(PublicView):
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.confirm_password_reset(
                code=serializer.validated_data["code"],
                new_password=serializer.validated_data["new_password"],
            )
        except services.InvalidToken:
            return Response(
                {"detail": "Código inválido ou expirado."}, status=status.HTTP_400_BAD_REQUEST
            )
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Senha redefinida."})


class MeView(APIView):
    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(current_user(request)).data)

    @extend_schema(request=MeSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        previous = {"display_name": current_user(request).display_name}
        serializer = MeSerializer(current_user(request), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit.record(
            "user.profile_updated",
            actor=current_user(request),
            entity_type="user",
            entity_id=current_user(request).pk,
            previous_value=previous,
            new_value={"display_name": current_user(request).display_name},
        )
        return Response(serializer.data)

    @extend_schema(request=DeleteAccountSerializer, responses={204: None})
    def delete(self, request: Request) -> Response:
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.delete_account(
                user=current_user(request),
                password=serializer.validated_data["password"],
                request=request._request,
            )
        except services.InvalidCredentials:
            return Response({"detail": "Senha incorreta."}, status=status.HTTP_403_FORBIDDEN)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConsentView(APIView):
    @extend_schema(responses=ConsentSerializer(many=True))
    def get(self, request: Request) -> Response:
        current = services.current_consents(current_user(request))
        return Response(ConsentSerializer(current.values(), many=True).data)

    @extend_schema(request=ConsentInputSerializer, responses=ConsentSerializer)
    def post(self, request: Request) -> Response:
        serializer = ConsentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent = services.set_consent(
            user=current_user(request), request=request._request, **serializer.validated_data
        )
        return Response(ConsentSerializer(consent).data, status=status.HTTP_201_CREATED)


class ExportView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request: Request) -> Response:
        audit.record(
            "user.data_exported",
            actor=current_user(request),
            entity_type="user",
            entity_id=current_user(request).pk,
        )
        return Response(services.export_user_data(current_user(request)))


class RoleChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated, rbac.require(rbac.USERS_CHANGE_ROLE)]

    @extend_schema(request=RoleChangeSerializer, responses=MeSerializer)
    def patch(self, request: Request, user_id: str) -> Response:
        target = get_object_or_404(User, pk=user_id, anonymized_at__isnull=True)
        if target.pk == current_user(request).pk:
            return Response(
                {"detail": "Você não pode alterar o seu próprio papel."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = RoleChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_role(
            actor=current_user(request),
            target=target,
            new_role=serializer.validated_data["role"],
            request=request._request,
        )
        return Response(MeSerializer(target).data)
