import hashlib
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models import Q

from apps.core.models import SoftDeleteModel, TimeStampedModel

from .normalization import normalize_text, to_base


class CatalogSource(models.TextChoices):
    MANUAL = "MANUAL", "Cadastro manual"
    MERCHANT = "MERCHANT", "Comerciante"
    USER = "USER", "Usuário"
    OPEN_FOOD_FACTS = "OPEN_FOOD_FACTS", "Open Food Facts"


class Unit(models.TextChoices):
    GRAM = "g", "g"
    KILOGRAM = "kg", "kg"
    MILLILITER = "ml", "ml"
    LITER = "l", "L"
    UNIT = "un", "un"
    METER = "m", "m"


class Brand(TimeStampedModel):
    name = models.CharField(max_length=120)
    normalized_name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Category(TimeStampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    # How long a price in this category is considered current (fresh produce vs pantry items).
    price_ttl_hours = models.PositiveIntegerField(default=168)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(TimeStampedModel, SoftDeleteModel):
    """The concept, e.g. 'Arroz Tio João'. Sizes and GTINs live on ProductVariant."""

    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, db_index=True)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.PROTECT)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    description = models.TextField(blank=True)
    catalog_source = models.CharField(
        max_length=20, choices=CatalogSource.choices, default=CatalogSource.MANUAL
    )
    source_ref = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_name", "brand"],
                condition=Q(deleted_at__isnull=True),
                name="product_unique_alive_name_brand",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return self.name


class ProductVariant(TimeStampedModel, SoftDeleteModel):
    """A purchasable presentation: size/type. Prices attach here, never to Product."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="variants")
    # Always stored as 14 digits (GTIN-14 form). Unique when known; many products have none yet.
    gtin = models.CharField(max_length=14, null=True, blank=True)
    label = models.CharField(max_length=120, blank=True, help_text="Ex.: Tipo 1")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=2, choices=Unit.choices)
    # Derived: base unit (g, ml, un, m) so unit prices are comparable across sizes.
    base_quantity = models.DecimalField(max_digits=14, decimal_places=3, editable=False)
    base_unit = models.CharField(max_length=2, editable=False)
    pack_count = models.PositiveSmallIntegerField(default=1)
    # Composite identity used when there is no GTIN (and to detect duplicates of known GTINs).
    identity_key = models.CharField(max_length=64, editable=False)
    catalog_source = models.CharField(
        max_length=20, choices=CatalogSource.choices, default=CatalogSource.MANUAL
    )
    source_ref = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["gtin"],
                condition=Q(deleted_at__isnull=True, gtin__isnull=False),
                name="variant_unique_alive_gtin",
            ),
            models.UniqueConstraint(
                fields=["identity_key"],
                condition=Q(deleted_at__isnull=True),
                name="variant_unique_alive_identity",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="variant_quantity_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.product} {self.quantity.normalize():f} {self.unit}"

    def compute_identity_key(self) -> str:
        brand_obj = self.product.brand
        brand = brand_obj.normalized_name if brand_obj is not None else ""
        raw = "|".join(
            [
                self.product.normalized_name,
                brand,
                normalize_text(self.label),
                f"{self.base_quantity.normalize():f}",
                self.base_unit,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:40]

    def save(self, *args: Any, **kwargs: Any) -> None:
        base_quantity, base_unit = to_base(Decimal(self.quantity), self.unit)
        self.base_quantity, self.base_unit = base_quantity, base_unit
        self.identity_key = self.compute_identity_key()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {
                *kwargs["update_fields"],
                "base_quantity",
                "base_unit",
                "identity_key",
            }
        super().save(*args, **kwargs)
