import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core import clock
from apps.core.append_only import AppendOnlyModel


class PriceSource(models.TextChoices):
    MERCHANT = "MERCHANT", "Informado pelo estabelecimento"
    USER = "USER", "Informado por consumidor"
    FLYER = "FLYER", "Encarte"
    PUBLIC_SOURCE = "PUBLIC_SOURCE", "Fonte pública"
    HISTORICAL = "HISTORICAL", "Histórico"
    CALCULATED = "CALCULATED", "Estimativa calculada"


class PaymentCondition(models.TextChoices):
    NORMAL = "NORMAL", "Preço normal"
    PIX = "PIX", "Pix"
    DEBIT = "DEBIT", "Débito"
    CREDIT = "CREDIT", "Crédito"
    LOYALTY = "LOYALTY", "Clube de fidelidade"
    COUPON = "COUPON", "Cupom"


class ConfidenceLevel(models.TextChoices):
    LOW = "LOW", "Baixa"
    MEDIUM = "MEDIUM", "Média"
    HIGH = "HIGH", "Alta"


class PriceObservation(AppendOnlyModel):
    """One price seen at one store at one moment. Never edited, never deleted.

    A correction is a new row whose `supersedes` points to the row it replaces, so the
    previous value, who changed it and when always remain answerable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.PROTECT, related_name="price_observations"
    )
    store = models.ForeignKey(
        "stores.Store", on_delete=models.PROTECT, related_name="price_observations"
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="BRL")
    payment_condition = models.CharField(
        max_length=10, choices=PaymentCondition.choices, default=PaymentCondition.NORMAL
    )
    is_promotional = models.BooleanField(default=False)
    source = models.CharField(max_length=15, choices=PriceSource.choices)
    collected_at = models.DateTimeField(default=clock.now)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    # Snapshot at creation. Reads recompute confidence because it decays with age.
    confidence_score = models.DecimalField(max_digits=4, decimal_places=3)
    confidence_level = models.CharField(max_length=6, choices=ConfidenceLevel.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by"
    )
    # True when the reporter's device was near the store. The coordinates are NOT stored.
    location_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(price__gt=0), name="price_positive"),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F("collected_at")),
                name="price_valid_until_after_collected",
            ),
        ]
        indexes = [
            models.Index(fields=["product_variant", "store", "-collected_at"]),
            models.Index(fields=["store", "-collected_at"]),
        ]
        ordering = ["-collected_at"]

    def __str__(self) -> str:
        return f"{self.product_variant_id} @ {self.store_id}: {self.price} ({self.source})"


class EvidenceKind(models.TextChoices):
    PHOTO = "PHOTO", "Fotografia"
    FLYER = "FLYER", "Encarte"
    URL = "URL", "Link"


class PriceEvidence(AppendOnlyModel):
    """Proof behind an observation. Files are private: no public URL is ever generated."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observation = models.ForeignKey(
        PriceObservation, on_delete=models.PROTECT, related_name="evidence"
    )
    kind = models.CharField(max_length=10, choices=EvidenceKind.choices)
    file = models.FileField(upload_to="evidence/%Y/%m/", blank=True)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    source_url = models.URLField(blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=clock.now, editable=False)


class PriceConfirmation(AppendOnlyModel):
    """An independent user agrees or disagrees with an observation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observation = models.ForeignKey(
        PriceObservation, on_delete=models.PROTECT, related_name="confirmations"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    agrees = models.BooleanField()
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["observation", "user"], name="one_confirmation_per_user"
            )
        ]
