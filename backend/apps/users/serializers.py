from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import ConsentPurpose, Role, User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "É necessário aceitar os Termos e a Política de Privacidade."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        validate_password(attrs["password"], User(email=attrs["email"]))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class CodeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=1024)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=1024)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class MeSerializer(serializers.ModelSerializer):
    """`role` and `email` are read-only: users cannot escalate themselves."""

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "role", "email_verified_at", "created_at"]
        read_only_fields = ["id", "email", "role", "email_verified_at", "created_at"]


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class ConsentInputSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=ConsentPurpose.choices)
    granted = serializers.BooleanField()


class ConsentSerializer(serializers.Serializer):
    purpose = serializers.CharField()
    granted = serializers.BooleanField()
    policy_version = serializers.CharField()
    created_at = serializers.DateTimeField()


class RoleChangeSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)
