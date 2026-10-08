from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core import clock
from apps.core.models import SoftDeleteModel, TimeStampedModel


class Promotion(TimeStampedModel, SoftDeleteModel):
    """A merchant's promotional rule for one product at one store.

    It is catalog data (a way the price is calculated), not advertising: it has no placement,
    budget or boost, and cannot influence ordering. See apps/promotions/engine.py for the rule
    format. Only promotions from VERIFIED merchants count as confirmed in recommendations.
    """

    store = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="promotions")
    product_variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.PROTECT, related_name="promotions"
    )
    title = models.CharField(max_length=120, help_text="Texto exibido, ex.: 3 por R$ 20")
    rule = models.JSONField()
    valid_from = models.DateTimeField(default=clock.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F("valid_from")),
                name="promotion_valid_until_after_from",
            )
        ]
        indexes = [models.Index(fields=["store", "product_variant", "is_active"])]

    def __str__(self) -> str:
        return f"{self.title} @ {self.store_id}"

    @property
    def rule_type(self) -> str:
        return str(self.rule.get("type", ""))
