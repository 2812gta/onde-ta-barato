from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.audit import services as audit
from apps.core.validators import normalize_cnpj
from apps.merchants import services as merchant_services
from apps.merchants.models import Merchant
from apps.users.models import User

from .models import Store, StoreSource
from .selectors import point_from

EDITABLE = {
    "name",
    "store_type",
    "street",
    "number",
    "neighborhood",
    "city",
    "state",
    "postal_code",
    "phone",
    "opening_hours",
    "status",
}


def _reject_unknown(fields: dict[str, Any]) -> None:
    unknown = set(fields) - EDITABLE
    if unknown:
        raise ValidationError(f"Campos não permitidos: {', '.join(sorted(unknown))}")


@transaction.atomic
def create_store(
    *, merchant: Merchant, actor: User, lat: float, lon: float, cnpj: str = "", **fields: Any
) -> Store:
    if not merchant_services.can_manage(actor, merchant):
        raise PermissionDenied("Apenas proprietário ou gerente cadastram lojas.")
    _reject_unknown(fields)
    store = Store.objects.create(
        merchant=merchant,
        source=StoreSource.MERCHANT,
        location=point_from(lat, lon),
        cnpj=normalize_cnpj(cnpj) if cnpj else None,
        **fields,
    )
    audit.record(
        "store.created",
        actor=actor,
        entity_type="store",
        entity_id=store.pk,
        new_value={"name": store.name, "merchant": str(merchant.pk)},
    )
    return store


@transaction.atomic
def update_store(
    *, store: Store, actor: User, lat: float | None = None, lon: float | None = None, **fields: Any
) -> Store:
    if store.merchant is None or not merchant_services.can_manage(actor, store.merchant):
        raise PermissionDenied("Sem permissão para editar esta loja.")
    _reject_unknown(fields)
    if (lat is None) != (lon is None):
        raise ValidationError("Informe latitude e longitude juntas.")
    previous = {k: getattr(store, k) for k in fields} | {"lat": store.lat, "lon": store.lon}
    for key, value in fields.items():
        setattr(store, key, value)
    if lat is not None and lon is not None:
        store.location = point_from(lat, lon)
    store.save()
    audit.record(
        "store.updated",
        actor=actor,
        entity_type="store",
        entity_id=store.pk,
        previous_value=previous,
        new_value={k: getattr(store, k) for k in fields} | {"lat": store.lat, "lon": store.lon},
    )
    return store
