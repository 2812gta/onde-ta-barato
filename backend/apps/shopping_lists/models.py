from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class ShoppingList(TimeStampedModel):
    """A shopper's planning list. Personal data: hard-deleted with the account (LGPD).

    It holds product presentations (variants) and quantities only. It has no prices: prices
    change, and what a list costs is answered on demand by the recommendation and cart APIs.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists"
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name


class ShoppingListItem(TimeStampedModel):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.PROTECT, related_name="+"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    checked = models.BooleanField(default=False)

    class Meta:
        ordering = ["checked", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["shopping_list", "product_variant"], name="unique_variant_per_list"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="list_item_quantity_positive"),
        ]
