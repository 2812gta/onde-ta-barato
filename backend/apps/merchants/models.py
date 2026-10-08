from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core import clock
from apps.core.append_only import AppendOnlyModel
from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.users.models import Role


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pendente"
    UNDER_REVIEW = "UNDER_REVIEW", "Em análise"
    VERIFIED = "VERIFIED", "Verificado"
    REJECTED = "REJECTED", "Rejeitado"
    SUSPENDED = "SUSPENDED", "Suspenso"


class MemberRole(models.TextChoices):
    OWNER = Role.MERCHANT_OWNER.value, Role.MERCHANT_OWNER.label
    MANAGER = Role.MERCHANT_MANAGER.value, Role.MERCHANT_MANAGER.label
    OPERATOR = Role.MERCHANT_OPERATOR.value, Role.MERCHANT_OPERATOR.label


class Merchant(TimeStampedModel, SoftDeleteModel):
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=14, null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=Q(deleted_at__isnull=True, cnpj__isnull=False),
                name="merchant_unique_alive_cnpj",
            )
        ]

    def __str__(self) -> str:
        return self.trade_name

    @property
    def is_verified(self) -> bool:
        """Only VERIFIED merchants may show the verified badge."""
        return self.status == VerificationStatus.VERIFIED


class MerchantMembership(TimeStampedModel):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="merchant_memberships"
    )
    role = models.CharField(max_length=20, choices=MemberRole.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["merchant", "user"], name="unique_merchant_member")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.merchant_id}:{self.role}"


class MerchantVerification(AppendOnlyModel, TimeStampedModel):
    """One row per status transition: who moved the merchant, when and why."""

    created_at = models.DateTimeField(default=clock.now, editable=False)

    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="verifications")
    from_status = models.CharField(max_length=20, choices=VerificationStatus.choices)
    to_status = models.CharField(max_length=20, choices=VerificationStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
