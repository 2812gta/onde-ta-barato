"""Shopping list use cases. Every function is scoped to the list's owner by the caller."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.products.models import ProductVariant
from apps.users.models import User

from .models import ShoppingList, ShoppingListItem

MAX_LISTS = 20
MAX_ITEMS = 100
MAX_QUANTITY = Decimal("1000")


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValidationError("Informe um nome para a lista.")
    return cleaned


def create_list(*, user: User, name: str) -> ShoppingList:
    if ShoppingList.objects.filter(user=user).count() >= MAX_LISTS:
        raise ValidationError(f"Limite de {MAX_LISTS} listas atingido.")
    return ShoppingList.objects.create(user=user, name=_clean_name(name))


def rename_list(*, shopping_list: ShoppingList, name: str) -> ShoppingList:
    shopping_list.name = _clean_name(name)
    shopping_list.save(update_fields=["name", "updated_at"])
    return shopping_list


def _check_quantity(quantity: Decimal) -> None:
    if not 0 < quantity <= MAX_QUANTITY:
        raise ValidationError("Quantidade fora do intervalo permitido.")


@transaction.atomic
def add_item(
    *, shopping_list: ShoppingList, variant: ProductVariant, quantity: Decimal
) -> ShoppingListItem:
    """Adding a product that is already on the list adds to its quantity."""
    _check_quantity(quantity)
    # Lock the list row so two simultaneous requests cannot both pass the size check.
    ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    item = ShoppingListItem.objects.filter(
        shopping_list=shopping_list, product_variant=variant
    ).first()
    if item is None:
        if shopping_list.items.count() >= MAX_ITEMS:
            raise ValidationError(f"Limite de {MAX_ITEMS} itens por lista atingido.")
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list, product_variant=variant, quantity=quantity
        )
    else:
        total = item.quantity + quantity
        _check_quantity(total)
        item.quantity = total
        item.save(update_fields=["quantity", "updated_at"])
    shopping_list.save(update_fields=["updated_at"])
    return item


def update_item(
    *, item: ShoppingListItem, quantity: Decimal | None = None, checked: bool | None = None
) -> ShoppingListItem:
    fields = ["updated_at"]
    if quantity is not None:
        _check_quantity(quantity)
        item.quantity = quantity
        fields.append("quantity")
    if checked is not None:
        item.checked = checked
        fields.append("checked")
    item.save(update_fields=fields)
    item.shopping_list.save(update_fields=["updated_at"])
    return item


def remove_item(*, item: ShoppingListItem) -> None:
    shopping_list = item.shopping_list
    item.delete()
    shopping_list.save(update_fields=["updated_at"])
