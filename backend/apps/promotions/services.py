from datetime import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.audit import services as audit
from apps.core import clock
from apps.merchants import services as merchant_services
from apps.products.models import ProductVariant
from apps.stores.models import Store, StoreStatus
from apps.users.models import User

from .engine import InvalidRule, validate_rule
from .models import Promotion


def _check_can_publish(store: Store, actor: User) -> None:
    if store.merchant is None or not merchant_services.can_publish(actor, store.merchant):
        raise PermissionDenied("Você não pode gerenciar promoções desta loja.")


@transaction.atomic
def create_promotion(
    *,
    store: Store,
    actor: User,
    variant: ProductVariant,
    title: str,
    rule: dict[str, Any],
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> Promotion:
    _check_can_publish(store, actor)
    if store.status != StoreStatus.ACTIVE:
        raise ValidationError("Loja inativa.")
    try:
        validate_rule(rule)
    except InvalidRule as exc:
        raise ValidationError(str(exc)) from exc
    start = valid_from or clock.now()
    if valid_until is not None and valid_until <= start:
        raise ValidationError("A validade deve ser posterior ao início.")
    promotion = Promotion.objects.create(
        store=store,
        product_variant=variant,
        title=title.strip(),
        rule=rule,
        valid_from=start,
        valid_until=valid_until,
        created_by=actor,
    )
    audit.record(
        "promotion.created",
        actor=actor,
        entity_type="promotion",
        entity_id=promotion.pk,
        new_value={"store": str(store.pk), "variant": str(variant.pk), "rule": rule},
    )
    return promotion


@transaction.atomic
def deactivate_promotion(*, promotion: Promotion, actor: User) -> Promotion:
    """Promotions are switched off, never erased: the history of what was offered stays."""
    _check_can_publish(promotion.store, actor)
    if promotion.is_active:
        promotion.is_active = False
        promotion.save(update_fields=["is_active", "updated_at"])
        audit.record(
            "promotion.deactivated",
            actor=actor,
            entity_type="promotion",
            entity_id=promotion.pk,
            previous_value={"is_active": True},
            new_value={"is_active": False},
        )
    return promotion
