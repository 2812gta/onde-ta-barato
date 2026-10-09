import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models

from apps.core import clock
from apps.core.append_only import AppendOnlyModel

DRAFT_TTL = timedelta(hours=24)


class ContributionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Aguardando confirmação"
    CONFIRMED = "CONFIRMED", "Confirmada"
    CANCELLED = "CANCELLED", "Cancelada"


class UserContribution(models.Model):
    """A price the user photographed. It becomes a price only after they confirm it.

    The photo lives here only while the draft is open. Confirming copies it into the price's
    evidence (when it is attached) and removes it from here; cancelling or expiring deletes it.
    Only the SHA-256 stays, to spot the same photo being reused.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contributions"
    )
    store = models.ForeignKey(
        "stores.Store", on_delete=models.PROTECT, related_name="contributions"
    )
    status = models.CharField(
        max_length=10, choices=ContributionStatus.choices, default=ContributionStatus.DRAFT
    )
    photo = models.FileField(upload_to="contributions/%Y/%m/", blank=True)
    photo_sha256 = models.CharField(max_length=64, db_index=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    # Raw text read on the device and our interpretation of it (labelled FACT / INFERENCE).
    ocr_text = models.TextField(blank=True)
    extraction = models.JSONField(default=dict)
    # True when the user's final price/product differ from what the reading suggested.
    corrected = models.BooleanField(default=False)
    observation = models.ForeignKey(
        "prices.PriceObservation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contributions",
    )
    created_at = models.DateTimeField(default=clock.now, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.store_id} ({self.status})"

    @property
    def expires_at(self):  # type: ignore[no-untyped-def]
        return self.created_at + DRAFT_TTL


class FraudSeverity(models.TextChoices):
    LOW = "LOW", "Baixa"
    MEDIUM = "MEDIUM", "Média"
    HIGH = "HIGH", "Alta"


class FraudKind(models.TextChoices):
    DUPLICATE_PHOTO = "DUPLICATE_PHOTO", "Foto já usada"
    PRICE_OUTLIER = "PRICE_OUTLIER", "Preço muito fora do usual"
    RATE_BURST = "RATE_BURST", "Muitas contribuições em pouco tempo"
    LOCATION_FAR = "LOCATION_FAR", "Aparelho longe da loja"
    LOCATION_MISSING = "LOCATION_MISSING", "Localização não informada"
    STALE_PHOTO = "STALE_PHOTO", "Foto antiga"


class FraudSignal(AppendOnlyModel):
    """A reason for a moderator to look. Never blocks, hides or lowers anything by itself."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contribution = models.ForeignKey(
        UserContribution, on_delete=models.PROTECT, related_name="fraud_signals"
    )
    kind = models.CharField(max_length=20, choices=FraudKind.choices)
    severity = models.CharField(max_length=6, choices=FraudSeverity.choices)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} ({self.severity})"
