from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class CartStatus(models.TextChoices):
    OPEN = "OPEN", "Aberto"
    CLOSED = "CLOSED", "Finalizado"


class ShoppingCart(TimeStampedModel):
    """The shopper's cart while at (or choosing) one store. Personal data: deleted with the account.

    Items hold quantities only. Prices are computed when the cart is read, so a price that
    changed or expired is never shown from a stale copy. Closing the cart keeps the final
    totals once, as the basis for savings history (M7).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_carts"
    )
    store = models.ForeignKey(
        "stores.Store", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=6, choices=CartStatus.choices, default=CartStatus.OPEN)
    payment_condition = models.CharField(max_length=10, default="NORMAL")
    has_loyalty = models.BooleanField(default=False)
    coupon_codes = models.JSONField(default=list, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    final_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    final_savings = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=Q(status="OPEN"), name="one_open_cart_per_user"
            )
        ]


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(ShoppingCart, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.PROTECT, related_name="+"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    in_basket = models.BooleanField(default=False)  # already picked up from the shelf

    class Meta:
        ordering = ["in_basket", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product_variant"], name="unique_variant_per_cart"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="cart_item_quantity_positive"),
        ]
