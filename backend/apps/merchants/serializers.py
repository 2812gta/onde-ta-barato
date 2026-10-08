from rest_framework import serializers

from .models import (
    MemberRole,
    Merchant,
    MerchantMembership,
    MerchantVerification,
    VerificationStatus,
)


class MerchantCreateSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=200)
    trade_name = serializers.CharField(max_length=200)
    cnpj = serializers.CharField(max_length=20, required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class MerchantSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "legal_name",
            "trade_name",
            "cnpj",
            "contact_email",
            "contact_phone",
            "status",
            "is_verified",
            "verified_at",
            "created_at",
        ]
        read_only_fields = fields


class TransitionSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=VerificationStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class VerificationHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantVerification
        fields = ["from_status", "to_status", "notes", "created_at"]
        read_only_fields = fields


class MemberInputSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[MemberRole.MANAGER, MemberRole.OPERATOR])


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = MerchantMembership
        fields = ["user_id", "email", "role", "created_at"]
        read_only_fields = fields
