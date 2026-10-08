from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet

from .models import Promotion

SCHEDULED = "SCHEDULED"
ACTIVE = "ACTIVE"
EXPIRED = "EXPIRED"
INACTIVE = "INACTIVE"


def status_of(promotion: Promotion, now: datetime) -> str:
    if not promotion.is_active:
        return INACTIVE
    if promotion.valid_from > now:
        return SCHEDULED
    if promotion.valid_until is not None and promotion.valid_until <= now:
        return EXPIRED
    return ACTIVE


def running_promotions(
    *, store_ids: Iterable[Any], variant_ids: Iterable[Any], now: datetime
) -> dict[tuple[Any, Any], list[Promotion]]:
    """Promotions inside their validity window, grouped by (store_id, variant_id).

    Weekday / time-of-day limits are NOT filtered here: the engine checks them against the
    shopper's moment and explains why a rule did not apply.
    """
    queryset: QuerySet[Promotion] = (
        Promotion.objects.filter(
            store_id__in=list(store_ids),
            product_variant_id__in=list(variant_ids),
            is_active=True,
            valid_from__lte=now,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("store__merchant")
        .order_by("created_at")
    )
    grouped: dict[tuple[Any, Any], list[Promotion]] = defaultdict(list)
    for promotion in queryset:
        grouped[(promotion.store_id, promotion.product_variant_id)].append(promotion)
    return grouped


def is_confirmed(promotion: Promotion) -> bool:
    """A promotion is confirmed only when its merchant went through verification."""
    merchant = promotion.store.merchant
    return merchant is not None and merchant.is_verified
