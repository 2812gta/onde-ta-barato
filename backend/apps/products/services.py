from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.core.validators import normalize_gtin
from apps.users.models import User

from .models import Brand, CatalogSource, Category, Product, ProductVariant
from .normalization import normalize_text, to_base


def get_or_create_brand(name: str) -> Brand | None:
    normalized = normalize_text(name)
    if not normalized:
        return None
    brand, _ = Brand.objects.get_or_create(
        normalized_name=normalized, defaults={"name": name.strip()}
    )
    return brand


def _get_or_create_product(
    *, name: str, brand: Brand | None, category: Category | None, source: str, source_ref: str
) -> Product:
    normalized = normalize_text(name)
    if not normalized:
        raise ValidationError("Nome do produto é obrigatório.")
    product = Product.objects.filter(normalized_name=normalized, brand=brand).first()
    if product is None:
        product = Product.objects.create(
            name=name.strip(),
            normalized_name=normalized,
            brand=brand,
            category=category,
            catalog_source=source,
            source_ref=source_ref,
        )
    elif product.category_id is None and category is not None:
        product.category = category
        product.save(update_fields=["category", "updated_at"])
    return product


@transaction.atomic
def get_or_create_variant(
    *,
    name: str,
    quantity: Decimal,
    unit: str,
    brand_name: str = "",
    category: Category | None = None,
    label: str = "",
    gtin: str = "",
    source: str = CatalogSource.MANUAL,
    source_ref: str = "",
    actor: User | None = None,
) -> tuple[ProductVariant, bool]:
    """Find the presentation by GTIN, then by composite identity; create only when new.

    Small spelling differences resolve to the same row. A GTIN learned later is attached to
    an existing GTIN-less variant instead of creating a duplicate.
    """
    if quantity <= 0:
        raise ValidationError("A quantidade deve ser positiva.")
    normalized_gtin = normalize_gtin(gtin) if gtin else None
    if normalized_gtin:
        existing = ProductVariant.objects.filter(gtin=normalized_gtin).first()
        if existing:
            return existing, False

    product = _get_or_create_product(
        name=name,
        brand=get_or_create_brand(brand_name),
        category=category,
        source=source,
        source_ref=source_ref,
    )
    probe = ProductVariant(product=product, label=label, quantity=quantity, unit=unit)
    probe.base_quantity, probe.base_unit = to_base(Decimal(quantity), unit)
    key = probe.compute_identity_key()

    existing = ProductVariant.objects.filter(identity_key=key).first()
    if existing:
        if normalized_gtin and existing.gtin is None:
            existing.gtin = normalized_gtin
            existing.save(update_fields=["gtin", "updated_at"])
            audit.record(
                "catalog.gtin_assigned",
                actor=actor,
                entity_type="product_variant",
                entity_id=existing.pk,
                new_value={"gtin": normalized_gtin},
            )
        elif normalized_gtin and existing.gtin != normalized_gtin:
            raise ValidationError("Esta apresentação já está associada a outro GTIN.")
        return existing, False

    try:
        with transaction.atomic():
            variant = ProductVariant.objects.create(
                product=product,
                gtin=normalized_gtin,
                label=label.strip(),
                quantity=quantity,
                unit=unit,
                catalog_source=source,
                source_ref=source_ref,
            )
    except IntegrityError:  # lost a race with another request creating the same variant
        return ProductVariant.objects.get(identity_key=key), False
    audit.record(
        "catalog.variant_created",
        actor=actor,
        entity_type="product_variant",
        entity_id=variant.pk,
        new_value={"product": product.name, "quantity": str(quantity), "unit": unit},
    )
    return variant, True
