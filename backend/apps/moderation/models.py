import uuid

from django.conf import settings
from django.db import models

from apps.core import clock
from apps.core.append_only import AppendOnlyModel


class ModerationAction(models.TextChoices):
    HIDE = "HIDE", "Ocultar"
    RESTORE = "RESTORE", "Restaurar"
    UPHOLD = "UPHOLD", "Manter oculto após recurso"


class PriceModeration(AppendOnlyModel):
    """One moderation decision about a consumer price. The price itself is never edited.

    The current state is the latest HIDE/UPHOLD (hidden) or RESTORE (visible) for the
    observation. Evidence and history rows stay untouched: hiding only keeps the price out
    of what other consumers see.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observation = models.ForeignKey(
        "prices.PriceObservation", on_delete=models.PROTECT, related_name="moderations"
    )
    action = models.CharField(max_length=7, choices=ModerationAction.choices)
    # Shown to the contributor: a hidden price always comes with a reason.
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["observation", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.observation_id}"


class PriceAppeal(AppendOnlyModel):
    """The contributor contesting a HIDE. At most one per HIDE decision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    moderation = models.OneToOneField(
        PriceModeration, on_delete=models.PROTECT, related_name="appeal"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    message = models.TextField()
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        ordering = ["-created_at"]


class SignalDecision(models.TextChoices):
    CONFIRMED = "CONFIRMED", "Indício confirmado"
    DISMISSED = "DISMISSED", "Descartado"


class SignalReview(AppendOnlyModel):
    """A moderator looked at a fraud signal. Without one, the signal is still pending."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signal = models.OneToOneField(
        "contributions.FraudSignal", on_delete=models.PROTECT, related_name="review"
    )
    decision = models.CharField(max_length=9, choices=SignalDecision.choices)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=clock.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
